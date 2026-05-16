# SK海力士 分析上下文

## 股票画像

- 代码：000660
- 市场：KR
- 名称：SK海力士
- 核心业务：SK hynix 是韩国存储半导体公司，核心业务覆盖 DRAM、HBM、NAND Flash 和 SSD。当前投资主线集中在 AI 服务器所需的高带宽内存 HBM、企业级 SSD，以及面向 AI PC 和客户端市场的 NAND/SSD 产品。
- 股权结构：截至 2026-04-07，SK Square 及关联方合计持有 146,118,388 股，占 20.5%，为主要股东；截至相关披露，韩国国民年金持股 7.9%，Capital Research and Management Company 持股 5.1%，BlackRock Fund Advisors 持股 5.0%。
- 股性：强周期科技成长股，股价通常受 DRAM/NAND 景气、HBM 供需、AI 算力资本开支、主要客户认证与订单、韩元汇率和半导体周期预期共同驱动。当前更偏 AI memory / HBM 龙头叙事，但仍保留存储周期股的高波动属性。
- 突出历史：2024 年公司量产世界首款 12 层 HBM3E，并量产 321 层 NAND Flash。2025 年实现历史最高年度业绩。2026 年在 GTC 展示 HBM4、SOCAMM2、定制 HBM 等 AI memory 产品组合，并与 Sandisk 推动 HBF 标准化。

## 板块归属

- `main` 科技 > 半导体 > 存储芯片 > DRAM/HBM (confidence=0.920, confirmed=True)
  - 描述：公司核心业务之一，HBM 是当前 AI 服务器内存的关键品类，也是公司高价值产品和利润弹性的主要来源。
  - 近况：AI memory 需求强劲，SK hynix 在官方资料中强调 HBM 和企业级 SSD 领导力，并在 GTC 2026 展示 HBM4 和定制 HBM。
- `main` 科技 > 半导体 > 存储芯片 > NAND/SSD (confidence=0.860, confirmed=True)
  - 描述：公司生产 NAND Flash，并提供企业级、客户端和消费级 SSD，是 DRAM/HBM 之外的重要业务线。
  - 近况：2026 年 4 月，公司开始供应采用 321 层 QLC NAND 的客户端 SSD PQC21，强调 AI PC 存储需求。
- `theme` AI基础设施 > AI服务器供应链 > 高带宽内存 (confidence=0.900, confirmed=True)
  - 描述：HBM、SOCAMM、LPDDR 和企业级 SSD 均围绕 AI 训练与推理基础设施展开，和 NVIDIA 等 GPU 平台生态高度相关。
  - 近况：GTC 2026 展示 NVIDIA Vera Rubin 200 搭配 SK hynix SOCAMM2 和 HBM4，强化 AI 平台配套逻辑。

## 个股事实知识

- `equity_structure` confidence=0.950, confirmed=True, source=[8] SK hynix Ownership Structure
  - 截至 2026-04-07，SK Square 及关联方合计持股 20.5%；5% 以上股东还包括韩国国民年金 7.9%、Capital Research and Management Company 5.1%、BlackRock Fund Advisors 5.0%。
- `announcement` confidence=0.950, confirmed=True, source=[5] SK hynix Announces FY25 Financial Results
  - 公司 2025 年实现收入 97.1467 万亿韩元、营业利润 47.2063 万亿韩元、净利润 42.9479 万亿韩元，均为历史高位；4Q25 收入 32.8267 万亿韩元、营业利润 19.1696 万亿韩元。
- `business` confidence=0.900, confirmed=True, source=[3] SK hynix Fact Sheet
  - SK hynix 官方 Fact Sheet 将公司定位为 global AI memory 行业先行者，业务覆盖 HBM、eSSD、DRAM、NAND Flash 和 SSD。
- `announcement` confidence=0.900, confirmed=True, source=[12] SK hynix Begins Supply of 321-layer QLC NAND cSSD
  - 2026 年 4 月，公司开始向 Dell Technologies 供应采用 321 层 QLC NAND 的客户端 SSD PQC21，并计划扩展至更多全球客户。
- `announcement` confidence=0.880, confirmed=True, source=[6] SK hynix Reaffirms Partnership With NVIDIA at GTC 2026
  - GTC 2026 期间，公司展示 HBM4、HBM3E、SOCAMM2、LPDDR5X、PEB210 E1.S eSSD 等 AI memory 产品，并强调与 NVIDIA AI 平台的配套关系。
- `sector_logic` confidence=0.860, confirmed=True, source=[5] SK hynix Announces FY25 Financial Results
  - 2025 年业绩创纪录的直接驱动来自 AI memory 竞争力和 HBM 等高附加值产品，说明公司当前投资逻辑不只是存储周期复苏，也包含 AI 算力产业链结构性需求。
- `business` confidence=0.830, confirmed=True, source=[11] SK hynix and Sandisk Begin Global Standardization of Next-Generation Memory HBF
  - SK hynix 与 Sandisk 启动 HBF 标准化工作，HBF 被定位为 HBM 与 SSD 之间的新存储层，目标是服务 AI 推理基础设施的容量、功耗和 TCO 需求。
- `watch_item` confidence=0.780, confirmed=True, source=[11] SK hynix and Sandisk Begin Global Standardization of Next-Generation Memory HBF
  - 后续复盘重点：HBM 出货和 ASP、NVIDIA/云厂商平台绑定、eSSD 需求、AI PC 对 QLC cSSD 的拉动、HBF 是否从远期叙事进入标准和商业化里程碑。
- `risk` confidence=0.720, confirmed=True, source=[6] SK hynix Reaffirms Partnership With NVIDIA at GTC 2026
  - 需要持续跟踪 HBM 供需是否过热、主要 GPU/云客户订单节奏、NAND/DRAM 价格周期、CAPEX 扩张后的供给压力，以及技术迭代中 HBM4/定制 HBM 的认证进度。

## 个股用户心得

- `stock` tags=['AI基础设施', 'HBM', 'memory-beta', '周期风险', '分析框架']
  - 原文：海力士可以按 AI 基础设施里的核心 memory beta 理解，基本面很强，但需要警惕周期股在极高景气时的预期反转；这只是第一版分析框架，后续可以随市场和我的想法调整。
  - 摘要：用户认可将 SK 海力士作为 AI memory/HBM 核心标的和 AI 基础设施 memory beta 来分析，同时保留对周期顶部和预期反转的警惕。
- `stock` tags=['AI内存', 'HBM', '存储周期', '核心标的']
  - 原文：首次录入时先把SK海力士作为AI内存/HBM核心标的跟踪，而不是单纯当传统存储周期股看。
  - 摘要：用户希望优先从AI内存和HBM主线理解SK海力士。

## 待确认个股候选心得

- 暂无

## 相关板块知识

- 暂无

## 相关板块心得

- 暂无

## 待确认板块候选心得

- [6] `sector` tags=['HBM', '高带宽内存', 'AI基础设施', '拥挤度', '追高风险']
  - 候选：HBM/高带宽内存方向可以作为 AI 基础设施的重要主线跟踪，但如果市场交易过于拥挤，不适合无脑追高，需要结合订单兑现、估值和仓位一起判断。
  - 摘要：用户认可 HBM/高带宽内存作为 AI 基础设施主线，但希望在交易拥挤时避免无脑追高。
  - 提出原因：此前助手演示时推断生成，需用户明确确认后才能转为正式心得。

## 组合/策略级用户偏好

- 暂无

## 待确认组合/策略候选心得

- [5] `portfolio` tags=['仓位管理', '主题集中度', '拥挤交易', '风险控制']
  - 候选：单一热门主题即使基本面很强，也不应该在组合里过度集中；主题越拥挤，越需要控制仓位和留出调整空间。
  - 摘要：用户希望控制单一热门主题的组合集中度，尤其在交易拥挤时保留仓位弹性。
  - 提出原因：此前助手演示时推断生成，需用户明确确认后才能转为正式心得。

## 来源

- [3] [SK hynix Fact Sheet](https://news.skhynix.com/corporate/fact-sheet/) SK hynix Newsroom
- [5] [SK hynix Announces FY25 Financial Results](https://news.skhynix.com/sk-hynix-announces-fy25-financial-results/) SK hynix Newsroom
- [6] [SK hynix Reaffirms Partnership With NVIDIA at GTC 2026](https://news.skhynix.com/gtc-2026-exhibition-booth/) SK hynix Newsroom
- [8] [SK hynix Ownership Structure](https://m.skhynix.com/ir/UI-FR-IR04/) SK hynix IR
- [11] [SK hynix and Sandisk Begin Global Standardization of Next-Generation Memory HBF](https://news.skhynix.com/sk-hynix-and-sandisk-begin-global-standardization-ofnext-generation-memory-hbf/) SK hynix Newsroom
- [12] [SK hynix Begins Supply of 321-layer QLC NAND cSSD](https://news.skhynix.com/begin-supply-321-layer-qlc-nand-cssd/) SK hynix Newsroom
