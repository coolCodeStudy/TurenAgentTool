# InvestmentKnowledge MCP 阿里云部署方案

这套系统的长期运行环境建议放在阿里云 ECS。个人 Mac 只作为开发入口，不承担数据库、定时任务和资料查询的长期运行职责。

第一次部署可先按 [docs/阿里云最小部署清单.md](docs/阿里云最小部署清单.md) 走最小闭环。

## 推荐架构

```text
ChatGPT / Codex / Web UI
  -> https://your-domain-or-ip/mcp
    -> InvestmentKnowledge MCP Server
      -> PostgreSQL + pgvector
      -> research_providers
      -> 定时复盘任务
```

第一版部署使用 Docker Compose：

- `postgres`: `pgvector/pgvector:pg16`
- `mcp`: Python FastMCP 服务，生产 transport 使用 `streamable-http`
- `command-api`: 给自动化、脚本和未来 Agent 外壳调用的 HTTP 指令入口
- `dingtalk-stream-bot`: 钉钉 Stream Mode 长连接机器人，不需要公网回调地址

生产默认 `COMPOSE_PROFILES=stream`，只启动 `postgres` 和 `dingtalk-stream-bot`，适合 2GB 内存左右的小规格 ECS。需要 HTTP/MCP 入口时再改成：

```text
COMPOSE_PROFILES=stream,http
```

## ECS 准备

建议最低配置：

- Ubuntu 22.04 LTS
- 2 vCPU / 4GB RAM 起步
- 40GB ESSD
- 安全组只开放必要端口

安装 Docker：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
```

## 首次部署

```bash
sudo mkdir -p /opt/investment-knowledge
sudo chown -R "$USER":"$USER" /opt/investment-knowledge
git clone <your-repo-url> /opt/investment-knowledge
cd /opt/investment-knowledge
python scripts/generate_prod_env.py --output .env
```

也可以手工复制模板：

```bash
cp .env.prod.example .env
```

编辑 `.env`，至少确认：

```text
POSTGRES_PASSWORD=<strong-password>
MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_HOST_PORT=8000
MCP_PATH=/mcp
COMMAND_API_HOST=0.0.0.0
COMMAND_API_PORT=8001
COMMAND_API_HOST_PORT=8001
COMMAND_API_TOKEN=<strong-command-token>
DINGTALK_API_HOST=0.0.0.0
DINGTALK_API_PORT=8002
DINGTALK_API_HOST_PORT=8002
DINGTALK_OUTGOING_SECRET=<dingtalk-outgoing-secret>
DINGTALK_ALLOW_WRITE_COMMANDS=false
DINGTALK_SEND_WEBHOOK=<dingtalk-custom-robot-webhook>
DINGTALK_SEND_SECRET=<dingtalk-custom-robot-secret>
DINGTALK_STREAM_CLIENT_ID=<dingtalk-stream-client-id>
DINGTALK_STREAM_CLIENT_SECRET=<dingtalk-stream-client-secret>
DINGTALK_STREAM_ALLOW_WRITE=false
OPENAI_API_KEY=<openai-api-key>
```

`scripts/generate_prod_env.py` 会自动生成强 `POSTGRES_PASSWORD` 和 `COMMAND_API_TOKEN`，但仍需人工确认是否要填 `OPENAI_API_KEY`、`DINGTALK_STREAM_CLIENT_ID` 和 `DINGTALK_STREAM_CLIENT_SECRET`。

如果第一版只使用钉钉 Stream Mode，可以保留：

```text
COMPOSE_PROFILES=stream
DINGTALK_ALLOW_WRITE_COMMANDS=false
DINGTALK_STREAM_ALLOW_WRITE=false
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
```

这样服务器不需要暴露钉钉回调端口给公网；机器人会从 ECS 主动连到钉钉。

启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f mcp
```

本地或服务器上可先运行准生产自检：

```bash
COMMAND_API_TOKEN=<strong-command-token> python scripts/prod_check.py --start-prod
```

自检脚本默认使用独立 Docker Compose project：`investment-kg-prod-check`，避免影响本地开发数据库。
如果只是本机临时演练，可以追加 `--down-after`，检查结束后自动关闭自检栈。

导入股票数据后，可以额外检查自然语言分析：

```bash
COMMAND_API_TOKEN=<strong-command-token> python scripts/prod_check.py --analysis-command "怎么看海力士"
```

如果只是检查已经运行中的服务：

```bash
COMMAND_API_TOKEN=<strong-command-token> python scripts/prod_check.py
```

MCP endpoint：

```text
http://<ecs-public-ip>:8000/mcp
```

Command API endpoint：

```text
http://<ecs-public-ip>:8001/command
```

DingTalk webhook endpoint：

```text
http://<ecs-public-ip>:8002/dingtalk/webhook
```

基础连通性检查：

```bash
curl -i http://localhost:8000/mcp
```

普通 `curl` 没有 MCP 客户端所需的请求头，返回 `406 Not Acceptable` 且提示需要 `text/event-stream` 时，说明 HTTP 服务和路由已经可达。

Command API 检查：

```bash
curl -i http://localhost:8001/health
curl -s http://localhost:8001/command \
  -H "Authorization: Bearer $COMMAND_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"查看候选心得","sender":"deploy-check","source":"curl"}'
```

DingTalk adapter 检查：

```bash
curl -i http://localhost:8002/health
curl -s http://localhost:8002/dingtalk/webhook \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"查看候选心得"},"senderNick":"deploy-check"}'
```

DingTalk Stream Mode 检查：

```bash
docker compose -f docker-compose.prod.yml logs -f dingtalk-stream-bot
```

看到 `DingTalk Stream bot starting` 且钉钉群里 `@机器人 怎么看海力士` 有回复，即表示长连接入口已经可用。

DingTalk 发送侧检查：

```bash
python scripts/send_dingtalk_message.py --message "InvestmentKnowledge online"
python scripts/send_dingtalk_message.py --command "怎么看海力士"
```

生产环境建议放到反向代理和 HTTPS 后面，再暴露给客户端。

## systemd 托管

复制服务文件：

```bash
sudo cp deploy/systemd/investment-knowledge.service /etc/systemd/system/investment-knowledge.service
sudo systemctl daemon-reload
sudo systemctl enable investment-knowledge
sudo systemctl start investment-knowledge
```

查看状态：

```bash
sudo systemctl status investment-knowledge
docker compose -f /opt/investment-knowledge/docker-compose.prod.yml ps
```

## 更新部署

```bash
cd /opt/investment-knowledge
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

如果使用 systemd：

```bash
sudo systemctl restart investment-knowledge
```

## GitHub Actions 自动部署

本仓库内置 `.github/workflows/deploy.yml`，参考了 ReportingSystem 的 ECS 部署方式，但部署目标改成 Docker Compose。

需要在 GitHub 仓库 `coolCodeStudy/TurenAgentTool` 配置这些 secrets：

```text
ECS_HOST
ECS_USERNAME
ECS_PASSWORD
POSTGRES_PASSWORD
COMMAND_API_TOKEN
OPENAI_API_KEY
DINGTALK_STREAM_CLIENT_ID
DINGTALK_STREAM_CLIENT_SECRET
```

可选 secrets：

```text
ECS_PORT
DINGTALK_OUTGOING_SECRET
DINGTALK_SEND_WEBHOOK
DINGTALK_SEND_SECRET
```

可选 repository variable：

```text
OPENAI_MODEL
```

workflow 会在 GitHub Actions runner 上打包当前提交，通过 SCP 上传到 ECS 的 `/tmp/investment-knowledge-release.tar.gz`，再解压到 `/opt/investment-knowledge`，生成服务器 `.env`，然后执行：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

第一次运行前，ECS 仍然需要预装 Docker Engine 和 Docker Compose plugin。
如果 ECS 是干净系统，workflow 会先尝试自动安装基础工具、Docker Engine 和 Docker Compose plugin；自动安装支持 Ubuntu/Debian、CentOS/RHEL 系系统。
ECS 不再需要访问 GitHub；代码由 GitHub Actions 通过 SCP 上传。

## 安全原则

- 不提交 `.env`。
- 不把 OpenAI、钉钉、ECS 密码写入仓库；统一放 GitHub Secrets 或服务器 `.env`。
- PostgreSQL 不对公网开放，只在 Docker 网络内给 MCP Server 使用。
- 如果只用 DingTalk Stream Mode，第一版安全组可以只开放 SSH；MCP/Command API/DingTalk webhook 端口先不对公网开放。
- MCP HTTP 服务如果要公网访问，应放到 HTTPS 和认证之后。
- 资料查询 provider 的 API key 统一放 `.env` 或云端 secret，不写进代码。
- 中国大陆 ECS 构建 Python 镜像时建议使用 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/`。

## 部署前检查清单

第一版上云前至少确认：

- 已设置强 `POSTGRES_PASSWORD`。
- 已设置 OpenAI 等外部 provider key，且不提交到 git。
- PostgreSQL 只在 Docker 网络内访问，不暴露公网端口。
- ECS 安全组只开放 SSH、HTTP/HTTPS 或必要端口。
- MCP `/mcp` 不直接公网裸奔，生产环境应放到 HTTPS 和认证之后。
- 数据库 volume 有备份策略。
- `scripts/ikg.py "分析 000660 KR"` 在服务器上能跑通。
- `scripts/prod_check.py --start-prod` 能完整通过。
- `/command` 带 `COMMAND_API_TOKEN` 能跑通，未带 token 会返回 `401`。
- `/dingtalk/webhook` 能处理文本消息，且真实接入时设置了 `DINGTALK_OUTGOING_SECRET`。
- `scripts/candidate_insights.py list` 能看到待确认候选心得。
- 写入类入口区分正式心得和候选心得，系统推断不能直接写入 `user_insights`。

## 消息入口

消息入口设计见 [docs/消息入口设计.md](docs/消息入口设计.md)。

建议第一版不要让钉钉、Hermes、OpenClaw 直接访问数据库。推荐路径：

```text
钉钉 / Web API / Agent 外壳
  -> dingtalk_api / command_api
  -> command_router.handle_command()
    -> repository / MCP tools
      -> PostgreSQL
```

这样可以统一处理鉴权、审计、候选确认和写入边界。

## 和本地开发的区别

本地默认：

```text
MCP_TRANSPORT=stdio
DATABASE_URL=postgresql://postgres:postgres@localhost:55432/investment_kg
```

云端默认：

```text
MCP_TRANSPORT=streamable-http
DATABASE_URL=postgresql://postgres:<password>@postgres:5432/investment_kg
```

`MCP_PORT` 是容器内 FastMCP 服务监听端口；`MCP_HOST_PORT` 是 ECS 对外暴露端口。大多数情况下两者都保持 `8000`。
