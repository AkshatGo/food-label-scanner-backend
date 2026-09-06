import unittest

from app.services.analysis_service import analyze_label
from app.services.nlp_service import clean_ocr_text


class AnalysisServiceTests(unittest.TestCase):
    def test_missing_fssai_fields_are_not_detected_not_violations(self):
        result = analyze_label("Ingredients: oats\nEnergy 100 kcal")
        statuses = result["fssai"]["statuses"]

        self.assertIn("NOT_DETECTED", {item["status"] for item in statuses})
        self.assertFalse(
            any(
                item["status"] == "POTENTIAL_ISSUE"
                for item in statuses
                if item["field"] in result["fssai"]["not_detected"]
            )
        )

    def test_missing_nutrition_values_are_zero_for_inr(self):
        result = analyze_label("Energy 100 kcal")
        self.assertTrue(result["inr"]["missing_values_treated_as_zero"])
        self.assertIsInstance(result["inr"]["score"], int)

    def test_nlp_cleanup_normalizes_ocr_whitespace(self):
        self.assertEqual(clean_ocr_text(" Ingredients |  oats\n\n\nSugar "), "Ingredients I oats\n\nSugar")


if __name__ == "__main__":
    unittest.main()