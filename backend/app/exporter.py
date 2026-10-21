"""
app/exporter.py
===============
Export findings for a case in JSON, CSV, or HTML format.

Template-based plain-language explanations are generated from the structured
rule trace only — no values are invented.  An optional LLM rewrite is
available when the environment variable SOUNDDUE_LLM_REWRITE=1 is set, but
is discarded if the rewrite introduces any number, name, or identifier that
was not already present in the original explanation.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plain-language templates  (filled only from the structured trace)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, str] = {
    "possible_missing_claim": (
        "An internal source credits {contributor} with a share in "
        "\"{work_title}\" (work {work_id}), but the registration snapshot for "
        "the same work and a compatible scope explicitly marks that share as "
        "missing from the supplied records. "
        "The next step is to verify the ownership agreement and registration "
        "status before requesting a correction."
    ),
    "incomplete_ownership_info": (
        "The registration for \"{work_title}\" (work {work_id}) omits "
        "{contributor} with no explanation. "
        "This constitutes incomplete or inconsistent ownership information. "
        "Additional evidence is required — specifically the contributor is "
        "missing from the supplied records."
    ),
    "conflicting_shares": (
        "Two records for \"{work_title}\" (work {work_id}) show different "
        "share values for {contributor}: {value_a} versus {value_b}. "
        "The records cannot both be correct. "
        "The discrepancy should be resolved against the authoritative "
        "ownership agreement."
    ),
    "unmapped_recording": (
        "Recording \"{recording_title}\" ({recording_id}) has no verified "
        "mapping to a work in the supplied records. "
        "Until a mapping is confirmed, royalty attribution for this "
        "recording cannot proceed."
    ),
    # Generic fallback
    "_default": (
        "A data quality issue was detected. "
        "Rule {rule_id} v{rule_version} fired with the following summary: "
        "{summary}. "
        "Please review the evidence and supporting records listed below."
    ),
}

_LLM_GUARD_RE = re.compile(
    r"""
    \b\d[\d,\.%]*    # any number (including %, decimals, thousands)
    | [A-Z]{2,}-[\w-]+  # ISRC/ISWC style identifiers
    """,
    re.VERBOSE,
)


def _fill_template(finding_type: str, trace: dict, finding: dict) -> str:
    """Return a plain-language explanation from the template."""
    ev = finding.get("evidence", [{}])
    first_ev = ev[0].get("field_values", {}) if ev else {}

    work_id = (
        trace.get("supporting_record_ids", [""])[0]
        if trace.get("supporting_record_ids")
        else first_ev.get("work_id", first_ev.get("iswc", "unknown"))
    )

    ctx: dict[str, str] = {
        "rule_id": trace.get("rule_id", finding.get("rule_id", "")),
        "rule_version": trace.get("rule_version", finding.get("rule_version", "")),
        "summary": finding.get("summary", ""),
        "work_id": str(work_id),
        "work_title": first_ev.get("title", first_ev.get("work_title", "this work")),
        "contributor": first_ev.get("contributor_name", first_ev.get("writer_name", "the contributor")),
        "recording_id": first_ev.get("recording_id", first_ev.get("isrc", "unknown")),
        "recording_title": first_ev.get("title", "this recording"),
        "value_a": "",
        "value_b": "",
    }

    if len(ev) >= 2:
        ctx["value_a"] = str(ev[0].get("field_values", {}).get("share_percentage", ""))
        ctx["value_b"] = str(ev[1].get("field_values", {}).get("share_percentage", ""))

    tmpl = _TEMPLATES.get(finding_type, _TEMPLATES["_default"])
    try:
        return tmpl.format(**ctx)
    except KeyError:
        return _TEMPLATES["_default"].format(**ctx)


def _maybe_llm_rewrite(original: str, finding: dict) -> str:
    """
    Optionally rewrite the explanation with an LLM.

    Only active when SOUNDDUE_LLM_REWRITE=1 and an API key is configured.
    The rewrite is silently discarded if it introduces any token (number,
    identifier) not present in the original.
    """
    if os.getenv("SOUNDDUE_LLM_REWRITE", "0") != "1":
        return original

    try:
        import openai  # type: ignore

        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a music-rights analyst writing plain-English "
                        "summaries for non-technical stakeholders. "
                        "Rewrite the provided finding explanation to be clearer "
                        "and more natural. "
                        "IMPORTANT: do NOT add, change, or invent any numbers, "
                        "names, IDs, or factual claims beyond what is in the "
                        "original text. If you cannot improve it without adding "
                        "new facts, return it unchanged."
                    ),
                },
                {"role": "user", "content": original},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        rewritten = resp.choices[0].message.content.strip()

        # Guard: reject if the rewrite contains tokens not in original
        orig_tokens = set(_LLM_GUARD_RE.findall(original))
        new_tokens = set(_LLM_GUARD_RE.findall(rewritten))
        invented = new_tokens - orig_tokens
        if invented:
            log.warning(
                "LLM rewrite discarded — introduced tokens not in original: %s",
                invented,
            )
            return original

        return rewritten

    except Exception as exc:  # pylint: disable=broad-except
        log.warning("LLM rewrite failed (%s); using template explanation.", exc)
        return original


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_finding_export(finding: dict) -> dict:
    """
    Enrich a finding dict with a plain-language explanation and return it
    ready for export.  The finding dict must include rule_trace and evidence.
    """
    trace: dict = finding.get("rule_trace") or {}
    ftype: str = finding.get("finding_type", "_default")

    explanation = _fill_template(ftype, trace, finding)
    explanation = _maybe_llm_rewrite(explanation, finding)

    return {
        **finding,
        "plain_language_explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Format renderers
# ---------------------------------------------------------------------------

def render_json(findings: list[dict]) -> str:
    enriched = [build_finding_export(f) for f in findings]
    return json.dumps(
        {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "finding_count": len(enriched),
            "findings": enriched,
        },
        indent=2,
        default=str,
    )


def render_csv(findings: list[dict]) -> str:
    buf = io.StringIO()
    fieldnames = [
        "id",
        "finding_type",
        "rule_id",
        "rule_version",
        "severity",
        "status",
        "summary",
        "plain_language_explanation",
        "uncertainty",
        "next_step",
        "evidence_record_ids",
        "matched_conditions",
        "created_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for f in findings:
        enriched = build_finding_export(f)
        trace = f.get("rule_trace") or {}
        evidence = f.get("evidence") or []
        row = {
            "id": enriched.get("id", ""),
            "finding_type": enriched.get("finding_type", ""),
            "rule_id": enriched.get("rule_id", ""),
            "rule_version": enriched.get("rule_version", ""),
            "severity": enriched.get("severity", ""),
            "status": enriched.get("status", ""),
            "summary": enriched.get("summary", ""),
            "plain_language_explanation": enriched.get("plain_language_explanation", ""),
            "uncertainty": enriched.get("uncertainty", ""),
            "next_step": enriched.get("next_step", ""),
            "evidence_record_ids": "|".join(
                str(ev.get("source_record_id", "")) for ev in evidence
            ),
            "matched_conditions": " | ".join(trace.get("matched_conditions", [])),
            "created_at": enriched.get("created_at", ""),
        }
        writer.writerow(row)
    return buf.getvalue()


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SoundDue Export – {case_name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; color: #1e293b; }}
  h1 {{ color: #4338ca; }}
  .finding {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.25rem;
              margin-bottom: 2rem; }}
  .badge {{ display: inline-block; font-size: .75rem; padding: .2rem .5rem;
             border-radius: 4px; font-weight: 600; margin-right: .5rem; }}
  .error   {{ background:#fee2e2; color:#991b1b; }}
  .warning {{ background:#fef3c7; color:#92400e; }}
  .info    {{ background:#dbeafe; color:#1e40af; }}
  .open    {{ background:#f1f5f9; color:#475569; }}
  .resolved {{ background:#dcfce7; color:#166534; }}
  h3 {{ font-size: .75rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: .08em; color: #64748b; margin: 1rem 0 .4rem; }}
  pre {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:4px;
         padding:.75rem; font-size:.78rem; overflow-x:auto; white-space:pre-wrap; }}
  .checklist li {{ list-style:none; padding: .15rem 0; }}
  .checklist li::before {{ content: "✓ "; color: #16a34a; }}
  .limitations {{ background:#fffbeb; border:1px solid #fde68a; border-radius:6px;
                  padding:1rem; margin-top:2rem; font-size:.85rem; }}
  footer {{ margin-top:2rem; font-size:.75rem; color:#94a3b8; border-top:1px solid #e2e8f0; padding-top:.75rem; }}
</style>
</head>
<body>
<h1>SoundDue Findings Report</h1>
<p><strong>Case:</strong> {case_name} &nbsp;|&nbsp;
   <strong>Exported:</strong> {exported_at} &nbsp;|&nbsp;
   <strong>Findings:</strong> {finding_count}</p>

{finding_blocks}

<div class="limitations">
  <strong>⚠ Prototype limitations</strong><br>
  This report is generated by an early-stage prototype.  Findings are
  <em>leads for human review, not ownership decisions</em>.  Each finding must
  be assessed by a qualified person before any action is taken.  The rule
  engine simulates MeTTa evaluation in Python — the hyperon/OpenCog backend
  is not yet integrated.  Share arithmetic may miss edge cases.  No legal
  advice is implied.
</div>

<footer>SoundDue © {year} — Prototype only. Generated {exported_at}.</footer>
</body>
</html>
"""

_FINDING_BLOCK = """\
<div class="finding">
  <div>
    <span class="badge {severity}">{severity}</span>
    <span class="badge {status}">{status}</span>
    <strong>Finding #{id}</strong> &mdash; <code>{finding_type}</code>
  </div>

  <h3>Issue</h3>
  <p>{summary}</p>

  <h3>Plain-Language Explanation</h3>
  <p>{explanation}</p>

  <h3>Rule</h3>
  <p><code>{rule_id}</code> v{rule_version}</p>
  {conditions_html}

  <h3>Evidence</h3>
  {evidence_html}

  <h3>Uncertainty</h3>
  <p>{uncertainty}</p>

  <h3>Next Step</h3>
  <p>{next_step}</p>

  {missing_html}
  {conflict_html}
</div>
"""


def render_html(findings: list[dict], case_name: str = "Unknown") -> str:
    blocks: list[str] = []
    for f in findings:
        enriched = build_finding_export(f)
        trace = f.get("rule_trace") or {}
        evidence = f.get("evidence") or []

        # Matched conditions checklist
        conditions = trace.get("matched_conditions", [])
        if conditions:
            items = "".join(f"<li>{c}</li>" for c in conditions)
            conditions_html = f'<ul class="checklist">{items}</ul>'
        else:
            conditions_html = "<p><em>No matched conditions recorded.</em></p>"

        # Evidence table
        if evidence:
            rows_html = ""
            for ev in evidence:
                fv = ev.get("field_values") or {}
                kv_rows = "".join(
                    f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
                    for k, v in fv.items()
                )
                src = ev.get("source_record_id") or ""
                row_n = ev.get("source_row") or ""
                label = f"Record {src}" + (f" · row {row_n}" if row_n else "")
                rows_html += f"""
                <tr><td colspan="2" style="font-weight:600;padding-top:.5rem">{label}</td></tr>
                {kv_rows}"""
            evidence_html = f"""
            <table style="width:100%;font-size:.82rem;border-collapse:collapse">
              <thead><tr>
                <th style="text-align:left;border-bottom:1px solid #e2e8f0;width:40%">Field</th>
                <th style="text-align:left;border-bottom:1px solid #e2e8f0">Value</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>"""
        else:
            evidence_html = "<p><em>No evidence records attached.</em></p>"

        missing = trace.get("missing_information", "")
        missing_html = (
            f'<h3>Missing Information</h3><p style="color:#92400e">{missing}</p>'
            if missing else ""
        )
        conflict = trace.get("conflicting_information", "")
        conflict_html = (
            f'<h3>Conflicting Information</h3><p style="color:#991b1b">{conflict}</p>'
            if conflict else ""
        )

        blocks.append(
            _FINDING_BLOCK.format(
                id=f.get("id", ""),
                finding_type=f.get("finding_type", ""),
                severity=f.get("severity", "info"),
                status=f.get("status", "open"),
                summary=f.get("summary", ""),
                explanation=enriched.get("plain_language_explanation", ""),
                rule_id=f.get("rule_id", ""),
                rule_version=f.get("rule_version", ""),
                conditions_html=conditions_html,
                evidence_html=evidence_html,
                uncertainty=f.get("uncertainty", "—"),
                next_step=f.get("next_step", "—"),
                missing_html=missing_html,
                conflict_html=conflict_html,
            )
        )

    return _HTML_TEMPLATE.format(
        case_name=case_name,
        exported_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        finding_count=len(findings),
        finding_blocks="\n".join(blocks),
        year=datetime.now().year,
    )
