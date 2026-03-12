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

SERIF_STACK = "Georgia"
SANS_STACK = "Helvetica"
MONO_STACK = "Menlo"


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
    return escape(text, quote=False).replace("'", "&#39;")


def _top_findings(findings: list[Finding], count: int = 4) -> list[Finding]:
    return findings[:count]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _wrap_text(text: str, limit: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _short_project_label(project_root: str, keep_parts: int = 4) -> str:
    parts = Path(project_root).parts
    if len(parts) <= keep_parts:
        return project_root
    return ".../" + "/".join(parts[-keep_parts:])


def _svg_text_block(
    x: int,
    y: int,
    lines: list[str],
    *,
    font_size: int,
    fill: str,
    font_family: str,
    line_height: int,
) -> str:
    tspan_lines = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        tspan_lines.append(
            f'<tspan x="{x}" dy="{dy}">{_escape_svg(line)}</tspan>'
        )
    return (
        f'<text x="{x}" y="{y}" font-size="{font_size}" fill="{fill}" '
        f'font-family="{font_family}">{"".join(tspan_lines)}</text>'
    )


def scorecard_paths(project_root: Path, config: dict | None = None) -> tuple[Path, Path]:
    cfg = config or load_config(project_root)
    scorecard_cfg = cfg.get("scorecard", {})
    svg_path = project_root / str(scorecard_cfg.get("svg_path", ".econharness/scorecard.svg"))
    html_path = project_root / str(scorecard_cfg.get("html_path", ".econharness/scorecard.html"))
    return svg_path, html_path


def _render_svg(result: ScanResult) -> str:
    width = 1420
    height = 1120
    score = result.overall_score
    score_color = _score_color(score)
    status_label = _score_label(score)
    today = datetime.now().strftime("%B %d, %Y")
    top_findings = _top_findings(result.findings, count=4)
    project_label = _short_project_label(result.project_root)
    concern_label = _friendly_dimension_name(min(result.dimension_scores, key=result.dimension_scores.get))
    intro_lines = _wrap_text(
        "This assessment summarizes repository practices associated with transparent, reproducible empirical workflows. It is a workflow score, not a judgment on the paper quality itself.",
        86,
    )
    findings_markup = []
    finding_y = 420
    if top_findings:
        for finding in top_findings:
            severity_color = SEVERITY_COLORS.get(finding.severity, PALETTE["slate"])
            location = f" [{finding.path}]" if finding.path else ""
            title = _truncate(finding.title + location, 58)
            detail = _truncate(finding.remediation, 88)
            findings_markup.append(
                f"""
                <rect x="64" y="{finding_y - 34}" width="696" height="90" rx="8" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}"/>
                <rect x="64" y="{finding_y - 34}" width="10" height="90" rx="5" fill="{severity_color}"/>
                <text x="96" y="{finding_y}" font-size="21" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{_escape_svg(title)}</text>
                <text x="96" y="{finding_y + 26}" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">{_escape_svg(detail)}</text>
                """
            )
            finding_y += 104
    else:
        findings_markup.append(
            f"""
            <rect x="64" y="386" width="696" height="90" rx="8" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}"/>
            <rect x="64" y="386" width="10" height="90" rx="5" fill="{PALETTE['olive']}"/>
            <text x="96" y="420" font-size="21" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">No open findings</text>
            <text x="96" y="446" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">The project looks structurally disciplined on the current heuristics.</text>
            """
        )

    dimension_rows = []
    row_y = 614
    for dimension, dimension_score in result.dimension_scores.items():
        tone = _score_color(dimension_score)
        dimension_rows.append(
            f"""
            <line x1="860" y1="{row_y - 20}" x2="1320" y2="{row_y - 20}" stroke="{PALETTE['rule']}" stroke-width="1"/>
            <text x="880" y="{row_y}" font-size="18" fill="{PALETTE['ink']}" font-family="{SANS_STACK}">{_escape_svg(_friendly_dimension_name(dimension))}</text>
            <text x="1300" y="{row_y}" text-anchor="end" font-size="21" fill="{tone}" font-family="{SERIF_STACK}">{dimension_score:.1f}</text>
            """
        )
        row_y += 46
    snapshot_y = 370
    snapshot_height = 166
    snapshot_lines = _wrap_text(
        f"Primary concern: {concern_label}. The current score suggests {_score_phrase(score)}.",
        46,
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="econharness scorecard">
  <rect width="{width}" height="{height}" fill="{PALETTE['paper']}"/>
  <rect x="30" y="30" width="{width - 60}" height="{height - 60}" rx="18" fill="{PALETTE['panel']}" stroke="{PALETTE['rule']}" stroke-width="1.5"/>
  <line x1="30" y1="112" x2="{width - 30}" y2="112" stroke="{PALETTE['rust']}" stroke-width="2.5"/>

  <text x="64" y="94" font-size="21" letter-spacing="2" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">ECONHARNESS</text>
  <text x="64" y="172" font-size="42" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Research Replication Assessment</text>
  <text x="64" y="206" font-size="19" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Repository structure, reproducibility, and traceability review</text>
  {_svg_text_block(64, 238, intro_lines, font_size=16, fill=PALETTE['muted'], font_family=SANS_STACK, line_height=22)}

  <rect x="860" y="136" width="460" height="224" rx="12" fill="{PALETTE['panel_alt']}" stroke="{PALETTE['rule']}"/>
  <text x="890" y="170" font-size="16" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Overall assessment</text>
  <text x="890" y="236" font-size="64" fill="{score_color}" font-family="{SERIF_STACK}">{score:.1f}</text>
  <text x="890" y="268" font-size="23" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{status_label}</text>
  <text x="890" y="300" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Assessed on {today}</text>
  <line x1="890" y1="316" x2="1290" y2="316" stroke="{PALETTE['rule']}" stroke-width="1"/>
  <text x="890" y="344" font-size="13" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Files</text>
  <text x="946" y="344" font-size="22" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('files_scanned', 0)}</text>
  <text x="1030" y="344" font-size="13" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Findings</text>
  <text x="1120" y="344" font-size="22" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('findings', 0)}</text>
  <text x="1200" y="344" font-size="13" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">High</text>
  <text x="1290" y="344" text-anchor="end" font-size="22" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">{result.summary.get('high_severity', 0)}</text>

  <text x="64" y="340" font-size="28" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Highest-priority improvements</text>
  <text x="64" y="370" font-size="15" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">A compact list of the next changes most likely to improve replication readiness.</text>
  {''.join(findings_markup)}

  <rect x="860" y="{snapshot_y}" width="460" height="{snapshot_height}" rx="12" fill="{PALETTE['panel_alt']}" stroke="{PALETTE['rule']}"/>
  <text x="890" y="{snapshot_y + 40}" font-size="24" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Repository snapshot</text>
  <text x="890" y="{snapshot_y + 68}" font-size="14" fill="{PALETTE['muted']}" font-family="{SANS_STACK}">Project</text>
  <text x="890" y="{snapshot_y + 94}" font-size="14" fill="{PALETTE['ink']}" font-family="{MONO_STACK}">{_escape_svg(project_label)}</text>
  {_svg_text_block(890, snapshot_y + 122, snapshot_lines, font_size=14, fill=PALETTE['muted'], font_family=SANS_STACK, line_height=18)}

  <text x="860" y="572" font-size="28" fill="{PALETTE['ink']}" font-family="{SERIF_STACK}">Dimension assessment</text>
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
    for finding in _top_findings(result.findings, count=6):
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
    .frame svg {{
      width: 100%;
      height: auto;
      display: block;
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
