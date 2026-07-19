from __future__ import annotations

from html import escape
from typing import Final, Literal

CANONICAL_ACCESS_KEY: Final = "investment_knowledge_access_token"
LEGACY_ACCESS_KEYS: Final = ("command_workbench_token", "weekly_review_web_token")
PageIdentity = Literal["daily_market_brief", "weekly_review", "command_workbench"]

PRIMARY_DESTINATIONS: Final = (
    ("daily_market_brief", "/daily-market-brief", "每日简报"),
    ("weekly_review", "/weekly-review", "每周复盘"),
    ("command_workbench", "/command", "命令工作台"),
)

_ACCESS_ERRORS: Final = {
    "access_required": {
        "message": "Private access is required for this operation.",
        "next_action": "enter_access",
        "retryable": True,
    },
    "access_rejected": {
        "message": "The saved access credential was rejected. Enter the current credential and try again.",
        "next_action": "replace_access",
        "retryable": True,
    },
    "access_not_configured": {
        "message": "Private access is temporarily unavailable because the service is not configured.",
        "next_action": "wait_for_service",
        "retryable": False,
    },
    "request_failed": {
        "message": "The request failed. Try again.",
        "next_action": "retry",
        "retryable": True,
    },
}


def render_primary_navigation(active_page: PageIdentity) -> str:
    links = []
    for page, href, label in PRIMARY_DESTINATIONS:
        current = ' aria-current="page"' if page == active_page else ""
        links.append(f'<a href="{escape(href)}"{current}>{escape(label)}</a>')
    return '<nav class="experience-nav" aria-label="主导航"><span class="experience-brand">InvestmentKnowledge</span>' + "".join(links) + "</nav>"


def render_experience_css() -> str:
    return """
:root {
  --experience-background: #f5f7fa;
  --experience-surface: #ffffff;
  --experience-border: #d9e1ea;
  --experience-text: #172033;
  --experience-muted: #5c6b7d;
  --experience-accent: #0f5fb8;
  --experience-danger: #b42318;
  --experience-radius: 12px;
}

.experience-shell {
  min-height: 100vh;
  background: var(--experience-background);
  color: var(--experience-text);
}

.experience-main {
  min-width: 0;
  width: min(100%, 1560px);
  margin: 0 auto;
  padding: 30px 32px 44px;
}

.experience-skip-link {
  position: fixed;
  z-index: 1000;
  top: 8px;
  left: 8px;
  padding: 10px 14px;
  border-radius: 6px;
  background: var(--experience-surface);
  color: var(--experience-accent);
  font-weight: 700;
  transform: translateY(-160%);
}

.experience-skip-link:focus {
  transform: translateY(0);
}

.page-header {
  min-width: 0;
}

.table-scroll {
  max-width: 100%;
  overflow-x: auto;
}

.table-scroll table {
  min-width: 680px;
}

.experience-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 64px;
  padding: 10px max(24px, calc((100vw - 1496px) / 2));
  background: color-mix(in srgb, var(--experience-surface) 96%, transparent);
  border-bottom: 1px solid var(--experience-border);
  box-shadow: 0 1px 0 rgba(18, 35, 58, 0.03);
  position: sticky;
  top: 0;
  z-index: 20;
  backdrop-filter: blur(10px);
}

.experience-brand {
  margin-right: 18px;
  color: var(--experience-text);
  font-size: 15px;
  font-weight: 760;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.experience-nav a {
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 0 12px;
  border-radius: 8px;
  color: var(--experience-text);
  text-decoration: none;
}

.experience-nav a[aria-current="page"] {
  color: var(--experience-accent);
  background: #e8f0fc;
  font-weight: 700;
}

:focus-visible {
  outline: 3px solid var(--experience-accent);
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .experience-main {
    padding: 16px;
  }

  .experience-nav {
    overflow-x: auto;
    padding: 8px 16px;
    gap: 4px;
  }

  .experience-brand {
    margin-right: 10px;
  }

  .experience-nav a {
    min-height: 44px;
    white-space: nowrap;
  }
}
""".strip()


def render_access_session_script() -> str:
    canonical_key = CANONICAL_ACCESS_KEY
    legacy_command_key, legacy_weekly_key = LEGACY_ACCESS_KEYS
    return f"""<script>
(() => {{
  "use strict";

  const canonicalKey = {canonical_key!r};
  const legacyKeys = [{legacy_command_key!r}, {legacy_weekly_key!r}];

  const memory = new Map();
  const storage = (() => {{
    try {{
      return window.localStorage;
    }} catch {{
      return null;
    }}
  }})();

  const read = (key) => {{
    try {{
      const stored = storage ? storage.getItem(key) : null;
      if (stored !== null) return String(stored).trim();
    }} catch {{
      // Browser storage can be unavailable in hardened/private contexts.
    }}
    return String(memory.get(key) || "").trim();
  }};

  const write = (key, value) => {{
    memory.set(key, value);
    try {{
      if (storage) storage.setItem(key, value);
    }} catch {{
      // Keep the access value only in this page session.
    }}
  }};

  const remove = (key) => {{
    memory.delete(key);
    try {{
      if (storage) storage.removeItem(key);
    }} catch {{
      // The in-memory copy is already cleared.
    }}
  }};

  const clearLegacy = () => legacyKeys.forEach(remove);

  const resolve = () => {{
    if (read(canonicalKey)) {{
      return {{status: "ready"}};
    }}

    const legacyValues = legacyKeys.map(read);
    const presentValues = legacyValues.filter(Boolean);
    if (presentValues.length === 2 && presentValues[0] !== presentValues[1]) {{
      return {{status: "legacy_conflict"}};
    }}
    if (presentValues.length) {{
      write(canonicalKey, presentValues[0]);
      clearLegacy();
      return {{status: "ready"}};
    }}
    return {{status: "missing"}};
  }};

  const getToken = () => resolve().status === "ready" ? read(canonicalKey) : "";

  const remember = (value) => {{
    const normalized = String(value || "").trim();
    if (!normalized) {{
      return {{status: "missing"}};
    }}
    write(canonicalKey, normalized);
    clearLegacy();
    return {{status: "ready"}};
  }};

  const forget = () => {{
    remove(canonicalKey);
    clearLegacy();
    return {{status: "missing"}};
  }};

  const authorizationHeaders = () => {{
    const value = getToken();
    return value ? {{Authorization: `Bearer ${{value}}`}} : {{}};
  }};

  const classifyResponse = (status, payload) => {{
    const code = payload && typeof payload.error === "string" ? payload.error : "";
    if (["access_required", "access_rejected", "access_not_configured"].includes(code)) {{
      return {{status: code}};
    }}
    if (status === 401 || status === 403) {{
      return {{status: "access_rejected"}};
    }}
    if (status >= 400) {{
      return {{status: "request_failed"}};
    }}
    return {{status: "ready"}};
  }};

  window.InvestmentKnowledgeAccess = {{
    resolve,
    getToken,
    remember,
    forget,
    authorizationHeaders,
    classifyResponse,
  }};
}})();
</script>"""


def render_access_recovery_panel(*, prefix: str) -> str:
    """Render an initially hidden, credential-only recovery panel for protected actions."""
    safe_prefix = escape(prefix)
    return f"""<section id="{safe_prefix}-access-panel" aria-labelledby="{safe_prefix}-access-title" hidden>
  <h2 id="{safe_prefix}-access-title">Private access</h2>
  <p id="{safe_prefix}-access-message" role="alert">Private access is required for generation.</p>
  <label for="{safe_prefix}-access-token">Access credential
    <input id="{safe_prefix}-access-token" type="password" autocomplete="current-password">
  </label>
  <div class="access-actions">
    <button id="{safe_prefix}-access-continue" class="primary" type="button">Continue</button>
    <button id="{safe_prefix}-access-forget" type="button">Forget access</button>
  </div>
</section>"""


def access_error_payload(code: str) -> dict[str, object]:
    details = _ACCESS_ERRORS.get(code, _ACCESS_ERRORS["request_failed"])
    error_code = code if code in _ACCESS_ERRORS else "request_failed"
    return {
        "error": error_code,
        "message": details["message"],
        "recovery": {
            "next_action": details["next_action"],
            "retryable": details["retryable"],
        },
    }
