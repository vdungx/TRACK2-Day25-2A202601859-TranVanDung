import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finops import pricing
from finops import sustainability
from missions import carbon_scheduling, m2_inference_levers, m3_purchasing


def test_cache_break_even_policy():
    assert pricing.cache_is_worth_it(2.0, 1.0, 0.10) is True
    assert pricing.cache_is_worth_it(1.0, 1.0, 0.10) is False
    assert pricing.cache_is_worth_it(0.0, 0.0, 0.10) is False


def test_m2_applies_cache_policy_and_reports_tiers():
    result = m2_inference_levers.run(verbose=False)
    cache = result["cache_analysis"]
    assert cache["enabled_groups"] > 0
    assert {row["route_tier"] for row in cache["by_tier"]} == {"small", "large"}
    assert cache["cache_savings_usd"] > 0


def test_advanced_tier_accounts_for_gpu_interruption_rate():
    assert pricing.recommend_tier(
        2,
        True,
        gpu_type="A10G",
        job_days=30,
        on_demand_hr=1.0,
        spot_hr=0.99,
    ) == "on_demand"
    assert pricing.recommend_tier(
        2,
        True,
        gpu_type="H100",
        job_days=30,
        on_demand_hr=2.5,
        spot_hr=1.5,
    ) == "spot"
    assert pricing.reserved_term(30, reserved_1yr_hr=0.8, reserved_3yr_hr=0.6) == "1yr"
    assert pricing.reserved_term(365, reserved_1yr_hr=0.8, reserved_3yr_hr=0.6) == "3yr"


def test_m3_reports_duration_aware_reserved_term():
    result = m3_purchasing.run(verbose=False)
    advanced = result["advanced"]["recommendations"]
    infer_chat = next(row for row in advanced if row["job_id"] == "job-infer-chat")
    assert infer_chat["tier"] == "reserved"
    assert infer_chat["reserved_term"] == "1yr"
    assert result["advanced_savings_delta_pct"] < 0


def test_carbon_scheduler_compares_all_regions():
    result = carbon_scheduling.run(verbose=False)
    assert result["cleanest_region"] == "europe-north1"
    assert result["cheapest_region"] == "us-east-wa"
    assert len(result["regions"]) == len(sustainability.REGION_CARBON) == 5
    assert result["carbon_saved_g"] > 0
    assert len(result["interruptible_jobs"]) == 5
