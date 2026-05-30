# Agent 工作模式演进计划

## 背景

当前 InvestmentKnowledge 已经跑通钉钉 Stream、富途 OpenD、OpenAI 持仓分析和 PostgreSQL 知识库雏形，但交互方式仍偏“命令机器人”：

```text
用户在钉钉提问
-> command_router 同步执行
-> 直接回复结果
```

这种模式在简单查询里够用，但遇到部署、OpenD、Docker、云服务、数据补全等多步骤任务时，用户需要不断执行命令、贴日志、等待判断，体验较累。

参考 Hermes Agent 后，核心启发不是立刻替换框架，而是把 InvestmentKnowledge 从“命令机器人”逐步升级成“投资 Agent 运行时”。

## Hermes 可借鉴点

- 统一 Gateway：CLI、消息平台、cron 都进入同一个 agent runtime。
- 会话隔离：群聊中可以按用户隔离 session，避免上下文串掉。
- 权限控制：allowed users、allowed chats、require mention 等机制清晰。
- Session 持久化：完整保存会话、工具调用和历史，可搜索恢复。
- Cron 一等公民：定时任务有 job id、状态、输出和投递目标。
- 工具运行时：工具注册、权限、后台进程、状态提示、长任务中断都属于框架能力。
- Memory / Skill：长期记忆和可复用工作流是内建概念。

## 演进原则

1. 不急着整套接入 Hermes，避免刚跑通的新加坡 ECS 链路再次复杂化。
2. 先吸收 Hermes 的工作模式，把最痛的“人肉 orchestrator”问题解决掉。
3. InvestmentKnowledge 继续掌握投资数据边界：知识库、候选确认、富途只读、用户心得落库。
4. 外部 Agent Shell 以后可以接，但所有写入仍必须走受控工具和白名单。

## 阶段 1：系统自检与运维助手

目标：减少用户贴日志和执行碎命令的次数。

新增钉钉指令：

```text
系统状态
自检
检查OpenD
检查OpenAI
检查部署
```

检查内容：

- Postgres 是否 healthy。
- dingtalk-stream-bot 是否在线。
- OpenD `127.0.0.1:11111` 是否监听。
- Docker bridge proxy `11112` 是否可达。
- 容器内是否能访问 OpenD。
- 容器内是否能访问 `api.openai.com:443`。
- 当前部署 commit / 镜像状态。
- 最近 bot 错误日志摘要。

输出目标：

- 明确告诉用户当前卡在哪一层。
- 给出下一步建议，但尽量避免让用户手工复制大量命令。

## 阶段 2：任务表与异步任务执行

目标：把多步骤工作变成可追踪任务，而不是长对话里的散落动作。

新增 `agent_tasks` 表：

```text
id
type
status: pending / running / succeeded / failed / needs_user
input
result
error
created_by
created_at
updated_at
```

典型任务：

- 补全前十大持仓画像。
- 生成今日复盘。
- 检查系统状态。
- 导入一只股票的研究草稿。
- 扫描 IPO 并更新提醒状态。

钉钉交互示例：

```text
用户：补全前十大持仓画像
系统：已创建任务 #42，开始执行。
系统：任务 #42 需要你确认：是否把阿里巴巴归入“港股互联网/电商平台”？
系统：任务 #42 完成，新增画像 8 条，待确认候选心得 3 条。
```

## 阶段 3：自然语言 Intent Router

目标：减少固定命令格式，让用户用自然语言表达目标。

支持：

```text
今天组合哪里风险最大？
帮我把这句话记成组合心得
最近有没有新股需要提醒？
帮我检查为什么机器人没回消息
把前十大持仓都补一下画像
```

实现方式：

- LLM 先判断 intent 和风险级别。
- 查询类可直接执行。
- 写入类必须满足白名单。
- 系统推断出的用户观点只能进入候选心得，不能直接变成正式心得。

## 阶段 4：Hermes 作为外壳

目标：让 Hermes 承担通用 gateway / session / cron / memory shell，InvestmentKnowledge 退到受控投资后端。

当前决策：

```text
钉钉 / CLI / Cron
-> Hermes Gateway
-> InvestmentKnowledge MCP / HTTP tools
-> PostgreSQL / Futu / OpenAI
```

落地原则：

- 单个钉钉机器人先由 Hermes 接管，InvestmentKnowledge 不再直接消费同一套 Stream 凭证。
- InvestmentKnowledge MCP 第一版只暴露安全总入口 `run_investment_command` 给 Hermes。
- 查询类和富途维护类可以直接执行；正式心得写入仍然必须经过候选确认。
- 开发类需求先进入 `coding_tasks`，由云端 Codex worker 自动领取、改代码、提交、推送分支，并在默认配置下触发 GitHub Actions 部署。
- GitHub Actions 继续作为正式发布与回滚通道；Hermes 负责日常交互和轻量任务调度。

## 推荐下一步

1. 给 InvestmentKnowledge MCP 增加安全自然语言命令入口。
2. 编写 Hermes ECS 安装脚本和单机器人切换文档。
3. 在新加坡 ECS 上先启动 InvestmentKnowledge MCP HTTP，再启动 Hermes Gateway。
4. 测试 `帮助`、`我的持仓`、`本月收益`、`富途状态`。
5. 稳定后再迁移 IPO 定时提醒和任务表。
