import copy
import csv
import hashlib
import json
from pathlib import Path
import unittest
from credit_scenarios.lending import transform as lending_transform
from credit_scenarios.macro import transform as macro_transform, DIMENSIONS, INDUSTRIES, months_to

ROOT = Path(__file__).resolve().parents[1]


def macro_fixture(months=None):
    months = months or ["2020M01", "2020M02", "2020M03"]
    categories = [months, ["SSS", "C", "F", "L"], ["SSS"], ["kylkm"]]
    data = {"id": DIMENSIONS, "size": [len(months), 4, 1, 1],
            "dimension": {}, "value": [100, 20, 30, 10] * len(months)}
    for name, codes in zip(DIMENSIONS, categories):
        data["dimension"][name] = {"category": {"index": {k: i for i, k in enumerate(codes)}}}
    return data, months


class SourceTests(unittest.TestCase):
    def test_raw_snapshot_integrity(self):
        for filename in ("bof_mfi_manifest.json", "statfin_kony_13fd_manifest.json"):
            manifest = json.loads((ROOT / "data/raw" / filename).read_text())
            for name, digest in manifest["sha256"].items():
                with self.subTest(file=name):
                    self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

    def test_lending_replay_matches_processed_snapshot(self):
        series = json.loads((ROOT / "data/raw/bof_mfi_series.json").read_text())
        observations = json.loads((ROOT / "data/raw/bof_mfi_observations.json").read_text())
        rows, total = lending_transform(series, observations)
        with (ROOT / "data/processed/exposures.csv").open() as handle:
            actual = {r["sector"]: float(r["exposure_eur"]) for r in csv.DictReader(handle)}
        self.assertEqual(set(actual), {r["sector"] for r in rows})
        for row in rows:
            self.assertAlmostEqual(actual[row["sector"]], row["exposure_eur"], delta=.01)
        self.assertAlmostEqual(total, 62_915_537_568.80, delta=.01)

    def test_lending_rejects_wrong_units_date_or_pagination(self):
        series = json.loads((ROOT / "data/raw/bof_mfi_series.json").read_text())
        observations = json.loads((ROOT / "data/raw/bof_mfi_observations.json").read_text())
        broken = copy.deepcopy(series)
        next(m for m in broken["items"][0]["metadatas"] if m["name"] == "UNIT_MULT")["value"] = "0"
        with self.assertRaisesRegex(ValueError, "EUR millions"):
            lending_transform(broken, observations)
        broken = copy.deepcopy(observations)
        broken["items"][0]["observations"] = [
            x for x in broken["items"][0]["observations"] if x["period"] != "2025-12-31"]
        with self.assertRaisesRegex(ValueError, "reference observation"):
            lending_transform(series, broken)
        broken = copy.deepcopy(observations)
        broken["totalPages"] = 2
        with self.assertRaisesRegex(ValueError, "paginated"):
            lending_transform(series, broken)

    def test_macro_replay_matches_processed_snapshot(self):
        query = json.loads((ROOT / "data/raw/statfin_kony_13fd_query.json").read_text())
        months = next(q["selection"]["values"] for q in query["query"] if q["code"] == "timeperiod_m")
        raw = json.loads((ROOT / "data/raw/statfin_kony_13fd_response.json").read_text())
        rows = macro_transform(raw, months)
        with (ROOT / "data/processed/macro.csv").open() as handle:
            actual = list(csv.DictReader(handle))
        self.assertEqual([{**r, "value": str(r["value"])} for r in rows], actual)

    def test_macro_uses_category_positions_not_object_order(self):
        data, months = macro_fixture()
        idx = data["dimension"]["toimiala_80_20180101"]["category"]["index"]
        data["dimension"]["toimiala_80_20180101"]["category"]["index"] = dict(reversed(list(idx.items())))
        values = {r["sector"]: r["value"] for r in macro_transform(data, months)}
        self.assertEqual(values, {"total": 300, "manufacturing": 60, "construction": 90, "real_estate": 30, "other": 120})

    def test_macro_rejects_missing_suppressed_invalid_counts(self):
        for value in (None, "..", True, -1, float("nan"), float("inf"), .5):
            data, months = macro_fixture()
            data["value"][1] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                macro_transform(data, months)

    def test_macro_rejects_incomplete_quarters_and_bad_reconciliation(self):
        data, months = macro_fixture(["2020M01", "2020M02"])
        with self.assertRaisesRegex(ValueError, "Incomplete quarter"):
            macro_transform(data, months)
        data, months = macro_fixture()
        data["value"][0] = 5
        with self.assertRaisesRegex(ValueError, "exceed total"):
            macro_transform(data, months)

    def test_macro_validates_period_selection(self):
        for period in ("2025X4", "2025Q5", "2019Q4", "2025Q4extra"):
            with self.assertRaises(ValueError):
                months_to(period)

if __name__ == "__main__":
    unittest.main()
