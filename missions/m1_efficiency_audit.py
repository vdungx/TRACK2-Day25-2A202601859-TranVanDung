"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics

DAYS = 30
MBU_MEMORY_BOUND_THRESHOLD = 0.40


def _memory_rightsizing(telemetry, workloads, catalog,
                        days: int = DAYS,
                        mbu_threshold: float = MBU_MEMORY_BOUND_THRESHOLD) -> dict:
    """Evaluate cheaper GPUs for low-MBU inference workloads.

    The synthetic telemetry labels the L4 fleet row as ``embed`` while the
    workload catalog contains an L4 inference job.  Therefore the bandwidth
    signal is aggregated by GPU type, then joined to inference jobs by type.
    A candidate must preserve the current HBM capacity and the observed
    bandwidth demand; otherwise a lower hourly price would be a misleading
    right-sizing recommendation.
    """
    bw_by_type = defaultdict(list)
    for row in telemetry:
        bw_by_type[row["gpu_type"]].append(num(row["achieved_bw_tbs"]))

    recommendations = []
    for job in workloads:
        if job.get("kind") != "infer":
            continue

        source_type = job["gpu_type"]
        source = catalog[source_type]
        samples = bw_by_type.get(source_type, [])
        if not samples:
            continue

        source_peak_bw = num(source["peak_bw_tbs"])
        required_bw = sum(samples) / len(samples)
        source_mbu = metrics.compute_mbu(required_bw, source_peak_bw)
        source_hbm = num(source["hbm_gb"])
        source_rate = num(source["on_demand_hr"])
        source_cost_per_gb = source_rate / source_hbm if source_hbm > 0 else 0.0
        memory_bound = source_mbu <= mbu_threshold

        candidates = []
        if memory_bound:
            for target_type, target in catalog.items():
                target_hbm = num(target["hbm_gb"])
                target_bw = num(target["peak_bw_tbs"])
                target_rate = num(target["on_demand_hr"])
                if (
                    target_type != source_type
                    and target_hbm >= source_hbm
                    and target_bw >= required_bw
                    and target_rate < source_rate
                ):
                    target_cost_per_gb = target_rate / target_hbm if target_hbm > 0 else 0.0
                    candidates.append((target_cost_per_gb, target_rate, target_type, target))

        if candidates:
            _, target_rate, target_type, target = min(
                candidates,
                key=lambda item: (item[0], item[1], item[2]),
            )
            reason = "meets HBM + observed bandwidth at lower $/GB"
        else:
            target_type = source_type
            target = source
            target_rate = source_rate
            reason = "no cheaper catalog GPU meets HBM + observed bandwidth"

        hours_per_day = num(job["hours_per_day"])
        num_gpus = int(num(job["num_gpus"]))
        monthly_savings = max(0.0, source_rate - target_rate) * hours_per_day * days * num_gpus
        target_hbm = num(target["hbm_gb"])
        target_cost_per_gb = target_rate / target_hbm if target_hbm > 0 else 0.0

        recommendations.append({
            "job_id": job["job_id"],
            "gpu_type": source_type,
            "recommended_gpu": target_type,
            "memory_bound": memory_bound,
            "mbu": round(source_mbu, 3),
            "required_bw_tbs": round(required_bw, 3),
            "source_hbm_gb": round(source_hbm, 1),
            "target_hbm_gb": round(target_hbm, 1),
            "source_peak_bw_tbs": round(source_peak_bw, 3),
            "target_peak_bw_tbs": round(num(target["peak_bw_tbs"]), 3),
            "source_on_demand_hr": round(source_rate, 4),
            "target_on_demand_hr": round(target_rate, 4),
            "source_usd_per_gb": round(source_cost_per_gb, 4),
            "target_usd_per_gb": round(target_cost_per_gb, 4),
            "monthly_savings": round(monthly_savings, 2),
            "reason": reason,
        })

    return {
        "workloads": recommendations,
        "monthly_savings": round(sum(r["monthly_savings"] for r in recommendations), 2),
        "mbu_threshold": mbu_threshold,
    }


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    memory_rightsizing = _memory_rightsizing(tel, load_csv("workloads.csv"), cat)

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print("\nMBU-aware right-sizing (inference workloads):")
        print(f"{'job':20}{'current':10}{'target':10}{'MBU':>7}{'$/GB':>10}{'target $/GB':>13}{'monthly save':>15}")
        for r in memory_rightsizing["workloads"]:
            print(
                f"{r['job_id']:20}{r['gpu_type']:10}{r['recommended_gpu']:10}"
                f"{r['mbu']:>7.3f}{r['source_usd_per_gb']:>10.4f}"
                f"{r['target_usd_per_gb']:>13.4f}${r['monthly_savings']:>14,.2f}"
            )
        print(f"MBU right-sizing scenario: ${memory_rightsizing['monthly_savings']:,.2f}/month")

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "memory_rightsizing": memory_rightsizing,
    }


if __name__ == "__main__":
    run()
