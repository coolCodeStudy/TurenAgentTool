# 持仓新闻事件雷达技术方案

## 结论

`PRD-持仓新闻事件雷达` 的方向成立，而且和当前系统的缺口高度匹配：周复盘和持仓分析已经明确缺少外部公告/事件源，事件雷达可以成为它们之间的事实层补丁。

我建议把 PRD 保留为产品边界文档，但实施时必须收窄 P1。第一版不要做“持仓新闻系统”，而要做“SEC 持仓事件探针 + 事件卡入库 + 命令查询”。这能先验证最难也最有价值的部分：官方文件发现、关键字段解析、事件日推导、低噪音输出。

新版 PRD 已经把 P1 收窄为“美股持仓 SEC 事件雷达”，并补充了“无事件”和“扫描失败”不能混淆、AXTI 只是高级样例、媒体源放到 P2、P1 只支持单事件静音等约束。技术方案需要显式承接这些产品约束。

## 需要 Pushback 的点

以下内容在新版 PRD 中大多已经被吸收，后续实施时仍作为技术 guardrail 保留。

### 1. P1 不能同时覆盖美股、港股和 A 股

PRD 写了美股优先、港股 P1 可选、A 股暂缓，这个方向对。但实施计划里要更明确：

- P1 只做美股 SEC。
- 港股 HKEXnews 放到 P1.5 或 P2。
- A 股不进入当前工程切片，只保留研究项。

原因是三地公告结构、事件定义和交易日口径差异很大。如果 P1 同时抽象三地规则，很容易先做出一个漂亮但不可用的泛化模型。

### 2. AXTI lock-up 样例不能作为唯一 P1 验收

AXTI 是一个好样例，但它依赖 `424B5 / 8-K / 媒体标签 / 交易日推导` 多源合成，复杂度偏高。P1 需要增加更稳定的验收路径：

- Form 4 实际卖出。
- Form 144 拟出售。
- 424B5 / S-3 / 8-K offering 候选发现。
- AXTI lock-up 作为 P1+ 样例，不作为 Slice 1 的唯一成败标准。

这样可以避免一开始卡在长文本条款抽取上。

### 3. `event_sources` 不宜完全新建孤岛

当前系统已有 `sources`、`knowledge_items`、`research_jobs` 和 `task_events`。PRD 建议新增 `event_sources` 有道理，因为 SEC filing 需要 accession number、form type、raw hash、fetch status 等字段。

但技术上要明确关系：

- `event_sources` 是事件雷达专用 source cache，不替代现有 `sources`。
- 重要事件经用户确认或周复盘引用后，可以再沉淀到 `sources` / `knowledge_items`。
- `portfolio_events.source_ids` 先关联 `event_sources.id`，不要混用 `sources.id`，避免语义不清。

### 4. 云端 Codex worker 应该是 fallback，不是主链路

PRD 中“复杂理解交给云端 Codex worker”的边界是对的，但 P1 主链路不能依赖 worker 才能产出事件。

P1 必须保证：

- 没有模型、没有 worker 时，也能列出 SEC filing 候选事件。
- Form 4 / Form 144 的结构化解析走脚本。
- `424B5 / 8-K` 先产出 `offering_candidate`，复杂 lock-up 摘要再进入 worker backlog。

这样系统才可重复、可测试、可控成本。

### 5. 事件提醒生命周期要先落状态机，不要先落交互按钮

PRD 里的“只在有新增时提醒”“不再提醒这件事”等用户动作很好，但 P1 可先实现底层字段：

- event status。
- alert policy。
- last alerted at。
- muted / watch only / default。

命令式反馈可以晚一步接入，否则容易把实现重心带偏到交互层。

## P1 目标

P1 的目标是支持以下闭环：

```text
富途当前持仓
-> 筛出美股 ticker
-> ticker 映射 CIK
-> 拉取 SEC submissions
-> 下载重点 filing 原文
-> 脚本解析结构化事件
-> 入库去重
-> 命令输出持仓事件卡
-> 周复盘可读取事件摘要
```

P1 不做：

- 全市场新闻流。
- 社交媒体或情绪监控。
- 自动交易建议。
- 高频刷新。
- 港股和 A 股完整公告解析。
- 技术面冲击评估。
- 媒体/数据平台自动抓取，除 AXTI 高级样例或人工补充来源外放到 P2。

## 模块设计

建议新增包：

```text
investment_knowledge_mcp/events/
  __init__.py
  models.py
  sec_client.py
  sec_parsers.py
  calendar.py
  scanner.py
  repository.py
  renderer.py
```

### `sec_client.py`

负责 SEC 网络访问和缓存。

职责：

- 下载 `company_tickers.json`。
- ticker -> CIK 映射。
- 下载 `data.sec.gov/submissions/CIK##########.json`。
- 下载 filing primary document 或 XML 附件。
- 生成 canonical URL。
- 计算 raw hash。

实现原则：

- 所有外部请求集中在 client。
- 支持缓存目录或数据库 cache。
- 对 SEC 请求设置 User-Agent。
- 网络失败返回 fetch status，不让命令整体崩掉。

### `sec_parsers.py`

负责从 SEC filing 中提取硬字段。

P1 parser：

- Form 4 XML：报告人、交易日期、transaction code、股数、价格、剩余持股、10b5-1 标记。
- Form 144：拟售人、拟售股数、notice date、approx sale date、market value。
- 424B5 / S-3 / 8-K：先识别 offering candidate，抽取发行股数、发行价、总金额、underwriter、lock-up 天数候选。

设计原则：

- parser 输出结构化 JSON。
- parser 不能生成投资结论。
- 不确定字段放入 `uncertainties`。
- lock-up 条款没有高置信解析时，只产生 `needs_research=true`。

### `scanner.py`

负责把持仓 universe 转换为事件候选。

职责：

- 读取富途持仓。
- 标准化市场和 ticker。
- 按扫描窗口选择 filing。
- 调用 parser 生成 event packet。
- 调用 repository upsert source / event / checkpoint。
- 对复杂候选创建 event research backlog。

P1 扫描窗口：

- 每日增量：30 天回看。
- 单票查询：90 天回看。
- lock-up deep scan：365 天回看，但只在新持仓、主动查询或强制刷新时触发。

### `repository.py`

负责事件雷达专用数据读写。

需要提供：

- `upsert_event_source(...)`
- `upsert_portfolio_event(...)`
- `record_event_scan_run(...)`
- `list_portfolio_events(...)`
- `record_event_alert(...)`
- `upsert_event_alert_preference(...)`
- `get_scan_checkpoint(...)`
- `update_scan_checkpoint(...)`

所有写入都应该幂等。

### `renderer.py`

负责命令行/钉钉可读输出。

输出原则：

- 每日摘要最多 5 条。
- 没有高优先级事件时输出一句明确结论。
- 只有扫描状态为 `ok` 时，才能输出“今日无高优先级持仓事件”。
- 扫描状态为 `partial` 或 `failed` 时，必须展示失败范围和原因。
- 单票详情展示时间线、来源、系统推导和不确定点。
- 不把相关性写成因果。

## 数据库设计

### `event_sources`

事件源缓存表。

```sql
CREATE TABLE IF NOT EXISTS event_sources (
  id BIGSERIAL PRIMARY KEY,
  source_type TEXT NOT NULL,
  publisher TEXT,
  url TEXT NOT NULL,
  canonical_url TEXT,
  title TEXT,
  published_at TIMESTAMPTZ,
  market TEXT,
  symbol TEXT,
  accession_number TEXT,
  cik TEXT,
  form_type TEXT,
  raw_hash TEXT,
  excerpt TEXT,
  parsed_facts JSONB NOT NULL DEFAULT '{}'::jsonb,
  fetch_status TEXT NOT NULL DEFAULT 'ok',
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_type, accession_number),
  UNIQUE (canonical_url, raw_hash)
);
```

注意：`canonical_url` 或 `raw_hash` 可能为空，PostgreSQL 的 unique index 会允许多个 NULL。实现时可以改成 partial unique index，避免空值造成误解。

### `portfolio_events`

归一化事件表。

```sql
CREATE TABLE IF NOT EXISTS portfolio_events (
  id BIGSERIAL PRIMARY KEY,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_title TEXT NOT NULL,
  event_date DATE,
  next_trading_date DATE,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  priority TEXT NOT NULL DEFAULT 'medium',
  confidence TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'active',
  source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
  derived_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
  media_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  uncertainties JSONB NOT NULL DEFAULT '[]'::jsonb,
  portfolio_relevance JSONB NOT NULL DEFAULT '{}'::jsonb,
  dedupe_key TEXT NOT NULL,
  scan_status TEXT NOT NULL DEFAULT 'ok',
  needs_research BOOLEAN NOT NULL DEFAULT false,
  research_job_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (dedupe_key)
);
```

推荐 `dedupe_key`：

```text
market:symbol:event_type:event_date_or_filing_date:primary_accession_or_url
```

### `event_alerts`

提醒快照表。

```sql
CREATE TABLE IF NOT EXISTS event_alerts (
  id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES portfolio_events(id) ON DELETE CASCADE,
  alert_date DATE NOT NULL,
  channel TEXT NOT NULL,
  alert_level TEXT NOT NULL DEFAULT 'medium',
  rendered_summary TEXT NOT NULL,
  user_action TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (event_id, alert_date, channel)
);
```

### `event_alert_preferences`

单事件提醒偏好表。P1 只需要支持“这一件事不再主动提醒”，不需要完整实现所有提醒策略。

```sql
CREATE TABLE IF NOT EXISTS event_alert_preferences (
  id BIGSERIAL PRIMARY KEY,
  event_id BIGINT NOT NULL REFERENCES portfolio_events(id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'all',
  preference TEXT NOT NULL DEFAULT 'default',
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (event_id, channel),
  CHECK (preference IN ('default', 'muted'))
);
```

P2 再扩展为 `new_sources_only`、`t_minus_1_only`、`continue_reminding` 等更细策略。

### `event_scan_runs`

扫描运行记录表。它解决一个关键产品问题：不能把“扫描失败”误报成“无事件”。

```sql
CREATE TABLE IF NOT EXISTS event_scan_runs (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  market TEXT,
  symbol TEXT,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  symbols_total INTEGER NOT NULL DEFAULT 0,
  symbols_scanned INTEGER NOT NULL DEFAULT 0,
  events_found INTEGER NOT NULL DEFAULT 0,
  errors JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (scope IN ('portfolio', 'stock')),
  CHECK (status IN ('ok', 'partial', 'failed'))
);
```

渲染规则：

- `status='ok'` 且无高优先级事件：可以输出“今日无高优先级持仓事件”。
- `status='partial'`：输出已扫描结果，同时说明哪些标的或来源失败。
- `status='failed'`：不得输出无事件，只输出扫描失败原因。

### `event_scan_checkpoints`

增量扫描 checkpoint。

```sql
CREATE TABLE IF NOT EXISTS event_scan_checkpoints (
  id BIGSERIAL PRIMARY KEY,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'sec',
  last_scanned_at TIMESTAMPTZ,
  last_filing_date DATE,
  last_accession_numbers JSONB NOT NULL DEFAULT '[]'::jsonb,
  deep_scan_completed_until DATE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (market, symbol, provider)
);
```

## 事件类型枚举

P1 建议先固定这些类型：

```text
form_4_insider_transaction
form_144_sale_notice
offering_candidate
registered_offering
shelf_registration
lockup_expiration
material_8k
earnings_event
```

第一版允许 `offering_candidate` 多于 `registered_offering`。宁可先提醒“发现增发相关文件，需要进一步解析”，也不要过早写成确定事件。

## 优先级规则

### High

满足任一：

- 当前持仓命中，且事件类型是 Form 4 卖出、Form 144、lock-up、registered offering。
- 明确事件日在未来 7 天或过去 3 天。
- source facts 中包含较大股数、发行规模、拟售规模。

### Medium

满足任一：

- 当前持仓命中，但事件类型仍是候选。
- 用户主动查询单票。
- 普通 8-K 或财报日。

### Low

满足任一：

- 非持仓观察名单事件。
- 无新增事实的媒体标签。
- 解析置信度低且不在事件窗口内。

P1 主动摘要只展示 High 和必要的 Medium。

## 命令入口

在 `command_router` 增加两个 intent：

```text
portfolio_events
stock_events
```

命令：

```text
持仓事件
持仓新闻
风险雷达
AXTI 事件
AXTI 最近有什么新闻
```

P1 行为：

- `持仓事件`：读取持仓，扫描美股持仓，输出当前事件摘要。
- `AXTI 事件`：单票扫描或读取缓存，输出事件时间线。
- `不再提醒 AXTI 这件事`：把匹配到的事件写入 `event_alert_preferences(preference='muted')`。
- 默认只读，不写用户心得。
- 如果网络或 SEC 不可用，输出数据源状态，不伪造“无事件”。

## 与周复盘集成

`weekly_review.build_weekly_review_context()` 当前 `source_status.events` 写死为未实现。P1 可以接入：

```text
repository.list_portfolio_events(
  symbols=current_holding_symbols,
  date_from=start - 14 days,
  date_to=end + 14 days,
  min_priority='medium',
)
```

周复盘只把事件作为“原因候选”：

```text
AXTI 本周回撤。事件层面，系统识别到 4 月发行文件后的 lock-up 到期候选，以及近期内部人交易披露。该组合可能强化供应压力担忧，但不能单独证明股价下跌原因。
```

## 云端 Codex Worker 集成

当前已有 `research_jobs`，但事件研究不应该硬塞进股票研究草稿流程。推荐新增轻量表或扩展 task 类型：

P1 保守方案：

- 不新增 worker 表。
- 对 `needs_research=true` 的事件只在输出中标注“需要进一步研究”。
- 不让 worker 结果阻塞 Form 4 / Form 144 / filing 候选事件输出。

如果 P1 必须创建云端研究任务，建议直接新增事件专用队列表，而不是复用股票研究草稿表：

```text
event_research_jobs
  event_id
  symbol / market
  provider
  source_policy
  status
  artifact_location
  source_audit
```

不要复用 `research_jobs` 的 `import_stock_research_draft` 语义，否则 worker 产物和入库流程会混乱。

## 实施切片

### Slice 1：SEC Filing 探针

交付：

- `events/sec_client.py`
- `events/scanner.py`
- `scripts/scan_portfolio_events.py`
- 不入库，只输出 JSON / Markdown。

验收：

- 给定 ticker 列表，能拉取 submissions。
- 能识别最近 30 天的 `4`、`144`、`8-K`、`424B5`、`S-3`。
- 网络失败时有清晰 source status。
- 输出扫描级 `scan_status`，区分 `ok` / `partial` / `failed`。

### Slice 2：Form 4 / Form 144 结构化解析

交付：

- `events/sec_parsers.py`
- parser fixture。
- 单元测试。

验收：

- Form 4 能区分实际卖出、授予、期权行权。
- Form 144 能提取拟售股数、拟售人、notice date。
- parser 不生成因果判断。

### Slice 3：事件入库和去重

交付：

- `event_sources`
- `portfolio_events`
- `event_scan_checkpoints`
- repository upsert。

验收：

- 重复扫描不会重复生成事件。
- 同一 accession number 不重复抓取和解析。
- 同一事件多来源能合并 source ids。

### Slice 4：命令入口

交付：

- `持仓事件`
- `AXTI 事件`
- `不再提醒这件事`
- renderer。

验收：

- 命令通过 `scripts/ikg.py` 可调用。
- 没有事件时输出明确低噪音结论。
- 数据源失败时不能输出“无事件”。
- 有事件时最多展示 5 条摘要。
- 输出包含来源、置信度、不确定点。
- 单事件静音后，主动摘要不再推送该事件；主动查询和周复盘仍可显示。

### Slice 5：AXTI lock-up 样例

交付：

- 424B5 / 8-K lock-up 候选解析。
- 下一交易日推导。
- AXTI fixture。

验收：

- 能从发行文件中抽取 8,560,311 股、64.25 美元、60 天 lock-up 候选。
- 能推导合同/日历日期和下一交易日口径。
- 输出明确说明“不应机械表述为全部股份在当天可卖”。

### Slice 6：周复盘接入

交付：

- `weekly_review` 读取 `portfolio_events`。
- `source_status.events` 变为 ok / partial / missing。

验收：

- 周复盘能列出本周发生和下周临近事件。
- 事件只作为原因候选，不写确定因果。

## 测试策略

### 单元测试

- ticker normalization。
- CIK mapping。
- SEC submissions filtering。
- scan status rendering。
- Form 4 parser。
- Form 144 parser。
- dedupe key。
- event priority。
- event alert preference。
- render output。

### Fixture 测试

把真实 SEC 文件保存为小型 fixture：

```text
tests/fixtures/sec/
  form4_sample.xml
  form144_sample.xml
  axti_424b5.html
  axti_8k.html
  submissions_axti.json
```

测试不能依赖实时网络。

### 手动验证

```bash
python scripts/scan_portfolio_events.py --symbol AXTI --market US --days 90
python scripts/ikg.py "AXTI 事件"
python scripts/ikg.py "持仓事件"
python scripts/smoke_test.py
```

如果当前 worktree 没有 `.venv`，先记录为环境限制，不要为了验证启动 prod compose。

## 风险

- SEC HTML 格式变化会影响 lock-up 条款抽取。
- Form 4 transaction code 容易误读，必须明确区分卖出、授予、行权、自动交易计划。
- 事件日和交易日口径需要市场日历，P1 可先用 `pandas_market_calendars` 或轻量 NYSE 日历，不能用“周末顺延”覆盖所有假期。
- 当前富途持仓可能只在云端环境可用，本地测试应支持 ticker fixture。
- 媒体标签不能成为事实源，只能作为发现和解释辅助。

## 推荐开工顺序

1. 先做 Slice 1 和 Slice 2，不改命令入口。
2. 再加 schema 和 repository，把事件入库跑通。
3. 接 `AXTI 事件` 单票命令。
4. 接 `持仓事件`，读取富途持仓；本地缺数据时允许 `--symbols` fixture。
5. 最后接周复盘。

这条路径能最快验证最核心假设：系统是否能稳定地从官方文件里发现持仓相关风险事件，并以低噪音方式解释给用户。
