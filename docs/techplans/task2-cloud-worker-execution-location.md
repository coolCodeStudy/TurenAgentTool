# Task 2 Tech Plan: 将本地研究流水线产品化为云端 worker 默认能力

## 背景

上一轮组合覆盖中，Codex desktop session 在本地完成了来源抓取、SEC/HKEX/PDF 清洗、draft 生成、audit/review，然后通过 MCP 工具导入 InvestmentKnowledge 数据库。这个流程能跑通，但执行位置不透明：用户没有明确选择“本地跑批量研究”，也无法在任务状态里直接看到任务到底是在本地 Codex、云主机 worker，还是仅执行导入。

更大的问题是：本地跑出来的来源定位、清洗、audit/review 和导入经验，如果只停留在本地脚本和手工操作里，云主机 worker 不会自动获得这些能力。后续批量研究和组合刷新应默认由云主机 worker 执行，并且云端 worker 必须复用同一套产品化后的研究流水线。本地 Codex 主要用于调试、少量补洞、人工审阅、工具修复和导入已确认 draft。

## 核心目的

Task 2 的核心不是单纯增加 `execution_location` 字段，也不是写一句“需要部署”。核心是：

1. 把这次本地跑通的研究流程沉淀成云端 worker 可以直接执行的代码路径。
2. 以后用户说“覆盖组合/刷新股票”时，默认只是创建云端任务，本地不再手工跑批量研究。
3. 云端 worker 产出的 draft、audit、review、token usage、warnings、import 状态都能被本地 Codex 查询到。
4. 本地和云端使用同一套 research pipeline，避免本地有能力、云端没有能力。
5. `execution_location` 只是这个目标的可观测性和防误解机制。

## 目标

1. 将本地跑通的研究流程产品化为云端 worker 默认执行路径。
2. 批量研究/组合刷新默认进入云主机 worker，而不是在 Codex desktop 本地手工跑。
3. 云端 worker 能完成 source collection、draft enrichment、validation、audit、review、artifact 持久化和可选 import。
4. 本地 Codex 能查询云端任务状态、artifact 摘要、token usage、warnings 和 import 状态。
5. 所有研究任务都能显示 `execution_location`，避免本地结果和云端结果混淆。
6. 本地脚本执行时明确提示 `local_codex`，并对批量本地执行加显式确认。

## 非目标

1. 不重写研究 agent 的核心研究逻辑。
2. 不改变 Futu 账户读取和交易相关逻辑。
3. 不在本任务中优化研究展示层；展示瘦身属于 Task 3。
4. 不把“部署说明”当作完成标准；必须验证云端 worker 真的能跑通同一条研究链路。

## 术语

- `cloud_worker`: 云主机上的 research/codex worker 执行。
- `local_codex`: 当前 Codex desktop session 或本地 shell 执行。
- `manual_import`: 用户确认的 draft 被手动导入知识库。
- `import_only`: 只导入已有 artifact，不执行研究。

## 需要梳理的入口

1. MCP tools:
   - `create_research_job`
   - `create_portfolio_research_jobs`
   - `list_research_jobs`
2. Scripts:
   - `scripts/create_research_jobs.py`
   - `scripts/research_agent_worker.py`
   - `scripts/research_stock.py`
   - `scripts/create_research_draft.py`
   - `scripts/import_research_draft.py`
3. Natural language command router:
   - 创建研究任务
   - 查看研究任务
   - 导入研究结果

## 数据模型建议

优先复用现有 `research_jobs` 的 metadata/json 字段；如果没有合适字段，再做 schema migration。

建议字段：

```text
execution_location: cloud_worker | local_codex | manual_import | import_only
worker_name: string | null
requested_by: string | null
created_from: mcp_tool | script | command_router | codex_desktop
artifact_location: local_path | object_url | null
started_at: timestamptz | null
finished_at: timestamptz | null
```

## 实现步骤

1. 阅读当前本地研究链路，确认本地覆盖股票时实际用到的能力：
   - source collection: SEC/HKEX/issuer pages/PDF。
   - source cleaning: iXBRL/PDF/text excerpt。
   - draft enrichment。
   - validation/audit/review。
   - import into InvestmentKnowledge。
2. 阅读云端 worker 链路，确认 `research_agent_worker.py` 现在是否真的调用同一套能力，还是只处理部分 mock/seed 流程。
3. 抽出或补齐共享 research pipeline，使本地脚本和云端 worker 调用同一套核心函数，而不是复制两套逻辑。
4. 云端 worker 需要能持久化 artifact metadata：
   - draft JSON。
   - audit report。
   - review report。
   - warnings。
   - token usage。
   - source policy。
   - import status。
5. 在创建 research job 的统一入口里设置默认 `execution_location=cloud_worker`。
6. `create_portfolio_research_jobs` 默认创建云端任务，不在本地直接跑研究。
7. `research_agent_worker.py` 领取任务时写入 `worker_name`、`started_at`、`finished_at`。
8. 本地脚本输出中增加 execution banner，并对批量本地研究加显式确认：
   - `research_stock.py`: `execution_location=local_codex`
   - `create_research_draft.py`: `execution_location=local_codex`
   - `import_research_draft.py`: `execution_location=manual_import` 或 `import_only`
9. `list_research_jobs` 默认显示 execution location、worker、artifact 存在性、token usage、warnings 和 import 状态。
10. command router 对“列出任务/查看任务”和“创建任务”做更严格区分，避免查询命令误创建任务。
11. 部署到 ECS/云主机并重启 MCP、research worker 或相关服务。
12. 创建一个真实或小型测试 research job，确认云端 worker 能完整跑完 source -> draft -> audit -> review -> artifact -> status。
13. 再用本地 Codex 查询该 job，确认看到的是云端执行结果，而不是本地 artifact。

## 验收标准

1. 创建单只股票 research job 时，默认进入云端 worker 队列，`execution_location=cloud_worker`。
2. 创建组合 research jobs 时，默认全部进入云端 worker 队列。
3. 云端 worker 能完整跑通至少一个测试标的的 source collection、draft、validation、audit、review 和 artifact 写回。
4. `list_research_jobs` 默认能看到任务在哪里跑、谁在跑、artifact 是否存在、token usage、warnings 和 import 状态。
5. 本地脚本运行时，终端输出明确显示 `local_codex`、`manual_import` 或 `import_only`。
6. 本地批量研究需要显式参数确认，不能静默执行。
7. 查看任务不会误触发创建任务。
8. 不改变交易/账户写入逻辑。

## 测试建议

1. 单元测试：创建 research job 后 metadata 包含 `execution_location=cloud_worker`。
2. 单元测试：portfolio job 批量创建后每个 job 都有 execution location。
3. 单元测试或集成测试：`list_research_jobs` 默认输出包含 execution location。
4. 回归测试：自然语言“列出 coding tasks / list research jobs”不会创建开发任务。
5. 手工测试：本地执行 import draft，输出不会让人误解为云端 worker 完成。
6. 云端 smoke test：部署后创建一个小型 mock/真实 research job，确认 worker 在 ECS 上领取、运行、写回状态和 artifact metadata。

## 风险

1. 如果现有 job schema 没有 metadata 字段，需要 migration，注意生产库兼容。
2. 如果 command router 的意图识别过宽，可能继续把“查看”误判成“创建”。
3. 如果云端 worker 未运行，默认云端执行会导致任务排队但不完成；需要在状态输出里显示 worker health。
4. 如果本地脚本和云端 worker 调用不同代码路径，本地优化仍然不会反映到云端；必须抽出共享 pipeline 或证明两边调用同一模块。
5. 如果云端 artifact 只落在云主机本地路径，本地 Codex 可能看不到；需要可查询的 artifact metadata 或可访问存储。
