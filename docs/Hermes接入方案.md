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

第一版只让 Hermes 调用 InvestmentKnowledge 的安全 MCP 工具：

```text
run_investment_command
```

这个工具只允许：

- 查询类指令：持仓、持仓分析、港股新股、本月收益、交易复盘、系统状态等。
- 富途维护类指令：富途状态、富途请求验证码、富途验证码、富途重登录等。

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
- Hermes 第一版先不允许自动改代码。后续可以再接 Codex/代码 worker，但那应该是第二阶段。
- GitHub Actions 仍然保留，用于备份、可回滚部署和正式发布；Hermes 适合做日常轻量调度，不替代版本管理。

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
