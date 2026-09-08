"""Local PETEY Plus plan previews and capability estimates."""

from __future__ import annotations

import copy
import math


PLAN_CATEGORIES = ("chat", "images", "video", "voice")
QUALITY_LEVELS = ("economy", "balanced", "premium")
DEFAULT_PLAN = {
    "monthly_budget": 25,
    "quality": "balanced",
    "mix": {"chat": 45, "images": 25, "video": 20, "voice": 10},
    "overage_mode": "stop",
}

# Planning rate card: estimated wholesale cost for one representative unit.
# The hosted billing gateway will replace these with versioned live rates.
UNIT_RATES = {
    "economy": {"chat": 0.003, "images": 0.04, "video": 0.04, "voice": 0.002},
    "balanced": {"chat": 0.008, "images": 0.08, "video": 0.10, "voice": 0.006},
    "premium": {"chat": 0.03, "images": 0.20, "video": 0.28, "voice": 0.018},
}
UNIT_LABELS = {
    "chat": "chat exchanges",
    "images": "generated images",
    "video": "video seconds",
    "voice": "voice minutes",
}


def normalize_plan(value: dict | None) -> dict:
    """Validate and normalize a saved plan preview."""
    source = value if isinstance(value, dict) else {}
    try:
        budget = int(round(float(source.get("monthly_budget", DEFAULT_PLAN["monthly_budget"]))))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Monthly budget must be a number.") from None
    if not 10 <= budget <= 150:
        raise ValueError("Monthly budget must be between $10 and $150.")
    quality = str(source.get("quality") or DEFAULT_PLAN["quality"])
    if quality not in QUALITY_LEVELS:
        raise ValueError("Choose Economy, Balanced, or Premium quality.")
    overage = str(source.get("overage_mode") or "stop")
    if overage not in {"stop", "top_up"}:
        raise ValueError("Choose whether usage stops or asks for a top-up.")
    supplied_mix = source.get("mix") if isinstance(source.get("mix"), dict) else {}
    raw = {}
    for category in PLAN_CATEGORIES:
        try:
            raw[category] = max(0.0, min(100.0, float(
                supplied_mix.get(category, DEFAULT_PLAN["mix"][category])
            )))
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"The {category} mix must be a number.") from None
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("Give at least one capability part of the monthly budget.")
    normalized = {
        category: int(round(raw[category] * 100 / total))
        for category in PLAN_CATEGORIES
    }
    normalized[max(PLAN_CATEGORIES, key=lambda item: raw[item])] += 100 - sum(normalized.values())
    return {
        "monthly_budget": budget,
        "quality": quality,
        "mix": normalized,
        "overage_mode": overage,
    }


def estimate_plan(value: dict | None) -> dict:
    """Break a monthly payment into operating shares and estimated capabilities."""
    plan = normalize_plan(value)
    budget = float(plan["monthly_budget"])
    platform = round(max(2.0, budget * 0.25), 2)
    payment_reserve = round(0.30 + budget * 0.04, 2)
    usage_pool = round(max(0.0, budget - platform - payment_reserve), 2)
    rates = UNIT_RATES[plan["quality"]]
    capabilities = {}
    for category in PLAN_CATEGORIES:
        share = plan["mix"][category]
        allocated = round(usage_pool * share / 100, 2)
        count = math.floor(allocated / rates[category]) if allocated else 0
        capabilities[category] = {
            "allocation_percent": share,
            "allocated_dollars": allocated,
            "estimated_units": count,
            "unit_label": UNIT_LABELS[category],
        }
    return {
        "plan": copy.deepcopy(plan),
        "breakdown": {
            "monthly_payment": round(budget, 2),
            "platform_and_support": platform,
            "payments_and_reserve": payment_reserve,
            "ai_usage": usage_pool,
        },
        "capabilities": capabilities,
        "currency": "USD",
        "checkout_available": False,
        "estimate_notice": (
            "Planning estimate based on representative requests. Final allowances will use "
            "the hosted PETEY rate card and can change when provider prices change."
        ),
    }
