"""
Join the wealth index to the extracted covariates, one row per cluster.

This is the modelling table. Everything downstream reads it and nothing
downstream reads the raw DHS files.

The label
---------
`hv271` is the DHS wealth index factor score, stored scaled by 100,000, one
value per household. The label is its mean over the households in a cluster,
which is the finest spatial unit at which wealth is released and the unit this
literature models.

Weighting. `hv005` is the household sample weight. Within a single cluster it is
usually constant, because the weight is built from the sampling probability of
the cluster, so a weighted and unweighted cluster mean coincide. That is checked
rather than assumed: `weight_varies` reports the share of clusters where it does
not hold, and if that share is material the weighted mean is the one to use.

Cluster size varies and matters
-------------------------------
The mean of 10 households is noisier than the mean of 30, and the number of
households per cluster differs by survey design, not at random: Mauritania
sampled about 10 per cluster where every other survey sampled 20 to 30. That is
label noise correlated with country, in the dimension this paper measures, so
`n_households` is carried into the table and must be available to any weighting
or heteroskedasticity decision later.

Coordinates
-----------
`lon` and `lat` come from the GPS file and are the displaced coordinates DHS
publishes, not true locations. They are here only to build spatial blocks; the
covariates were already extracted over displacement-matched buffers.

Run:  python src/build_table.py
"""

from __future__ import annotations

import glob
import os
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dhs"
PROC = ROOT / "data" / "processed"

WEALTH_COL = "hv271"
CLUSTER_COL = "hv001"
WEIGHT_COL = "hv005"
WEALTH_SCALE = 100_000.0


def cluster_wealth(hr_path: Path) -> pd.DataFrame:
    """Cluster-mean wealth index, with the sample size that produced it."""
    cols = [CLUSTER_COL, WEALTH_COL, WEIGHT_COL]
    try:
        hr = pd.read_stata(hr_path, columns=cols, convert_categoricals=False)
    except ValueError:
        hr = pd.read_stata(hr_path, columns=[CLUSTER_COL, WEALTH_COL],
                           convert_categoricals=False)
        hr[WEIGHT_COL] = 1.0

    hr = hr.dropna(subset=[CLUSTER_COL, WEALTH_COL])
    hr[WEALTH_COL] = hr[WEALTH_COL] / WEALTH_SCALE

    g = hr.groupby(CLUSTER_COL)
    out = pd.DataFrame({
        "cluster": g.size().index,
        "wealth": g[WEALTH_COL].mean().to_numpy(),
        "wealth_sd": g[WEALTH_COL].std().to_numpy(),
        "n_households": g.size().to_numpy(),
    })

    # Does the sample weight vary inside a cluster? If it does not, the
    # unweighted mean is the weighted mean and there is nothing to decide.
    varies = g[WEIGHT_COL].nunique() > 1
    out.attrs["weight_varies"] = float(varies.mean())

    w = hr[WEIGHT_COL].to_numpy(float)
    hr["_wx"] = hr[WEALTH_COL] * w
    gw = hr.groupby(CLUSTER_COL)
    out["wealth_weighted"] = (gw["_wx"].sum() / gw[WEIGHT_COL].sum()).to_numpy()
    return out


def cluster_coords(ge_path: Path) -> pd.DataFrame:
    """Displaced cluster coordinates, ungeoreferenced points removed."""
    g = gpd.read_file(ge_path)
    g.columns = [c.upper() if c != "geometry" else c for c in g.columns]
    g = g[["DHSCLUST", "LATNUM", "LONGNUM", "URBAN_RURA"]].copy()
    g = g[~((g.LATNUM == 0) & (g.LONGNUM == 0))]
    return g.rename(columns={"DHSCLUST": "cluster", "LATNUM": "lat",
                             "LONGNUM": "lon", "URBAN_RURA": "urban_rural"})


def main() -> None:
    frames, report = [], []
    for cov_path in sorted(PROC.glob("covariates_*.csv")):
        cc = os.path.basename(cov_path)[11:13]
        hr = glob.glob(str(RAW / f"{cc}HR*.DTA"))
        ge = glob.glob(str(RAW / f"{cc}GE*.shp"))
        if not hr or not ge:
            print(f"{cc}: missing HR or GE, skipped")
            continue

        cov = pd.read_csv(cov_path)
        w = cluster_wealth(Path(hr[0]))
        xy = cluster_coords(Path(ge[0]))

        df = cov.merge(w, on="cluster", how="inner", validate="one_to_one")
        df = df.merge(xy, on="cluster", how="inner", validate="one_to_one")
        df["country"] = cc

        report.append({
            "cc": cc,
            "covariates": len(cov),
            "wealth": len(w),
            "joined": len(df),
            "lost": len(cov) - len(df),
            "weight_varies": round(w.attrs.get("weight_varies", 0.0), 3),
            "wealth_null": int(df["wealth"].isna().sum()),
        })
        frames.append(df)

    if not frames:
        raise SystemExit(f"No covariate tables in {PROC}.")

    rep = pd.DataFrame(report)
    print(rep.to_string(index=False))

    if rep["lost"].sum():
        print(f"\n  {int(rep['lost'].sum())} cluster(s) dropped in the join. "
              "These are covariate rows with no wealth or no coordinate.")

    # If the weight never varies within a cluster, the weighted and unweighted
    # means are the same number and the choice is not a real one.
    share = float(rep["weight_varies"].max())
    print(f"\n  clusters where hv005 varies within the cluster: max {share:.1%} "
          "across countries")

    full = pd.concat(frames, ignore_index=True)
    diff = (full["wealth"] - full["wealth_weighted"]).abs().max()
    print(f"  largest |unweighted - weighted| cluster mean: {diff:.6f}")

    out = PROC / "modelling_table.csv"
    full.to_csv(out, index=False)
    print(f"\nWrote {out.name}: {len(full)} clusters, {full.shape[1]} columns, "
          f"{full['country'].nunique()} countries")
    print(full.groupby("country").size().to_string())


if __name__ == "__main__":
    main()
