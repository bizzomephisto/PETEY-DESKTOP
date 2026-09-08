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

# Planning rate card: estimated provider cost for one representative unit. These
# rates favor efficient routing while leaving room for normal variation in prompt
# size, resolution, and model choice. The hosted gateway will replace them with a
# versioned live rate card.
UNIT_RATES = {
    "economy": {"chat": 0.0005, "images": 0.0025, "video": 0.004, "voice": 0.0008},
    "balanced": {"chat": 0.002, "images": 0.006, "video": 0.012, "voice": 0.0015},
    "premium": {"chat": 0.008, "images": 0.018, "video": 0.035, "voice": 0.004},
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
        raise ValueError("Recurring contribution must be a number.") from None
    if not 5 <= budget <= 150:
        raise ValueError("Recurring contribution must be between $5 and $150.")
    if budget % 5:
        raise ValueError("Recurring contribution must use $5 increments.")
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
        raise ValueError("Give at least one capability part of the recurring contribution.")
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
    platform = round(max(0.75, budget * 0.15), 2)
    payment_reserve = round(0.30 + budget * 0.035, 2)
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
        "balance_policy": {
            "rolls_over": True,
            "expires": False,
            "description": "Unused AI balance carries forward and does not expire.",
            "example": "With light use, a single $5 contribution could last several months.",
        },
        "estimate_notice": (
            "Planning estimate calibrated to current public provider rates, efficient routing, "
            "and typical request sizes. Unused AI balance carries forward and does not reset. "
            "Long requests use more, and future estimates can change with provider prices."
        ),
    }
