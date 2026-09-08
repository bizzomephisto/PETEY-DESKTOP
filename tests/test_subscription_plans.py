import tempfile
import unittest
from unittest.mock import MagicMock

from petey.desktop_state import DesktopState
from petey.subscription_plans import estimate_plan, normalize_plan
from web.desktop_app import create_desktop_app


class SubscriptionPlanTests(unittest.TestCase):
    def test_estimate_breaks_payment_into_balanced_capabilities(self):
        estimate = estimate_plan({
            "monthly_budget": 25,
            "quality": "balanced",
            "mix": {"chat": 40, "images": 30, "video": 20, "voice": 10},
            "overage_mode": "stop",
        })

        breakdown = estimate["breakdown"]
        self.assertAlmostEqual(
            breakdown["monthly_payment"],
            breakdown["platform_and_support"] + breakdown["payments_and_reserve"] + breakdown["ai_usage"],
        )
        self.assertGreater(estimate["capabilities"]["chat"]["estimated_units"], 0)
        self.assertGreater(estimate["capabilities"]["images"]["estimated_units"], 0)
        self.assertFalse(estimate["checkout_available"])
        self.assertTrue(estimate["balance_policy"]["rolls_over"])
        self.assertFalse(estimate["balance_policy"]["expires"])
        self.assertIn("$5", estimate["balance_policy"]["example"])

    def test_mix_is_normalized_and_invalid_budget_is_rejected(self):
        plan = normalize_plan({
            "monthly_budget": 30,
            "quality": "premium",
            "mix": {"chat": 10, "images": 10, "video": 10, "voice": 10},
            "overage_mode": "top_up",
        })

        self.assertEqual(sum(plan["mix"].values()), 100)
        self.assertEqual(plan["overage_mode"], "top_up")
        self.assertEqual(normalize_plan({"monthly_budget": 5})["monthly_budget"], 5)
        with self.assertRaisesRegex(ValueError, "between"):
            normalize_plan({"monthly_budget": 2})
        with self.assertRaisesRegex(ValueError, "increments"):
            normalize_plan({"monthly_budget": 7})

    def test_five_dollars_can_support_light_use_for_more_than_one_month(self):
        estimate = estimate_plan({"monthly_budget": 5, "quality": "balanced"})

        self.assertGreaterEqual(estimate["capabilities"]["chat"]["estimated_units"], 800)
        self.assertGreaterEqual(estimate["capabilities"]["images"]["estimated_units"], 150)
        self.assertGreaterEqual(estimate["capabilities"]["voice"]["estimated_units"], 250)

    def test_efficient_quality_produces_more_units_than_premium(self):
        base = {
            "monthly_budget": 20,
            "mix": {"chat": 25, "images": 25, "video": 25, "voice": 25},
            "overage_mode": "stop",
        }
        economy = estimate_plan({**base, "quality": "economy"})
        premium = estimate_plan({**base, "quality": "premium"})

        for category in ("chat", "images", "video", "voice"):
            self.assertGreater(
                economy["capabilities"][category]["estimated_units"],
                premium["capabilities"][category]["estimated_units"],
            )

    def test_preview_endpoint_estimates_without_saving_and_put_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state = DesktopState(directory)
            client = create_desktop_app(
                state=state, memory=MagicMock(), job_manager=MagicMock()
            ).test_client()
            preview = {
                "monthly_budget": 60,
                "quality": "premium",
                "mix": {"chat": 25, "images": 25, "video": 25, "voice": 25},
                "overage_mode": "top_up",
            }

            estimated = client.post("/api/desktop/plan", json=preview)
            self.assertEqual(estimated.status_code, 200)
            self.assertEqual(estimated.json["plan"]["monthly_budget"], 60)
            self.assertEqual(DesktopState(directory).plan_preview["monthly_budget"], 25)

            saved = client.put("/api/desktop/plan", json=preview)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(DesktopState(directory).plan_preview["monthly_budget"], 60)
            self.assertEqual(client.put("/api/desktop/plan", json={"monthly_budget": 2}).status_code, 400)
            self.assertEqual(client.put("/api/desktop/plan", json={"monthly_budget": 7}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
