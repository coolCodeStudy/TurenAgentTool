# AI Industry Panorama V1 Source Review

## Review status

- Artifact reviewed: `docs/changes/ai-industry-panorama/v1-source-manifest.md` at commit `9162248`
- Reviewer: `/root/panorama_source_review`
- Review date: `2026-07-24`
- Retrieval date: `2026-07-24`
- Scope: all 16 source records and all 45 relationship/assertion/evidence rows
- Final verdict: `correction_required`
- Publication and product status: this review does not mark publication, user acceptance, implementation completion, or feature completion.

## Methodology

1. Read the PRD, V1 technical plan, and source manifest from commit `9162248`.
2. Opened only the 16 direct official URLs listed in the manifest. No search-result page, aggregator, journalism, secondary research, or newly discovered source was used as evidence.
3. Checked source URL reachability, official publisher identity, displayed title, displayed publication/filing date where available, and the named locator.
4. Reviewed each row for source and target identity, canonical direction, relationship type, exact assertion, assertion kind, lifecycle, valid time, geography/role, confidence cap, limitation, and inference premise IDs.
5. Applied these verdicts:
   - `accepted`: the listed source and locator support the complete row without a material correction.
   - `correction_required`: the relationship is potentially usable, but one or more fields must be corrected before implementation.
   - `rejected`: the relationship is unsupported by the listed official source and cannot be repaired by narrowing or correcting the row.
6. Treated year-only or month-only timing as lower precision than a full date; a first-day normalization is not accepted unless the row explicitly records that normalization and its uncertainty.
7. Kept every source-backed confidence label capped at `medium` because each row has a single primary publication path. The derived Meta row remains `inference`.

## Official URL checks

All 16 listed URLs were reachable at review time and resolved to the stated official publisher. Thirteen source records had a locator that matched the live content without a source-record correction. Three require locator/content corrections: `SRC-007`, `SRC-013`, and `SRC-016`.

| Source ID | Official URL and metadata result | Locator result |
| --- | --- | --- |
| SRC-001 | [Alphabet Investor Relations](https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx); title and `2026-02-04` date displayed | CapEx, technical-infrastructure mix, and NVIDIA paragraphs found |
| SRC-002 | [Microsoft Investor Relations](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3); title and `2026-04-29` date displayed | Fairwater, Q3 asset mix, Q4 capacity outlook, and calendar-2026 CapEx paragraphs found |
| SRC-003 | [Meta Investor Relations](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-First-Quarter-2026-Results/); title and `2026-04-29` date displayed | Q1 CapEx and CFO outlook paragraphs found |
| SRC-004 | [SEC / Amazon 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm); issuer, form, period, and accession valid | Item 7 cash CapEx and technology/infrastructure cost definitions found on the cited printed pages |
| SRC-005 | [Amazon Investor Relations](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/default.aspx); title and `2026-04-29` date displayed | Custom silicon, OpenAI, and Anthropic bullets found |
| SRC-006 | [Corning](https://www.corning.com/worldwide/en/about-us/news-events/news-releases/2026/06/amazon-announces-agreement-with-corning-to-boost-us-fiber-optics-manufacturing-creating-1000-advanced-manufacturing-jobs-in-north-carolina.html); title and `2026-06-08` date displayed | Multiyear agreement, U.S. geography, and optical product scope found |
| SRC-007 | [OpenAI five-site Stargate announcement](https://openai.com/index/five-new-stargate-sites/); title and original `2025-09-23` date displayed | Page also displays an `2025-10-22` update. Manifest locator phrases do not match the current text, and the page does not use the name `Stargate I` |
| SRC-008 | [OpenAI Oracle/Stargate announcement](https://openai.com/index/stargate-advances-with-partnership-with-oracle/); title and `2025-07-22` date displayed | 4.5 GW, `Stargate I`, partial operation, rack delivery, and early-workload text found; this page does not say the site “runs on OCI” |
| SRC-009 | [Anthropic](https://www.anthropic.com/news/google-broadcom-partnership-compute); title and `2026-04-06` date displayed | Google, Broadcom, 2027 TPU capacity, Amazon/AWS, and NVIDIA text found |
| SRC-010 | [SEC / NVIDIA 2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm); issuer, form, accession, and `2026-02-25` filing/signature date valid | Company/platform and Manufacturing locators found |
| SRC-011 | [TSMC 2025 Annual Report, Chapter 5 PDF](https://investor.tsmc.com/static/annualReports/2025/english/pdf/2025_tsmc_ar_e_ch5.pdf); official PDF and chapter identity valid | Printed pp. 102-104 contain CoWoS/HBM and variant-specific volume-production text |
| SRC-012 | [SK hynix FY2025 results](https://news.skhynix.com/en/sk-hynix-announces-fy25-financial-results/); title and `2026-01-28` date displayed | HBM4 large-scale-production paragraph found |
| SRC-013 | [SK hynix HBM4E media page](https://news.skhynix.com/en/12-layer-hbm4e-sample-1/); title and `2026-06-18` date displayed | Direct page is an image/video entry with an empty text description. The claimed “News Highlights” and opening paragraph, including “major customers,” are absent from the listed URL |
| SRC-014 | [ASML 2025 Annual Report financials](https://www.asml.com/en/investors/annual-report/2025/financials); official annual-report page valid | Complete R&D bullet list found |
| SRC-015 | [Schneider Electric](https://www.se.com/ww/en/about-us/newsroom/news/press-releases/schneider-electric-teams-with-nvidia-to-develop-validated-blueprints-to-design-simulate-build-operate-and-maintain-gigawattscale-ai-factories-69b82397e7fa28870e0cd5a3/); title and `2026-03-16` date displayed | Co-developed Vera Rubin reference design and power/cooling text found; `liquid-cooling infrastructure` is not stated on the listed page |
| SRC-016 | [Open Compute Project Foundation](https://www.opencompute.org/community/open-data-centers-for-ai); undated current official page | Scope text found, but the current page says `Power Estimation Methodologies`, not `capacity planning` |

## Relationship and assertion verdicts

| Row ID | Verdict | Review finding |
| --- | --- | --- |
| REL-AIP-0001 | accepted | Alphabet source, direction, guidance kind, committed lifecycle, 2026 interval, global role, medium cap, and limitation are supported. |
| REL-AIP-0002 | correction_required | The 2025 server/machine investment mix is supported, but `operating` is not an evidenced asset lifecycle; use `unknown` or a non-capacity realized-spend lifecycle. |
| REL-AIP-0003 | correction_required | The 2025 data-center/networking investment mix is supported, but the source does not establish that the combined assets were operating; correct lifecycle to `unknown` or a realized-spend state. |
| REL-AIP-0004 | accepted | Alphabet explicitly names partner NVIDIA GPUs alongside its TPUs. Identity, direction, current use, medium cap, and limitations are sound. |
| REL-AIP-0005 | correction_required | The source says **calendar year 2026**, not Microsoft fiscal year 2026. Correct the assertion and interval to `2026-01-01` through `2026-12-31`. |
| REL-AIP-0006 | correction_required | Fairwater came online sometime earlier in April 2026, but the exact day is not disclosed. Do not assert `valid_from=2026-04-01` as an exact start without a month-precision qualifier. |
| REL-AIP-0007 | correction_required | The site-level operating-capacity interpretation is bounded, but its exact start date repeats the unsupported `2026-04-01` precision. Record month-level or unknown-day timing. |
| REL-AIP-0008 | correction_required | The row combines an observed Q3 CapEx mix with a separate forward/current effort to bring GPU, CPU, and storage capacity online. Split the statements or narrow to the Q3 GPU/CPU CapEx fact; do not label the combined claim `operating` for the Q3 interval. |
| REL-AIP-0009 | accepted | Meta's 2026 range, guidance kind, committed lifecycle, period, medium cap, and forward-looking limitation are supported. |
| REL-AIP-0010 | accepted | Meta explicitly connects additional 2026 data-center costs with future-year capacity. No site, supplier, or operating capacity is inferred. |
| REL-AIP-0011 | correction_required | Premises `AST-AIP-0010` and `AST-AIP-0045` are valid and the row remains inference, but `United States` is unsupported and “buildout” is stronger than Meta's disclosed “additional data center costs.” Use unknown/global geography and premise-faithful wording. |
| REL-AIP-0012 | correction_required | The 2025 cash CapEx fact is supported, but `operating` is not a lifecycle established for the investment relationship; use `unknown` or a realized-spend state. |
| REL-AIP-0013 | correction_required | Amazon's filing defines shared infrastructure costs, but it does not directly establish the `develops_or_operates` relationship to capacity. Use `depends_on` or narrow the edge to a disclosed infrastructure-cost/capability relationship. |
| REL-AIP-0014 | accepted | Amazon names the three chip families and its continuing custom-silicon capability. Kind, lifecycle, time, geography, cap, and limitation are valid. |
| REL-AIP-0015 | correction_required | Commitment and approximate 2 GW are supported, but only the start year `2027` is known. Record year precision instead of implying January 1, and use `unknown` geography rather than `global/United States not specified`. |
| REL-AIP-0016 | correction_required | The upper-bound 5 GW commitment is supported, but geography is not disclosed. Replace `global/United States not specified` with explicit `unknown`; keep `up to`, committed lifecycle, and current/future qualifier. |
| REL-AIP-0017 | accepted | The Corning-hosted announcement names Amazon, Corning, the multiyear agreement, products, and U.S. use. Canonical buyer-to-supplier direction and medium cap are appropriate. |
| REL-AIP-0018 | accepted | Optical fiber, cable, connectivity scope, U.S./North Carolina role, committed lifecycle, and limitations are supported. |
| REL-AIP-0019 | correction_required | Platform identity and ongoing development are supported, but `valid_from=2025-01-21` is not established by `SRC-007`, and the named locator text is stale on the updated live page. Use the observed announcement date or a supported lower-precision start and update the locator. |
| REL-AIP-0020 | accepted | OpenAI and Oracle, additional 4.5 GW, U.S. geography, committed lifecycle, forward-capacity limitation, and medium cap are supported. |
| REL-AIP-0021 | accepted | OpenAI and SoftBank are explicitly named as partners developing multiple U.S. sites. Direction, lifecycle, time, and limitation are sound. |
| REL-AIP-0022 | correction_required | `SRC-007` supports the Abilene flagship's operating status but does not call it `Stargate I` or say “parts” were running. Cite `SRC-008` for the `Stargate I` name and partial status, or narrow the assertion and target identity to what `SRC-007` says. |
| REL-AIP-0023 | correction_required | `SRC-008` supports Oracle rack delivery at Stargate I but does not say the site runs on OCI. Add `SRC-007` for the OCI clause or remove that clause; preserve the one-party-announcement limitation. |
| REL-AIP-0024 | accepted | First NVIDIA GB200 rack delivery to Stargate I is explicit. Direction, operating/partial-site context, geography, cap, and delivery limitation are valid. |
| REL-AIP-0025 | accepted | Partial operation and early training/inference workloads are explicit, and the limitation correctly blocks full-site capacity or service-level inference. |
| REL-AIP-0026 | correction_required | The source names **Google** and later **Google Cloud**, not Alphabet. Do not normalize this counterparty to the parent. Create/use a Google or Google Cloud entity and point the relationship to it. |
| REL-AIP-0027 | accepted | Anthropic explicitly names Broadcom in the signed next-generation TPU agreement. The row does not infer manufacturing, revenue, or share. |
| REL-AIP-0028 | correction_required | Multiple-GW TPU capacity and expected 2027 start are supported, but the exact start day is unknown. Preserve year-level precision instead of treating January 1 as a disclosed effective date. |
| REL-AIP-0029 | accepted | Anthropic explicitly calls Amazon its primary cloud provider and training partner and names AWS Trainium. Parent identity is also named by the source. |
| REL-AIP-0030 | accepted | Anthropic explicitly says Claude runs on NVIDIA GPUs. Current dependency, global role, medium cap, and limitations are supported. |
| REL-AIP-0031 | accepted | NVIDIA's filing supports its co-designed data-center stack and interconnected GPUs for training/inference. Capability direction and management-claim classification are sound. |
| REL-AIP-0032 | accepted | NVIDIA explicitly names TSMC as a foundry producing its wafers. Supplier-to-customer direction, operating lifecycle, Asia/global role, and limitations are valid. |
| REL-AIP-0033 | accepted | NVIDIA explicitly names Samsung as a foundry producing its wafers. Supplier-to-customer direction, operating lifecycle, Asia/global role, and limitations are valid. |
| REL-AIP-0034 | accepted | NVIDIA explicitly says it purchases memory from SK hynix. The assertion correctly avoids HBM generation, quantity, share, and revenue inference. |
| REL-AIP-0035 | accepted | NVIDIA explicitly says it purchases memory from Micron. The assertion correctly avoids HBM generation, quantity, share, and revenue inference. |
| REL-AIP-0036 | accepted | NVIDIA explicitly says it uses CoWoS for semiconductor packaging without naming a provider. Capability direction, medium cap, and limitation are correct. |
| REL-AIP-0037 | correction_required | TSMC's source supports CoWoS integration and **variant-specific** volume production (CoWoS-S, CoWoS-R, and CoWoS-L). Rewrite “reports it in volume production” to identify the variants and avoid implying every CoWoS configuration shares one lifecycle. |
| REL-AIP-0038 | correction_required | The source supports HBM as an input to the described CoWoS configuration, but the endpoints broaden that into all advanced packaging and a combined memory/storage capability. Use a CoWoS-specific source node and HBM-specific target, or a narrower relationship type/text that cannot be read as applying to all advanced packaging or storage. |
| REL-AIP-0039 | accepted | SK hynix explicitly states that large-scale HBM4 production was underway. Mass-production lifecycle, time, medium cap, and unnamed-customer limitation are supported. |
| REL-AIP-0040 | correction_required | The direct page supports the title-level claim that SK hynix shipped samples of 12-layer HBM4E, but the listed URL contains no “News Highlights,” opening paragraph, or “major customers” text. Narrow to the title-level claim and locator, or replace the evidence with a separately reviewed official text source. |
| REL-AIP-0041 | accepted | ASML's R&D bullets support NXE/EXE development, future Logic/DRAM nodes for EXE, next-generation lithography, XT:260 packaging investment, and inspection/metrology. Under-development lifecycle and medium cap are conservative. |
| REL-AIP-0042 | accepted | Schneider explicitly says the Vera Rubin reference design was co-developed with NVIDIA and validates power/cooling. `qualification` is acceptable only as design validation, and the limitation correctly excludes deployment or purchase. |
| REL-AIP-0043 | correction_required | The listed Schneider page says power and cooling, 480 VAC distribution, TCS loop temperature, layout, and airflow, but not `liquid-cooling infrastructure`. Remove `liquid-` or cite a separately reviewed listed source that states it. |
| REL-AIP-0044 | correction_required | The current OCP page supports reference designs, open SLAs, telemetry/management, power estimation, and advanced power/cooling, but not the manifest phrase `capacity planning`. Replace it with `power estimation methodologies` and update the locator. |
| REL-AIP-0045 | accepted | OCP explicitly treats advanced power/cooling as reference-design scope and securing power as the primary bottleneck. Generic scope, unknown lifecycle/time, global geography, medium cap, and limitations are valid. |

## Required corrections

Before implementation, correct these row groups:

- Lifecycle or time precision: `REL-AIP-0002`, `REL-AIP-0003`, `REL-AIP-0005`, `REL-AIP-0006`, `REL-AIP-0007`, `REL-AIP-0008`, `REL-AIP-0012`, `REL-AIP-0015`, `REL-AIP-0028`.
- Geography or premise-faithful inference wording: `REL-AIP-0011`, `REL-AIP-0015`, `REL-AIP-0016`.
- Relationship identity or type: `REL-AIP-0013`, `REL-AIP-0026`, `REL-AIP-0038`.
- Source/locator mismatch: `REL-AIP-0019`, `REL-AIP-0022`, `REL-AIP-0023`, `REL-AIP-0040`, `REL-AIP-0044`.
- Capability or lifecycle overbreadth: `REL-AIP-0037`, `REL-AIP-0038`, `REL-AIP-0043`.

Rows that appear in more than one group require all listed corrections. After correction, every affected source/assertion pair must be re-reviewed; acceptance of an unaffected row does not publish it.

## Unsupported and uncertain notes

- `SRC-007` is a mutable live page with an explicit October 22, 2025 update. Its original September 23 publication date is valid, but the evidence implementation needs a content fingerprint and a locator matching the retrieved version.
- `SRC-013` is reachable and official, but its direct HTML is an image/video entry with no text body. The manifest's paragraph-level locator and “major customers” detail are therefore unsupported by the listed URL.
- `SRC-011` and `SRC-014` identify the 2025 annual reports, but the reviewed chapter/page content does not itself display the manifest's precise web-publication date. Preserve the annual-report identity and treat that date as source metadata rather than assertion-effective time.
- Month-only and year-only operating/availability statements must not silently become exact first-day dates. Store explicit precision or include a limitation.
- `Google` or `Google Cloud` cannot be normalized to `Alphabet` when the third-party source names the subsidiary/service counterparty and the parent is not the named party.
- One-party announcements remain capped at `medium` even when a named executive of the counterparty is quoted in the same publisher-hosted release.
- No source-backed row should be upgraded above `medium` solely because this review was completed. Independent corroboration and the release confidence derivation remain separate concerns.

## Count summary

| Verdict | Count |
| --- | ---: |
| accepted | 24 |
| correction_required | 21 |
| rejected | 0 |
| total | 45 |

Source URL summary:

- Reachable official URLs: 16
- Unreachable official URLs: 0
- Source records with locator/content correction needed: 3 (`SRC-007`, `SRC-013`, `SRC-016`)

## Final verdict

`correction_required`

The manifest must not be marked `reviewed_for_implementation` at commit `9162248`. Correct the 21 affected rows and re-run an independent row-level review. This document does not change any manifest review state, release state, user-acceptance state, or feature-completion state.
