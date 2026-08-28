"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def cache_is_worth_it(
    avg_cache_reads: float,
    write_cost_per_m: float,
    read_discount: float = 0.10,
) -> bool:
    """Return whether repeated cached reads recover the cache-write cost.

    ``avg_cache_reads`` is the average number of *repeat* reads for one
    cached prefix.  ``write_cost_per_m`` is expressed in full-price input-read
    equivalents per million tokens because the helper intentionally has no
    model-price argument.  Callers can normalize a dollar write charge by the
    model's uncached input price before calling this function.
    """
    reads = max(0.0, float(avg_cache_reads))
    write_cost = max(0.0, float(write_cost_per_m))
    discount = max(0.0, min(1.0, float(read_discount)))
    return reads * (1.0 - discount) > write_cost


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


GPU_INTERRUPTION_RATES = {
    # Illustrative June-2026 rates for the lab's neocloud catalog.
    "H100": 0.03,
    "H200": 0.04,
    "A100": 0.05,
    "A10G": 0.08,
    "L4": 0.10,
    "B200": 0.06,
    "MI300X": 0.05,
}


def reserved_term(
    job_days: float | None,
    reserved_1yr_hr: float | None = None,
    reserved_3yr_hr: float | None = None,
) -> str:
    """Choose a reserved term from duration, then compare available rates."""
    if job_days is None or float(job_days) < 365.0:
        return "1yr"
    if reserved_1yr_hr is not None and reserved_3yr_hr is not None:
        return "3yr" if float(reserved_3yr_hr) <= float(reserved_1yr_hr) else "1yr"
    return "3yr"


def effective_spot_rate(
    spot_hr: float,
    interruption_rate: float,
    ckpt_overhead_frac: float = 0.03,
    rework_hours_per_interrupt: float = 0.5,
) -> float:
    """Expected spot $/GPU-hour after checkpoint overhead and rework."""
    return max(0.0, float(spot_hr)) * (
        1.0
        + max(0.0, float(ckpt_overhead_frac))
        + max(0.0, float(interruption_rate)) * max(0.0, float(rework_hours_per_interrupt))
    )


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    gpu_type: str | None = None,
    job_days: float | None = None,
    on_demand_hr: float | None = None,
    spot_hr: float | None = None,
    reserved_1yr_hr: float | None = None,
    reserved_3yr_hr: float | None = None,
    interruption_rate: float | None = None,
) -> str:
    """Pick a purchasing tier from a workload's duty cycle + interruptibility.

    DOCUMENTED simple policy (instructor extension point — swap in your own):
      - interruptible & not 24/7  -> 'spot'      (checkpoint and ride the discount)
      - duty cycle >= break-even  -> 'reserved'  (steady, high utilization)
      - otherwise                 -> 'on_demand' (spiky / low duty)
    """
    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        # The old call shape has no prices, so retain its deterministic spot
        # recommendation.  The advanced call shape rejects spot only when
        # expected interruption/rework makes it more expensive than on-demand.
        if spot_hr is None or on_demand_hr is None:
            return "spot"
        rate = (
            GPU_INTERRUPTION_RATES.get(gpu_type, 0.05)
            if interruption_rate is None
            else max(0.0, float(interruption_rate))
        )
        if effective_spot_rate(spot_hr, rate) < float(on_demand_hr):
            return "spot"
        if duty < be:
            return "on_demand"
    if duty >= be:
        if on_demand_hr is not None:
            term = reserved_term(job_days, reserved_1yr_hr, reserved_3yr_hr)
            reserved_hr = reserved_3yr_hr if term == "3yr" else reserved_1yr_hr
            if reserved_hr is not None and float(reserved_hr) >= float(on_demand_hr):
                return "on_demand"
        return "reserved"
    return "on_demand"


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }
