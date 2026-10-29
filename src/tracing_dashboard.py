"""The error kinds in the traces of Langfuse, counted for the dashboard page.

Every message and every tool call that went wrong carries the span attribute
marketdesk.error with one of the codes of src.failures or of the tools.
Langfuse can filter by it but cannot group by it, so the page reads the
observations through Langfuse's API and counts them here.

Only numbers leave this module: the traces hold no message text and no id
(the hosted target gets an allowlist of attributes), and the keys are used in
one header and never logged or put into an error.
"""

import base64
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import config

ERROR_KEY = "attributes.marketdesk.error"
MESSAGE_SPAN = "message"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30


class DashboardUnavailable(RuntimeError):
    """The page cannot show its numbers; the code says why, in no words."""

    def __init__(self, code: str, status: int | None = None):
        super().__init__(code)
        self.code = code
        self.status = status

    def __reduce__(self):
        # Streamlit keeps a cached failure by pickling it.
        return (type(self), (self.code, self.status))


@dataclass(frozen=True)
class ErrorCount:
    """How many observations carry one error kind, in a message or a tool."""

    kind: str
    where: str
    count: int


def credentials(environment: Mapping[str, str] = os.environ) -> tuple[str, str]:
    """The public and the secret key of the Langfuse project."""
    public = environment.get("LANGFUSE_PUBLIC_KEY", "")
    secret = environment.get("LANGFUSE_SECRET_KEY", "")
    if not public or not secret:
        raise DashboardUnavailable("KEYS_MISSING")
    return public, secret


def observations_url(base_url: str, cursor: str | None) -> str:
    """The v2 observations request: newest first, with their metadata.

    No start time is given, so the machine clock is not needed: Langfuse
    answers the newest observations first, and the cursor goes on from there.
    """
    query = {"limit": PAGE_SIZE, "fields": "core,basic,metadata"}
    if cursor:
        query["cursor"] = cursor
    base = base_url.rstrip("/")
    return f"{base}/api/public/v2/observations?" + urllib.parse.urlencode(query)


def fetch_observations(
    public_key: str,
    secret_key: str,
    newest: int = config.TRACING_DASHBOARD_OBSERVATIONS,
    base_url: str = config.LANGFUSE_BASE_URL,
    opener: Callable = urllib.request.urlopen,
) -> list[dict]:
    """The newest observations, page by page, at most as many as asked."""
    signed = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    headers = {"Authorization": f"Basic {signed}"}
    observations: list[dict] = []
    cursor = None
    while len(observations) < newest:
        request = urllib.request.Request(
            observations_url(base_url, cursor), headers=headers
        )
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as failure:
            # The status only: the answer may repeat what was sent.
            raise DashboardUnavailable("REQUEST_FAILED", failure.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DashboardUnavailable("UNREACHABLE") from None
        page = body.get("data") or []
        observations += page
        cursor = (body.get("meta") or {}).get("cursor")
        if not cursor or not page:
            break
    return observations[:newest]


def count_errors(observations: list[dict]) -> list[ErrorCount]:
    """The error kinds, most frequent first, apart for messages and tools."""
    counts: Counter = Counter()
    for observation in observations:
        metadata = observation.get("metadata") or {}
        kind = metadata.get(ERROR_KEY)
        if not kind:
            continue
        where = "message" if observation.get("name") == MESSAGE_SPAN else "tool"
        counts[(str(kind), where)] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [ErrorCount(kind, where, count) for (kind, where), count in ranked]


def failure_text(texts, failure: DashboardUnavailable) -> str:
    """What the page or the command says when the numbers cannot be read."""
    if failure.code == "KEYS_MISSING":
        return texts.DASH_KEYS_MISSING
    if failure.code == "REQUEST_FAILED":
        return texts.DASH_REQUEST_FAILED.format(status=failure.status)
    return texts.DASH_UNREACHABLE


# --- The page and the table -------------------------------------------------

STYLE = """
:root { color-scheme: light dark; --bg: #f7f7f5; --card: #ffffff; --ink: #1b1b1b;
  --muted: #666660; --line: #dcdcd6; --message: #2f6fb3; --tool: #d98324; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #17181a; --card: #202225; --ink: #ececec; --muted: #9a9a94;
    --line: #34363a; --message: #5b9bd8; --tool: #e8a24a; } }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.5 system-ui, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { margin: 0 0 4px; font-size: 1.6rem; }
h2 { margin: 28px 0 8px; font-size: 1.1rem; }
.caption { margin: 0 0 20px; color: var(--muted); }
.metrics { display: flex; flex-wrap: wrap; gap: 12px; }
.metric { flex: 1 1 160px; background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 16px; }
.metric b { display: block; font-size: 1.6rem; }
.metric span { color: var(--muted); font-size: 0.9rem; }
.card { background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 16px; overflow-x: auto; }
svg { width: 100%; height: auto; display: block; }
svg text { fill: var(--ink); font: 13px system-ui, sans-serif; }
.legend { display: flex; gap: 16px; margin-top: 8px; color: var(--muted);
  font-size: 0.9rem; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
  margin-right: 6px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
td.number, th.number { text-align: right; }
"""
LABEL_WIDTH = 190
BAR_WIDTH = 330
ROW_HEIGHT = 30


def chart_svg(rows: list[ErrorCount]) -> str:
    """Bars by error kind, a message and a tool part in each."""
    by_kind: dict[str, dict[str, int]] = {}
    for row in rows:
        by_kind.setdefault(row.kind, {})[row.where] = row.count
    ordered = sorted(
        by_kind.items(), key=lambda item: (-sum(item[1].values()), item[0])
    )
    top = max(sum(parts.values()) for _, parts in ordered)
    height = ROW_HEIGHT * len(ordered)
    width = LABEL_WIDTH + BAR_WIDTH + 60
    lines = [f'<svg viewBox="0 0 {width} {height}" role="img">']
    for index, (kind, parts) in enumerate(ordered):
        y = index * ROW_HEIGHT
        x = LABEL_WIDTH
        lines.append(
            f'<text x="{LABEL_WIDTH - 8}" y="{y + 19}" text-anchor="end">'
            f"{html.escape(kind)}</text>"
        )
        for where, colour in (("message", "--message"), ("tool", "--tool")):
            count = parts.get(where, 0)
            if not count:
                continue
            size = BAR_WIDTH * count / top
            lines.append(
                f'<rect x="{x:.1f}" y="{y + 5}" width="{size:.1f}" height="20" '
                f'rx="2" style="fill: var({colour})"/>'
            )
            x += size
        lines.append(f'<text x="{x + 6:.1f}" y="{y + 19}">{sum(parts.values())}</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def render_html(rows: list[ErrorCount], observed: int, texts, language: str) -> str:
    """The whole page as one file: no server, no script, nothing from outside."""
    errors = sum(row.count for row in rows)
    kinds = len({row.kind for row in rows})
    metrics = "".join(
        f'<div class="metric"><b>{value}</b><span>{html.escape(label)}</span></div>'
        for label, value in (
            (texts.DASH_OBSERVATIONS, observed),
            (texts.DASH_ERRORS, errors),
            (texts.DASH_KINDS, kinds),
        )
    )
    if rows:
        legend = "".join(
            f'<span><i class="dot" style="background: var({colour})"></i>'
            f"{html.escape(texts.DASH_WHERE[where])}</span>"
            for where, colour in (("message", "--message"), ("tool", "--tool"))
        )
        body_rows = "".join(
            f"<tr><td>{html.escape(row.kind)}</td>"
            f"<td>{html.escape(texts.DASH_WHERE[row.where])}</td>"
            f'<td class="number">{row.count}</td></tr>'
            for row in rows
        )
        content = (
            f'<h2>{html.escape(texts.DASH_BY_KIND)}</h2><div class="card">'
            f'{chart_svg(rows)}<div class="legend">{legend}</div></div>'
            f'<div class="card" style="margin-top: 16px"><table><thead><tr>'
            f"<th>{html.escape(texts.DASH_COLUMN_KIND)}</th>"
            f"<th>{html.escape(texts.DASH_COLUMN_WHERE)}</th>"
            f'<th class="number">{html.escape(texts.DASH_COLUMN_COUNT)}</th>'
            f"</tr></thead><tbody>{body_rows}</tbody></table></div>"
        )
    else:
        content = f'<p class="card">{html.escape(texts.DASH_NO_ERRORS)}</p>'
    return (
        f'<!doctype html><html lang="{html.escape(language)}"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(texts.DASH_TITLE)}</title><style>{STYLE}</style></head>"
        f"<body><main><h1>{html.escape(texts.DASH_TITLE)}</h1>"
        f'<p class="caption">{html.escape(texts.DASH_CAPTION)}</p>'
        f'<div class="metrics">{metrics}</div>{content}</main></body></html>'
    )


def render_table(rows: list[ErrorCount], observed: int, texts) -> str:
    """The same numbers as plain lines for the terminal."""
    head = (
        f"{texts.DASH_OBSERVATIONS}: {observed}   "
        f"{texts.DASH_ERRORS}: {sum(row.count for row in rows)}   "
        f"{texts.DASH_KINDS}: {len({row.kind for row in rows})}"
    )
    if not rows:
        return head + "\n" + texts.DASH_NO_ERRORS
    width = max(len(row.kind) for row in rows)
    lines = [
        f"{row.kind:<{width}}  {texts.DASH_WHERE[row.where]:<8} {row.count:>4}"
        for row in rows
    ]
    return "\n".join([head, *lines])
