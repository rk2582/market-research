"""Renders a Report as Markdown so a person can review its quality (used by the live tests only)."""

from __future__ import annotations

from schemas.report import InsightOut, Report, ReportClaim


def _refs(refs: list[int]) -> str:
    return "".join(f"[{r}]" for r in refs)


def _claim(c: ReportClaim) -> str:
    flag = {"supported": "", "partially_supported": " ⚠ partial", "unsupported": " ❓ unconfirmed"}.get(c.verdict, "")
    if c.estimate:
        flag += " _(estimate — research firm)_"
    if c.old_source_year:
        flag += f" _(old source: {c.old_source_year})_"
    return f"- {c.text} {_refs(c.refs)}{flag}"


def _insights(items: list[InsightOut]) -> list[str]:
    return [f"- {i.text} {_refs(i.refs)} _({i.kind})_" for i in items] or ["- _none_"]


def report_to_markdown(r: Report) -> str:
    m, v = r.meta, r.validation
    title = "Market-entry report" if m.mode == "market" else "Market intelligence report"
    lines = [
        f"# {title}: {m.company_name}",
        "",
        f"_Query: {m.query} · Outcome: **{m.outcome}** · Generated {m.generated_at} · {m.total_tokens:,} tokens_",
        "",
    ]
    if m.missing_sections:
        lines += [f"> Partial report — missing: {', '.join(m.missing_sections)}", ""]
    lines += ["## 1. Executive summary", "", r.executive_summary or "_missing_", ""]
    co = r.company_overview
    lines += ["## 2. Company overview", "", f"**{co.name}** — {co.website or 'website unknown'}", ""]
    if co.identity:
        lines += [f"_Identity: {co.identity.text}_ {_refs(co.identity.refs)}", ""]
    for group in co.facts:
        lines += [f"**{group.label}**", *(_claim(c) for c in group.claims), ""]
    lines += ["## 3. Industry overview", "", r.industry_overview.text or "_missing_", ""]
    lines += [_claim(c) for c in r.industry_overview.claims] + [""]
    lines += ["## 4. Competitor landscape", ""]
    for comp in r.competitor_landscape:
        lines += [f"### {comp.name} ({comp.relation}) — {comp.website or ''}", ""]
        for group in comp.facts:
            lines += [f"**{group.label}**", *(_claim(c) for c in group.claims), ""]
    lines += ["## 5. Competitive comparison", ""]
    if r.competitive_comparison:
        companies = [cell.company for cell in r.competitive_comparison[0].cells]
        lines += ["| Dimension | " + " | ".join(companies) + " |", "|---" * (len(companies) + 1) + "|"]
        for row in r.competitive_comparison:
            cells = [f"{c.value} {_refs(c.refs)}".replace("|", "/") for c in row.cells]
            lines.append(f"| {row.dimension} | " + " | ".join(cells) + " |")
    if r.market:
        mk = r.market
        if mk.not_found:
            lines += ["", f"_Not found in public sources: {', '.join(mk.not_found)}._"]
        lines += ["", f"> {mk.disclaimer}", "", "## 6. Market attractiveness (five forces)", ""]
        rated = {f.force: f for f in mk.forces}
        for force in ("rivalry", "entry_barriers", "supplier_power", "buyer_power", "substitutes"):
            f = rated.get(force)
            label = force.replace("_", " ").capitalize()
            lines.append(
                f"- **{label}:** {f.rating} — {f.reason} {_refs(f.refs)}" if f else f"- **{label}:** not rated"
            )
        lines += ["", "**Signals for entering**", *_insights(mk.signals_for), ""]
        lines += ["**Signals against entering**", *_insights(mk.signals_against), ""]
    else:
        lines += ["", "## 6. SWOT", ""]
        for name in ("strengths", "weaknesses", "opportunities", "threats"):
            lines += [f"**{name.title()}**", *_insights(getattr(r.swot, name)), ""]
    lines += ["## 7. Market trends", "", *_insights(r.market_trends), ""]
    lines += ["## 8. Opportunities", "", *_insights(r.opportunities), ""]
    lines += ["## 9. Risks", "", *_insights(r.risks), ""]
    lines += ["## 10. Strategic recommendations", ""]
    for rec in r.recommendations:
        lines += [
            f"### {rec.priority}. {rec.title} (impact: {rec.impact}) {_refs(rec.refs)}",
            "",
            rec.rationale,
            "",
            *(f"- Next: {s}" for s in rec.next_steps),
            *(f"- Risk: {s}" for s in rec.risks_tradeoffs),
            *([f"> ⚠ {rec.warning}"] if rec.warning else []),
            "",
        ]
    if r.market:
        lines += ["## Check before you invest", "", *(f"- [ ] {c}" for c in r.market.checks_before_investing), ""]
    lines += ["## 11. Actionable next steps", "", *(f"1. {s}" for s in r.next_steps), ""]
    lines += ["## 12. References", "", *(f"{s.ref}. [{s.title or s.url}]({s.url})" for s in r.references), ""]
    lines += [
        "## Fact-check summary",
        "",
        f"{v.claims_total} claims: {v.supported} supported, {v.partially_supported} partially supported, "
        f"{v.unsupported} unconfirmed, {v.contradicted} contradicted (removed).",
        "",
        *(f"- {w}" for w in v.warnings),
        *(
            [
                f"Second research round: {m.second_round.filled} of {len(m.second_round.gaps)} gaps filled"
                + (f" (failed: {m.second_round.error})" if m.second_round.error else "")
                + "".join(f"\n  - {g}" for g in m.second_round.gaps)
            ]
            if m.second_round
            else []
        ),
        "",
        "## Usage",
        "",
        "| Step | Agent | Model | Tokens in | Tokens out | Tool calls | Time (s) |",
        "|---|---|---|---|---|---|---|",
        *(
            f"| {u.step} | {u.agent_version} | {u.model} | {u.input_tokens:,} | {u.output_tokens:,} | {u.tool_calls} "
            f"| {(u.duration_ms or 0) / 1000:.1f} |"
            for u in m.usage
        ),
        "",
    ]
    return "\n".join(lines)
