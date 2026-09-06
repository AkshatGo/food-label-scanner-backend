import unittest

from app.services.fssai_rating import calculate_inr


class FssaiRatingTests(unittest.TestCase):
    def test_solid_draft_rating_uses_required_fields(self):
        result = calculate_inr(
            {
                "energy_kcal": 160,
                "total_sugars_g": 1,
                "saturated_fat_g": 1.5,
                "sodium_mg": 170,
                "dietary_fiber_g": 1,
                "protein_g": 2,
            },
            category="solid",
        )
        self.assertEqual(result["inr_score"], 2)
        self.assertEqual(result["rating_stars"], 3.5)
        self.assertEqual(result["missing_fields"], [])

    def test_missing_values_are_estimated_as_zero(self):
        result = calculate_inr({"sodium_mg": 170}, category="solid")
        self.assertEqual(result["status"], "estimated_missing_as_zero")
        self.assertIn("energy_kcal", result["missing_fields_treated_as_zero"])


if __name__ == "__main__":
    unittest.main()