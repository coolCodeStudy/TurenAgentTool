from __future__ import annotations

from html import escape

from investment_knowledge_mcp.web_experience import (
    render_experience_css,
    render_primary_navigation,
)


def render_page() -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Earnings Brief Studio</title>
  <style>
  {render_experience_css()}
  :root {{ --ink:#102a43; --paper:#f6f3e9; --blue:#245a9b; --red:#a7444c; }}
  body {{ margin:0; color:var(--ink); background:var(--paper); font-family:Inter,system-ui,sans-serif; }}
  .studio {{ max-width:1220px; margin:auto; padding:24px; }}
  .toolbar {{ display:flex; gap:12px; align-items:end; flex-wrap:wrap; padding:16px; background:#fff; border:1px solid #d9dfdf; border-radius:18px; }}
  label {{ display:grid; gap:6px; font-weight:700; }} select,button {{ min-height:44px; border-radius:10px; border:1px solid #b8c2c7; padding:0 14px; background:#fff; }}
  button.primary {{ color:#fff; background:var(--ink); border-color:var(--ink); font-weight:800; }}
  .brief {{ margin-top:20px; }} .masthead {{ padding:24px 8px 12px; }}
  .judgment {{ padding:22px; background:var(--ink); color:#fff; border-radius:18px; }}
  .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
  .card,.panel {{ background:#fff; border:1px solid #d9dfdf; border-radius:16px; padding:18px; }}
  .metric {{ font-size:30px; font-weight:850; }} .meta,.source-ref {{ color:#607483; font-size:13px; }}
  button.source-ref {{ min-height:32px; padding:0; border:0; background:transparent; text-decoration:underline; cursor:pointer; }}
  .source-highlight {{ outline:3px solid #c97a2b; outline-offset:4px; }}
  .section-title {{ margin:30px 0 12px; font-size:20px; }}
  .chart {{ min-height:220px; }} .bars {{ display:flex; align-items:end; gap:12px; height:180px; }}
  .bar {{ flex:1; background:var(--blue); border-radius:8px 8px 0 0; min-height:4px; position:relative; }}
  .margin-bars {{ display:flex; gap:10px; align-items:end; height:92px; margin-top:12px; }}
  .margin-bar {{ flex:1; background:#2e7d64; min-height:4px; border-radius:6px 6px 0 0; text-align:center; color:#fff; font-size:12px; }}
  .bar span {{ position:absolute; bottom:-40px; left:0; right:0; text-align:center; font-size:11px; }}
  .mix {{ display:flex; min-height:54px; border-radius:10px; overflow:hidden; }} .mix span {{ min-width:24px; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  .scenario.bull {{ border-top:5px solid #2e7d64; }} .scenario.base {{ border-top:5px solid #245a9b; }} .scenario.bear {{ border-top:5px solid #a7444c; }}
  .sources a {{ color:#174e8c; overflow-wrap:anywhere; }} [data-state]:not([data-state="available"]) {{ border-left:5px solid #c97a2b; }}
  @media (max-width:760px) {{ .studio{{padding:12px}} .grid,.two{{grid-template-columns:1fr}} .toolbar>*{{width:100%}} .metric{{font-size:25px}} }}
  </style>
</head>
<body>
{render_primary_navigation("earnings_brief_studio")}
<main class="studio">
  <section class="toolbar" aria-label="Brief selection">
    <label>公司<select id="company-select" aria-label="Company"></select></label>
    <label>报告期<select id="period-select" aria-label="Reporting period"></select></label>
    <button id="export-png" class="primary" type="button">导出 PNG</button>
    <span id="status" role="status" aria-live="polite">正在载入已审核简报…</span>
  </section>
  <article id="brief-root" class="brief" aria-busy="true"></article>
  <section id="source-drawer" class="panel sources" aria-label="来源与证据"><h2>来源与证据</h2><div id="source-list"></div></section>
</main>
<script src="/assets/earnings-brief-studio.js"></script>
</body></html>"""


def render_javascript() -> str:
    return r"""
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let current = null;
const refs = item => `<button type="button" class="source-ref" data-source-ids="${escapeHtml(item.source_ids.join(","))}">证据：${item.source_ids.length} · 截至 ${escapeHtml(item.as_of)} · ${escapeHtml(item.evidence_state)}</button>`;
const cardValue = item => item.evidence_state !== "available" ? (item.evidence_state === "not_disclosed" ? "未披露" : item.evidence_state) : (item.display || item.claim_kind);
const candidates = item => item.candidates ? `<ul>${item.candidates.map(candidate=>`<li>${escapeHtml(candidate.display)} · ${escapeHtml(candidate.as_of)} · ${escapeHtml(candidate.source_ids.join(", "))}</li>`).join("")}</ul>` : "";
const card = item => `<article class="card" data-state="${escapeHtml(item.evidence_state)}"><div>${escapeHtml(item.label)}</div><div class="metric">${escapeHtml(cardValue(item))}</div>${item.text ? `<p>${escapeHtml(item.text)}</p>` : ""}${candidates(item)}${refs(item)}</article>`;
const claimCards = items => `<div class="grid">${items.map(card).join("")}</div>`;
const section = (title, body) => `<section><h2 class="section-title">${title}</h2>${body}</section>`;
function renderBrief(data) {
  const b = data.brief; current = data;
  const max = Math.max(...b.quarterly_trends.map(x => Number(x.value)));
  const bars = b.quarterly_trends.map(x => `<div class="bar" style="height:${Math.max(8, Number(x.value)/max*150)}px" title="${escapeHtml(x.label)} ${escapeHtml(x.display)}"><span>${escapeHtml(x.label)}<br>${escapeHtml(x.display)}</span></div>`).join("");
  const marginMin = Math.min(...b.gross_margin_trends.map(x=>Number(x.value))) - 2;
  const marginBars = b.gross_margin_trends.map(x=>`<div class="margin-bar" style="height:${Math.max(12,(Number(x.value)-marginMin)*24)}px" title="${escapeHtml(x.label)} ${escapeHtml(x.display)}">${escapeHtml(x.display)}</div>`).join("");
  const total = b.revenue_mix.reduce((sum,x) => sum + Number(x.value), 0);
  const mix = b.revenue_mix.map((x,i) => `<span style="flex:${Number(x.value)};background:${["#173f69","#2c65a8","#668cb7","#9bb5ca","#c7d2d8"][i]}" title="${escapeHtml(x.label)} ${escapeHtml(x.display)}"></span>`).join("");
  const flow = b.financial_flow, byId = new Map(b.kpis.map(item => [item.id,item]));
  $("#brief-root").innerHTML = `
    <header class="masthead"><div>${escapeHtml(b.company.name)} · ${escapeHtml(b.company.ticker)}</div><h1>${escapeHtml(b.reporting_period.label)} 业绩简报</h1><div class="meta">生成于 ${escapeHtml(b.generated_at)} · 证据截至 ${escapeHtml(b.evidence_as_of)} · ${escapeHtml(data.release.release_id)}</div></header>
    <section class="judgment" data-state="${escapeHtml(b.judgment.evidence_state)}"><strong>核心判断</strong><h2>${escapeHtml(b.judgment.text)}</h2>${refs(b.judgment)}</section>
    ${section("01 核心业绩", claimCards(b.kpis))}
    ${section("管理层信号", claimCards(b.management_signals))}
    ${section("02 收入与利润流", `<div class="panel chart"><div class="grid"><div><b>营业收入</b><div class="metric">${escapeHtml(byId.get(flow.revenue_id).display)}</div>${refs(byId.get(flow.revenue_id))}</div><div><b>毛利润</b><div class="metric">${escapeHtml(byId.get(flow.gross_profit_id).display)}</div>${refs(byId.get(flow.gross_profit_id))}</div><div><b>净利润</b><div class="metric">${escapeHtml(byId.get(flow.net_income_id).display)}</div>${refs(byId.get(flow.net_income_id))}</div></div><p>收入 → 销售成本 ${escapeHtml(byId.get(flow.cost_of_sales_id).display)} → 经营费用 ${escapeHtml(byId.get(flow.operating_expenses_id).display)} → 净利润</p>${refs(byId.get(flow.cost_of_sales_id))} ${refs(byId.get(flow.operating_expenses_id))}</div>`)}
    ${section("03 趋势与结构", `<div class="two"><div class="panel chart"><h3>季度收入趋势</h3><div class="bars">${bars}</div><h3>毛利率趋势</h3><div class="margin-bars">${marginBars}</div><ul>${b.gross_margin_trends.map(x=>`<li>${escapeHtml(x.label)} 毛利率 · ${escapeHtml(x.display)}</li>`).join("")}</ul></div><div class="panel chart"><h3>收入结构</h3><div class="mix">${mix}</div><ul>${b.revenue_mix.map(x=>`<li>${escapeHtml(x.label)} · ${escapeHtml(x.display)}</li>`).join("")}</ul></div></div>`)}
    ${section("04 市场焦点", claimCards(b.market_focus))}
    ${section("结构性信号", claimCards(b.structural_signals))}
    ${section("05 前瞻情景", `<div class="grid">${b.scenarios.map(x=>`<article class="card scenario ${escapeHtml(x.kind)}"><b>${escapeHtml(x.label)}</b><p>${escapeHtml(x.summary)}</p><ul>${x.validation_conditions.map(c=>`<li>${escapeHtml(c)}</li>`).join("")}</ul></article>`).join("")}</div>`)}
  `;
  $("#source-list").innerHTML = b.sources.map(s => `<article id="${escapeHtml(s.source_id)}" data-source-id="${escapeHtml(s.source_id)}"><h3>${escapeHtml(s.document_title)}</h3><p>${escapeHtml(s.publisher)} · ${escapeHtml(s.family)} · ${escapeHtml(s.tier)} · ${escapeHtml(s.publication_date)}</p><p>${escapeHtml(s.locator)}</p><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">打开官方来源</a></article>`).join("");
  document.querySelectorAll("[data-source-ids]").forEach(button => button.addEventListener("click", () => {document.querySelectorAll(".source-highlight").forEach(node=>node.classList.remove("source-highlight"));const targets=button.dataset.sourceIds.split(",").map(sourceId=>document.querySelector(`[data-source-id="${CSS.escape(sourceId)}"]`)).filter(Boolean);targets.forEach(target=>target.classList.add("source-highlight"));if(targets[0])targets[0].scrollIntoView({behavior:"smooth",block:"center"})}));
  $("#brief-root").setAttribute("aria-busy","false"); $("#status").textContent = "已载入审核版本";
}
async function loadCatalog() {
  const catalog = await fetch("/api/earnings-briefs").then(r => r.json());
  $("#company-select").innerHTML = catalog.catalog.map(x=>`<option value="${escapeHtml(x.company_id)}">${escapeHtml(x.company_name)} (${escapeHtml(x.ticker)})</option>`).join("");
  $("#period-select").innerHTML = catalog.catalog.map(x=>`<option value="${escapeHtml(x.period_id)}">${escapeHtml(x.period_label)}</option>`).join("");
  const query = new URLSearchParams({company_id:$("#company-select").value,period_id:$("#period-select").value});
  renderBrief(await fetch(`/api/earnings-brief?${query}`).then(r=>r.json()));
}
const wrap = (ctx,text,x,y,maxWidth,lineHeight) => { const value=String(text), words=/\s/.test(value)?value.split(/\s+/):Array.from(value); let line=""; for(const word of words){const separator=/\s/.test(value)&&line?" ":"";const test=`${line}${separator}${word}`;if(ctx.measureText(test).width>maxWidth&&line){ctx.fillText(line,x,y);y+=lineHeight;line=word}else line=test}if(line){ctx.fillText(line,x,y);y+=lineHeight}return y;};
function exportPng() {
  if (!current) return;
  const b=current.brief, width=1440, height=12000;
  const canvas=document.createElement("canvas"); canvas.width=width; canvas.height=height;
  const ctx=canvas.getContext("2d"); ctx.fillStyle="#f6f3e9";ctx.fillRect(0,0,width,height);ctx.fillStyle="#102a43";
  let y=90;ctx.font="700 28px system-ui";ctx.fillText(`${b.company.name} · ${b.company.ticker}`,70,y);y+=64;ctx.font="850 52px system-ui";ctx.fillText(`${b.reporting_period.label} 业绩简报`,70,y);y+=52;ctx.font="22px system-ui";ctx.fillText(`生成于 ${b.generated_at} · 证据截至 ${b.evidence_as_of} · ${current.release.release_id}`,70,y);
  y+=45;ctx.fillStyle="#102a43";ctx.fillRect(55,y,1330,250);ctx.fillStyle="#fff";ctx.font="700 23px system-ui";ctx.fillText("核心判断",85,y+48);ctx.font="700 32px system-ui";wrap(ctx,b.judgment.text,85,y+100,1260,44);y+=300;
  const drawTitle=t=>{ctx.fillStyle="#102a43";ctx.font="800 28px system-ui";ctx.fillText(t,70,y);y+=48;};
  drawTitle("核心业绩"); for(const item of b.kpis){ctx.fillStyle="#fff";ctx.fillRect(70,y,1300,78);ctx.fillStyle="#102a43";ctx.font="20px system-ui";ctx.fillText(`${item.label} · ${item.evidence_state} · ${item.as_of} · ${item.source_ids.length} source(s)`,95,y+30);ctx.font="800 30px system-ui";ctx.fillText(item.display||item.evidence_state,650,y+66);y+=92}
  drawTitle("管理层信号");for(const item of b.management_signals){ctx.font="20px system-ui";y=wrap(ctx,`${item.label} [${item.evidence_state} · ${item.as_of}]：${item.text}`,90,y,1250,30)+18}
  drawTitle("收入与利润流");const flow=b.financial_flow,byId=new Map(b.kpis.map(item=>[item.id,item]));y=wrap(ctx,`收入 ${byId.get(flow.revenue_id).display} → 销售成本 ${byId.get(flow.cost_of_sales_id).display} → 毛利润 ${byId.get(flow.gross_profit_id).display} → 经营费用 ${byId.get(flow.operating_expenses_id).display} → 净利润 ${byId.get(flow.net_income_id).display}`,90,y,1250,34)+24;
  drawTitle("趋势与结构");ctx.fillStyle="#245a9b";const max=Math.max(...b.quarterly_trends.map(x=>Number(x.value)));for(const [i,item] of b.quarterly_trends.entries()){const h=Number(item.value)/max*210;ctx.fillRect(110+i*290,y+240-h,180,h);ctx.fillStyle="#102a43";ctx.font="18px system-ui";ctx.fillText(`${item.label} ${item.display}`,100+i*290,y+275);ctx.fillStyle="#245a9b"}y+=320;ctx.fillStyle="#102a43";y=wrap(ctx,`毛利率：${b.gross_margin_trends.map(x=>`${x.label} ${x.display}`).join(" · ")}`,90,y,1250,30)+20;y=wrap(ctx,`收入结构：${b.revenue_mix.map(x=>`${x.label} ${x.display}`).join(" · ")}`,90,y,1250,30)+20;
  drawTitle("市场焦点 vs 结构性信号");for(const item of [...b.market_focus,...b.structural_signals]){ctx.fillStyle="#102a43";ctx.font="20px system-ui";y=wrap(ctx,`${item.label}：${item.text}`,90,y,1250,30)+15}
  drawTitle("前瞻情景");for(const item of b.scenarios){ctx.font="800 24px system-ui";ctx.fillText(item.label,90,y);ctx.font="20px system-ui";y=wrap(ctx,item.summary,230,y,1100,30)+10;for(const condition of item.validation_conditions)y=wrap(ctx,`• ${condition}`,230,y,1100,28);y+=20}
  drawTitle("来源与证据");for(const source of b.sources){ctx.font="18px system-ui";y=wrap(ctx,`${source.publisher} · ${source.family} · ${source.tier} · ${source.publication_date} · ${source.locator} · ${source.url}`,90,y,1250,26)+12}
  if(y+70>height)throw new Error("export_content_exceeds_bound");const out=document.createElement("canvas");out.width=width;out.height=Math.ceil(y+70);out.getContext("2d").drawImage(canvas,0,0,width,out.height,0,0,width,out.height);
  const downloadCanvas = canvas => {const a=document.createElement("a");a.href=canvas.toDataURL("image/png");a.download=`${b.company.ticker}-${b.reporting_period.period_id}-earnings-brief-${current.release.release_id.split(":").pop()}.png`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>a.remove(),1000)};
  downloadCanvas(out);
}
$("#export-png").addEventListener("click",exportPng);
loadCatalog().catch(()=>{$("#status").textContent="简报载入失败，请重试";$("#brief-root").setAttribute("aria-busy","false")});
"""
