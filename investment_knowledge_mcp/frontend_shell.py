from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Literal


NavKey = Literal["weekly-review", "command"]


@dataclass(frozen=True)
class NavItem:
    key: NavKey
    label: str
    href: str


@dataclass(frozen=True)
class ShellPage:
    title: str
    lang: str
    active_nav: NavKey
    page_class: str
    heading: str
    subtitle: str
    main_html: str
    aside_html: str = ""
    page_css: str = ""
    page_js: str = ""


def shared_nav_items() -> list[NavItem]:
    return [
        NavItem(key="weekly-review", label="Weekly Review", href="/weekly-review"),
        NavItem(key="command", label="Command Workbench", href="/command"),
    ]


def shared_design_tokens_css() -> str:
    return """
    :root {
      color-scheme: light;
      --app-bg: #f6f7f9;
      --app-surface: #ffffff;
      --app-surface-muted: #f0f3f6;
      --app-ink: #20242a;
      --app-muted: #627083;
      --app-line: #d8e0e8;
      --app-accent: #176b6f;
      --app-accent-strong: #145f63;
      --app-accent-soft: #e5f2f1;
      --app-good: #176b43;
      --app-bad: #a33b35;
      --app-warn: #8a5a00;
      --app-warn-bg: #fff7df;
      --app-focus: #254edb;
      --app-radius: 6px;
      --app-space-1: 4px;
      --app-space-2: 8px;
      --app-space-3: 12px;
      --app-space-4: 16px;
      --app-space-5: 24px;
    }
    """


def shared_base_css() -> str:
    return """
    * { box-sizing: border-box; }
    html { min-width: 0; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--app-bg);
      color: var(--app-ink);
    }
    a { color: inherit; }
    a:focus-visible,
    button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    textarea:focus-visible,
    summary:focus-visible {
      outline: 3px solid var(--app-focus);
      outline-offset: 2px;
    }
    .skip-link {
      position: fixed;
      top: var(--app-space-3);
      left: var(--app-space-3);
      z-index: 20;
      transform: translateY(-160%);
      border: 1px solid var(--app-focus);
      border-radius: var(--app-radius);
      background: var(--app-surface);
      color: var(--app-focus);
      padding: var(--app-space-2) var(--app-space-3);
      font-weight: 700;
      text-decoration: none;
    }
    .skip-link:focus { transform: translateY(0); }
    .app-shell { min-height: 100vh; }
    .app-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--app-space-4);
      align-items: center;
      border-bottom: 1px solid var(--app-line);
      background: var(--app-surface);
      padding: var(--app-space-4) var(--app-space-5);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .app-brand {
      display: grid;
      gap: 2px;
      min-width: 0;
    }
    .app-brand-name {
      font-size: 16px;
      font-weight: 800;
    }
    .app-brand-context {
      color: var(--app-muted);
      font-size: 12px;
    }
    .app-primary-nav {
      display: flex;
      flex-wrap: wrap;
      gap: var(--app-space-2);
      justify-content: flex-end;
    }
    .app-nav-link {
      border: 1px solid var(--app-line);
      border-radius: var(--app-radius);
      color: var(--app-muted);
      padding: 8px 10px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 650;
      line-height: 1.2;
    }
    .app-nav-link:hover {
      border-color: var(--app-accent);
      color: var(--app-accent);
    }
    .app-nav-link[aria-current="page"] {
      border-color: var(--app-accent);
      background: var(--app-accent-soft);
      color: var(--app-accent-strong);
    }
    .app-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
      gap: var(--app-space-5);
      padding: var(--app-space-5);
    }
    .app-main { min-width: 0; }
    .app-main-header {
      display: grid;
      gap: 6px;
      margin-bottom: var(--app-space-4);
    }
    .app-main-header h1 {
      font-size: 26px;
      letter-spacing: 0;
      line-height: 1.18;
      margin: 0;
    }
    .app-main-header p {
      color: var(--app-muted);
      font-size: 14px;
      line-height: 1.45;
      margin: 0;
    }
    .app-side {
      min-width: 0;
    }
    .app-panel {
      background: var(--app-surface);
      border: 1px solid var(--app-line);
      border-radius: 8px;
      padding: var(--app-space-4);
    }
    .app-notice {
      border-left: 3px solid var(--app-warn);
      border-radius: var(--app-radius);
      background: var(--app-warn-bg);
      color: #604000;
      padding: 10px 12px;
    }
    .app-button {
      border: 1px solid var(--app-line);
      border-radius: var(--app-radius);
      background: var(--app-surface);
      color: var(--app-ink);
      cursor: pointer;
      font: inherit;
      font-weight: 650;
      min-height: 34px;
      padding: 0 11px;
    }
    .app-button.primary {
      background: var(--app-accent);
      border-color: var(--app-accent);
      color: #fff;
    }
    .app-status-region { min-width: 0; }
    .app-table-scroll {
      max-width: 100%;
      overflow-x: auto;
    }
    @media (max-width: 980px) {
      .app-header {
        grid-template-columns: 1fr;
        align-items: start;
      }
      .app-primary-nav { justify-content: flex-start; }
      .app-layout { grid-template-columns: 1fr; }
    }
    @media (max-width: 680px) {
      .app-header,
      .app-layout {
        padding: var(--app-space-4);
      }
      .app-nav-link {
        flex: 1 1 auto;
        text-align: center;
      }
      .app-main-header h1 { font-size: 23px; }
    }
    """


def render_app_shell(page: ShellPage) -> str:
    safe_title = escape(page.title)
    safe_lang = escape(page.lang, quote=True)
    safe_page_class = escape(page.page_class, quote=True)
    safe_heading = escape(page.heading)
    safe_subtitle = escape(page.subtitle)
    nav_html = "\n".join(_render_nav_item(item, page.active_nav) for item in shared_nav_items())
    aside_html = f'\n      <aside class="app-side">{page.aside_html}</aside>' if page.aside_html else ""
    return f"""<!doctype html>
<html lang="{safe_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
{shared_design_tokens_css()}
{shared_base_css()}
{page.page_css}
  </style>
</head>
<body class="{safe_page_class}">
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-brand" aria-label="Application">
        <div class="app-brand-name">InvestmentKnowledge</div>
        <div class="app-brand-context">Portfolio intelligence workspace</div>
      </div>
      <nav class="app-primary-nav" aria-label="Primary">
{nav_html}
      </nav>
    </header>
    <div class="app-layout">
      <main id="main-content" class="app-main {safe_page_class}" tabindex="-1">
        <div class="app-main-header">
          <h1>{safe_heading}</h1>
          <p>{safe_subtitle}</p>
        </div>
{page.main_html}
      </main>{aside_html}
    </div>
  </div>
{page.page_js}
</body>
</html>"""


def _render_nav_item(item: NavItem, active_nav: NavKey) -> str:
    safe_label = escape(item.label)
    safe_href = escape(item.href, quote=True)
    current = ' aria-current="page"' if item.key == active_nav else ""
    return f'        <a class="app-nav-link" href="{safe_href}"{current}>{safe_label}</a>'
