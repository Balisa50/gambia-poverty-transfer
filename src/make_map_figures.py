"""
Three figures that carry what the tables state less legibly.

  fig4  Study area. Twelve countries, shaded by out-of-country coverage, with
        the target outlined. A paper about transfer across borders should show
        the borders.
  fig5  Predicted against observed, in-country and out-of-country and on the
        target, so a reader can see the fit rather than take an R-squared.
  fig6  Coverage deviation from nominal, country by nominal level. Both
        post-hoc observations appear here at once: the spread down the rows,
        and the level dependence across the columns.

No cluster coordinates are plotted or written anywhere. The map carries country
polygons and twelve aggregate numbers, and the scatter carries predictions
against labels with no location attached. Cluster locations joined to wealth are
DHS data and are not redistributable.

Run:  python src/make_map_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from run_gate import FEATURES, TARGET_COUNTRY
from splits import assign_blocks, blocked_kfold, leave_one_country_out

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
GEO = ROOT / "data" / "geo" / "ne_110m_admin_0_countries.shp"

plt.rcParams.update({
    "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 200, "savefig.bbox": "tight",
})

NAMES = {"BF": "Burkina\nFaso", "BJ": "Benin", "CI": "Côte\nd'Ivoire",
         "GH": "Ghana", "GM": "The Gambia", "GN": "Guinea", "ML": "Mali",
         "MR": "Mauritania", "NG": "Nigeria", "SL": "Sierra\nLeone",
         "SN": "Senegal", "TG": "Togo"}
LEVELS = [0.50, 0.80, 0.90, 0.95]


def _coverage_table() -> pd.DataFrame:
    """Out-of-country coverage per country and nominal level, plus the target."""
    r = pd.read_csv(PROC / "h2_h3_results.csv")
    r = r[(~r["coral"]) & (r["method"] == "split")]
    tab = r.pivot_table(index="held_out", columns="nominal", values="cov_out")
    g = json.loads((PROC / "gambia_evaluation.json").read_text())
    gm = {row["nominal"]: row["coverage"] for row in g["all"]
          if row["method"] == "split"}
    tab.loc[TARGET_COUNTRY] = [gm[l] for l in tab.columns]
    return tab


def fig4_map() -> None:
    import geopandas as gpd
    if not GEO.exists():
        print("  fig4 skipped: no boundary file at", GEO)
        return
    world = gpd.read_file(GEO)
    tab = _coverage_table()
    cov90 = tab[0.90]

    world["cov"] = world["ISO_A2"].map(cov90)
    study = world[world["ISO_A2"].isin(cov90.index)]

    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    # Neighbours for context, so the study area is not floating in white.
    world.cx[-20:20, 0:30].plot(ax=ax, color="0.96", edgecolor="0.85", lw=0.4)

    norm = TwoSlopeNorm(vmin=0.80, vcenter=0.90, vmax=1.00)
    study.plot(ax=ax, column="cov", cmap="RdYlBu", norm=norm,
               edgecolor="0.35", lw=0.5, legend=True,
               legend_kwds={"label": "coverage of a nominal 90% interval",
                            "shrink": 0.62, "pad": 0.02})

    target = world[world["ISO_A2"] == TARGET_COUNTRY]
    target.boundary.plot(ax=ax, color="#111111", lw=1.8, zorder=5)

    # The Gambia is a thin strip enclosed by Senegal, and Togo and Benin are
    # narrow. Centroid labels collide, so those four are placed outside the
    # polygon with a leader line. Offsets are in degrees.
    OUTSIDE = {"GM": (-5.4, -1.4), "TG": (-1.6, -3.6), "BJ": (2.6, -3.4),
               "SL": (-3.0, -3.0)}
    for _, row in study.iterrows():
        cc = row["ISO_A2"]
        c = row.geometry.representative_point()
        bold = "bold" if cc == TARGET_COUNTRY else "normal"
        if cc in OUTSIDE:
            dx, dy = OUTSIDE[cc]
            label = NAMES.get(cc, cc).replace("\n", " ")
            if cc == TARGET_COUNTRY:
                label += "\n(target, evaluated once)"
            ax.annotate(label, xy=(c.x, c.y), xytext=(c.x + dx, c.y + dy),
                        fontsize=6.4, fontweight=bold, color="#111111",
                        ha="center", va="top",
                        arrowprops=dict(arrowstyle="-", lw=0.6,
                                        color="#111111",
                                        shrinkA=0, shrinkB=2))
        else:
            ax.annotate(NAMES.get(cc, cc), (c.x, c.y), ha="center",
                        va="center", fontsize=6.4, fontweight=bold,
                        color="#111111")

    ax.set_xlim(-23.5, 16)
    ax.set_ylim(1.0, 27.5)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title("Out-of-country coverage, by held-out country", fontsize=9,
                 loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(FIG / "fig4_study_area.pdf")
    plt.close(fig)
    print("  fig4_study_area.pdf")


def fig5_predicted_observed() -> None:
    df = pd.read_csv(PROC / "modelling_table.csv")
    full = df.dropna(subset=FEATURES + ["wealth", "lon", "lat"])
    src = full[full["country"] != TARGET_COUNTRY].reset_index(drop=True)
    tgt = full[full["country"] == TARGET_COUNTRY].reset_index(drop=True)
    Xs, ys = src[FEATURES].to_numpy(float), src["wealth"].to_numpy(float)

    # In-country: held-out spatial blocks of the training countries.
    folds = blocked_kfold(
        assign_blocks(src["lon"].to_numpy(), src["lat"].to_numpy(), 110.0),
        n_folds=5, seed=42)
    pin = np.full(len(ys), np.nan)
    for f in range(5):
        te, tr = folds == f, folds != f
        pin[te] = GradientBoostingRegressor(random_state=0).fit(
            Xs[tr], ys[tr]).predict(Xs[te])

    # Out-of-country: each training country predicted from the other ten.
    pout = np.full(len(ys), np.nan)
    for sp in leave_one_country_out(src["country"].to_numpy()):
        pout[sp.test] = GradientBoostingRegressor(random_state=0).fit(
            Xs[sp.train], ys[sp.train]).predict(Xs[sp.test])

    # Target: fitted exactly as evaluate_gambia.py does, on folds 3-9 with
    # folds 0-2 reserved for conformal calibration. Fitting on all eleven
    # countries instead gives 0.696 and would not match the reported 0.673.
    f10 = blocked_kfold(
        assign_blocks(src["lon"].to_numpy(), src["lat"].to_numpy(), 110.0),
        n_folds=10, seed=42)
    fit_mask = f10 >= 3
    ptg = GradientBoostingRegressor(random_state=0).fit(
        Xs[fit_mask], ys[fit_mask]).predict(tgt[FEATURES].to_numpy(float))
    ytg = tgt["wealth"].to_numpy(float)

    panels = [("In-country, spatially blocked\n(predictions pooled)",
               ys, pin, "#777777"),
              ("Out-of-country, leave-one-country-out\n(predictions pooled)",
               ys, pout, "#1a1a1a"),
              ("The Gambia\n(target, evaluated once)", ytg, ptg, "#1a5490")]

    fig, axes = plt.subplots(1, 3, figsize=(7.6, 2.8), sharex=True, sharey=True)
    for ax, (title, y, p, col) in zip(axes, panels):
        ax.plot([-3, 3.5], [-3, 3.5], color="#c1272d", lw=1, zorder=1)
        ax.scatter(y, p, s=4, alpha=0.28, color=col, edgecolors="none", zorder=2)
        ax.set_title(title, fontsize=8, loc="left")
        ax.set_xlabel("observed cluster wealth")
        ax.set_xlim(-2.6, 3.2)
        ax.set_ylim(-2.6, 3.2)
        ax.text(0.04, 0.93, f"$R^2$ = {r2_score(y, p):.3f}\nn = {len(y):,}",
                transform=ax.transAxes, fontsize=7.5, va="top")
    axes[0].set_ylabel("predicted")
    fig.savefig(FIG / "fig5_predicted_observed.pdf")
    plt.close(fig)
    print("  fig5_predicted_observed.pdf")


def fig6_coverage_heatmap() -> None:
    tab = _coverage_table()
    order = tab[0.90].sort_values().index.tolist()
    order = [c for c in order if c != TARGET_COUNTRY] + [TARGET_COUNTRY]
    tab = tab.loc[order]
    dev = tab.subtract(pd.Series(tab.columns, index=tab.columns), axis=1)

    fig, ax = plt.subplots(figsize=(5.0, 4.2))
    im = ax.imshow(dev.to_numpy(), cmap="RdBu", vmin=-0.16, vmax=0.16,
                   aspect="auto")
    ax.set_xticks(range(len(tab.columns)))
    ax.set_xticklabels([f"{c:.0%}" for c in tab.columns])
    ax.set_yticks(range(len(tab.index)))
    ax.set_yticklabels([NAMES[c].replace("\n", " ") for c in tab.index])
    ax.get_yticklabels()[-1].set_fontweight("bold")
    ax.set_xlabel("nominal coverage")
    ax.set_title("Coverage minus nominal, split conformal", fontsize=9,
                 loc="left")

    for i in range(dev.shape[0]):
        for j in range(dev.shape[1]):
            v = dev.iat[i, j]
            ax.text(j, i, f"{v:+.03f}", ha="center", va="center", fontsize=6.6,
                    color="white" if abs(v) > 0.10 else "#222222")
    ax.axhline(len(tab) - 1.5, color="#111111", lw=1.2)
    fig.colorbar(im, ax=ax, shrink=0.72, pad=0.03,
                 label="empirical minus nominal")
    fig.savefig(FIG / "fig6_coverage_heatmap.pdf")
    plt.close(fig)
    print("  fig6_coverage_heatmap.pdf")


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    print("writing figures:")
    fig4_map()
    fig6_coverage_heatmap()
    fig5_predicted_observed()
