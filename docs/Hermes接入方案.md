# Hermes 接入方案

## 目标

把当前单个钉钉机器人从 InvestmentKnowledge 直连，逐步切换为：

```text
钉钉机器人
-> Hermes Gateway
-> InvestmentKnowledge MCP
-> Futu / PostgreSQL / OpenAI
```

这样用户仍然只在一个钉钉群里说话，但 Hermes 负责意图理解、会话和任务调度，InvestmentKnowledge 继续负责投资数据、富途只读查询、知识库和权限边界。

## 为什么这样做

- 当前 InvestmentKnowledge 已经能查询持仓、新股、交易复盘、收益估算和 OpenD 维护，但交互仍偏命令式。
- Hermes 更适合做统一消息入口、session 管理、长任务编排和自然语言分发。
- InvestmentKnowledge 不应该被替换；它是投资领域后端，掌握数据边界和安全规则。

## 第一版边界

第一版只让 Hermes 调用 InvestmentKnowledge 的安全 MCP 总入口：

```text
run_investment_command
```

这个工具内部复用 `command_router.handle_command()`，避免 Hermes 在多个底层工具之间猜测或直接操作数据库。它只允许：

- 查询类指令：持仓、持仓分析、港股新股、本月收益、交易复盘、系统状态等。
- 富途维护类指令：富途状态、富途请求验证码、富途验证码、富途重登录等。
- 候选心得类指令：提出候选心得、查看候选心得、确认候选心得、拒绝候选心得。
- 开发任务类指令：创建开发任务、查看开发任务。开发任务会进入 `coding_tasks`，由云端 Codex worker 后续处理。

不允许 Hermes 直接写正式心得。知识沉淀仍然走候选心得和确认流程，避免把群聊里的随口讨论写进长期记忆。

## 单机器人切换方案

由于当前只有一个钉钉 Stream 机器人，同一组 Client ID / Client Secret 不应该同时被两个进程消费。

切换到 Hermes 时：

1. InvestmentKnowledge 停止 `dingtalk-stream-bot`。
2. InvestmentKnowledge 启动 MCP HTTP 服务。
3. Hermes Gateway 使用同一套钉钉 Stream 凭证接管消息。
4. Hermes 通过 MCP 调用 InvestmentKnowledge。

回滚时：

1. 停止 Hermes Gateway。
2. 重新启动 InvestmentKnowledge 的 `dingtalk-stream-bot`。

## ECS 配置草稿

InvestmentKnowledge 侧 `.env`：

```dotenv
COMPOSE_PROFILES=http
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_HOST_PORT=8000
MCP_PATH=/mcp
```

Hermes `~/.hermes/config.yaml`：

```yaml
model:
  default: gpt-5.2
  provider: custom
  base_url: https://api.openai.com/v1

group_sessions_per_user: true

mcp_servers:
  investment_knowledge:
    url: http://127.0.0.1:8000/mcp
    enabled: true
    timeout: 180
    connect_timeout: 30
    tools:
      include:
        - run_investment_command
      resources: false
      prompts: false
```

Hermes `~/.hermes/.env`：

```dotenv
OPENAI_API_KEY=...
DINGTALK_CLIENT_ID=...
DINGTALK_CLIENT_SECRET=...
DINGTALK_ALLOWED_USERS=0140522255091257971
DINGTALK_REQUIRE_MENTION=true
```

## 已知影响

- IPO 定时提醒目前在 InvestmentKnowledge 的 `dingtalk-stream-bot` 进程内；切给 Hermes 后，提醒需要迁移到独立任务或 Hermes cron。
- Hermes 不直接改代码；开发任务进入 `coding_tasks` 后，由云端 Codex worker 领取、改代码、提交并推送分支。
- GitHub Actions 仍然保留，用于备份、可回滚部署和正式发布；Hermes 适合做日常轻量调度，不替代版本管理。

## Codex Worker

云端 Codex worker 是 Hermes 后面的执行层：

```text
钉钉
-> Hermes Gateway
-> InvestmentKnowledge MCP
-> coding_tasks
-> ECS Codex worker
-> GitHub branch/commit
-> ECS local deploy
-> DingTalk result notification
```

权限边界：

- worker 可以在独立 clone 里运行 `codex exec`、修改代码、提交并推送 `codex/task-*` 分支。
- worker 默认使用 `CODEX_WORKER_DANGER_FULL_ACCESS=true`，适合当前早期快速迭代；如果后续要收紧，可以改成 `false`。
- worker 默认使用 `CODEX_WORKER_LOCAL_DEPLOY=true`，任务完成后直接在 ECS 本机同步代码并重启服务。
- `CODEX_WORKER_AUTO_DEPLOY=false`，GitHub Actions deploy 默认只作为备用通道。
- 需要一次性配置 `CODEX_WORKER_GITHUB_TOKEN`，用于 ECS worker 推送分支和触发 workflow dispatch。

安装入口：

```bash
bash scripts/install_codex_worker_on_ecs.sh --start
```

GitHub Actions：

```text
Actions -> Codex Worker -> install/start/status/stop/run-once
```

## 验证步骤

1. 先只安装 Hermes，不启动、不切入口：

```bash
cd /opt/investment-knowledge
bash scripts/install_hermes_gateway_on_ecs.sh
```

2. InvestmentKnowledge MCP 在线：

```bash
docker compose -f docker-compose.prod.yml ps
```

3. 正式切入口时再执行：

```bash
cd /opt/investment-knowledge
bash scripts/install_hermes_gateway_on_ecs.sh --switch-dingtalk
```

4. Hermes 能收到钉钉消息并回复。
5. 在钉钉里测试：

```text
@机器人 帮助
@机器人 我的持仓
@机器人 本月收益
@机器人 富途状态
```

6. 确认写入类表达不会直接入库：

```text
@机器人 我觉得港股亏损太消耗精力
```

预期：Hermes 可以理解和回应，但 InvestmentKnowledge MCP 不会直接写正式心得。
