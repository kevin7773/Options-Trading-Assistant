from __future__ import annotations

from datetime import date, datetime
from html import escape
from pathlib import Path

from options_trading_assistant.config import PROJECT_ROOT
from options_trading_assistant.models import RecommendationAction, ScanResult


def write_daily_report(
    as_of: date,
    content: str,
    output_dir: Path | None = None,
) -> Path:
    base_dir = output_dir or PROJECT_ROOT / "data" / "reports" / "daily"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    path = base_dir / f"{as_of.isoformat()}-{timestamp}-daily-report.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_daily_report_html(
    as_of: date,
    content: str,
    output_dir: Path | None = None,
) -> Path:
    base_dir = output_dir or PROJECT_ROOT / "data" / "reports" / "daily"
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    path = base_dir / f"{as_of.isoformat()}-{timestamp}-daily-report.html"
    path.write_text(content, encoding="utf-8")
    return path


def format_report_footer(result: ScanResult, decision_packet_count: int) -> str:
    context = result.context
    lines = [
        "",
        "Report Context",
        f"- Stocks scanned: {context.stocks_scanned}",
        f"- Option spreads evaluated: {context.spreads_evaluated}",
        f"- Volatility source: {context.volatility_source or 'unknown'}",
        f"- Decision packets written: {decision_packet_count}",
    ]
    if context.top_sectors:
        lines.append("- Top sectors:")
        for sector in context.top_sectors[:5]:
            eligible = "eligible" if sector.eligible else "not eligible"
            lines.append(f"  - {sector.rank}. {sector.sector} ({sector.etf}) {sector.score:.2f}/15, {eligible}")
    return "\n".join(lines)


def format_daily_report_html(result: ScanResult, decision_packet_count: int) -> str:
    action_class = "buy" if result.action == RecommendationAction.BUY else "sitout"
    recommendation_html = "".join(_recommendation_card(candidate) for candidate in result.recommendations)
    if not recommendation_html:
        recommendation_html = '<p class="muted">No trade recommendations passed the configured rules.</p>'

    rejection_rows = "".join(_rejection_row(rejection) for rejection in result.rejections[:12])
    if not rejection_rows:
        rejection_rows = '<tr><td colspan="4" class="muted">No rejected candidates recorded.</td></tr>'

    sectors = "".join(
        f"<li><strong>{sector.rank}. {escape(sector.sector)}</strong> "
        f"({escape(sector.etf)}) <span>{sector.score:.2f}/15</span> "
        f"<em>{'eligible' if sector.eligible else 'not eligible'}</em></li>"
        for sector in result.context.top_sectors[:5]
    )
    if not sectors:
        sectors = '<li class="muted">No sector ranking available.</li>'

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #f6f7f9;
      color: #1f2933;
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.45;
    }}
    .wrap {{
      max-width: 880px;
      margin: 0 auto;
      padding: 28px 18px;
    }}
    .header {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 22px;
    }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 18px; margin: 24px 0 10px; }}
    .meta {{ color: #667085; margin-top: 6px; }}
    .badge {{
      display: inline-block;
      margin-top: 16px;
      padding: 8px 12px;
      border-radius: 6px;
      font-weight: bold;
      letter-spacing: .02em;
    }}
    .badge.buy {{ background: #e8f5ee; color: #116329; }}
    .badge.sitout {{ background: #fff4df; color: #8a4b00; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 16px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 12px;
    }}
    .metric span {{ display: block; color: #667085; font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 18px; }}
    .card {{
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 16px;
      margin: 10px 0;
    }}
    .card h3 {{ font-size: 17px; margin-bottom: 8px; }}
    .details {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 12px 0;
      font-size: 13px;
    }}
    .details div {{
      background: #f9fafb;
      border: 1px solid #eaecf0;
      border-radius: 6px;
      padding: 8px;
    }}
    ul {{ margin-top: 8px; padding-left: 20px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid #eaecf0;
      padding: 9px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{ background: #f2f4f7; color: #475467; }}
    .muted {{ color: #667085; }}
    .footer {{ color: #667085; font-size: 12px; margin-top: 22px; }}
    @media (max-width: 720px) {{
      .grid, .details {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <h1>Options Trading Assistant Daily Report</h1>
      <div class="meta">{escape(result.as_of.isoformat())} · {escape(result.mode)} · Strategy {escape(result.strategy_version)}</div>
      <div class="badge {action_class}">{escape(result.action.value)}</div>
      <p><strong>Reason:</strong> {escape(result.reason)}</p>
    </div>

    <div class="grid">
      <div class="metric"><span>Market Score</span><strong>{result.market_score:.2f}/30</strong></div>
      <div class="metric"><span>Stocks Scanned</span><strong>{result.context.stocks_scanned}</strong></div>
      <div class="metric"><span>Spreads Evaluated</span><strong>{result.context.spreads_evaluated}</strong></div>
      <div class="metric"><span>Decision Packets</span><strong>{decision_packet_count}</strong></div>
    </div>

    <h2>Recommendations</h2>
    {recommendation_html}

    <h2>Rejected Candidates</h2>
    <table>
      <thead><tr><th>Stage</th><th>Ticker</th><th>Score</th><th>Reasons</th></tr></thead>
      <tbody>{rejection_rows}</tbody>
    </table>

    <h2>Top Sectors</h2>
    <div class="card"><ul>{sectors}</ul></div>

    <div class="footer">
      Volatility source: {escape(str(result.context.volatility_source or 'unknown'))}.
      Generated locally by Options Trading Assistant.
    </div>
  </div>
</body>
</html>
"""


def _recommendation_card(candidate) -> str:
    spread = candidate.spread
    rationale = "".join(f"<li>{escape(item)}</li>" for item in candidate.rationale)
    risks = "".join(f"<li>{escape(item)}</li>" for item in candidate.risks)
    return f"""
    <div class="card">
      <h3>{escape(candidate.stock.ticker)} · {escape(candidate.sector.name)} · {escape(candidate.grade)} · {candidate.score.total:.2f}/100</h3>
      <div class="details">
        <div><strong>Spread</strong><br>{spread.long_call:g}/{spread.short_call:g} call spread</div>
        <div><strong>Expiration</strong><br>{escape(spread.expiration.isoformat())}</div>
        <div><strong>Debit / Risk</strong><br>${spread.debit:.2f} / ${spread.max_loss:.0f}</div>
        <div><strong>Max Profit</strong><br>${spread.max_profit:.0f}</div>
        <div><strong>Breakeven</strong><br>${spread.breakeven:.2f}</div>
        <div><strong>Reward/Risk</strong><br>{spread.reward_to_risk:.2f}</div>
      </div>
      <strong>Why this trade</strong>
      <ul>{rationale}</ul>
      <strong>Key risks</strong>
      <ul>{risks}</ul>
    </div>
    """


def _rejection_row(rejection) -> str:
    ticker = rejection.ticker or rejection.sector or ""
    score = "" if rejection.score is None else f"{rejection.score:.2f}"
    reasons = "; ".join(rejection.reasons[:3])
    if len(rejection.reasons) > 3:
        reasons += f"; +{len(rejection.reasons) - 3} more"
    return (
        "<tr>"
        f"<td>{escape(rejection.stage.value)}</td>"
        f"<td>{escape(str(ticker))}</td>"
        f"<td>{escape(score)}</td>"
        f"<td>{escape(reasons)}</td>"
        "</tr>"
    )
