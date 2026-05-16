# SK海力士 研究草稿审阅

## 确认状态

- [ ] 我已确认股票画像可以入库
- [ ] 我已确认板块归属可以入库
- [ ] 我已确认事实知识和来源匹配
- [ ] 我已确认用户心得代表我的观点

## 股票画像

- 代码：000660
- 市场：KR
- 名称：SK海力士
- 核心业务：SK hynix 是韩国存储半导体公司，核心业务覆盖 DRAM、HBM、NAND Flash 和 SSD。当前投资主线集中在 AI 服务器所需的高带宽内存 HBM、企业级 SSD，以及面向 AI PC 和客户端市场的 NAND/SSD 产品。
- 股权结构：截至 2026-04-07，SK Square 及关联方合计持有 146,118,388 股，占 20.5%，为主要股东；截至相关披露，韩国国民年金持股 7.9%，Capital Research and Management Company 持股 5.1%，BlackRock Fund Advisors 持股 5.0%。
- 股性：强周期科技成长股，股价通常受 DRAM/NAND 景气、HBM 供需、AI 算力资本开支、主要客户认证与订单、韩元汇率和半导体周期预期共同驱动。当前更偏 AI memory / HBM 龙头叙事，但仍保留存储周期股的高波动属性。
- 突出历史：2024 年公司量产世界首款 12 层 HBM3E，并量产 321 层 NAND Flash。2025 年实现历史最高年度业绩。2026 年在 GTC 展示 HBM4、SOCAMM2、定制 HBM 等 AI memory 产品组合，并与 Sandisk 推动 HBF 标准化。

## 板块归属

- `main` 科技 > 半导体 > 存储芯片 > DRAM/HBM (confidence=0.92, source=fact_sheet)
  - 描述：公司核心业务之一，HBM 是当前 AI 服务器内存的关键品类，也是公司高价值产品和利润弹性的主要来源。
  - 近况：AI memory 需求强劲，SK hynix 在官方资料中强调 HBM 和企业级 SSD 领导力，并在 GTC 2026 展示 HBM4 和定制 HBM。
- `main` 科技 > 半导体 > 存储芯片 > NAND/SSD (confidence=0.86, source=fact_sheet)
  - 描述：公司生产 NAND Flash，并提供企业级、客户端和消费级 SSD，是 DRAM/HBM 之外的重要业务线。
  - 近况：2026 年 4 月，公司开始供应采用 321 层 QLC NAND 的客户端 SSD PQC21，强调 AI PC 存储需求。
- `theme` AI基础设施 > AI服务器供应链 > 高带宽内存 (confidence=0.9, source=gtc_2026)
  - 描述：HBM、SOCAMM、LPDDR 和企业级 SSD 均围绕 AI 训练与推理基础设施展开，和 NVIDIA 等 GPU 平台生态高度相关。
  - 近况：GTC 2026 展示 NVIDIA Vera Rubin 200 搭配 SK hynix SOCAMM2 和 HBM4，强化 AI 平台配套逻辑。

## 事实知识

- `business` (confidence=0.9, source=fact_sheet)
  - SK hynix 官方 Fact Sheet 将公司定位为 global AI memory 行业先行者，业务覆盖 HBM、eSSD、DRAM、NAND Flash 和 SSD。
- `equity_structure` (confidence=0.95, source=ownership)
  - 截至 2026-04-07，SK Square 及关联方合计持股 20.5%；5% 以上股东还包括韩国国民年金 7.9%、Capital Research and Management Company 5.1%、BlackRock Fund Advisors 5.0%。
- `announcement` (confidence=0.95, source=fy25_results)
  - 公司 2025 年实现收入 97.1467 万亿韩元、营业利润 47.2063 万亿韩元、净利润 42.9479 万亿韩元，均为历史高位；4Q25 收入 32.8267 万亿韩元、营业利润 19.1696 万亿韩元。
- `sector_logic` (confidence=0.86, source=fy25_results)
  - 2025 年业绩创纪录的直接驱动来自 AI memory 竞争力和 HBM 等高附加值产品，说明公司当前投资逻辑不只是存储周期复苏，也包含 AI 算力产业链结构性需求。
- `announcement` (confidence=0.88, source=gtc_2026)
  - GTC 2026 期间，公司展示 HBM4、HBM3E、SOCAMM2、LPDDR5X、PEB210 E1.S eSSD 等 AI memory 产品，并强调与 NVIDIA AI 平台的配套关系。
- `business` (confidence=0.83, source=hbf_standard)
  - SK hynix 与 Sandisk 启动 HBF 标准化工作，HBF 被定位为 HBM 与 SSD 之间的新存储层，目标是服务 AI 推理基础设施的容量、功耗和 TCO 需求。
- `announcement` (confidence=0.9, source=qlc_cssd)
  - 2026 年 4 月，公司开始向 Dell Technologies 供应采用 321 层 QLC NAND 的客户端 SSD PQC21，并计划扩展至更多全球客户。
- `risk` (confidence=0.72, source=gtc_2026)
  - 需要持续跟踪 HBM 供需是否过热、主要 GPU/云客户订单节奏、NAND/DRAM 价格周期、CAPEX 扩张后的供给压力，以及技术迭代中 HBM4/定制 HBM 的认证进度。
- `watch_item` (confidence=0.78, source=hbf_standard)
  - 后续复盘重点：HBM 出货和 ASP、NVIDIA/云厂商平台绑定、eSSD 需求、AI PC 对 QLC cSSD 的拉动、HBF 是否从远期叙事进入标准和商业化里程碑。

## 用户心得

- 暂无

## 来源

- `fact_sheet` [SK hynix Fact Sheet](https://news.skhynix.com/corporate/fact-sheet/) - SK hynix Newsroom
- `ownership` [SK hynix Ownership Structure](https://m.skhynix.com/ir/UI-FR-IR04/) - SK hynix IR
- `fy25_results` [SK hynix Announces FY25 Financial Results](https://news.skhynix.com/sk-hynix-announces-fy25-financial-results/) - SK hynix Newsroom
- `gtc_2026` [SK hynix Reaffirms Partnership With NVIDIA at GTC 2026](https://news.skhynix.com/gtc-2026-exhibition-booth/) - SK hynix Newsroom
- `hbf_standard` [SK hynix and Sandisk Begin Global Standardization of Next-Generation Memory HBF](https://news.skhynix.com/sk-hynix-and-sandisk-begin-global-standardization-ofnext-generation-memory-hbf/) - SK hynix Newsroom
- `qlc_cssd` [SK hynix Begins Supply of 321-layer QLC NAND cSSD](https://news.skhynix.com/begin-supply-321-layer-qlc-nand-cssd/) - SK hynix Newsroom

## 确认后导入

确认无误后运行：

```bash
python scripts/import_research_draft.py drafts/000660_KR_research_draft.enriched.json --confirmed
```

如果不确认，请直接修改原 JSON，再重新运行：

```bash
python scripts/validate_research_draft.py drafts/000660_KR_research_draft.enriched.json
python scripts/review_research_draft.py drafts/000660_KR_research_draft.enriched.json
```
