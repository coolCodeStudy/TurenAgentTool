from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys

import certifi


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.command_router import (
    handle_command,
    is_candidate_write_command,
    is_coding_task_command,
    is_maintenance_command,
    is_query_command,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.ipo_reminders import start_ipo_reminder_loop


def main() -> None:
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    logger = _setup_logger()

    parser = argparse.ArgumentParser(description="Run InvestmentKnowledge as a DingTalk Stream Mode bot.")
    parser.add_argument("--allow-write", action="store_true", help="Allow write commands from DingTalk.")
    args = parser.parse_args()

    try:
        import dingtalk_stream
        from dingtalk_stream import AckMessage
    except ImportError as exc:
        raise SystemExit("dingtalk-stream is not installed. Run: pip install -r requirements.txt") from exc

    config = get_config()
    if not config.dingtalk_stream_client_id or not config.dingtalk_stream_client_secret:
        raise SystemExit("DINGTALK_STREAM_CLIENT_ID and DINGTALK_STREAM_CLIENT_SECRET are required.")

    logger.info(
        (
            "DingTalk Stream config loaded: client_id_present=%s, "
            "client_secret_present=%s, allow_write=%s, write_allowed_senders=%s"
        ),
        bool(config.dingtalk_stream_client_id),
        bool(config.dingtalk_stream_client_secret),
        args.allow_write,
        len(config.dingtalk_stream_write_allowed_senders),
    )
    logger.info("Initializing database schema")
    run_schema()
    logger.info("Database schema ready")
    start_ipo_reminder_loop(config=config, logger=logger)

    class InvestmentKnowledgeHandler(dingtalk_stream.ChatbotHandler):
        async def process(self, callback: dingtalk_stream.CallbackMessage):
            incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            command = _extract_text(incoming_message).strip()
            sender = _extract_sender(incoming_message)
            logger.info(
                "received DingTalk stream message: %s sender=%s",
                command,
                _format_sender_for_log(sender),
            )

            if not command:
                self.reply_text("目前只支持文本消息，例如：怎么看海力士", incoming_message)
                return AckMessage.STATUS_OK, "OK"

            is_query = is_query_command(command)
            is_candidate_write = is_candidate_write_command(command)
            is_coding_task = is_coding_task_command(command)
            is_maintenance = is_maintenance_command(command)
            sender_can_write = _sender_can_write(sender, config.dingtalk_stream_write_allowed_senders)
            if not args.allow_write and not is_query and not (
                (is_candidate_write or is_coding_task or is_maintenance) and sender_can_write
            ):
                logger.warning(
                    "blocked DingTalk non-query command: candidate_write=%s coding_task=%s maintenance=%s sender=%s",
                    is_candidate_write,
                    is_coding_task,
                    is_maintenance,
                    _format_sender_for_log(sender),
                )
                self.reply_text(
                    "Stream 入口当前只开放查询类指令；候选心得、开发任务和富途维护指令只允许写入白名单本人提交。可用：怎么看海力士、持仓分析、交易记录 2026-05、富途状态、查看候选心得、创建开发任务、帮助。",
                    incoming_message,
                )
                return AckMessage.STATUS_OK, "OK"

            if args.allow_write and not is_query and not sender_can_write:
                logger.warning(
                    "blocked DingTalk write command from unauthorized sender=%s",
                    _format_sender_for_log(sender),
                )
                self.reply_text(
                    "这条是写入类指令，但当前发送者不在写入白名单里。为了避免群聊污染知识库，已拒绝落库。",
                    incoming_message,
                )
                return AckMessage.STATUS_OK, "OK"

            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                None,
                lambda: handle_command(
                    command,
                    output_dir=PROJECT_ROOT / "drafts",
                    include_artifact_path=False,
                ),
            )
            try:
                result = await asyncio.wait_for(future, timeout=config.dingtalk_command_timeout_seconds)
            except asyncio.TimeoutError:
                logger.exception(
                    "DingTalk command timed out after %s seconds: %s",
                    config.dingtalk_command_timeout_seconds,
                    command,
                )
                self.reply_text(
                    (
                        f"这条指令超过 {config.dingtalk_command_timeout_seconds} 秒还没返回，我先中止等待。\n\n"
                        "如果是富途相关指令，大概率是 OpenD 登录态/验证码/网络连接卡住了。"
                        "可以先试：富途状态、富途请求验证码、富途验证码 123456。"
                    ),
                    incoming_message,
                )
                return AckMessage.STATUS_OK, "OK"
            self.reply_text(result.message, incoming_message)
            return AckMessage.STATUS_OK, "OK"

    credential = dingtalk_stream.Credential(
        config.dingtalk_stream_client_id,
        config.dingtalk_stream_client_secret,
    )
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(dingtalk_stream.chatbot.ChatbotMessage.TOPIC, InvestmentKnowledgeHandler())
    logger.info("DingTalk Stream bot starting")
    client.start_forever()


def _setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger("investment_knowledge_mcp.dingtalk_stream")


def _extract_text(incoming_message: object) -> str:
    text = getattr(incoming_message, "text", None)
    content = getattr(text, "content", None)
    if content is None:
        return ""
    return str(content)


def _extract_sender(incoming_message: object) -> dict[str, str]:
    sender: dict[str, str] = {}
    for key in ("sender_staff_id", "sender_id", "sender_nick"):
        value = getattr(incoming_message, key, None)
        if value:
            sender[key] = str(value).strip()
    return sender


def _sender_can_write(sender: dict[str, str], allowed_senders: tuple[str, ...]) -> bool:
    if not allowed_senders:
        return False
    allowed = {item.strip() for item in allowed_senders if item.strip()}
    return any(value in allowed for value in sender.values())


def _format_sender_for_log(sender: dict[str, str]) -> str:
    if not sender:
        return "<unknown>"
    return ",".join(f"{key}={value}" for key, value in sorted(sender.items()))


if __name__ == "__main__":
    main()
