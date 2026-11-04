import copy
import math
import unittest
from credit_scenarios.model import calculate_losses, sensitivity, validate_exposures, validate_scenarios


def fixture():
    return ([{"sector": "example", "exposure_eur": 10_000_000}], {
        "horizon_years": 1, "sectors": {"example": {
            "baseline_pd": .01, "baseline_lgd": .4,
            "adverse_pd_multiplier": 3, "adverse_lgd_uplift": .1}}})


class ModelTests(unittest.TestCase):
    def test_known_financial_example(self):
        totals = calculate_losses(*fixture())["totals"]
        for key, value in {"baseline_loss_eur": 40000, "adverse_loss_eur": 150000,
                           "increase_eur": 110000, "adverse_loss_rate": .015}.items():
            self.assertAlmostEqual(totals[key], value)

    def test_heterogeneous_sectors_and_weighted_rates(self):
        records, config = fixture()
        records.append({"sector": "second", "exposure_eur": 20_000_000})
        config["sectors"]["second"] = {"baseline_pd": .02, "baseline_lgd": .5,
                                       "adverse_pd_multiplier": 2, "adverse_lgd_uplift": .1}
        result = calculate_losses(records, config)
        self.assertAlmostEqual(result["totals"]["baseline_loss_eur"], 240000)
        self.assertAlmostEqual(result["totals"]["adverse_loss_eur"], 630000)
        self.assertAlmostEqual(result["totals"]["baseline_loss_rate"], .008)
        for key in ("exposure_eur", "baseline_loss_eur", "adverse_loss_eur", "increase_eur"):
            self.assertAlmostEqual(result["totals"][key], sum(r[key] for r in result["segments"]))

    def test_zero_pd_or_exposure(self):
        for field in ("pd", "exposure"):
            records, config = fixture()
            if field == "pd":
                config["sectors"]["example"]["baseline_pd"] = 0
            else:
                records[0]["exposure_eur"] = 0
            totals = calculate_losses(records, config)["totals"]
            for key in ("baseline_loss_eur", "adverse_loss_eur", "adverse_loss_rate"):
                self.assertEqual(totals[key], 0)

    def test_no_shock(self):
        records, config = fixture()
        config["sectors"]["example"].update(adverse_pd_multiplier=1, adverse_lgd_uplift=0)
        self.assertEqual(calculate_losses(records, config)["totals"]["increase_eur"], 0)

    def test_caps_bound_loss_and_are_visible(self):
        records, config = fixture()
        config["sectors"]["example"].update(baseline_pd=.8, baseline_lgd=.8,
                                            adverse_pd_multiplier=2, adverse_lgd_uplift=.3)
        r = calculate_losses(records, config)
        self.assertEqual(r["totals"]["adverse_loss_eur"], 10_000_000)
        self.assertEqual(r["totals"]["pd_cap_count"], 1)
        self.assertEqual(r["totals"]["lgd_cap_count"], 1)

    def test_monotonicity_including_plateau(self):
        records, config = fixture()
        config["sectors"]["example"].update(baseline_pd=.4, baseline_lgd=.7)
        grid = sensitivity(records, config, [0, 1, 2, 3, 4], [0, .1, .3, .5])
        values = {(r["pd_multiplier"], r["lgd_uplift"]): r["loss_eur"] for r in grid}
        for u in (0, .1, .3, .5):
            values_pd = [values[m, u] for m in (0, 1, 2, 3, 4)]
            self.assertEqual(values_pd, sorted(values_pd))
        for m in (0, 1, 2, 3, 4):
            values_lgd = [values[m, u] for u in (0, .1, .3, .5)]
            self.assertEqual(values_lgd, sorted(values_lgd))
        self.assertEqual(values[3, .5], values[4, .5])

    def test_sensitivity_reference_and_units(self):
        grid = sensitivity(*fixture(), pd_multipliers=[1, 3], lgd_uplifts=[0, .1])
        self.assertAlmostEqual(grid[0]["loss_eur"], 40000)
        self.assertAlmostEqual(grid[-1]["loss_eur"], 150000)
        self.assertEqual(len(sensitivity(*fixture())), 35)

    def test_no_input_mutation(self):
        records, config = fixture()
        before = copy.deepcopy((records, config))
        calculate_losses(records, config)
        sensitivity(records, config)
        self.assertEqual((records, config), before)

    def test_invalid_exposures(self):
        for value in (None, True, False, "100", -1, math.nan, math.inf, -math.inf, 10**400):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                validate_exposures([{"sector": "example", "exposure_eur": value}])
        with self.assertRaisesRegex(ValueError, "exposure_eur"):
            validate_exposures([{"sector": "example"}])

    def test_invalid_probabilities_before_caps(self):
        for key in ("baseline_pd", "baseline_lgd"):
            for value in (None, True, "0.1", -.1, 1.1, math.nan, math.inf):
                records, config = fixture()
                config["sectors"]["example"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    calculate_losses(records, config)

    def test_invalid_stress_and_horizon(self):
        for key, values in {"adverse_pd_multiplier": [-1, math.inf, True, None],
                            "adverse_lgd_uplift": [-.1, 1.1, math.nan, None]}.items():
            for value in values:
                records, config = fixture()
                config["sectors"]["example"][key] = value
                with self.assertRaises(ValueError):
                    calculate_losses(records, config)
        for horizon in (None, True, 0, 2, math.nan):
            _, config = fixture()
            config["horizon_years"] = horizon
            with self.assertRaises(ValueError):
                validate_scenarios(config)

    def test_sector_integrity(self):
        records, config = fixture()
        for rows in [[], records + records, [{"sector": "", "exposure_eur": 1}],
                     [{"sector": None, "exposure_eur": 1}]]:
            with self.assertRaises(ValueError):
                calculate_losses(rows, config)
        with self.assertRaisesRegex(ValueError, "sector mismatch"):
            calculate_losses([{"sector": "unknown", "exposure_eur": 1}], config)
        config["sectors"]["missing"] = copy.deepcopy(config["sectors"]["example"])
        with self.assertRaisesRegex(ValueError, "sector mismatch"):
            calculate_losses(records, config)

    def test_invalid_sensitivity_axes(self):
        for multipliers, uplifts in [([], [0]), ([1], []), ([1, 1], [0]), ([1], [0, 0]),
                                    ([-1], [0]), ([1], [-.1]), ([math.nan], [0]), ([1], [1.1]), (1, [0])]:
            with self.assertRaises(ValueError):
                sensitivity(*fixture(), pd_multipliers=multipliers, lgd_uplifts=uplifts)

    def test_invalid_shape_and_overflow(self):
        for records in (None, "bad", {"sector": "example", "exposure_eur": 1}, [None]):
            with self.assertRaises(ValueError):
                validate_exposures(records)
        for config in (None, [], {}, {"horizon_years": 1, "sectors": []}):
            with self.assertRaises(ValueError):
                validate_scenarios(config)
        with self.assertRaisesRegex(ValueError, "finite numeric range"):
            validate_exposures([{"sector": "a", "exposure_eur": 1e308},
                                {"sector": "b", "exposure_eur": 1e308}])

if __name__ == "__main__":
    unittest.main()
