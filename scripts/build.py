#!/usr/bin/env python3
"""Rebuild the review package offline from the checked-in source snapshots."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
sys.path.insert(0, str(ROOT / "src"))

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from credit_scenarios.reporting import (
    LABELS, load_inputs, result_tables, plot_losses, plot_sensitivity,
    plot_context, save_fig, manifest,
)

def analysis_note(result, segments, period):
    t = result["totals"]
    largest = segments.sort_values("increase_eur", ascending=False).iloc[0]
    label = LABELS.get(largest.sector, largest.sector)
    ratio_text = (
        f"Adverse loss is {t['adverse_loss_eur']/t['baseline_loss_eur']:.2f} times baseline."
        if t["baseline_loss_eur"] else "A baseline multiple is undefined because baseline loss is zero."
    )
    driver_text = (
        f"**{label}** contributes the largest euro increase: **EUR {largest.increase_eur/1e6:,.1f} million**, "
        f"or {largest.share_of_increase:.1%} of the net increase."
        if t["increase_eur"] > 0 else
        "There is no positive portfolio-level deterioration under this configuration."
    )
    pds, lgds = segments.baseline_pd.unique(), segments.baseline_lgd.unique()
    starting = (
        f"Each industry starts with the same assumed {pds[0]:.2%} one-year PD and {lgds[0]:.1%} LGD."
        if len(pds) == len(lgds) == 1 else
        "Starting one-year PD and LGD vary by industry as shown in the configuration."
    )
    return f"""# Finnish corporate lending: a transparent scenario exercise

**Question.** Which industries contribute most to an illustrative one-year loss increase, given observed lending exposures and explicit recession assumptions?

**Evidence.** The exposure snapshot is {period}: **EUR {t['exposure_eur']/1e9:,.3f} billion** in outstanding loans to domestic non-financial corporations, excluding housing corporations. Reporters are MFIs excluding Bank of Finland; all currencies are expressed in euros. Statistics Finland bankruptcy counts provide historical context. See [lending definitions](SOURCES_LENDING.md) and [economic context](SOURCES_MACRO.md).

**Assumptions.** {starting} The adverse PD multipliers and LGD increases are chosen assumptions, disclosed in the [configuration](../config/scenarios.json), rather than fitted estimates. Exposures remain fixed. **Existing non-performing balances are retained and are not separately modelled.** This is a loss proxy on outstanding stocks, not an estimate of future losses on a performing-loan portfolio.

**Results.** Baseline illustrative loss is **EUR {t['baseline_loss_eur']/1e6:,.1f} million** ({t['baseline_loss_rate']:.2%} of exposure). Adverse loss is **EUR {t['adverse_loss_eur']/1e6:,.1f} million** ({t['adverse_loss_rate']:.2%}), a change of **EUR {t['increase_eur']/1e6:,.1f} million**. {ratio_text} {driver_text} The ranking reflects exposure weights and imposed stress parameters, rather than an empirically measured ranking of borrower risk. The remaining-industries group is a heterogeneous residual including unclassified industries.

**Uncertainty.** The heatmap varies a common PD multiplier and LGD uplift while holding exposures fixed. It gives conditional outcomes, not a confidence interval, and differs from the industry-specific adverse scenario. Cap counts are reported. PD and LGD enter multiplicatively, so simultaneous deterioration matters.

**What to investigate next.** Obtain one-year default transitions, starting credit states, recoveries and their timing, collateral and loan-to-value distributions, and exposure changes at default. Investigate variation within industries. A longer history and out-of-sample validation would be required to estimate macro-to-credit relationships. Bankruptcy counts and NPL ratios cannot substitute directly for one-year PD.

**Limits.** This exercise does not estimate Nordea's portfolio, IFRS 9 provisions, regulatory capital or tail losses. Economic indicators provide context and do not calibrate PD/LGD. Source revisions, reporting populations and aggregation limit inference. Numerical traceability is available in the [notebook](../notebooks/analysis.ipynb), [results](../outputs/sector_results.csv) and [manifest](../outputs/run_manifest.json).
"""

def make_notebook(note, period):
    md = nbformat.v4.new_markdown_cell
    code = nbformat.v4.new_code_cell
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata["language_info"] = {"name": "python", "version": sys.version.split()[0]}
    nb.cells = [
        md("# Finnish corporate credit-risk scenarios\n\n"
           "A learning exercise using public aggregate lending exposures and Finnish economic context. "
           "How do exposure composition and explicit recession assumptions affect an illustrative one-year loss?\n\n"
           "| Observed | Assumed | Derived |\n|---|---|---|\n"
           "| Published loan balances and economic indicators | Baseline PD/LGD, adverse multipliers and recovery deterioration | "
           "Exposure weights, conditional losses and sensitivity |\n\n"
           "PD and LGD are not estimated from the public indicators. This is not a Nordea portfolio or an IFRS 9 model."),
        code("from pathlib import Path\nimport json, os\n"
             "ROOT = Path.cwd()\n"
             "if not (ROOT / 'pyproject.toml').exists():\n    ROOT = ROOT.parent\n"
             "assert (ROOT / 'pyproject.toml').exists(), 'Run from project root or notebooks/'\n"
             "os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.mplconfig'))\n"
             "import pandas as pd\n"
             "from IPython.display import display, Markdown\n"
             "from matplotlib_inline.backend_inline import set_matplotlib_formats\n"
             "set_matplotlib_formats(\"png\")\n"
             "from credit_scenarios.reporting import (load_inputs, result_tables, plot_context, plot_losses, plot_sensitivity)\n"
             "records, config, lending_meta, macro = load_inputs(ROOT)\n"
             "result, segments, grid = result_tables(records, config)"),
        md("## 1. The observed exposure snapshot\n\n"
           f"Reference period: **{period}**. Amounts below are euros. Source documentation records coverage, "
           "industry mappings, exclusions and the conversion from loan balances to the EAD proxy. "
           "Existing non-performing balances are retained; this is a loss proxy on total stocks. Observation and retrieval dates are distinct."),
        code("display(pd.read_csv(ROOT / 'data/processed/exposures.csv'))\n"
             "display(Markdown('Source definitions: [lending](../docs/SOURCES_LENDING.md) · [economic context](../docs/SOURCES_MACRO.md)'))"),
        md("## 2. The economic context\n\n"
           "Observed time series describe recent conditions. Bankruptcy petitions measure business distress in a different "
           "population from bank borrowers. Counts depend on industry size and are not default rates; pandemic-era policy "
           "changes also affect comparisons. These indicators do not feed a fitted PD or LGD regression."),
        code("fig = plot_context(macro)\ndisplay(fig)\nimport matplotlib.pyplot as plt\nplt.close(fig)"),
        md("## 3. From the recession narrative to explicit credit assumptions\n\n"
           "We consider a hypothetical contraction in activity, weaker cash flows and deterioration in collateral recovery. "
           "The configuration records the chosen translation into PD and LGD. The baseline is a reference set of assumptions, "
           "not an official economic forecast. The default configuration shares starting PD and LGD so exposure weights and imposed "
           "stress differences can be inspected directly.\n\n"
           r"$$EL_s = EAD_s \times PD_s \times LGD_s,\qquad EL = \sum_s EL_s.$$"
           "\n\nValid stressed probabilities are capped at 100%; invalid starting parameters are rejected. Cap counts are reported."),
        code("assumptions = pd.DataFrame(config['sectors']).T\n"
             "assumptions.index.name = 'sector'\ndisplay(assumptions)\n"
             "display(pd.Series(result['totals'], name='portfolio'))"),
        md("## 4. Results and contributions\n\n"
           "Compare loss amounts and loss rates. A sector can account for a large loss because of its exposure, "
           "its assumed credit deterioration, or both. Contribution shares allocate the change in euro losses."),
        code("display(segments[['sector', 'exposure_eur', 'exposure_share', 'baseline_loss_eur', "
             "'adverse_loss_eur', 'increase_eur', 'adverse_loss_rate', 'share_of_increase']])\n"
             f"fig = plot_losses(segments, {period!r})\ndisplay(fig)\nplt.close(fig)"),
        md("## 5. Sensitivity to uncertain parameters\n\n"
           "This separate grid applies the same PD multiplier and LGD uplift to every industry's baseline. "
           "It is not a confidence interval and does not reproduce the industry-specific adverse scenario."),
        code("fig = plot_sensitivity(grid)\ndisplay(fig)\nplt.close(fig)\n"
             "display(grid[['pd_multiplier', 'lgd_uplift', 'loss_eur', 'loss_rate']])"),
        md("## 6. Interpretation\n\n" + note.split("\n", 1)[1].replace("](SOURCES_LENDING.md)", "](../docs/SOURCES_LENDING.md)").replace("](SOURCES_MACRO.md)", "](../docs/SOURCES_MACRO.md)")),
        md("## 7. Reproduce and challenge the result\n\n"
           "Run python scripts/build.py from the project root after installing the documented environment. "
           "It runs tests, rebuilds results and charts, and executes this notebook in a fresh Python kernel using local "
           "snapshots. Live data refresh is separate.\n\n"
           "Source metadata records queries, retrieval dates and hashes; outputs/run_manifest.json records input/code "
           "hashes and package versions. Automated checks cover arithmetic, validation, caps, monotonicity and snapshot "
           "consistency. They check implementation, not empirical model validity."),
    ]
    for i, cell in enumerate(nb.cells):
        cell["id"] = f"analysis-{i:02d}"
    return nb

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-notebook", action="store_true", help="Development only; final build executes notebook.")
    args = parser.parse_args()
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    checked = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
        cwd=ROOT, capture_output=True, text=True,
    )
    (out / "validation.txt").write_text(checked.stdout + checked.stderr)
    if checked.returncode:
        print(checked.stdout + checked.stderr)
        raise SystemExit("Tests failed; report build stopped.")
    records, config, lending_meta, macro = load_inputs(ROOT)
    result, segments, grid = result_tables(records, config)
    period = lending_meta["reference_period"]
    segments.to_csv(out / "sector_results.csv", index=False, float_format="%.12g")
    grid.to_csv(out / "sensitivity.csv", index=False, float_format="%.12g")
    (out / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    save_fig(plot_context(macro), out / "economic_context.png")
    save_fig(plot_losses(segments, period), out / "loss_by_sector.png")
    save_fig(plot_sensitivity(grid), out / "sensitivity.png")
    note = analysis_note(result, segments, period)
    (ROOT / "docs/ANALYSIS_NOTE.md").write_text(note)
    nb = make_notebook(note, period)
    if not args.skip_notebook:
        km = KernelManager(kernel_name="python3")
        km.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        NotebookClient(nb, km=km, timeout=120, resources={"metadata": {"path": str(ROOT)}}).execute()
    nbformat.write(nb, ROOT / "notebooks/analysis.ipynb")
    (out / "run_manifest.json").write_text(json.dumps(manifest(ROOT), indent=2) + "\n")
    print(checked.stderr.strip().splitlines()[-1])
    print(json.dumps(result["totals"], indent=2))
    print("Built analysis; notebook executed:", not args.skip_notebook)

if __name__ == "__main__":
    main()
