import importlib.util
from pathlib import Path
import unittest
from credit_scenarios.reporting import result_tables
from credit_scenarios.model import validate_scenarios

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("report_build", ROOT / "scripts/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def inputs(pd=.03, lgd=.2, exposure=1_000_000):
    return [{"sector": "example", "exposure_eur": exposure}], {
        "horizon_years": 1, "sectors": {"example": {
            "baseline_pd": pd, "baseline_lgd": lgd,
            "adverse_pd_multiplier": 2, "adverse_lgd_uplift": .1}},
        "sensitivity": {"pd_multipliers": [1, 2], "lgd_uplifts": [0, .1]}}


class ReportingTests(unittest.TestCase):
    def test_configured_sensitivity_axes_are_used(self):
        _, _, grid = result_tables(*inputs())
        self.assertEqual(len(grid), 4)
        self.assertEqual(set(grid.pd_multiplier), {1, 2})

    def test_note_uses_actual_assumptions(self):
        result, segments, _ = result_tables(*inputs())
        note = builder.analysis_note(result, segments, "2025Q4")
        self.assertIn("3.00%", note)
        self.assertIn("20.0%", note)
        self.assertIn("Adverse loss is 3.00 times baseline", note)

    def test_zero_baseline_and_zero_exposure_reports(self):
        for records, config in (inputs(pd=0), inputs(lgd=0), inputs(exposure=0)):
            result, segments, _ = result_tables(records, config)
            note = builder.analysis_note(result, segments, "2025Q4")
            self.assertIn("baseline loss is zero", note)
            self.assertFalse(segments.exposure_share.isna().any())
            self.assertFalse(segments.share_of_increase.isna().any())

    def test_no_shock_has_no_spurious_driver(self):
        records, config = inputs()
        config["sectors"]["example"].update(adverse_pd_multiplier=1, adverse_lgd_uplift=0)
        result, segments, _ = result_tables(records, config)
        self.assertIn("no positive portfolio-level deterioration", builder.analysis_note(result, segments, "2025Q4"))

    def test_non_euro_config_rejected(self):
        _, config = inputs()
        config["currency"] = "USD"
        with self.assertRaisesRegex(ValueError, "EUR"):
            validate_scenarios(config)

if __name__ == "__main__":
    unittest.main()
