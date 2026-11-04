"""Checks against the real snapshot and cross-source integration contract."""
import csv
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "data/processed/exposures.csv").open() as handle:
            cls.exposures = list(csv.DictReader(handle))
        cls.meta = json.loads((ROOT / "data/processed/lending_metadata.json").read_text())
        cls.config = json.loads((ROOT / "config/scenarios.json").read_text())
        with (ROOT / "data/processed/macro.csv").open() as handle:
            cls.macro = list(csv.DictReader(handle))

    def test_observed_exposures_reconcile_to_source_total(self):
        sectors = [row["sector"] for row in self.exposures]
        self.assertEqual(len(sectors), len(set(sectors)), "Duplicate exposure sectors")
        self.assertEqual(set(sectors), set(self.config["sectors"]))
        values = [float(row["exposure_eur"]) for row in self.exposures]
        self.assertTrue(all(math.isfinite(x) and x >= 0 for x in values))
        self.assertGreater(sum(values), 0)
        self.assertAlmostEqual(
            math.fsum(values), float(self.meta["reported_total_exposure_eur"]), delta=.01,
            msg="Industry exposures must reconcile to the independently documented source total",
        )

    def test_macro_observations_are_unique_and_finite(self):
        keys = [(r["period"], r["sector"], r["indicator"]) for r in self.macro]
        self.assertEqual(len(keys), len(set(keys)))
        for row in self.macro:
            with self.subTest(key=(row["period"], row["sector"], row["indicator"])):
                value = float(row["value"])
                self.assertTrue(math.isfinite(value))
                self.assertRegex(row["period"], r"^\d{4}Q[1-4]$")
                if row["indicator"] == "bankruptcies_count":
                    self.assertGreaterEqual(value, 0)
                    self.assertEqual(value, int(value))

    def test_bankruptcy_groups_reconcile_each_quarter(self):
        by_period = {}
        for row in self.macro:
            if row["indicator"] == "bankruptcies_count":
                by_period.setdefault(row["period"], {})[row["sector"]] = float(row["value"])
        self.assertGreaterEqual(len(by_period), 8)
        for period, values in by_period.items():
            with self.subTest(period=period):
                self.assertEqual(set(values), {"total", "manufacturing", "construction", "real_estate", "other"})
                self.assertEqual(values["total"], sum(v for k, v in values.items() if k != "total"))


if __name__ == "__main__":
    unittest.main()
