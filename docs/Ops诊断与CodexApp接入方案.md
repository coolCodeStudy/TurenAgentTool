# Ops 诊断与 Codex App 接入方案

## 目标

让 InvestmentKnowledge 的云端状态、日志和开发任务不再依赖人工 SSH 复制。

目标交互：

```text
Codex App
  -> Hermes/Codex App MCP Bridge
      -> Hermes / InvestmentKnowledge Command API
      -> ECS Ops API
          -> Docker / systemd / journalctl / Codex worker / Hermes / Futu / Postgres
```

钉钉、Hermes、Codex App 复用同一套能力。

## 组件

- `scripts/ecs_ops_api.py`
  - 跑在 ECS 宿主机 systemd 下。
  - 只允许白名单诊断动作。
  - 返回日志前做脱敏和截断。

- `investment_knowledge_mcp/ops_client.py`
  - 应用侧访问 Ops API 的客户端。
  - 提供结构化查询和中文摘要渲染。

- `scripts/hermes_mcp_bridge.py`
  - 给 Codex App 使用的 MCP bridge。
  - 可调用云端 command API 和 Ops API。
  - 后续如果 Hermes 暴露稳定 HTTP/API，可把下游切到 Hermes，Codex App 配置不变。

## 钉钉/Hermes 可用命令

- `云端状态`
- `最近错误`
- `worker日志`
- `hermes日志`
- `mcp日志`
- `钉钉日志`
- `futu日志`
- `postgres日志`
- `服务日志 codex-worker`

## GitHub Actions

- `ECS Ops API -> install`
  - 上传并安装 `investment-ops-api.service`。
- `ECS Ops API -> status`
  - 查看服务状态和最近日志。
- 正常 `Deploy to Alibaba Cloud ECS` 的 full deploy 会自动安装/重启 Ops API。
- quick deploy 如果 Ops API 已安装，会重启它以加载最新脚本。

## Codex App MCP 配置

本地运行 MCP bridge 时需要提供：

```bash
COMMAND_API_URL=http://<host>:8001
COMMAND_API_TOKEN=<token>
OPS_API_URL=http://<host>:8767
OPS_API_TOKEN=<token>
python scripts/hermes_mcp_bridge.py
```

生产环境建议不要直接把 `8767` 暴露到公网；优先让 Codex App 通过安全隧道或后续 Hermes API 调用。

## 安全边界

- Ops API 默认监听 `127.0.0.1:8767`。
- 需要 `OPS_API_TOKEN` 或 `COMMAND_API_TOKEN` 才能访问。
- 不支持任意 shell 命令。
- 服务名白名单：`hermes`、`codex-worker`、`mcp`、`dingtalk-stream-bot`、`postgres`、`futu-opend`、`futu-proxy`、`ops-api`。
- 日志会脱敏 `token`、`secret`、`password`、`webhook`、`access_token`、OpenAI key、Futu 登录参数等敏感内容。
