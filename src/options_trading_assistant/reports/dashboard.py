from __future__ import annotations

import json
from datetime import datetime
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from options_trading_assistant.config import PROJECT_ROOT, load_config
from options_trading_assistant.providers.historical import historical_tickers


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
    backtest_dir = PROJECT_ROOT / "backtesting" / "results"
    config_dir = PROJECT_ROOT / "config"
    validation_reports_dir = PROJECT_ROOT / "data" / "reports" / "validation"
    signal_rankings_dir = PROJECT_ROOT / "data" / "journal" / "signal_rankings"
    prospective_doc = PROJECT_ROOT / "docs" / "prospective_tracking.md"
    experiment_dir = PROJECT_ROOT / "research" / "experiments"
    items.append(_data_quality_item())

    for path in sorted(daily_dir.glob("*-daily-report.html")) if daily_dir.exists() else []:
        items.append(_report_item(path, "Daily HTML Report", "html"))

    for path in sorted(daily_dir.glob("*-daily-report.md")) if daily_dir.exists() else []:
        items.append(_report_item(path, "Daily Markdown Report", "markdown"))

    for path in sorted(packet_dir.rglob("*.json")) if packet_dir.exists() else []:
        items.append(_packet_item(path))

    for path in sorted(backtest_dir.rglob("summary.json")) if backtest_dir.exists() else []:
        items.append(_backtest_summary_item(path))

    for path in sorted(backtest_dir.rglob("validation.md")) if backtest_dir.exists() else []:
        items.append(_report_item(path, "Edge Validation Report", "validation"))

    for path in sorted(backtest_dir.rglob("validation.json")) if backtest_dir.exists() else []:
        items.append(_json_report_item(path, "Edge Validation Data", "validation"))

    for path in sorted(validation_reports_dir.rglob("*.md")) if validation_reports_dir.exists() else []:
        items.append(_report_item(path, "Prospective Validation Report", "prospective"))

    for path in sorted(validation_reports_dir.rglob("*.json")) if validation_reports_dir.exists() else []:
        items.append(_json_report_item(path, "Prospective Validation Data", "prospective"))

    for path in sorted(signal_rankings_dir.rglob("*.json")) if signal_rankings_dir.exists() else []:
        items.append(_signal_ranking_item(path))

    for path in sorted(experiment_dir.rglob("*.yaml")) if experiment_dir.exists() else []:
        items.append(_experiment_manifest_item(path))

    readme = experiment_dir / "README.md"
    if readme.exists():
        items.append(_report_item(readme, "Experiment Manifest Spec", "experiment"))

    if prospective_doc.exists():
        items.append(_report_item(prospective_doc, "Prospective Tracking Runbook", "prospective"))

    universe_path = config_dir / "universe_v2.yaml"
    if universe_path.exists():
        items.append(_universe_summary_item(universe_path))
        items.append(_report_item(universe_path, "Universe v2 YAML", "universe"))

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
        <option value="backtest">Backtest / benchmark summaries</option>
        <option value="validation">Edge validation reports</option>
        <option value="prospective">Prospective evidence</option>
        <option value="experiment">Research experiments</option>
        <option value="quality">Data quality</option>
        <option value="universe">Universe</option>
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


def _backtest_summary_item(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        summary = json.loads(content)
    except json.JSONDecodeError:
        summary = {}
    run_dir = path.parent
    run_name = run_dir.name
    date_value = _date_from_run_name(run_name)
    scenario = summary.get("scenario") or _run_part(run_name, 2) or "unknown"
    strike_model = summary.get("strike_model") or _run_part(run_name, 3) or "unknown"
    formatted = _format_backtest_summary(run_name, summary) if summary else content
    return {
        "type": "backtest",
        "date": date_value,
        "label": f"{date_value} · {scenario} · {strike_model} · {run_name}",
        "path": str(path),
        "content": formatted,
    }


def _json_report_item(path: Path, title: str, report_type: str) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(content)
        content = json.dumps(payload, indent=2, sort_keys=True)
    except json.JSONDecodeError:
        pass
    return {
        "type": report_type,
        "date": _date_from_name(path),
        "label": f"{_date_from_name(path)} · {title} · {path.parent.name}",
        "path": str(path),
        "content": content,
    }


def _signal_ranking_item(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {}
    date_value = str(payload.get("as_of") or _date_from_parts(path))
    mode = payload.get("mode", "unknown")
    strategy_version = payload.get("strategy_version", "unknown")
    top = payload.get("rankings", [])
    top_ticker = top[0].get("ticker", "none") if top and isinstance(top[0], dict) else "none"
    return {
        "type": "prospective",
        "date": date_value,
        "label": f"{date_value} · signal ranking · {strategy_version} · {mode} · top {top_ticker}",
        "path": str(path),
        "content": json.dumps(payload, indent=2, sort_keys=True) if payload else content,
    }


def _experiment_manifest_item(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        payload = {}
    experiment_id = str(payload.get("experiment_id") or path.stem)
    hypotheses = ", ".join(payload.get("hypotheses") or [])
    decision = (payload.get("decision") or {}).get("status") or payload.get("status") or "unknown"
    date_value = str(payload.get("date_completed") or payload.get("date_started") or "experiment")
    name = payload.get("name") or path.stem
    formatted = _format_experiment_manifest(payload) if payload else content
    return {
        "type": "experiment",
        "date": date_value,
        "label": f"{date_value} · {experiment_id} · {hypotheses or 'no hypothesis'} · {decision}",
        "path": str(path),
        "content": formatted,
        "experiment_id": experiment_id,
        "decision": decision,
        "name": name,
    }


def _universe_summary_item(path: Path) -> dict[str, Any]:
    config = load_config()
    sectors = config.universe.get("sectors", {})
    research_slices = config.universe.get("research_slices", {})
    scan_stocks: set[str] = set()
    research_stocks: set[str] = set()
    etfs: set[str] = {"SPY", "QQQ", "VIXY"}
    research_slice_symbols: set[str] = set()
    lines = [
        "Universe v2 Summary",
        f"Version: {config.universe.get('version', 'legacy')}",
        f"Scan tiers: {', '.join(config.universe.get('scan_tiers', ['legacy']))}",
        f"Lifecycle statuses: {', '.join(config.universe.get('lifecycle_statuses', {}).keys())}",
        "",
        "Coverage",
    ]
    for sector_name, sector_config in sectors.items():
        tickers = sector_config.get("tickers", [])
        research_tickers = sector_config.get("research_tickers", tickers)
        scan_stocks.update(tickers)
        research_stocks.update(research_tickers)
        etfs.update(sector_config.get("etfs", []))
        lines.append(
            f"- {sector_name}: scan={len(tickers)} research={len(research_tickers)} "
            f"etfs={len(sector_config.get('etfs', []))}"
        )
        research_history = sector_config.get("research_history") or {}
        if research_history:
            lines.append(
                "  research history: "
                f"hypotheses={', '.join(research_history.get('hypotheses', []) or ['none'])}; "
                f"experiments={', '.join(research_history.get('experiments', []) or ['none'])}; "
                f"prospective_observations={research_history.get('prospective_observations', 0)}"
            )
    if research_slices:
        lines.extend(["", "Research slices"])
    for slice_name, slice_config in research_slices.items():
        tracked_symbols = slice_config.get("tracked_symbols", [])
        research_slice_symbols.update(tracked_symbols)
        etfs.update(slice_config.get("etfs", []))
        lines.append(
            f"- {slice_name}: status={slice_config.get('status', 'research')} "
            f"tracked={len(tracked_symbols)} etfs={len(slice_config.get('etfs', []))}"
        )
        promotion = slice_config.get("promotion_requirements") or {}
        history = slice_config.get("research_history") or {}
        if promotion:
            lines.append(
                "  promotion: "
                f"minimum_completed_trades={promotion.get('minimum_completed_trades', 'n/a')}; "
                f"minimum_expectancy={promotion.get('minimum_expectancy', 'n/a')}; "
                f"max_drawdown={promotion.get('max_drawdown', 'n/a')}"
            )
        if history:
            lines.append(
                "  research history: "
                f"hypotheses={', '.join(history.get('hypotheses', []) or ['none'])}; "
                f"experiments={', '.join(history.get('experiments', []) or ['none'])}; "
                f"prospective_observations={history.get('prospective_observations', 0)}"
            )
    lines.insert(6, f"- Sectors: {len(sectors)}")
    lines.insert(7, f"- Scan stocks: {len(scan_stocks)}")
    lines.insert(8, f"- Research stocks: {len(research_stocks)}")
    lines.insert(9, f"- Research slice symbols: {len(research_slice_symbols)}")
    lines.insert(10, f"- ETFs / proxies: {len(etfs)}")
    lines.insert(11, f"- Default hydrate symbols: {len(scan_stocks | research_slice_symbols | etfs)}")
    return {
        "type": "universe",
        "date": "universe",
        "label": "Universe v2 · summary",
        "path": str(path),
        "content": "\n".join(lines),
    }


def _data_quality_item() -> dict[str, Any]:
    config = load_config()
    expected_symbols = set(historical_tickers(config))
    cache_files = _historical_cache_files()
    cached_symbols = {_symbol_from_cache_file(path) for path in cache_files}
    cached_symbols.discard("")
    missing = sorted(expected_symbols - cached_symbols)
    extra = sorted(cached_symbols - expected_symbols)
    malformed_packets = _malformed_json_files(PROJECT_ROOT / "data" / "journal" / "decision_packets")
    malformed_experiments = _malformed_yaml_files(PROJECT_ROOT / "research" / "experiments")
    malformed_notebooks = _malformed_json_files(PROJECT_ROOT / "research" / "notebooks", pattern="*.ipynb")
    daily_reports = list((PROJECT_ROOT / "data" / "reports" / "daily").glob("*-daily-report.*"))
    packet_files = list((PROJECT_ROOT / "data" / "journal" / "decision_packets").rglob("*.json"))
    experiment_files = list((PROJECT_ROOT / "research" / "experiments").glob("*.yaml"))
    notebook_files = list((PROJECT_ROOT / "research" / "notebooks").glob("*.ipynb"))
    latest_cache_write = max((path.stat().st_mtime for path in cache_files), default=0)
    latest_cache_text = (
        datetime.fromtimestamp(latest_cache_write).isoformat(timespec="seconds")
        if latest_cache_write
        else "none"
    )
    coverage = len(expected_symbols & cached_symbols)
    lines = [
        "Data Quality Dashboard",
        "",
        "Category | Status",
        "--- | ---",
        f"Symbols hydrated | {coverage} / {len(expected_symbols)}",
        f"Missing configured symbols | {', '.join(missing) if missing else 'none'}",
        f"Unexpected cached symbols | {', '.join(extra) if extra else 'none'}",
        f"Historical cache files | {len(cache_files)}",
        f"Cache freshness | latest historical cache write {latest_cache_text}",
        f"Decision packets | {_health_label(packet_files, malformed_packets)}",
        f"Reports | {_count_label(daily_reports)}",
        f"Notebook metadata | {_health_label(notebook_files, malformed_notebooks)}",
        f"Experiment manifests | {_health_label(experiment_files, malformed_experiments)}",
        "",
        "Interpretation",
        "- Treat missing configured symbols as data-quality issues before interpreting strategy results.",
        "- Measurement-only research slices are included in hydration coverage but are not production scan sectors.",
    ]
    return {
        "type": "quality",
        "date": "quality",
        "label": "Data Quality · repository health",
        "path": str(PROJECT_ROOT),
        "content": "\n".join(lines),
    }


def _historical_cache_files() -> list[Path]:
    base = PROJECT_ROOT / "data" / "historical"
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.csv") if path.is_file())


def _symbol_from_cache_file(path: Path) -> str:
    return path.stem.split("_", 1)[0].upper()


def _malformed_json_files(directory: Path, pattern: str = "*.json") -> list[Path]:
    malformed: list[Path] = []
    for path in sorted(directory.rglob(pattern)) if directory.exists() else []:
        try:
            json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            malformed.append(path)
    return malformed


def _malformed_yaml_files(directory: Path) -> list[Path]:
    malformed: list[Path] = []
    for path in sorted(directory.rglob("*.yaml")) if directory.exists() else []:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except yaml.YAMLError:
            malformed.append(path)
    return malformed


def _health_label(files: list[Path], malformed: list[Path]) -> str:
    if not files:
        return "no files found"
    if malformed:
        return f"{len(files) - len(malformed)} / {len(files)} healthy; malformed: {', '.join(path.name for path in malformed)}"
    return f"healthy ({len(files)} files)"


def _count_label(files: list[Path]) -> str:
    return f"healthy ({len(files)} files)" if files else "no files found"


def _format_backtest_summary(run_name: str, summary: dict[str, Any]) -> str:
    lines = [
        f"Backtest Summary: {run_name}",
        "",
        f"Scenario: {summary.get('scenario', 'unknown')}",
        f"Strike model: {summary.get('strike_model', 'unknown')}",
        f"Scans: {summary.get('scan_count', 0)}",
        f"Trades: {summary.get('trade_count', 0)}",
        f"Sit-outs: {summary.get('sit_out_count', 0)}",
        f"Win rate: {_pct(summary.get('win_rate', 0))}",
        f"Average win: ${summary.get('average_win', 0):.2f}",
        f"Average loss: ${summary.get('average_loss', 0):.2f}",
        f"Expectancy: ${summary.get('expectancy', 0):.2f}",
        f"Max drawdown: ${summary.get('max_drawdown', 0):.2f}",
    ]
    for title, key in (
        ("Performance by sector", "performance_by_sector"),
        ("Performance by market regime", "performance_by_market_regime"),
        ("Performance by score bucket", "performance_by_score_bucket"),
    ):
        group = summary.get(key) or {}
        lines.extend(["", title])
        if not group:
            lines.append("- none")
        for name, metrics in group.items():
            lines.append(
                f"- {name}: trades={metrics.get('trades', 0)} "
                f"win_rate={_pct(metrics.get('win_rate', 0))} "
                f"total_pl=${metrics.get('total_pl', 0):.2f} "
                f"avg_pl=${metrics.get('average_pl', 0):.2f}"
            )
    return "\n".join(lines)


def _format_experiment_manifest(payload: dict[str, Any]) -> str:
    baseline = payload.get("baseline_results") or {}
    results = payload.get("results") or {}
    decision = payload.get("decision") or {}
    hypotheses = ", ".join(payload.get("hypotheses") or [])
    lines = [
        f"Experiment: {payload.get('experiment_id', 'unknown')}",
        "",
        f"Name: {payload.get('name', 'unknown')}",
        f"Strategy: {payload.get('strategy', 'unknown')}",
        f"Baseline: {payload.get('baseline', 'unknown')}",
        f"Hypotheses: {hypotheses or 'none'}",
        f"Status: {payload.get('status', 'unknown')}",
        f"Decision: {decision.get('status', 'pending')}",
        "",
        "Result Summary",
        f"- Trade count: {_fmt_value(results.get('trade_count'))} ({_delta(results.get('trade_count'), baseline.get('trade_count'))} vs baseline)",
        f"- Win rate: {_pct(results.get('win_rate'))} ({_delta_pct(results.get('win_rate'), baseline.get('win_rate'))} vs baseline)",
        f"- Expectancy: {_money(results.get('expectancy'))} ({_delta_money(results.get('expectancy'), baseline.get('expectancy'))} vs baseline)",
        f"- Max drawdown: {_money(results.get('drawdown'))} ({_delta_money(results.get('drawdown'), baseline.get('drawdown'))} vs baseline)",
        "",
        "Baseline",
        f"- Run: {baseline.get('run_id', 'unknown')}",
        f"- Trades: {_fmt_value(baseline.get('trade_count'))}",
        f"- Win rate: {_pct(baseline.get('win_rate'))}",
        f"- Expectancy: {_money(baseline.get('expectancy'))}",
        f"- Max drawdown: {_money(baseline.get('drawdown'))}",
    ]
    semiconductor = results.get("semiconductor") or {}
    baseline_semiconductor = baseline.get("semiconductor") or {}
    if semiconductor or baseline_semiconductor:
        lines.extend(
            [
                "",
                "Semiconductors",
                f"- Trades: {_fmt_value(semiconductor.get('trades'))} ({_delta(semiconductor.get('trades'), baseline_semiconductor.get('trades'))} vs baseline)",
                f"- Win rate: {_pct(semiconductor.get('win_rate'))} ({_delta_pct(semiconductor.get('win_rate'), baseline_semiconductor.get('win_rate'))} vs baseline)",
                f"- Total P/L: {_money(semiconductor.get('total_pl'))} ({_delta_money(semiconductor.get('total_pl'), baseline_semiconductor.get('total_pl'))} vs baseline)",
                f"- Expectancy: {_money(semiconductor.get('expectancy'))}",
            ]
        )
    artifacts = payload.get("artifacts") or {}
    lines.extend(["", "Artifacts"])
    for key, values in artifacts.items():
        if not values:
            continue
        lines.append(f"- {key}:")
        for value in values:
            lines.append(f"  - {value}")
    if not any(artifacts.values()):
        lines.append("- none")
    rationale = decision.get("rationale")
    if rationale:
        lines.extend(["", "Decision Rationale", str(rationale).strip()])
    return "\n".join(lines)


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "0.0%"


def _fmt_value(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _money(value: Any) -> str:
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _delta(value: Any, baseline: Any) -> str:
    try:
        return f"{float(value) - float(baseline):+.0f}"
    except (TypeError, ValueError):
        return "n/a"


def _delta_money(value: Any, baseline: Any) -> str:
    try:
        return f"${float(value) - float(baseline):+.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _delta_pct(value: Any, baseline: Any) -> str:
    try:
        return f"{float(value) - float(baseline):+.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _date_from_run_name(name: str) -> str:
    if len(name) >= 8 and name[:8].isdigit():
        return f"{name[:4]}-{name[4:6]}-{name[6:8]}"
    return "backtest"


def _run_part(name: str, index: int) -> str | None:
    parts = name.split("-")
    return parts[index] if len(parts) > index else None


def _date_from_name(path: Path) -> str:
    return path.name[:10] if len(path.name) >= 10 else "unknown"


def _date_from_parts(path: Path) -> str:
    for part in path.parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    return "unknown"
