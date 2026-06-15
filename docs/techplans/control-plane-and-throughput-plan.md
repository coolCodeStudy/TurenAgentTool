# Control Plane 与跑数效率升级计划

## 背景判断

当前 InvestmentKnowledge 的最高频使用主线不是钉钉查询，而是：

```text
用户
  -> Codex App
    -> Codex 读本地代码 / 修改代码 / 跑验证
    -> Codex 通过云端 MCP / Ops API 查看 ECS 状态和日志
    -> Codex 总结问题、实施修复、触发或检查部署
```

钉钉是日常投资查询和通知入口，云端 worker 是异步执行入口，但系统的核心开发效率取决于 Codex App 协作链路是否顺滑。

因此下一阶段优先级应从“多入口能力”调整为“Codex 协作控制平面”：

- 让 Codex 能快速知道系统当前状态。
- 让 Codex 能快速定位部署、worker、研究任务卡点。
- 让任务和部署过程结构化落库，而不是只靠日志。
- 让跑数任务支持批量、分层和可恢复执行。

安全增强暂不作为前排优先级，只保留不影响产出的最低边界。

## 修正后的交互架构

```text
用户
  |
  | 高频：提出目标、让 Codex 判断/修改/部署/诊断
  v
Codex App
  |
  +-- 本地仓库：读代码、改代码、跑测试
  |
  +-- 云端 MCP /mcp
        |
        +-- InvestmentKnowledge MCP tools
              |
              +-- Ops API：ECS 状态、服务日志、worker 状态
              +-- PostgreSQL：任务、知识库、事件、部署记录
              +-- Futu OpenD：持仓、交易、IPO
              +-- OpenAI：分析/路由/研究补全

钉钉
  |
  +-- 日常查询：持仓分析、本月收益、怎么看某股票
  +-- 通知：worker 完成、部署完成、任务失败、需要确认

云端 worker
  |
  +-- research_jobs：研究跑数
  +-- coding_tasks：开发任务
```

## 持久化位置

所有协作和任务控制平面数据优先持久化在当前 PostgreSQL 数据库，不另起新存储。

建议新增表：

```text
work_sessions
  id
  source              -- codex_app / dingtalk / github_action / worker
  goal
  status             -- active / completed / blocked
  summary
  related_task_ids
  related_job_ids
  started_at
  finished_at
  created_at
  updated_at

task_events
  id
  task_type           -- research / coding / deploy / snapshot / ipo / command
  task_id
  event_type          -- claimed / started / step_finished / failed / completed
  status
  message
  metadata
  created_at

deploy_events
  id
  source              -- github_action / codex_worker / local_codex
  deploy_mode         -- quick / full / local
  commit_sha
  branch_name
  status              -- started / succeeded / failed
  started_at
  finished_at
  duration_seconds
  summary
  logs_tail
  created_at
```

文档层只保存阶段计划、项目状态、经验教训和人工复盘；运行态事实放数据库。例行流水账已废弃，长期信息应进入 `docs/当前工程状态.md`、`docs/agent-lessons.md` 或 `docs/project-history.md`。

## 当前流水线问题

### Codex 协作链路

现状：

- Codex 可以读本地代码。
- Codex 可以通过 MCP/Ops API 看云端状态和日志。
- 但 Codex 缺少一个系统总览工具，需要在多个日志、表和命令之间来回拼。

优化目标：

- 新增 `system_overview` / `系统总览`。
- 一次返回服务状态、部署状态、任务队列、最近失败、账户快照新鲜度。
- 用户不需要看 Docker 日志；日志是 Codex 的输入，不是用户的工作。

### 部署流水线

现状：

- quick deploy 和 full deploy 已区分。
- quick deploy 仍打较大的 release tar。
- 部署后主要输出日志，没有结构化部署事件。
- 健康检查不是所有部署路径的强制步骤。

优化目标：

- quick deploy 排除 `drafts/` 等大产物。
- quick/full deploy 都写入 `deploy_events`。
- 部署结束自动跑健康检查，并把结果摘要落库。
- Codex 可以直接问最近一次部署结果。

### 研究跑数流水线

现状：

- 已有 `research_jobs`。
- worker 默认偏单并发，适合稳，不适合批量补全。
- 状态粒度偏粗，不知道卡在 source、draft、audit、import 哪一步。
- `scripts/create_research_jobs.py` 当前传入了 `execution_location`、`created_from`、`requested_by` 等参数，但 `research.jobs.create_research_job` 现有签名没有这些参数；这条脚本路径需要修正，否则批量创建任务可能直接失败。

优化目标：

- 新增 `task_events` 记录每一步。
- 把研究拆成 fast seed 和 deep codex 两段。
- fast seed 可并发，deep codex 控制并发。
- 批量任务有 `run_group_id`，支持“前十大持仓补全”的整体汇总。

## 优先级计划

### P0：Codex 协作控制平面

产出：

- 新增 `系统总览` 命令。
- 新增 MCP tool：`system_overview` 或扩展 `cloud_system_status`。
- 汇总：
  - 服务状态
  - 最近部署
  - research queue
  - coding queue
  - worker status
  - 最近 command failures
  - 最近 account snapshot

成功标准：

- 用户问“现在系统怎么样”，Codex 不需要先翻 5 个日志。
- Codex 能 1 分钟内判断卡点在部署、worker、Futu、OpenAI、DB 还是任务数据。

### P1：部署事件化

产出：

- 新增 `deploy_events`。
- 修改 GitHub Actions 和 `deploy_from_local_checkout.sh`，部署开始/结束写事件。
- quick deploy 排除 `drafts/`。
- 部署后自动健康检查。

成功标准：

- 用户问“上次部署成功了吗”，系统能直接答。
- Codex 可以看到 commit、deploy mode、耗时、失败摘要。

### P2：任务事件化

产出：

- 新增 `task_events`。
- coding worker / research worker 每个关键阶段写事件。
- 新增命令：
  - `任务状态 #id`
  - `研究任务 #id`
  - `最近失败任务`

成功标准：

- 不看日志也能知道任务卡在哪一步。
- 失败任务可以按原因聚合。

### P3：研究跑数并发与分层

产出：

- `research_jobs` 增加 `run_group_id`、`stage`、`max_attempts`、`attempt_count`。
- fast seed worker 支持并发 2-4。
- deep codex worker 保持低并发。
- 批任务汇总报告。

成功标准：

- 前十大持仓画像补全可以批量跑。
- 大部分股票先用低成本 seed 完成，只有不足的进入 Codex 深研。

### P4：开发任务效率

产出：

- `coding_tasks` 增加 `task_kind`。
- docs 类任务不部署。
- bugfix/feature 跑 targeted tests。
- ops 类任务部署后强制健康检查。
- 支持多个完成任务合并部署。

成功标准：

- 小修不再每次完整重启。
- Codex worker 的结果包含验证和部署状态。

### P5：结构重构

产出：

- 拆 `command_router.py` 到 `commands/`。
- 拆 `repository.py` 到 `stores/`。
- research pipeline 显式 workflow 化。

成功标准：

- 新增功能不继续堆到超级路由器。
- 测试能覆盖命令路由、任务事件、研究导入。

## 云上多线程跑数结论

可以云上并发跑，但建议分层并发，不建议所有任务都直接多 Codex 并发。

推荐：

```text
fast seed research:
  并发 2-4
  低成本、短耗时、适合批量

OpenAI enrich:
  并发 1-2
  受 API 成本和 rate limit 控制

Codex deep research:
  并发 1
  高成本、高不确定性、适合难票或失败补救

DB import:
  可并发，但同一 symbol/market 需要唯一约束和幂等
```

技术上可选：

- 单 worker 进程内部 `ThreadPoolExecutor`。
- 多个 systemd worker 实例。
- 多容器 worker replicas。

短期最稳的是多个 worker 角色：

```text
research-seed-worker@1..N
research-codex-worker@1
coding-worker@1
```

每个 worker 用 `FOR UPDATE SKIP LOCKED` 抢任务，当前代码已经具备这个基础。
