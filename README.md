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

启动 MCP Server：

```bash
python -m investment_knowledge_mcp.server
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
- `add_knowledge_item`
- `add_user_insight`
