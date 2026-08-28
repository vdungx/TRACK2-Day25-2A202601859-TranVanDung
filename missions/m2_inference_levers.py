"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
from collections import defaultdict
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}
REASONING_TOKEN_CAP = 0.10
REASONING_OUTPUT_MULTIPLIER = 6.0
CACHE_READ_DISCOUNT = 0.10
# The lab has no separate storage price column.  One cache write is therefore
# modeled as one full-price input-read equivalent per million tokens.
CACHE_WRITE_COST_EQUIV = 1.0


def _cache_key(row: dict) -> tuple[str, str, str]:
    """Return the synthetic static-prefix identity used for cache accounting."""
    return (
        str(row.get("route_tier", "")),
        str(row.get("team", "")),
        str(row.get("project", "") or "<untagged>"),
    )


def _cache_enabled_for_row(row: dict, cache_policy: dict | None) -> bool | None:
    if cache_policy is None:
        return None
    return _cache_key(row) in cache_policy["enabled_keys"]


def _cache_policy(rows: list[dict]) -> dict:
    """Evaluate cache economics by route/team/static-prefix group."""
    groups = defaultdict(list)
    for row in rows:
        if int(num(row.get("cached_input_tokens", 0))) > 0:
            groups[_cache_key(row)].append(row)

    group_rows = []
    enabled_keys = set()
    tier_stats = defaultdict(lambda: {
        "groups": 0,
        "enabled_groups": 0,
        "repeat_reads": 0.0,
        "cached_input_tokens": 0,
        "cache_savings_usd": 0.0,
    })
    total_cache_savings = 0.0
    for key, group in sorted(groups.items()):
        tier, team, project = key
        repeat_reads = max(0.0, float(len(group) - 1))
        worth = pricing.cache_is_worth_it(
            repeat_reads,
            CACHE_WRITE_COST_EQUIV,
            CACHE_READ_DISCOUNT,
        )
        if worth:
            enabled_keys.add(key)
        with_cache = sum(_optimized_request_cost(row, cache_enabled=worth) for row in group)
        without_cache = sum(_optimized_request_cost(row, cache_enabled=False) for row in group)
        savings = max(0.0, without_cache - with_cache)
        total_cache_savings += savings
        input_price = MODEL_PRICES[tier][0]
        stats = tier_stats[tier]
        stats["groups"] += 1
        stats["enabled_groups"] += int(worth)
        stats["repeat_reads"] += repeat_reads
        stats["cached_input_tokens"] += sum(int(num(row["cached_input_tokens"])) for row in group)
        stats["cache_savings_usd"] += savings
        group_rows.append({
            "route_tier": tier,
            "team": team,
            "project": project,
            "requests": len(group),
            "avg_repeat_reads": round(repeat_reads, 2),
            "break_even_repeat_reads": round(
                CACHE_WRITE_COST_EQUIV / (1.0 - CACHE_READ_DISCOUNT), 2
            ),
            "write_cost_usd_per_m": round(input_price * CACHE_WRITE_COST_EQUIV, 4),
            "cache_is_worth_it": worth,
            "cached_input_tokens": sum(int(num(row["cached_input_tokens"])) for row in group),
            "savings_usd": round(savings, 6),
        })

    by_tier = []
    for tier in sorted(tier_stats):
        stats = tier_stats[tier]
        by_tier.append({
            "route_tier": tier,
            "groups": stats["groups"],
            "enabled_groups": stats["enabled_groups"],
            "avg_repeat_reads": round(
                stats["repeat_reads"] / stats["groups"], 2
            ) if stats["groups"] else 0.0,
            "break_even_repeat_reads": round(
                CACHE_WRITE_COST_EQUIV / (1.0 - CACHE_READ_DISCOUNT), 2
            ),
            "cached_input_tokens": stats["cached_input_tokens"],
            "cache_savings_usd": round(stats["cache_savings_usd"], 6),
        })

    return {
        "write_cost_equiv": CACHE_WRITE_COST_EQUIV,
        "read_discount": CACHE_READ_DISCOUNT,
        "groups": group_rows,
        "by_tier": by_tier,
        "enabled_groups": len(enabled_keys),
        "cache_savings_usd": round(total_cache_savings, 6),
        "enabled_keys": enabled_keys,
    }


def _optimized_request_cost(
    row: dict,
    output_tokens: int | None = None,
    cache_enabled: bool | None = None,
) -> float:
    """Price one token-usage row using the optimized routing configuration."""
    input_tokens = int(num(row["input_tokens"]))
    output_tokens = int(num(row["output_tokens"])) if output_tokens is None else int(output_tokens)
    cached = int(num(row["cached_input_tokens"]))
    if cache_enabled is False:
        cached = 0
    price_in, price_out = MODEL_PRICES[row["route_tier"]]
    return pricing.request_cost(
        input_tokens,
        output_tokens,
        price_in,
        price_out,
        cached_in=cached,
        batch=bool(int(num(row["is_batch"]))),
    )


def analyze_reasoning(rows, optimized_cost_total: float | None = None,
                      token_cap: float = REASONING_TOKEN_CAP,
                      cache_policy: dict | None = None) -> dict:
    """Measure reasoning's cost/energy impact and a token-budget scenario.

    The generator multiplies reasoning output by six.  The cap scenario uses
    that deterministic relationship as a counterfactual: demoted requests keep
    their route/cache/batch settings but use one-sixth of their output tokens.
    The largest reasoning requests are retained first as a proxy for task
    complexity, and the cap is applied to token traffic rather than request
    count because cost and energy scale with tokens.
    """
    rows = list(rows)
    records = []
    total_tokens = 0
    optimized_cost = 0.0
    reasoning_cost = non_reasoning_cost = 0.0
    reasoning_tokens = non_reasoning_tokens = 0
    reasoning_wh = non_reasoning_wh = 0.0
    reasoning_premium_usd = reasoning_premium_wh = 0.0

    for index, row in enumerate(rows):
        input_tokens = int(num(row["input_tokens"]))
        output_tokens = int(num(row["output_tokens"]))
        row_tokens = input_tokens + output_tokens
        is_reasoning = bool(int(num(row["is_reasoning"])))
        cache_enabled = _cache_enabled_for_row(row, cache_policy)
        cost = _optimized_request_cost(row, cache_enabled=cache_enabled)
        normal_wh = sustainability.wh_per_query(row_tokens)
        actual_wh = sustainability.wh_per_query(row_tokens, is_reasoning=is_reasoning)

        total_tokens += row_tokens
        optimized_cost += cost
        records.append({
            "index": index,
            "row": row,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens": row_tokens,
            "is_reasoning": is_reasoning,
            "cache_enabled": cache_enabled,
        })

        if is_reasoning:
            reasoning_cost += cost
            reasoning_tokens += row_tokens
            reasoning_wh += actual_wh
            reasoning_premium_usd += cost - _optimized_request_cost(
                row,
                output_tokens=max(1, int(round(output_tokens / REASONING_OUTPUT_MULTIPLIER))),
                cache_enabled=cache_enabled,
            )
            reasoning_premium_wh += actual_wh - normal_wh
        else:
            non_reasoning_cost += cost
            non_reasoning_tokens += row_tokens
            non_reasoning_wh += actual_wh

    if optimized_cost_total is not None:
        optimized_cost = optimized_cost_total

    cap_budget = max(0.0, total_tokens * token_cap)
    reasoning_records = sorted(
        (r for r in records if r["is_reasoning"]),
        key=lambda r: (-r["tokens"], -r["output_tokens"], r["index"]),
    )
    kept_indices = set()
    capped_reasoning_tokens = 0
    for record in reasoning_records:
        if capped_reasoning_tokens + record["tokens"] <= cap_budget:
            kept_indices.add(record["index"])
            capped_reasoning_tokens += record["tokens"]

    capped_cost = 0.0
    capped_wh = 0.0
    capped_total_tokens = 0
    capped_reasoning_requests = 0
    for record in records:
        kept_reasoning = record["is_reasoning"] and record["index"] in kept_indices
        output_tokens = record["output_tokens"]
        if record["is_reasoning"] and not kept_reasoning:
            output_tokens = max(1, int(round(output_tokens / REASONING_OUTPUT_MULTIPLIER)))
        capped_cost += _optimized_request_cost(
            record["row"],
            output_tokens=output_tokens,
            cache_enabled=record["cache_enabled"],
        )
        capped_row_tokens = record["input_tokens"] + output_tokens
        capped_total_tokens += capped_row_tokens
        capped_wh += sustainability.wh_per_query(capped_row_tokens, is_reasoning=kept_reasoning)
        if kept_reasoning:
            capped_reasoning_requests += 1

    def pct(value: float, denominator: float) -> float:
        return value / denominator * 100.0 if denominator else 0.0

    total_wh = reasoning_wh + non_reasoning_wh
    return {
        "reasoning_requests": sum(1 for r in records if r["is_reasoning"]),
        "total_requests": len(records),
        "reasoning_request_pct": round(pct(sum(1 for r in records if r["is_reasoning"]), len(records)), 2),
        "reasoning_tokens": reasoning_tokens,
        "non_reasoning_tokens": non_reasoning_tokens,
        "total_tokens": total_tokens,
        "reasoning_token_pct": round(pct(reasoning_tokens, total_tokens), 2),
        "reasoning_cost_usd": round(reasoning_cost, 2),
        "non_reasoning_cost_usd": round(non_reasoning_cost, 2),
        "optimized_cost_usd": round(optimized_cost, 2),
        "reasoning_cost_pct": round(pct(reasoning_cost, optimized_cost), 2),
        "reasoning_wh": round(reasoning_wh, 2),
        "non_reasoning_wh": round(non_reasoning_wh, 2),
        "total_wh": round(total_wh, 2),
        "reasoning_wh_pct": round(pct(reasoning_wh, total_wh), 2),
        "reasoning_premium_usd": round(reasoning_premium_usd, 2),
        "reasoning_premium_wh": round(reasoning_premium_wh, 2),
        "token_cap_pct": round(token_cap * 100.0, 2),
        "capped_reasoning_requests": capped_reasoning_requests,
        "capped_reasoning_tokens": capped_reasoning_tokens,
        "capped_reasoning_token_pct": round(pct(capped_reasoning_tokens, total_tokens), 2),
        "capped_cost_usd": round(capped_cost, 2),
        "capped_total_tokens": capped_total_tokens,
        "capped_wh": round(capped_wh, 2),
        "cap_cost_savings_usd": round(optimized_cost - capped_cost, 2),
        "cap_cost_savings_pct": round(pct(optimized_cost - capped_cost, optimized_cost), 2),
        "cap_wh_savings": round(total_wh - capped_wh, 2),
        "cap_wh_savings_pct": round(pct(total_wh - capped_wh, total_wh), 2),
    }


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    cache_policy = _cache_policy(rows)
    base_cost = opt_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        opt_cost += _optimized_request_cost(
            r,
            cache_enabled=_cache_enabled_for_row(r, cache_policy),
        )

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0
    reasoning_analysis = analyze_reasoning(
        rows,
        optimized_cost_total=opt_cost,
        cache_policy=cache_policy,
    )

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("\nCache economics:")
        print(
            f"  enabled groups: {cache_policy['enabled_groups']}/{len(cache_policy['groups'])}  "
            f"break-even repeat reads: "
            f"{CACHE_WRITE_COST_EQUIV / (1.0 - CACHE_READ_DISCOUNT):.2f}"
        )
        print(f"  measured cache savings: ${cache_policy['cache_savings_usd']:.4f}/day")
        for tier in cache_policy["by_tier"]:
            print(
                f"  {tier['route_tier']}: avg repeat reads={tier['avg_repeat_reads']:.2f}, "
                f"enabled={tier['enabled_groups']}/{tier['groups']}"
            )
        print("\nReasoning budget analysis:")
        print(
            f"  requests: {reasoning_analysis['reasoning_requests']}/{reasoning_analysis['total_requests']} "
            f"({reasoning_analysis['reasoning_request_pct']:.1f}%)"
        )
        print(
            f"  tokens: {reasoning_analysis['reasoning_tokens']:,}/{reasoning_analysis['total_tokens']:,} "
            f"({reasoning_analysis['reasoning_token_pct']:.1f}%)"
        )
        print(
            f"  optimized cost: ${reasoning_analysis['reasoning_cost_usd']:,.2f} "
            f"({reasoning_analysis['reasoning_cost_pct']:.1f}%)"
        )
        print(
            f"  energy: {reasoning_analysis['reasoning_wh']:,.2f} Wh "
            f"({reasoning_analysis['reasoning_wh_pct']:.1f}%)"
        )
        print(
            f"  {reasoning_analysis['token_cap_pct']:.0f}% token cap: "
            f"${reasoning_analysis['cap_cost_savings_usd']:,.2f} and "
            f"{reasoning_analysis['cap_wh_savings']:,.2f} Wh saved"
        )

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_analysis": {
            key: value for key, value in cache_policy.items() if key != "enabled_keys"
        },
        "reasoning_analysis": reasoning_analysis,
        "_cache_policy": cache_policy,
    }


if __name__ == "__main__":
    run()
