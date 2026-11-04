#!/usr/bin/env python3
"""Cross-check the browser model against the Python engine. Requires Node.js."""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from credit_scenarios.model import calculate_losses

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js is required; supply --node /path/to/node")
    data = json.loads((ROOT / "site/dist/data.json").read_text())
    config = json.loads((ROOT / "config/scenarios.json").read_text())
    import csv
    with (ROOT / "data/processed/exposures.csv").open() as f:
        exposures = [{"sector": r["sector"], "exposure_eur": float(r["exposure_eur"])} for r in csv.DictReader(f)]
    assert data["exposures"] == exposures, "Browser exposure snapshot differs"
    assert data["scenario"] == config, "Browser assumptions differ"
    cases = [{"pd":pd,"lgd":lgd,"severity":s} for pd in [0,.015,.1,1] for lgd in [0,.4,1] for s in [0,.5,1,2]]
    script = """
import {readFileSync} from 'node:fs';
import {calculate} from './site/dist/model.mjs';
const {data,cases}=JSON.parse(readFileSync(0,'utf8'));
const results=cases.map(options=>calculate(data.exposures,data.scenario,options));
for (const pd of [-1,NaN,Infinity,true]) {
  let rejected=false; try {calculate(data.exposures,data.scenario,{pd});} catch {rejected=true;}
  if (!rejected) throw Error('Invalid PD accepted');
}
console.log(JSON.stringify(results));
"""
    run = subprocess.run([args.node,"--input-type=module","-e",script],input=json.dumps({"data":data,"cases":cases}),text=True,capture_output=True,cwd=ROOT,check=True)
    results=json.loads(run.stdout)
    mapping={"exposure":"exposure_eur","baseline":"baseline_loss_eur","adverse":"adverse_loss_eur","change":"increase_eur","pdCaps":"pd_cap_count","lgdCaps":"lgd_cap_count"}
    for options,actual in zip(cases,results,strict=True):
        c=copy.deepcopy(config)
        for sector in c["sectors"].values():
            sector["baseline_pd"]=options["pd"]
            sector["baseline_lgd"]=options["lgd"]
            sector["adverse_pd_multiplier"]=1+options["severity"]*(sector["adverse_pd_multiplier"]-1)
            sector["adverse_lgd_uplift"]*=options["severity"]
        expected=calculate_losses(exposures,c)
        for js,py in mapping.items():
            assert math.isclose(actual["totals"][js],expected["totals"][py],rel_tol=1e-12,abs_tol=0.001),(options,js)
        for row,segment in zip(actual["rows"],expected["segments"],strict=True):
            assert row["sector"]==segment["sector"]
            for js,py in [("baseline","baseline_loss_eur"),("adverse","adverse_loss_eur"),("change","increase_eur"),("adversePd","adverse_pd"),("adverseLgd","adverse_lgd")]:
                assert math.isclose(row[js],segment[py],rel_tol=1e-12,abs_tol=0.001),(options,row["sector"],js)
    print(f"PASS: browser inputs match Python inputs; {len(cases)} scenarios match the Python engine, including zero losses, no shock and caps; invalid PD inputs rejected.")

if __name__=="__main__":
    main()
