"""Fetch (--refresh) or replay public StatFin bankruptcy data; no synthetic data."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
API = "https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/kony/13fd.px"
INDUSTRIES = {"SSS": "total", "C": "manufacturing", "F": "construction", "L": "real_estate"}
DIMENSIONS = ["timeperiod_m", "toimiala_80_20180101", "velka_a_oikm_1_20181023", "contentscode"]


def months_to(end_quarter):
    if not re.fullmatch(r"\d{4}Q[1-4]", end_quarter):
        raise ValueError("End quarter must be YYYYQ1 through YYYYQ4")
    year, quarter = int(end_quarter[:4]), int(end_quarter[-1])
    months = [f"{y}M{m:02d}" for y in range(2020, year + 1) for m in range(1, 13)
              if y < year or m <= quarter * 3]
    if not months:
        raise ValueError("End quarter must be 2020Q1 or later")
    return months


def make_query(months):
    return {"query": [
        {"code": code, "selection": {"filter": "item", "values": values}}
        for code, values in zip(DIMENSIONS, [months, list(INDUSTRIES), ["SSS"], ["kylkm"]])
    ], "response": {"format": "json-stat2"}}


def fetch(url, body=None):
    headers = {"User-Agent": "FinlandCreditScenarios/0.1 (public statistical analysis)"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=body, headers=headers), timeout=40) as response:
        raw = response.read()
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def transform(dataset, months):
    """Parse numeric JSON-stat2 category positions and aggregate complete quarters."""
    if not months or len(set(months)) != len(months):
        raise ValueError("Expected unique monthly observations")
    dimensions = dataset["id"]
    if set(dimensions) != set(DIMENSIONS) or len(dimensions) != 4:
        raise ValueError("Unexpected response dimensions")
    expected = dict(zip(DIMENSIONS, [months, list(INDUSTRIES), ["SSS"], ["kylkm"]]))
    codes = {}
    for i, name in enumerate(dimensions):
        index = dataset["dimension"][name]["category"]["index"]
        codes[name] = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        if set(codes[name]) != set(expected[name]) or len(codes[name]) != dataset["size"][i]:
            raise ValueError(f"Unexpected/missing response categories: {name}")
        if isinstance(index, dict) and sorted(index.values()) != list(range(len(index))):
            raise ValueError(f"Invalid category positions: {name}")
    strides = [math.prod(dataset["size"][i + 1:]) for i in range(len(dimensions))]
    values = dataset.get("value", [])
    quarterly, quarter_months = {}, {}
    for month in months:
        if not re.fullmatch(r"\d{4}M(0[1-9]|1[0-2])", month):
            raise ValueError("Invalid month")
        q = f"{month[:4]}Q{(int(month[-2:])-1)//3+1}"
        quarter_months.setdefault(q, set()).add(int(month[-2:]))
        counts = {}
        for industry in INDUSTRIES:
            coord = dict(zip(DIMENSIONS, [month, industry, "SSS", "kylkm"]))
            offset = sum(codes[d].index(coord[d]) * stride for d, stride in zip(dimensions, strides))
            value = values.get(str(offset)) if isinstance(values, dict) else (
                values[offset] if offset < len(values) else None)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Missing/suppressed/non-numeric count: {month}, {industry}")
            if not math.isfinite(value) or value < 0 or int(value) != value:
                raise ValueError(f"Invalid enterprise count: {month}, {industry}")
            counts[INDUSTRIES[industry]] = int(value)
        counts["other"] = counts["total"] - sum(counts[s] for s in ("manufacturing", "construction", "real_estate"))
        if counts["other"] < 0:
            raise ValueError(f"Industries exceed total: {month}")
        bucket = quarterly.setdefault(q, dict.fromkeys(counts, 0))
        for sector, value in counts.items():
            bucket[sector] += value
    for q, found in quarter_months.items():
        end = int(q[-1]) * 3
        if found != set(range(end - 2, end + 1)):
            raise ValueError(f"Incomplete quarter: {q}")
    return [{"period": q, "sector": s, "indicator": "bankruptcies_count", "value": v, "unit": "enterprises"}
            for q, sectors in sorted(quarterly.items()) for s, v in sectors.items()]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def run(refresh=False, end_quarter=None, root=ROOT):
    rawdir, processed = root / "data/raw", root / "data/processed"
    rawdir.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    paths = {key: rawdir / f"statfin_kony_13fd_{key}.json" for key in ("query", "response", "metadata", "manifest")}
    if refresh:
        end_quarter = end_quarter or "2025Q4"
        months = months_to(end_quarter)
        payloads = {"query": json.dumps(make_query(months), separators=(",", ":")).encode()}
        payloads["metadata"] = fetch(API)
        metadata = json.loads(payloads["metadata"])
        available = {v["code"]: set(v["values"]) for v in metadata["variables"]}
        for selection in make_query(months)["query"]:
            if not set(selection["selection"]["values"]) <= available.get(selection["code"], set()):
                raise ValueError("Requested categories not available in current source metadata")
        payloads["response"] = fetch(API, payloads["query"])
        rows = transform(json.loads(payloads["response"]), months)
        manifest = {"source_url": API, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "end_quarter": end_quarter,
                    "sha256": {str(paths[k].relative_to(root)): _sha(b) for k, b in payloads.items()},
                    "licence": "CC BY 4.0", "attribution": "Source: Statistics Finland"}
        for key, value in payloads.items():
            paths[key].write_bytes(value)
        paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    else:
        manifest = json.loads(paths["manifest"].read_text())
        for name, digest in manifest["sha256"].items():
            if _sha((root / name).read_bytes()) != digest:
                raise ValueError(f"Snapshot hash mismatch: {name}")
        if end_quarter is not None and end_quarter != manifest["end_quarter"]:
            raise ValueError("Replay end-quarter differs from saved query; use --refresh explicitly")
        end_quarter = manifest["end_quarter"]
        query = json.loads(paths["query"].read_text())
        months = next(q["selection"]["values"] for q in query["query"] if q["code"] == "timeperiod_m")
        if months != months_to(end_quarter):
            raise ValueError("Saved query does not match declared date range")
        rows = transform(json.loads(paths["response"].read_bytes()), months)
    with (processed / "macro.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["period", "sector", "indicator", "value", "unit"])
        writer.writeheader()
        writer.writerows(rows)
    (processed / "macro_metadata.json").write_text(json.dumps({
        **manifest, "period_start": "2020Q1", "period_end": end_quarter,
        "indicator": "bankruptcies_count", "unit": "enterprises",
        "aggregation": "Quarterly sum of monthly first-petition enterprise counts; other is total minus C,F,L.",
        "scope": "All legal forms, including natural persons; not a matched population of bank borrowers.",
        "interpretation": "Instigated bankruptcy proceedings, not concluded bankruptcies or credit defaults. Never used as PD.",
    }, indent=2) + "\n")
    return processed / "macro.csv"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--end-quarter", default=None)
    args = parser.parse_args()
    print(run(args.refresh, args.end_quarter))
