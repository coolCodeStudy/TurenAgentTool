# Ops 诊断与 Codex App 接入方案

## 目标

让 Codex App 可以直接查看 InvestmentKnowledge 云端状态、日志和开发任务，不再依赖用户 SSH 到 ECS 复制日志。

当前主链路：

```text
Codex App
  -> InvestmentKnowledge MCP /mcp
      -> ECS 内部 Ops API
          -> Docker / systemd / journalctl / Codex worker / Futu / Postgres
```

关键原则：

- Codex App 只连接云端 `InvestmentKnowledge MCP /mcp`。
- `Ops API` 只在 ECS 内网使用，不直接暴露公网。
- Hermes 暂时不是主链路，只作为未来多入口网关的可选组件。

## 组件

- `scripts/ecs_ops_api.py`
  - 跑在 ECS 宿主机 systemd 下。
  - 监听 ECS 内部地址，例如 `127.0.0.1:8767` 或 docker bridge 地址。
  - 只允许白名单诊断动作。
  - 返回日志前做脱敏和截断。

- `investment_knowledge_mcp/ops_client.py`
  - 应用侧访问 Ops API 的客户端。
  - 负责结构化查询和中文摘要渲染。

- `investment_knowledge_mcp/server.py`
  - 云端 MCP 入口。
  - 已暴露云端诊断工具：
    - `cloud_system_status`
    - `cloud_recent_errors`
    - `cloud_service_logs`
    - `cloud_coding_status`

- `scripts/hermes_mcp_bridge.py`
  - 备用的本地 stdio MCP bridge。
  - 只有当 Codex App 不能直接连接云端 `/mcp`，或需要通过本地隧道/代理访问时使用。
  - 支持自动读取 `.env.codex`、`.env`、`~/.investment-knowledge/ops.env`。

## Codex App 推荐接入

优先使用云端 MCP：

```text
类型：流式 HTTP
URL：http://<ECS_HOST>:8000/mcp
```

要求：

- ECS 安全组允许你的可信来源访问 `8000`。
- `docker-compose.prod.yml` 已启动 `mcp` 服务。
- 云端 `.env` 中 MCP 配置大致为：

```env
COMPOSE_PROFILES=stream,http
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_HOST_PORT=8000
MCP_PATH=/mcp
OPS_API_URL=http://host.docker.internal:8767
OPS_API_TOKEN=<same-as-command-api-token-or-dedicated-token>
```

连接后，Codex App 应该可以调用：

- `cloud_system_status`：查看 Docker、systemd、Postgres、Futu、MCP 等状态。
- `cloud_recent_errors`：查看最近 warning/error。
- `cloud_service_logs`：查看指定服务日志，支持 `mcp`、`dingtalk-stream-bot`、`codex-worker`、`hermes`、`postgres`、`futu-opend`、`futu-proxy`、`ops-api`。
- `cloud_coding_status`：查看云端 Codex worker 状态和最近任务。

## 备用：本地 Bridge 接入

如果不想直接开放云端 `/mcp`，可以先用本地 bridge：

```text
Codex App
  -> local stdio MCP bridge
      -> Command API / Ops API
```

在项目根目录创建本地文件 `.env.codex`，不要提交：

```env
COMMAND_API_URL=http://<ECS_HOST>:8001
COMMAND_API_TOKEN=<command-api-token>
OPS_API_URL=http://<ECS_HOST>:8767
OPS_API_TOKEN=<ops-api-token>
HERMES_BRIDGE_TIMEOUT_SECONDS=20
```

然后在 Codex App 里添加 stdio MCP：

```bash
python scripts/hermes_mcp_bridge.py
```

注意：这个备用方案只有在你通过安全组、VPN、SSH tunnel 或反向代理安全暴露对应端口时才建议使用。默认不建议直接把 `8767` 暴露到公网。

## 钉钉可用诊断命令

当前钉钉入口也复用同一套 Ops 能力：

- `云端状态`
- `最近错误`
- `worker日志`
- `hermes日志`
- `mcp日志`
- `钉钉日志`
- `futu日志`
- `postgres日志`
- `服务日志 codex-worker`

## Hermes 定位

Hermes 暂时不进入主链路。

保留 Hermes 的原因：

- 未来可能承接多个聊天入口。
- 未来可能做更复杂的意图分发。
- 未来可能统一钉钉、网页、Codex worker 等入口。

暂时不用 Hermes 的原因：

- 当前 InvestmentKnowledge MCP 已经能直接提供诊断能力。
- Hermes 失败不应影响投资查询、日志诊断和 Codex App 调试。
- 主链路越短，定位问题越快。

## 安全边界

- Ops API 不支持任意 shell 命令。
- Ops API 服务名白名单：
  - `hermes`
  - `codex-worker`
  - `mcp`
  - `dingtalk-stream-bot`
  - `postgres`
  - `futu-opend`
  - `futu-proxy`
  - `ops-api`
- 日志会脱敏：
  - token
  - secret
  - password
  - webhook
  - access_token
  - OpenAI key
  - Futu 登录参数

## 当前结论

现阶段的主方向是：

1. 让 InvestmentKnowledge MCP 成为 Codex App 访问云端系统的主入口。
2. 让 Ops API 只作为 ECS 内部诊断服务。
3. 保留 Hermes，但不让它阻塞主系统迭代。
