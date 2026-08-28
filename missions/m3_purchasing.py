"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing

DAYS = 30


def _run_strategy(jobs: list[dict], cat: dict, advanced: bool = False) -> dict:
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        if advanced:
            tier = pricing.recommend_tier(
                hpd,
                interruptible,
                gpu_type=gtype,
                job_days=num(j["days"]),
                on_demand_hr=od,
                spot_hr=num(c["spot_hr"]),
                reserved_1yr_hr=num(c["reserved_1yr_hr"]),
                reserved_3yr_hr=num(c["reserved_3yr_hr"]),
            )
        else:
            tier = pricing.recommend_tier(hpd, interruptible)

        term = None
        interruption_rate = None
        if tier == "spot":
            interruption_rate = pricing.GPU_INTERRUPTION_RATES.get(gtype, 0.05)
            sim = pricing.spot_checkpoint_cost(
                gpu_hours,
                num(c["spot_hr"]),
                od,
                interrupt_rate=interruption_rate if advanced else 0.05,
            )
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            term = pricing.reserved_term(
                num(j["days"]),
                reserved_1yr_hr=num(c["reserved_1yr_hr"]),
                reserved_3yr_hr=num(c["reserved_3yr_hr"]),
            ) if advanced else "3yr"
            reserved_rate = num(c[f"reserved_{term}_hr"])
            opt_cost = gpu_hours * reserved_rate
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recommendation = {
            "job_id": j["job_id"],
            "gpu_type": gtype,
            "tier": tier,
            "on_demand": round(on_demand_cost),
            "optimized": round(opt_cost),
        }
        if advanced:
            recommendation.update({
                "reserved_term": term or "n/a",
                "interruption_rate": interruption_rate,
                "effective_spot_hr": round(
                    pricing.effective_spot_rate(
                        num(c["spot_hr"]),
                        interruption_rate,
                    ),
                    4,
                ) if interruption_rate is not None else None,
            })
        recs.append(recommendation)

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0
    return {
        "recommendations": recs,
        "on_demand_monthly": round(on_demand_monthly),
        "optimized_monthly": round(optimized_monthly),
        "savings_pct": round(savings_pct, 1),
    }


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    legacy = _run_strategy(jobs, cat, advanced=False)
    advanced = _run_strategy(jobs, cat, advanced=True)
    savings_delta = advanced["savings_pct"] - legacy["savings_pct"]

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in legacy["recommendations"]:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(
            f"\nlegacy monthly: on-demand ${legacy['on_demand_monthly']:,.0f} -> "
            f"optimized ${legacy['optimized_monthly']:,.0f} ({legacy['savings_pct']:.1f}% saved)"
        )
        print("\nadvanced policy (GPU interruption + duration-aware reserved term):")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'term':8}{'effective spot':>16}")
        for r in advanced["recommendations"]:
            effective = (
                f"${r['effective_spot_hr']:.4f}/hr"
                if r["effective_spot_hr"] is not None else "n/a"
            )
            print(
                f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}"
                f"{r['reserved_term']:8}{effective:>16}"
            )
        print(
            f"advanced monthly: on-demand ${advanced['on_demand_monthly']:,.0f} -> "
            f"optimized ${advanced['optimized_monthly']:,.0f} ({advanced['savings_pct']:.1f}% saved)"
        )
        print(f"savings change vs legacy: {savings_delta:+.1f} percentage points")

    return {
        **legacy,
        "advanced": advanced,
        "advanced_savings_delta_pct": round(savings_delta, 1),
    }


if __name__ == "__main__":
    run()
