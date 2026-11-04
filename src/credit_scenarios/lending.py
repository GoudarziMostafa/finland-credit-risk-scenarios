"""Reproduce a verified Bank of Finland MFI loan-stock snapshot."""
import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.boffsaopendata.fi/v4"
INDUSTRIES = {"ZZ": "total", "C": "manufacturing", "F": "construction", "L": "real_estate"}
SERIES = {code: f"M.A.0.A.A20.A.A.U6.2241.{code}.Z01.A.A.0.A.0.A.0" for code in INDUSTRIES}
REFERENCE_DATE = "2025-12-31"


def _items(document):
    if document.get("totalPages") != 1:
        raise ValueError("Incomplete/paginated source response")
    items = document.get("items", [])
    if document.get("totalCount") != 4 or len(items) != 4:
        raise ValueError("Expected exactly four source series")
    names = [item["name"] for item in items]
    if len(set(names)) != 4 or set(names) != set(SERIES.values()):
        raise ValueError("Unexpected, missing or duplicate source series")
    return {item["name"]: item for item in items}


def transform(series_document, observations_document):
    """Return observed/derived exposure rows after validating source metadata."""
    series, observations = _items(series_document), _items(observations_document)
    values = {}
    for code, name in SERIES.items():
        info = series[name]
        dimensions = sorted(info["dimensions"], key=lambda d: d["position"])
        if [d["value"] for d in dimensions] != name.split("."):
            raise ValueError("Series code and dimension metadata disagree")
        attrs = {entry["name"]: entry["value"] for entry in info["metadatas"]}
        if (attrs.get("UNIT"), attrs.get("UNIT_MULT"), attrs.get("COLLECTION")) != ("EUR", "6", "E"):
            raise ValueError("Expected period-end EUR millions")
        matches = [o for o in observations[name]["observations"] if o["period"] == REFERENCE_DATE]
        if len(matches) != 1 or matches[0].get("periodCode") != "2025M12":
            raise ValueError(f"Missing/duplicate/mismatched reference observation: {name}")
        raw = matches[0].get("value")
        if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
            raise ValueError("Missing/non-numeric loan stock")
        value = Decimal(str(raw))
        if not value.is_finite() or value < 0:
            raise ValueError("Invalid loan stock")
        values[INDUSTRIES[code]] = value * Decimal(1_000_000)
    residual = values["total"] - sum(values[s] for s in ("manufacturing", "construction", "real_estate"))
    if residual < 0:
        raise ValueError("Industry loans exceed source total")
    values["other"] = residual
    rows = [{
        "sector": sector, "exposure_eur": float(values[sector]),
        "source_industry": next((c for c, s in INDUSTRIES.items() if s == sector), "residual"),
        "reference_date": REFERENCE_DATE,
        "value_status": "derived residual" if sector == "other" else "observed",
        "exposure_basis": "outstanding stock; NPLs not deducted",
    } for sector in ("manufacturing", "construction", "real_estate", "other")]
    return rows, float(values["total"])


def run(refresh=False, root=ROOT):
    rawdir, processed = root / "data/raw", root / "data/processed"
    rawdir.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    paths = {key: rawdir / f"bof_mfi_{key}.json" for key in ("series", "observations", "manifest")}
    if refresh:
        query = urlencode({"seriesName": ";".join(SERIES.values()), "pageSize": 100})
        payloads = {}
        manifest = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "requests": {}, "sha256": {}}
        for key in ("series", "observations"):
            url = f"{BASE}/{key}/MFI_PUBL?{query}"
            with urlopen(url, timeout=40) as response:
                raw = response.read()
                manifest["licence_header"] = response.headers.get("License", manifest.get("licence_header"))
            payloads[key] = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            manifest["requests"][key] = url
            manifest["sha256"][str(paths[key].relative_to(root))] = hashlib.sha256(payloads[key]).hexdigest()
        rows, total = transform(*(json.loads(payloads[k], parse_float=Decimal) for k in ("series", "observations")))
        for key, data in payloads.items():
            paths[key].write_bytes(data)
        paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    else:
        manifest = json.loads(paths["manifest"].read_text())
        for name, digest in manifest["sha256"].items():
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Snapshot hash mismatch: {name}")
        rows, total = transform(*(json.loads(paths[k].read_bytes(), parse_float=Decimal)
                                  for k in ("series", "observations")))
    with (processed / "exposures.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        **manifest, "reference_period": "2025Q4", "reference_date": REFERENCE_DATE,
        "reported_total_exposure_eur": total, "units": "EUR; source EUR millions multiplied by 1,000,000",
        "coverage": "MFIs excluding Bank of Finland; domestic non-financial corporations, excluding housing corporations; all currencies expressed in euros.",
        "industry_classification": "TOL 2008. C/F/L series end December 2025; total continues later. Common cutoff deliberately fixed at December 2025.",
        "other_definition": "Total less manufacturing, construction and real estate; includes remaining and unclassified industries.",
        "exposure_definition": "Outstanding loan stock used as fixed EAD proxy. Existing non-performing balances are retained; compatible NPL balances were not included in this snapshot.",
        "interpretation": "Scenario loss proxy on total outstanding stocks, not an estimate of new defaults on performing loans or IFRS 9 provisions.",
        "housing_scope_corroboration": "https://www.suomenpankki.fi/en/statistics/statistical-news/mfi-balance-sheet/2026/household-bank-loans-almost-unchanged-year-on-year-in-december-2025/",
    }
    (processed / "lending_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return processed / "exposures.csv"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Fetch revised source vintage; default verifies and replays snapshots.")
    print(run(parser.parse_args().refresh))
