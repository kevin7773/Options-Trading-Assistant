from __future__ import annotations

import json
from datetime import datetime
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from options_trading_assistant.config import PROJECT_ROOT


def build_dashboard(output_path: Path | None = None) -> Path:
    path = output_path or PROJECT_ROOT / "data" / "dashboard" / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = collect_dashboard_items()
    path.write_text(render_dashboard_html(reports), encoding="utf-8")
    return path


def serve_dashboard(path: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    directory = str(path.parent)

    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=directory, **kwargs)

    with ThreadingHTTPServer((host, port), DashboardHandler) as server:
        print(f"Dashboard available at: http://{host}:{port}/{path.name}")
        print("Press Ctrl+C to stop.")
        server.serve_forever()


def collect_dashboard_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    daily_dir = PROJECT_ROOT / "data" / "reports" / "daily"
    packet_dir = PROJECT_ROOT / "data" / "journal" / "decision_packets"

    for path in sorted(daily_dir.glob("*-daily-report.html")) if daily_dir.exists() else []:
        items.append(_report_item(path, "Daily HTML Report", "html"))

    for path in sorted(daily_dir.glob("*-daily-report.md")) if daily_dir.exists() else []:
        items.append(_report_item(path, "Daily Markdown Report", "markdown"))

    for path in sorted(packet_dir.rglob("*.json")) if packet_dir.exists() else []:
        items.append(_packet_item(path))

    return sorted(items, key=lambda item: (item["date"], item["label"]), reverse=True)


def render_dashboard_html(items: list[dict[str, Any]]) -> str:
    data_json = (
        json.dumps(items, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    generated_at = datetime.now().isoformat(timespec="seconds")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Options Trading Assistant Dashboard</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #1f2933;
      --muted: #667085;
      --accent: #1769aa;
      --good: #116329;
      --warn: #8a4b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
    }}
    header {{
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }}
    .sub {{
      color: var(--muted);
      margin-top: 4px;
      font-size: 13px;
    }}
    main {{
      display: grid;
      grid-template-columns: 340px minmax(0, 1fr);
      min-height: calc(100vh - 72px);
    }}
    aside {{
      border-right: 1px solid var(--line);
      background: #fbfcfd;
      padding: 16px;
    }}
    .viewer {{
      padding: 16px;
      min-width: 0;
    }}
    label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: bold;
      margin: 14px 0 6px;
    }}
    select, input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      padding: 9px 10px;
      font-size: 14px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 14px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
    }}
    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
    }}
    .stat strong {{
      display: block;
      margin-top: 3px;
      font-size: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .card-head {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      gap: 10px;
      justify-content: space-between;
      align-items: center;
    }}
    .title {{
      font-weight: bold;
    }}
    .path {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 3px;
      overflow-wrap: anywhere;
    }}
    .badge {{
      display: inline-block;
      padding: 5px 8px;
      border-radius: 6px;
      background: #eef4ff;
      color: var(--accent);
      font-size: 12px;
      font-weight: bold;
      white-space: nowrap;
    }}
    iframe {{
      width: 100%;
      height: calc(100vh - 160px);
      border: 0;
      background: white;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      overflow: auto;
      height: calc(100vh - 160px);
      white-space: pre-wrap;
      font-family: Consolas, Monaco, monospace;
      font-size: 13px;
      line-height: 1.45;
      background: #ffffff;
    }}
    .empty {{
      padding: 32px;
      color: var(--muted);
    }}
    @media (max-width: 860px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      iframe, pre {{ height: 70vh; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Options Trading Assistant Dashboard</h1>
    <div class="sub">Generated {escape(generated_at)} · Local report viewer</div>
  </header>
  <main>
    <aside>
      <label for="dateFilter">Date</label>
      <select id="dateFilter"></select>

      <label for="typeFilter">Type</label>
      <select id="typeFilter">
        <option value="all">All viewable reports</option>
        <option value="html">Daily HTML reports</option>
        <option value="markdown">Daily Markdown reports</option>
        <option value="packet">Decision packets</option>
      </select>

      <label for="reportSelect">Report</label>
      <select id="reportSelect"></select>

      <div class="stats">
        <div class="stat"><span>Reports</span><strong id="reportCount">0</strong></div>
        <div class="stat"><span>Dates</span><strong id="dateCount">0</strong></div>
      </div>
    </aside>
    <section class="viewer">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="title" id="reportTitle">No report selected</div>
            <div class="path" id="reportPath"></div>
          </div>
          <span class="badge" id="reportType">none</span>
        </div>
        <div id="content" class="empty">No reports available yet.</div>
      </div>
    </section>
  </main>
  <script>
    const REPORTS = {data_json};
    const dateFilter = document.getElementById('dateFilter');
    const typeFilter = document.getElementById('typeFilter');
    const reportSelect = document.getElementById('reportSelect');
    const content = document.getElementById('content');
    const reportTitle = document.getElementById('reportTitle');
    const reportPath = document.getElementById('reportPath');
    const reportType = document.getElementById('reportType');
    const reportCount = document.getElementById('reportCount');
    const dateCount = document.getElementById('dateCount');

    function initDates() {{
      const dates = [...new Set(REPORTS.map(r => r.date))].sort().reverse();
      dateFilter.innerHTML = '<option value="all">All dates</option>' + dates.map(d => `<option value="${{d}}">${{d}}</option>`).join('');
      dateCount.textContent = dates.length;
    }}

    function filteredReports() {{
      return REPORTS.filter(report => {{
        const dateOk = dateFilter.value === 'all' || report.date === dateFilter.value;
        const typeOk = typeFilter.value === 'all' || report.type === typeFilter.value;
        return dateOk && typeOk;
      }});
    }}

    function updateReportSelect() {{
      const reports = filteredReports();
      reportCount.textContent = reports.length;
      reportSelect.innerHTML = reports.map((report, index) => `<option value="${{index}}">${{report.label}}</option>`).join('');
      renderSelected();
    }}

    function renderSelected() {{
      const reports = filteredReports();
      const report = reports[Number(reportSelect.value || 0)];
      if (!report) {{
        reportTitle.textContent = 'No report selected';
        reportPath.textContent = '';
        reportType.textContent = 'none';
        content.className = 'empty';
        content.textContent = 'No reports match the current filters.';
        return;
      }}
      reportTitle.textContent = report.label;
      reportPath.textContent = report.path;
      reportType.textContent = report.type;
      if (report.type === 'html') {{
        content.className = '';
        content.innerHTML = `<iframe sandbox="allow-same-origin" srcdoc="${{escapeAttribute(report.content)}}"></iframe>`;
      }} else {{
        content.className = '';
        content.innerHTML = `<pre>${{escapeHtml(report.content)}}</pre>`;
      }}
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, char => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }}[char]));
    }}

    function escapeAttribute(value) {{
      return escapeHtml(value).replace(/`/g, '&#96;');
    }}

    dateFilter.addEventListener('change', updateReportSelect);
    typeFilter.addEventListener('change', updateReportSelect);
    reportSelect.addEventListener('change', renderSelected);

    initDates();
    updateReportSelect();
  </script>
</body>
</html>
"""


def _report_item(path: Path, title: str, report_type: str) -> dict[str, Any]:
    return {
        "type": report_type,
        "date": _date_from_name(path),
        "label": f"{_date_from_name(path)} · {title} · {path.name}",
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


def _packet_item(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        packet = json.loads(content)
    except json.JSONDecodeError:
        packet = {}
    scan = packet.get("scan", {})
    date_value = str(scan.get("as_of") or _date_from_parts(path))
    decision_type = packet.get("decision_type", "packet")
    ticker = packet.get("ticker") or packet.get("sector") or "unknown"
    stage = packet.get("stage")
    status = (packet.get("outcome") or {}).get("status", "unknown")
    stage_text = f" · {stage}" if stage else ""
    return {
        "type": "packet",
        "date": date_value,
        "label": f"{date_value} · {decision_type} · {ticker}{stage_text} · {status}",
        "path": str(path),
        "content": json.dumps(packet, indent=2, sort_keys=True) if packet else content,
    }


def _date_from_name(path: Path) -> str:
    return path.name[:10] if len(path.name) >= 10 else "unknown"


def _date_from_parts(path: Path) -> str:
    for part in path.parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    return "unknown"
