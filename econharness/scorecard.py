"""Scorecard visualization output."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from econharness.config import load_config
from econharness.models import Finding, ScanResult

DIMENSION_LABELS = {
    "automation_and_one_command_rebuild": "Automation",
    "manual_step_elimination": "Manual-step elimination",
    "directory_and_stage_structure": "Stage structure",
    "relational_data_discipline": "Relational data",
    "environment_reproducibility": "Environment",
    "path_portability": "Path portability",
    "artifact_traceability": "Artifact traceability",
    "self_documenting_clarity": "Self-documenting clarity",
    "software_hygiene_and_redundancy": "Hygiene and redundancy",
}

PALETTE = {
    "paper": "#f7f4ee",
    "panel": "#fffdf8",
    "panel_alt": "#f0ebe3",
    "ink": "#2c2825",
    "muted": "#6f665d",
    "rule": "#d7cec2",
    "navy": "#314a67",
    "olive": "#66714b",
    "rust": "#8b4a3a",
    "ochre": "#a1782f",
    "slate": "#7c8792",
}

SEVERITY_COLORS = {
    "high": PALETTE["rust"],
    "medium": PALETTE["ochre"],
    "low": PALETTE["slate"],
}

SERIF_STACK = "Georgia, Baskerville, 'Times New Roman', serif"
SANS_STACK = "'Avenir Next', 'Gill Sans', 'Trebuchet MS', sans-serif"
MONO_STACK = "Menlo, Monaco, 'Courier New', monospace"


def _score_color(score: float) -> str:
    if score >= 90:
        return PALETTE["olive"]
    if score >= 75:
        return PALETTE["navy"]
    if score >= 60:
        return PALETTE["ochre"]
    return PALETTE["rust"]


def _score_label(score: float) -> str:
    if score >= 90:
        return "Strong"
    if score >= 75:
        return "Solid with gaps"
    if score >= 60:
        return "Needs attention"
    return "At risk"


def _dimension_label(score: float) -> str:
    if score >= 90:
        return "Strong"
    if score >= 75:
        return "Stable"
    if score >= 60:
        return "Watchlist"
    return "At risk"


def _score_phrase(score: float) -> str:
    if score >= 90:
        return "strong replication readiness"
    if score >= 75:
        return "solid replication readiness with visible gaps"
    if score >= 60:
        return "replication readiness that still needs attention"
    return "fragile replication readiness"


def _friendly_dimension_name(key: str) -> str:
    return DIMENSION_LABELS.get(key, key.replace("_", " ").title())


def _escape_svg(text: str) -> str:
    return escape(text, quote=False)


def _top_findings(findings: list[Finding], count: int = 4) -> list[Finding]:
    return findings[:count]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def scorecard_paths(project_root: Path, config: dict | None = None) -> tuple[Path, Path]:
    cfg = config or load_config(project_root)
    scorecard_cfg = cfg.get("scorecard", {})
    svg_path = project_root / str(scorecard_cfg.get("svg_path", ".econharness/scorecard.svg"))
    html_path = project_root / str(scorecard_cfg.get("html_path", ".econharness/scorecard.html"))
    return svg_path, html_path


def _render_svg(result: ScanResult) -> str:
    width = 1320
    height = 1100
    score = result.overall_score
    score_color = _score_color(score)
    status_label = _score_label(score)
    today = datetime.now().strftime("%B %d, %Y")
    top_findings = _top_findings(result.findings, count=5)
    project_label = _truncate(result.project_root, 92)

    finding_blocks = []
    finding_y = 286
    if top_findings:
        for finding in top_findings:
            severity_color = SEVERITY_COLORS.get(finding.severity, PALETTE["slate"])
            location = f" [{finding.path}]" if finding.path else ""
            title = _truncate(finding.title + location, 82)
            detail = _truncate(finding.remediation, 92)
            finding_blocks.append(
                f"""
                <rect x="64" y="{finding_y - 34}" width="690" height="84" rx="8" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}"/>
                <rect x="64" y="{finding_y - 34}" width="10" height="84" rx="5" fill="{severity_color}"/>
                <text x="96" y="{finding_y}" font-size="23" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{_escape_svg(title)}</text>
                <text x="96" y="{finding_y + 27}" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">{_escape_svg(detail)}</text>
                """
            )
            finding_y += 96
    else:
        finding_blocks.append(
            f"""
            <rect x="64" y="252" width="690" height="84" rx="8" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}"/>
            <rect x="64" y="252" width="10" height="84" rx="5" fill="{PALETTE['olive']}"/>
            <text x="96" y="286" font-size="23" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">No open findings</text>
            <text x="96" y="313" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">The project looks structurally disciplined on the current heuristics.</text>
            """
        )

    dimension_rows = []
    row_y = 690
    for dimension, dimension_score in result.dimension_scores.items():
        tone = _score_color(dimension_score)
        dimension_rows.append(
            f"""
            <line x1="64" y1="{row_y - 18}" x2="1256" y2="{row_y - 18}" stroke="{PALETTE['rule']}" stroke-width="1"/>
            <text x="82" y="{row_y}" font-size="20" fill="{PALETTE['ink']}" font-family="{SANS_STACK}">{_escape_svg(_friendly_dimension_name(dimension))}</text>
            <text x="975" y="{row_y}" font-size="18" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">{_dimension_label(dimension_score)}</text>
            <text x="1230" y="{row_y}" text-anchor="end" font-size="22" fill="{tone}" font-family="{SERIF_STACK}">{dimension_score:.1f}</text>
            """
        )
        row_y += 42

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="econharness scorecard">
  <rect width="{width}" height="{height}" fill="{PALETTE['paper']}"/>
  <rect x="30" y="30" width="{width - 60}" height="{height - 60}" rx="18" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}" stroke-width="1.5"/>
  <line x1="30" y1="112" x2="{width - 30}" y2="112" stroke="{PALETTE['rust']}" stroke-width="2.5"/>

  <text x="64" y="94" font-size="21" letter-spacing="2" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">ECONHARNESS</text>
  <text x="64" y="172" font-size="42" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Research Replication Assessment</text>
  <text x="64" y="206" font-size="19" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Repository structure, reproducibility, and traceability review</text>
  <text x="64" y="238" font-size="16" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">This assessment summarizes repository practices associated with transparent, reproducible empirical workflows. It is a workflow score, not a judgment on the paper's substantive quality.</text>

  <text x="822" y="170" font-size="16" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Overall assessment</text>
  <text x="822" y="238" font-size="88" fill="{score_color}" font-family="{SERIF_STACK}">{score:.1f}</text>
  <text x="1012" y="236" font-size="26" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{status_label}</text>
  <text x="822" y="278" font-size="16" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Assessed on {today}</text>

  <line x1="798" y1="132" x2="798" y2="314" stroke="{PALETTE['rule']}" stroke-width="1"/>
  <text x="1088" y="164" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Files reviewed</text>
  <text x="1228" y="164" text-anchor="end" font-size="24" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('files_scanned', 0)}</text>
  <text x="1088" y="208" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Open findings</text>
  <text x="1228" y="208" text-anchor="end" font-size="24" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('findings', 0)}</text>
  <text x="1088" y="252" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">High-severity findings</text>
  <text x="1228" y="252" text-anchor="end" font-size="24" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('high_severity', 0)}</text>

  <text x="64" y="340" font-size="28" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Highest-priority improvements</text>
  <text x="64" y="370" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">The first items below are intended to guide the next changes to the repository.</text>
  {''.join(finding_blocks)}

  <rect x="790" y="338" width="466" height="318" rx="12" fill="{PALETTE['panel_alt']}" stroke="{PALETTE['rule']}"/>
  <text x="822" y="384" font-size="27" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Repository snapshot</text>
  <text x="822" y="418" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Project</text>
  <text x="822" y="444" font-size="15" fill="{PALETTE['ink']}" font-family="{MONO_STACK}">{_escape_svg(project_label)}</text>
  <line x1="822" y1="468" x2="1222" y2="468" stroke="{PALETTE['rule']}" stroke-width="1"/>
  <text x="822" y="504" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Interpretation</text>
  <text x="822" y="532" font-size="18" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">The current score suggests {_score_phrase(score)}.</text>
  <text x="822" y="562" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Strong scores indicate cleaner handoff to a new RA or coauthor. Lower scores usually reflect manual steps, weak path discipline, or unclear data lineage.</text>
  <line x1="822" y1="594" x2="1222" y2="594" stroke="{PALETTE['rule']}" stroke-width="1"/>
  <text x="822" y="630" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Primary concern area</text>
  <text x="822" y="656" font-size="18" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{_escape_svg(_friendly_dimension_name(min(result.dimension_scores, key=result.dimension_scores.get)))}</text>

  <text x="64" y="652" font-size="28" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Dimension assessment</text>
  <text x="64" y="682" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Each row summarizes one part of the repository workflow rather than generic engineering aesthetics.</text>
  {''.join(dimension_rows)}
</svg>
"""


def _render_html(result: ScanResult, svg_markup: str) -> str:
    rows = []
    for dimension, score in result.dimension_scores.items():
        tone = _score_color(score)
        rows.append(
            f"<tr><td>{escape(_friendly_dimension_name(dimension))}</td><td>{escape(_dimension_label(score))}</td><td style=\"color:{tone}\">{score:.1f}</td></tr>"
        )
    findings = []
    for finding in _top_findings(result.findings, count=8):
        color = SEVERITY_COLORS.get(finding.severity, PALETTE["slate"])
        path = f" <code>{escape(finding.path)}</code>" if finding.path else ""
        findings.append(
            f"<li style=\"border-left:6px solid {color}\"><strong>{escape(finding.title)}</strong>{path}<br>{escape(finding.detail)}</li>"
        )
    finding_block = "\n".join(findings) if findings else "<li style=\"border-left:6px solid #66714b\">No open findings.</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>econharness scorecard</title>
  <style>
    :root {{
      --paper: {PALETTE['paper']};
      --panel: {PALETTE['panel']};
      --panel-alt: {PALETTE['panel_alt']};
      --ink: {PALETTE['ink']};
      --muted: {PALETTE['muted']};
      --rule: {PALETTE['rule']};
      --navy: {PALETTE['navy']};
      --rust: {PALETTE['rust']};
    }}
    body {{
      margin: 0;
      background:
        linear-gradient(180deg, rgba(139,74,58,0.06), rgba(139,74,58,0) 160px),
        radial-gradient(circle at top right, rgba(49,74,103,0.08), rgba(49,74,103,0) 35%),
        var(--paper);
      color: var(--ink);
      font-family: {SANS_STACK};
    }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    .frame {{
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--rule);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 18px 40px rgba(70, 58, 44, 0.08);
    }}
    h2 {{
      font-family: {SERIF_STACK};
      font-weight: 500;
      margin: 0 0 14px;
      color: var(--ink);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 16px;
    }}
    td {{
      padding: 12px 0;
      border-bottom: 1px solid var(--rule);
    }}
    td:last-child {{
      text-align: right;
      font-family: {SERIF_STACK};
      font-size: 20px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 24px;
      margin-top: 24px;
    }}
    ul {{
      list-style: none;
      padding: 0;
      margin: 0;
    }}
    li {{
      background: var(--panel);
      border: 1px solid var(--rule);
      padding: 14px 16px 14px 18px;
      margin-bottom: 12px;
      border-radius: 10px;
      line-height: 1.45;
    }}
    code {{
      color: var(--navy);
      font-family: {MONO_STACK};
      font-size: 0.95em;
    }}
    .caption {{
      color: var(--muted);
      margin: 0 0 16px;
      line-height: 1.5;
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
      .frame svg {{
        height: auto;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="frame">{svg_markup}</div>
    <div class="grid">
      <section class="frame">
        <h2>Dimension assessment</h2>
        <p class="caption">Rows are intended to read like an analytical summary rather than a generic engineering dashboard.</p>
        <table>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </section>
      <section class="frame">
        <h2>Highest-priority improvements</h2>
        <p class="caption">These are the findings most likely to change the current replication-readiness assessment.</p>
        <ul>{finding_block}</ul>
      </section>
    </div>
  </main>
</body>
</html>
"""


def generate_scorecard(result: ScanResult, project_root: Path, *, svg_path: Path | None = None, html_path: Path | None = None) -> tuple[Path, Path]:
    resolved_svg, resolved_html = scorecard_paths(project_root)
    svg_output = svg_path or resolved_svg
    html_output = html_path or resolved_html
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    svg_markup = _render_svg(result)
    svg_output.write_text(svg_markup, encoding="utf-8")
    html_output.write_text(_render_html(result, svg_markup), encoding="utf-8")
    return svg_output, html_output
