"""Extension 5 — carbon-aware scheduling for interruptible GPU workloads.

Run: python missions/carbon_scheduling.py
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from finops import sustainability
from missions._common import catalog_by_type, load_csv, num


def analyze_carbon_schedule(
    workloads: list[dict],
    catalog: dict,
    baseline_region: str = "us-east-1",
    clean_region: str | None = None,
) -> dict:
    """Compare interruptible workloads in the baseline and cleanest regions.

    GPU energy is estimated from catalog watts multiplied by actual GPU-hours
    in ``workloads``.  The returned regional table uses that same total energy
    so cost and carbon are directly comparable across every catalog region.
    """
    clean_region = clean_region or min(
        sustainability.REGION_CARBON,
        key=sustainability.REGION_CARBON.get,
    )
    if baseline_region not in sustainability.REGION_CARBON:
        raise ValueError(f"Unknown baseline region: {baseline_region}")
    if clean_region not in sustainability.REGION_CARBON:
        raise ValueError(f"Unknown clean region: {clean_region}")

    job_rows = []
    total_energy_kwh = 0.0
    for job in workloads:
        if int(num(job.get("interruptible", 0))) != 1:
            continue
        gpu_type = job["gpu_type"]
        if gpu_type not in catalog:
            raise KeyError(f"GPU type {gpu_type!r} is missing from the price catalog")
        gpu_hours = (
            num(job.get("hours_per_day", 0))
            * num(job.get("days", 0))
            * int(num(job.get("num_gpus", 0)))
        )
        energy_kwh = gpu_hours * num(catalog[gpu_type]["watts"]) / 1000.0
        total_energy_kwh += energy_kwh
        baseline_carbon = sustainability.carbon_g(energy_kwh * 1000.0, baseline_region)
        clean_carbon = sustainability.carbon_g(energy_kwh * 1000.0, clean_region)
        baseline_cost = sustainability.energy_cost_usd(energy_kwh * 1000.0, baseline_region)
        clean_cost = sustainability.energy_cost_usd(energy_kwh * 1000.0, clean_region)
        job_rows.append({
            "job_id": job["job_id"],
            "gpu_type": gpu_type,
            "gpu_hours": round(gpu_hours, 2),
            "energy_kwh": round(energy_kwh, 3),
            "baseline_region": baseline_region,
            "clean_region": clean_region,
            "baseline_cost_usd": round(baseline_cost, 2),
            "clean_cost_usd": round(clean_cost, 2),
            "cost_delta_usd": round(clean_cost - baseline_cost, 2),
            "baseline_carbon_g": round(baseline_carbon, 2),
            "clean_carbon_g": round(clean_carbon, 2),
            "carbon_saved_g": round(max(0.0, baseline_carbon - clean_carbon), 2),
            "carbon_saved_pct": round(
                (baseline_carbon - clean_carbon) / baseline_carbon * 100.0,
                1,
            ) if baseline_carbon else 0.0,
        })

    regional = []
    for region in sustainability.REGION_CARBON:
        regional.append({
            "region": region,
            "price_usd_per_kwh": sustainability.REGION_PRICE_KWH.get(region, 0.12),
            "carbon_g_per_kwh": sustainability.REGION_CARBON[region],
            "energy_kwh": round(total_energy_kwh, 3),
            "electricity_cost_usd": round(
                sustainability.energy_cost_usd(total_energy_kwh * 1000.0, region), 2
            ),
            "carbon_g": round(
                sustainability.carbon_g(total_energy_kwh * 1000.0, region), 2
            ),
        })

    max_price = max((row["price_usd_per_kwh"] for row in regional), default=1.0)
    max_carbon = max((row["carbon_g_per_kwh"] for row in regional), default=1.0)
    balanced_region = min(
        regional,
        key=lambda row: (
            row["price_usd_per_kwh"] / max_price
            + row["carbon_g_per_kwh"] / max_carbon,
            row["carbon_g_per_kwh"],
            row["price_usd_per_kwh"],
        ),
    )["region"] if regional else None

    baseline_total_carbon = sustainability.carbon_g(
        total_energy_kwh * 1000.0,
        baseline_region,
    )
    clean_total_carbon = sustainability.carbon_g(
        total_energy_kwh * 1000.0,
        clean_region,
    )
    baseline_total_cost = sustainability.energy_cost_usd(
        total_energy_kwh * 1000.0,
        baseline_region,
    )
    clean_total_cost = sustainability.energy_cost_usd(
        total_energy_kwh * 1000.0,
        clean_region,
    )
    return {
        "baseline_region": baseline_region,
        "cleanest_region": clean_region,
        "cheapest_region": min(
            sustainability.REGION_PRICE_KWH,
            key=sustainability.REGION_PRICE_KWH.get,
        ),
        "balanced_region": balanced_region,
        "interruptible_jobs": job_rows,
        "regions": regional,
        "total_energy_kwh": round(total_energy_kwh, 3),
        "baseline_cost_usd": round(baseline_total_cost, 2),
        "clean_cost_usd": round(clean_total_cost, 2),
        "cost_delta_usd": round(clean_total_cost - baseline_total_cost, 2),
        "baseline_carbon_g": round(baseline_total_carbon, 2),
        "clean_carbon_g": round(clean_total_carbon, 2),
        "carbon_saved_g": round(max(0.0, baseline_total_carbon - clean_total_carbon), 2),
        "carbon_saved_pct": round(
            (baseline_total_carbon - clean_total_carbon)
            / baseline_total_carbon
            * 100.0,
            1,
        ) if baseline_total_carbon else 0.0,
    }


def run(verbose: bool = True) -> dict:
    result = analyze_carbon_schedule(load_csv("workloads.csv"), catalog_by_type())
    if verbose:
        print("== Extension 5: Carbon-aware Scheduling ==")
        print(
            f"interruptible GPU energy: {result['total_energy_kwh']:,.2f} kWh; "
            f"cleanest={result['cleanest_region']}; "
            f"cheapest={result['cheapest_region']}; "
            f"balanced={result['balanced_region']}"
        )
        print(
            f"carbon: {result['baseline_carbon_g']:,.0f} g -> "
            f"{result['clean_carbon_g']:,.0f} g "
            f"({result['carbon_saved_g']:,.0f} g, {result['carbon_saved_pct']:.1f}% saved)"
        )
        print(
            f"electricity: ${result['baseline_cost_usd']:,.2f} -> "
            f"${result['clean_cost_usd']:,.2f} "
            f"({result['cost_delta_usd']:+,.2f})"
        )
        print("\nRegional comparison:")
        print(f"{'region':18}{'$/kWh':>9}{'gCO2/kWh':>12}{'cost':>14}{'carbon g':>14}")
        for row in result["regions"]:
            print(
                f"{row['region']:18}${row['price_usd_per_kwh']:>8.3f}"
                f"{row['carbon_g_per_kwh']:>12.0f}${row['electricity_cost_usd']:>13,.2f}"
                f"{row['carbon_g']:>14,.0f}"
            )
    return result


if __name__ == "__main__":
    run()
