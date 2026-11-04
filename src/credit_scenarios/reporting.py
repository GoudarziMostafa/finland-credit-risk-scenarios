"""Presentation helpers; all financial arithmetic lives in model.py."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .model import calculate_losses, sensitivity

LABELS = {
    "manufacturing": "Manufacturing",
    "construction": "Construction",
    "real_estate": "Real estate",
    "other": "Remaining industries",
    "total": "All industries",
}
COLORS = {"navy": "#16324f", "teal": "#168c94", "red": "#cb6949", "muted": "#617082"}
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.labelcolor": COLORS["navy"], "text.color": COLORS["navy"],
    "axes.titleweight": "bold", "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def load_inputs(root: Path):
    exposures = pd.read_csv(root / "data/processed/exposures.csv")
    records = exposures[["sector", "exposure_eur"]].to_dict("records")
    config = json.loads((root / "config/scenarios.json").read_text())
    lending_meta = json.loads((root / "data/processed/lending_metadata.json").read_text())
    macro = pd.read_csv(root / "data/processed/macro.csv")
    return records, config, lending_meta, macro


def result_tables(records, config):
    result = calculate_losses(records, config)
    segments = pd.DataFrame(result["segments"])
    total_delta = result["totals"]["increase_eur"]
    segments["share_of_increase"] = (
        segments["increase_eur"] / total_delta if total_delta else 0.0
    )
    total_exposure = result["totals"]["exposure_eur"]
    segments["exposure_share"] = segments["exposure_eur"] / total_exposure if total_exposure else 0.0
    axes = config.get("sensitivity", {})
    grid = sensitivity(records, config, axes.get("pd_multipliers"), axes.get("lgd_uplifts"))
    return result, segments, pd.DataFrame(grid)


def plot_losses(segments, reference_period: str):
    frame = segments.sort_values("increase_eur", ascending=False)
    x = np.arange(len(frame))
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.bar(x - .19, frame.baseline_loss_eur / 1e6, width=.36,
           color=COLORS["teal"], label="Baseline assumptions")
    ax.bar(x + .19, frame.adverse_loss_eur / 1e6, width=.36,
           color=COLORS["navy"], label="Adverse assumptions")
    ax.set_xticks(x, [LABELS.get(s, s) for s in frame.sector])
    ax.set_ylabel("Illustrative one-year loss (EUR million)")
    ax.set_title("Which sectors drive the assumed deterioration?", loc="left", pad=34)
    ax.text(0, 1.035, f"Observed exposures: {reference_period} | PD and LGD are assumptions",
            transform=ax.transAxes, fontsize=10, color=COLORS["muted"])
    ax.legend(frameon=False, loc="upper right")
    ax.set_ylim(0, max(1.0, max(frame.adverse_loss_eur.max(), frame.baseline_loss_eur.max()) / 1e6 * 1.25))
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=.16)
    for i, row in enumerate(frame.itertuples()):
        ax.text(i + .19, row.adverse_loss_eur / 1e6, f"{row.adverse_loss_eur/1e6:,.1f}",
                ha="center", va="bottom", fontsize=10)
    fig.text(.08, .025,
             "Scenario illustration on aggregate balances; not a forecast or an estimate of any bank's provisions.",
             fontsize=9, color=COLORS["muted"])
    fig.tight_layout(rect=(0, .06, 1, 1))
    return fig


def plot_sensitivity(grid):
    pivot = grid.pivot(index="lgd_uplift", columns="pd_multiplier", values="loss_eur") / 1e6
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    im = ax.imshow(pivot.to_numpy(), origin="lower", aspect="auto", cmap="YlGnBu")
    ax.set_xticks(range(len(pivot.columns)), [f"{x:g}×" for x in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), [f"+{x*100:g} pp" for x in pivot.index])
    ax.set_xlabel("Uniform multiplier applied to each sector's baseline PD")
    ax.set_ylabel("Uniform addition to baseline LGD")
    ax.set_title("How much do assumed PD and LGD matter?", loc="left", pad=34)
    ax.text(0, 1.035, "Fixed observed exposures | Each cell: illustrative one-year loss, EUR million",
            transform=ax.transAxes, fontsize=10, color=COLORS["muted"])
    values = pivot.to_numpy()
    midpoint = (values.min() + values.max()) / 2
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            ax.text(j, i, f"{values[i,j]:,.0f}", ha="center", va="center",
                    color="white" if values[i,j] > midpoint else COLORS["navy"], fontsize=11)
    fig.colorbar(im, ax=ax, label="EUR million", shrink=.8)
    fig.text(.08, .025,
             "Sensitivity grid is separate from the sector-specific adverse scenario; it is not a confidence interval.",
             fontsize=9, color=COLORS["muted"])
    fig.tight_layout(rect=(0, .06, 1, 1))
    return fig


def save_fig(fig, path: Path):
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def manifest(root: Path):
    paths = sorted(
        list((root / "src").rglob("*.py"))
        + list((root / "scripts").glob("*.py"))
        + list((root / "config").glob("*.json"))
        + [root / "pyproject.toml", root / "requirements-lock.txt"]
        + [p for p in (root / "data").rglob("*") if p.is_file()]
    )
    distributions = ["pandas", "numpy", "matplotlib", "nbformat", "nbclient", "ipykernel", "jupyter_client", "matplotlib-inline"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reproducible scenario analysis",
        "python": platform.python_version(),
        "scenario_configuration": json.loads((root / "config/scenarios.json").read_text()),
        "packages": {name: importlib.metadata.version(name) for name in distributions},
        "sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "reproducibility": "Inputs and code are content-addressed. Build timestamps may differ; numerical outputs should agree.",
    }


def plot_context(macro):
    """Observed context only; no macro series enters the PD/LGD calculation."""
    counts = macro.loc[macro["indicator"].eq("bankruptcies_count")].copy()
    if counts.empty:
        raise ValueError("Economic context requires observed bankruptcy counts.")
    counts["date"] = pd.PeriodIndex(counts["period"], freq="Q").to_timestamp()
    if counts.duplicated(["period", "sector", "indicator"]).any():
        raise ValueError("Duplicate economic observations.")
    gdp = macro.loc[macro["indicator"].eq("real_gdp_yoy_pct")].copy()
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7), sharex=True)
    first = axes[0]
    if not gdp.empty:
        gdp["date"] = pd.PeriodIndex(gdp["period"], freq="Q").to_timestamp()
        gdp = gdp.sort_values("date")
        first.plot(gdp.date, gdp.value, color=COLORS["navy"], linewidth=2)
        first.axhline(0, color=COLORS["muted"], linewidth=.7)
        first.set_ylabel("Real GDP growth, % y/y")
        first.set_title("Observed Finnish economic context", loc="left", pad=26)
    else:
        total = counts.loc[counts.sector.eq("total")].sort_values("date")
        if total.empty:
            raise ValueError("Missing total bankruptcy count series.")
        first.plot(total.date, total.value, color=COLORS["navy"], linewidth=2)
        first.set_ylabel("Bankruptcies: all industries")
        first.set_title("Observed business distress in Finland", loc="left", pad=26)
    first.text(0, 1.04, "Quarterly observations | Source: Statistics Finland",
               transform=first.transAxes, fontsize=10, color=COLORS["muted"])
    for sector, color in zip(
        ["manufacturing", "construction", "real_estate"],
        [COLORS["teal"], COLORS["red"], COLORS["navy"]],
    ):
        part = counts.loc[counts.sector.eq(sector)].sort_values("date")
        if part.empty:
            raise ValueError(f"Missing bankruptcy count series for {sector}.")
        axes[1].plot(part.date, part.value, label=LABELS[sector], color=color, linewidth=2)
    axes[1].set_ylabel("Enterprises in bankruptcy\nproceedings initiated")
    axes[1].set_xlabel("Quarter")
    axes[1].legend(frameon=False, loc="upper left", ncols=3)
    for ax in axes:
        ax.grid(axis="y", alpha=.16)
        ax.set_axisbelow(True)
    fig.text(.08, .02, "Counts are not default rates. Industry size, population coverage and changes in bankruptcy rules affect comparisons.",
             fontsize=9, color=COLORS["muted"])
    fig.tight_layout(rect=(0, .05, 1, 1))
    return fig
