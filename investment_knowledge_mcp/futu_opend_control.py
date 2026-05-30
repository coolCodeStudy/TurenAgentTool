from __future__ import annotations

import socket
import time
from typing import Iterable

from investment_knowledge_mcp.config import AppConfig, get_config


class FutuOpenDControlError(RuntimeError):
    pass


def request_phone_verify_code(config: AppConfig | None = None) -> str:
    return send_opend_command("req_phone_verify_code", config=config)


def submit_phone_verify_code(code: str, config: AppConfig | None = None) -> str:
    cleaned = code.strip()
    if not cleaned.isdigit() or not 4 <= len(cleaned) <= 8:
        raise FutuOpenDControlError("验证码格式不对，需要 4-8 位数字。")
    return send_opend_command(f"input_phone_verify_code -code={cleaned}", config=config)


def relogin_opend(config: AppConfig | None = None) -> str:
    return send_opend_command("relogin", config=config)


def ping_opend_telnet(config: AppConfig | None = None) -> str:
    return send_opend_command("help", config=config, timeout=3.0)


def send_opend_command(command: str, config: AppConfig | None = None, timeout: float = 8.0) -> str:
    config = config or get_config()
    command = command.strip()
    if not command:
        raise FutuOpenDControlError("OpenD 命令不能为空。")

    try:
        with socket.create_connection(
            (config.futu_opend_telnet_host, config.futu_opend_telnet_port),
            timeout=timeout,
        ) as sock:
            sock.settimeout(timeout)
            banner = _read_available(sock, idle_seconds=0.25)
            sock.sendall(command.encode("utf-8") + b"\r\n")
            time.sleep(0.05)
            response = _read_until_timeout(sock)
    except OSError as exc:
        raise FutuOpenDControlError(
            "连接 OpenD Telnet 控制口失败，请确认 OpenD 已用 -telnet_ip/-telnet_port 启动，"
            "并且容器可访问该端口。"
        ) from exc

    decoded_banner = _decode_response(banner).strip()
    decoded_response = _decode_response(response).strip()
    if decoded_response:
        return decoded_response
    if decoded_banner:
        return decoded_banner + "\n\n注意：OpenD 只返回了连接欢迎信息，没有返回命令处理结果。"
    return "OpenD 已接收命令，但没有返回文本。"


def _read_available(sock: socket.socket, idle_seconds: float) -> bytes:
    chunks: list[bytes] = []
    original_timeout = sock.gettimeout()
    sock.settimeout(idle_seconds)
    try:
        while True:
            try:
                chunk = sock.recv(4096)
            except (TimeoutError, socket.timeout):
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.settimeout(original_timeout)
    return b"".join(chunks)


def _read_until_timeout(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            break
        except socket.timeout:
            break
        if not chunk:
            break
        chunks.append(chunk)
        if _looks_complete(chunks):
            break
    return b"".join(chunks)


def _looks_complete(chunks: Iterable[bytes]) -> bool:
    joined = b"".join(chunks).lower()
    return any(marker in joined for marker in (b"success", b"failed", b"error", b"ok"))


def _decode_response(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
