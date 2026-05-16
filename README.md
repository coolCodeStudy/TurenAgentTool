# InvestmentKnowledge MCP

InvestmentKnowledge MCP 是投资知识图谱系统的第一阶段后端骨架。当前目标是跑通股票画像、板块树、知识项、用户心得的写入和查询闭环。

## 本地启动

创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

启动 PostgreSQL + pgvector：

```bash
docker compose up -d postgres
```

初始化数据库：

```bash
python scripts/init_db.py
```

运行 smoke test：

```bash
python scripts/smoke_test.py
```

导入个股研究草稿样例：

```bash
python scripts/import_research_draft.py examples/tencent_research_draft.json --confirmed
```

从资料来源生成研究草稿骨架：

```bash
python scripts/create_research_draft.py 000660 KR \
  --manual-source-file examples/manual_sources/sk_hynix_sources.json
```

也可以直接加入公开网页来源：

```bash
python scripts/create_research_draft.py 000660 KR --name SK海力士 \
  --source-url fact_sheet=https://news.skhynix.com/corporate/fact-sheet/
```

从草稿骨架生成大模型补全 prompt：

```bash
python scripts/build_research_prompt.py drafts/000660_KR_research_draft.json
```

校验补全后的研究草稿：

```bash
python scripts/validate_research_draft.py examples/sk_hynix_research_draft.json
```

使用模型 provider 补全草稿。第一版先用 `mock` 跑通流程：

```bash
python scripts/enrich_research_draft.py drafts/000660_KR_research_draft.json --provider mock
```

使用 OpenAI provider 前，请在本地 `.env` 中配置：

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.2
```

然后运行：

```bash
python scripts/enrich_research_draft.py drafts/000660_KR_research_draft.json --provider openai
```

一键准备研究工作流：

```bash
python scripts/research_stock.py 000660 KR \
  --manual-source-file examples/manual_sources/sk_hynix_sources.json
```

启动 MCP Server：

```bash
python -m investment_knowledge_mcp.server
```

本地默认使用 `stdio` transport。云端部署时使用 `streamable-http`：

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8000 python -m investment_knowledge_mcp.server
```

## 配置

默认数据库连接：

```text
postgresql://postgres:postgres@localhost:55432/investment_kg
```

如需覆盖，复制 `.env.example` 为 `.env` 并修改 `DATABASE_URL`。

## 当前 MCP 工具

- `search_stock`
- `upsert_stock_profile`
- `upsert_sector_tree`
- `link_stock_to_sector`
- `add_source`
- `add_knowledge_item`
- `add_user_insight`
- `import_stock_research_draft`

## 云端部署

阿里云/ECS 部署见 [DEPLOYMENT.md](DEPLOYMENT.md)。生产环境推荐使用：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```
