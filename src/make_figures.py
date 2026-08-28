"""
Figures for the paper. Reads only committed result tables, never raw DHS data.

Two figures, both showing something a table states less well:

  fig1  coverage by held-out country against nominal, with the binomial
        interval that sampling alone would produce. The point is the spread.
  fig2  calibration curves, training pool and The Gambia, both conformal
        methods. The point is that the two methods agree in-domain and
        separate on the target at the lower nominal levels.

Run:  python src/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"

plt.rcParams.update({
    "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.bbox": "tight",
})

NAMES = {"BF": "Burkina Faso", "BJ": "Benin", "CI": "Côte d'Ivoire",
         "GH": "Ghana", "GM": "The Gambia", "GN": "Guinea", "ML": "Mali",
         "MR": "Mauritania", "NG": "Nigeria", "SL": "Sierra Leone",
         "SN": "Senegal", "TG": "Togo"}


def fig1_coverage_by_country() -> None:
    r = pd.read_csv(PROC / "h2_h3_results.csv")
    h = r[(~r["coral"]) & (r["method"] == "split") &
          (r["nominal"] == 0.90)].sort_values("cov_out")
    g = json.loads((PROC / "gambia_evaluation.json").read_text())
    gm_cov, gm_n = g["primary"]["coverage"], g["n_gambia"]

    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    y = np.arange(len(h))

    # Binomial 95% interval per country under exactly nominal coverage.
    se = np.sqrt(0.9 * 0.1 / h["n_out"].to_numpy())
    ax.barh(y, 2 * 1.96 * se, left=0.9 - 1.96 * se, height=0.7,
            color="0.88", label="sampling variation alone (95%)")
    ax.scatter(h["cov_out"], y, s=26, color="#1a1a1a", zorder=3,
               label="out-of-country")
    ax.scatter(h["cov_in"], y, s=22, facecolors="none", edgecolors="#777",
               zorder=3, label="in-country")

    ax.axvline(0.90, color="#c1272d", lw=1, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([NAMES[c] for c in h["held_out"]])
    ax.set_xlabel("empirical coverage of a nominal 90% interval")
    ax.set_xlim(0.78, 1.0)

    # The Gambia, evaluated once, plotted apart from the training countries.
    ax.axhline(len(h) - 0.5, color="0.7", lw=0.6, ls=":")
    se_gm = np.sqrt(0.9 * 0.1 / gm_n)
    ax.barh([len(h)], [2 * 1.96 * se_gm], left=0.9 - 1.96 * se_gm, height=0.7,
            color="0.88")
    ax.scatter([gm_cov], [len(h)], s=40, color="#1a5490", marker="D", zorder=3,
               label="The Gambia (held-out target)")
    ax.set_yticks(list(y) + [len(h)])
    ax.set_yticklabels([NAMES[c] for c in h["held_out"]] + ["The Gambia"])
    ax.get_yticklabels()[-1].set_fontweight("bold")

    # Legend below the axes. Inside the plot it collided with the lowest
    # three countries and the sampling bars, which is where the data is densest.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2,
              frameon=False, fontsize=7.5, handletextpad=0.4,
              columnspacing=1.4)
    ax.invert_yaxis()
    fig.savefig(FIG / "fig1_coverage_by_country.pdf")
    plt.close(fig)
    print("  fig1_coverage_by_country.pdf")


def fig2_calibration_curves() -> None:
    r = pd.read_csv(PROC / "h2_h3_results.csv")
    g = json.loads((PROC / "gambia_evaluation.json").read_text())
    gdf = pd.DataFrame(g["all"])

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), sharey=True)
    for ax, meth, title in zip(axes, ["split", "cqr"],
                               ["Split conformal (constant width)",
                                "CQR (adaptive width)"]):
        base = r[(~r["coral"]) & (r["method"] == meth)]
        lv = sorted(base["nominal"].unique())
        ax.plot([0.45, 1.0], [0.45, 1.0], color="#c1272d", lw=1, zorder=1)
        ax.plot(lv, [base[base["nominal"] == l]["cov_in"].mean() for l in lv],
                "o-", ms=4, color="#777", label="in-country (11 countries)")
        ax.plot(lv, [base[base["nominal"] == l]["cov_out"].mean() for l in lv],
                "s-", ms=4, color="#1a1a1a", label="out-of-country (mean)")
        gg = gdf[gdf["method"] == meth].sort_values("nominal")
        ax.plot(gg["nominal"], gg["coverage"], "D-", ms=5, color="#1a5490",
                label="The Gambia")
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("nominal coverage")
        ax.set_xlim(0.45, 1.0)
        ax.set_ylim(0.30, 1.0)
    axes[0].set_ylabel("empirical coverage")
    axes[0].legend(loc="upper left", frameon=False, fontsize=7.5)
    fig.savefig(FIG / "fig2_calibration_curves.pdf")
    plt.close(fig)
    print("  fig2_calibration_curves.pdf")


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    print("writing figures:")
    fig1_coverage_by_country()
    fig2_calibration_curves()
