"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly",
                 unit_economics: dict | None = None,
                 extensions: dict | None = None,
                 recommendations: list[str] | None = None) -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}<br>",
        f"**Baseline spend:** ${baseline_usd:,.0f}<br>",
        f"**Optimized spend:** ${optimized_usd:,.0f}<br>",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")

    if unit_economics:
        lines += [
            "",
            "## Inference unit economics",
            "",
            f"- Token volume: {unit_economics.get('tokens_per_day', 0):,} tokens/day",
            f"- Baseline: ${unit_economics.get('baseline_per_m', 0):,.3f}/1M-token",
            f"- Optimized: ${unit_economics.get('optimized_per_m', 0):,.3f}/1M-token",
            f"- Inference savings: {unit_economics.get('savings_pct', 0):.1f}%",
        ]

    if sustainability:
        cleanest = sustainability.get("cleanest_region", sustainability.get("best_region", "n/a"))
        cheapest = sustainability.get("cheapest_region", "n/a")
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Cleanest region (carbon): {cleanest}",
            f"- Cheapest electricity region: {cheapest}",
            f"- Electricity cost per query: ${sustainability.get('energy_cost_usd', 0):.6f}",
        ]

    if extensions:
        mbu = extensions.get("mbu_rightsizing")
        if mbu:
            lines += [
                "",
                "## Extension 2 — MBU-aware right-sizing",
                "",
                f"Threshold: MBU <= {mbu.get('mbu_threshold', 0):.2f}. "
                "Candidates preserve HBM capacity and observed bandwidth.",
                "",
                "| Workload | Current | Recommendation | MBU | $/GB current | $/GB target | Monthly savings |",
                "|---|---|---|---:|---:|---:|---:|",
            ]
            for row in mbu.get("workloads", []):
                lines.append(
                    f"| {row['job_id']} | {row['gpu_type']} | {row['recommended_gpu']} | "
                    f"{row['mbu']:.3f} | ${row['source_usd_per_gb']:.4f} | "
                    f"${row['target_usd_per_gb']:.4f} | ${row['monthly_savings']:,.2f} |"
                )
            lines.append(
                f"\nScenario savings: ${mbu.get('monthly_savings', 0):,.2f}/month "
                "(reported separately from the M5 headline to avoid double-counting)."
            )

        reasoning = extensions.get("reasoning")
        if reasoning:
            lines += [
                "",
                "## Extension 4 — Reasoning budget",
                "",
                f"- Reasoning traffic: {reasoning.get('reasoning_requests', 0)}/"
                f"{reasoning.get('total_requests', 0)} requests "
                f"({reasoning.get('reasoning_request_pct', 0):.1f}%), "
                f"{reasoning.get('reasoning_token_pct', 0):.1f}% of tokens",
                f"- Optimized reasoning cost: ${reasoning.get('reasoning_cost_usd', 0):,.2f} "
                f"({reasoning.get('reasoning_cost_pct', 0):.1f}% of optimized inference cost)",
                f"- Reasoning energy: {reasoning.get('reasoning_wh', 0):,.2f} Wh "
                f"({reasoning.get('reasoning_wh_pct', 0):.1f}% of total)",
                f"- {reasoning.get('token_cap_pct', 0):.0f}% token-cap scenario: "
                f"${reasoning.get('cap_cost_savings_usd', 0):,.2f} and "
                f"{reasoning.get('cap_wh_savings', 0):,.2f} Wh saved",
            ]

        cache = extensions.get("cache")
        if cache:
            lines += [
                "",
                "## Extension 3 — KV-cache economics",
                "",
                f"- Cache policy enabled for {cache.get('enabled_groups', 0)}/"
                f"{len(cache.get('groups', []))} observed prefix groups",
                f"- Break-even: more than "
                f"{1.0 / (1.0 - cache.get('read_discount', 0.10)):.2f} "
                "repeat reads per prefix under the normalized write-cost assumption",
                f"- Measured cache savings: ${cache.get('cache_savings_usd', 0):,.4f}/day",
                "",
                "| Route tier | Groups | Enabled | Avg repeat reads | Break-even reads | Cache savings/day |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for row in cache.get("by_tier", []):
                lines.append(
                    f"| {row['route_tier']} | {row['groups']} | {row['enabled_groups']} | "
                    f"{row['avg_repeat_reads']:.2f} | {row['break_even_repeat_reads']:.2f} | "
                    f"${row['cache_savings_usd']:.4f} |"
                )

        advanced_purchasing = extensions.get("advanced_purchasing")
        if advanced_purchasing:
            lines += [
                "",
                "## Extension 1 — Advanced purchasing policy",
                "",
                "The advanced scenario adds GPU-specific interruption rates and selects "
                "the reserved term from observed job duration.",
                "",
                "| Workload | GPU | Tier | Reserved term | Effective spot $/hr | Optimized/month |",
                "|---|---|---|---|---:|---:|",
            ]
            for row in advanced_purchasing.get("recommendations", []):
                effective_spot = (
                    f"${row['effective_spot_hr']:.4f}"
                    if row.get("effective_spot_hr") is not None else "n/a"
                )
                lines.append(
                    f"| {row['job_id']} | {row['gpu_type']} | {row['tier']} | "
                    f"{row.get('reserved_term', 'n/a')} | {effective_spot} | "
                    f"${row['optimized']:,} |"
                )
            lines += [
                f"\nLegacy savings: {extensions.get('legacy_purchasing_savings_pct', 0):.1f}%; "
                f"advanced savings: {advanced_purchasing.get('savings_pct', 0):.1f}%; "
                f"change: {extensions.get('advanced_purchasing_delta_pct', 0):+.1f} percentage points.",
            ]

        carbon = extensions.get("carbon_scheduling")
        if carbon:
            lines += [
                "",
                "## Extension 5 — Carbon-aware Scheduling",
                "",
                f"- Interruptible workload energy: {carbon.get('total_energy_kwh', 0):,.2f} kWh",
                f"- Cleanest region: {carbon.get('cleanest_region', 'n/a')}; "
                f"cheapest electricity: {carbon.get('cheapest_region', 'n/a')}; "
                f"balanced score: {carbon.get('balanced_region', 'n/a')}",
                f"- Moving interruptible jobs from {carbon.get('baseline_region', 'n/a')} "
                f"to {carbon.get('cleanest_region', 'n/a')} saves "
                f"{carbon.get('carbon_saved_g', 0):,.0f} gCO2e "
                f"({carbon.get('carbon_saved_pct', 0):.1f}%) and changes electricity cost by "
                f"${carbon.get('cost_delta_usd', 0):+,.2f}",
                "",
                "| Region | $/kWh | gCO2/kWh | Electricity cost | Carbon |",
                "|---|---:|---:|---:|---:|",
            ]
            for row in carbon.get("regions", []):
                lines.append(
                    f"| {row['region']} | ${row['price_usd_per_kwh']:.3f} | "
                    f"{row['carbon_g_per_kwh']:.0f} | ${row['electricity_cost_usd']:,.2f} | "
                    f"{row['carbon_g']:,.0f} g |"
                )
            lines += [
                "",
                "| Interruptible job | GPU-hours | Baseline carbon | Clean carbon | Saved |",
                "|---|---:|---:|---:|---:|",
            ]
            for row in carbon.get("interruptible_jobs", []):
                lines.append(
                    f"| {row['job_id']} | {row['gpu_hours']:,.0f} | "
                    f"{row['baseline_carbon_g']:,.0f} g | {row['clean_carbon_g']:,.0f} g | "
                    f"{row['carbon_saved_g']:,.0f} g |"
                )

    if recommendations:
        lines += ["", "## Recommended actions", ""]
        lines.extend(f"{index}. {item}" for index, item in enumerate(recommendations, start=1))

    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [max(0.0, float(levers[n])) for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    running = 0.0
    colors = ["#2e548a"] * len(names)
    for name, value, color in zip(names, vals, colors):
        ax.bar(name, value, bottom=running, color=color)
        ax.text(name, running + value, f"${value:,.0f}", ha="center", va="bottom", fontsize=8)
        running += value
    ax.set_ylabel("Cumulative savings (USD / month)")
    ax.set_title(f"GPU cost savings waterfall (total ${running:,.0f})")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
