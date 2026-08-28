"""
Check our Earth Engine extraction against DHS's own, cluster by cluster.

Why this runs before anything else
----------------------------------
Every downstream number depends on the covariates being extracted correctly, and
until now there was no external way to confirm that. DHS publishes its own
pre-computed geospatial covariates per cluster, shipped as the GC file alongside
the GPS data. They are an independent extraction of comparable quantities over
the same clusters, which makes them the closest thing available to ground truth
for our pipeline.

They are NOT features. Building the model on DHS's extraction would make the
paper a wrapper around their pipeline and tie the covariate set to their
choices. See docs/04.

What agreement can and cannot mean here
---------------------------------------
Three things stop this being a like-for-like comparison, and all three were
discovered by reading the delivered files rather than assumed:

1. **The years do not match.** Every DHS covariate stops at 2015, and
   Nightlights_Composite carries no year at all. Our extraction is matched to
   each survey year, 2013 to 2021. So this compares different years of the same
   quantity.

2. **The buffer conventions differ.** DHS does not document extracting over a
   displacement-matched buffer the way we do.

3. **-9999 is a nodata sentinel, not a value.** It is widespread: rainfall and
   UN population density are -9999 for every cluster in Benin and Mali, and
   Gambia has 42 of 280 clusters with sentinel rainfall, which independently
   corroborates the CHIRPS water-masking problem recorded in docs/02.

Rank correlation is therefore the right measure, not agreement in level. The
spatial pattern of settlement and lighting is highly persistent year to year, so
a high rank correlation still demonstrates that the buffers, the joins and the
reducers are working. A low one means a bug.

docs/04 fixed the failure threshold at Spearman rho 0.9 for nightlights. That
was written before the year mismatch above was known. The threshold is kept
as-is rather than loosened after seeing results, because moving a
pre-registered bound to accommodate an outcome is exactly the practice this
project is arguing against. If it fails, the year mismatch is a candidate
explanation to investigate and report, not a reason to have set it lower.

Run:  python src/dhs_crosscheck.py --country GM
"""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dhs"
PROC = ROOT / "data" / "processed"

# DHS writes this where a covariate could not be computed.
SENTINEL = -9998.0

# Pre-registered in docs/04.
RHO_FAIL = 0.90

# Ours -> theirs. Only quantities both pipelines actually produce.
#
# Rainfall and UN_Population_Density are deliberately absent: they are -9999 for
# every cluster in Benin and Mali, so they cannot support a cross-check across
# the twelve countries and a partial one would be misleading.
# Our column names carry the reducer suffix that Earth Engine appends for a
# multi-band reduction: nightlights_mean, not nightlights. Naming them without
# it made every comparison report MISSING with n=0.
PAIRS = {
    "nightlights_mean": "Nightlights_Composite",
    "population_mean": "UN_Population_Density_2015",
}

# The population counterpart is chosen on units, before looking at any
# correlation, and this must stay that way.
#
# Our population_mean is the mean of a 100 m population raster over the buffer:
# persons per pixel, a density. All_Population_Count_* is a count. Comparing a
# density against a count across clusters whose buffers differ by area (2 km
# urban, 5 km rural) scrambles the ranking, and it did: Ghana scored 0.262
# against the count and 0.836 against the density.
#
# The temptation here is to try every DHS population column and keep whichever
# ranks highest. That is exactly the practice this paper exists to criticise, so
# the rule is units first: a density is compared with a density. If the result
# is poor, that is the finding.


def load_ours(country: str) -> pd.DataFrame:
    """Our extracted covariate table for one country."""
    hits = sorted(PROC.glob(f"covariates_{country}*.csv"))
    if not hits:
        raise SystemExit(
            f"No extraction found for {country} in {PROC}.\n"
            f"Run:  python src/gee_covariates.py --country {country} ...")
    df = pd.read_csv(hits[-1])
    df.columns = [c.lower() for c in df.columns]
    if "cluster" not in df.columns:
        raise SystemExit(f"{hits[-1].name} has no 'cluster' column.")
    return df


def load_theirs(country: str) -> pd.DataFrame:
    """DHS's own covariate table for one country, with sentinels masked."""
    hits = sorted(glob.glob(str(RAW / f"{country}GC*.csv")))
    if not hits:
        raise SystemExit(
            f"No DHS covariate (GC) file for {country} in {RAW}.\n"
            "It is the 'Geospatial Covariates' download on the survey page.")
    df = pd.read_csv(hits[-1])
    num = df.select_dtypes(include=[np.number]).columns
    # Mask rather than drop: which clusters lost which covariate is itself
    # information, and dropping rows here would silently shrink the comparison.
    df[num] = df[num].mask(df[num] <= SENTINEL)
    return df


def compare(country: str) -> pd.DataFrame:
    ours, theirs = load_ours(country), load_theirs(country)
    theirs.columns = [c if c == "DHSCLUST" else c for c in theirs.columns]
    merged = ours.merge(theirs, left_on="cluster", right_on="DHSCLUST",
                        how="inner", validate="one_to_one")

    print(f"{country}: {len(ours)} extracted, {len(theirs)} in DHS file, "
          f"{len(merged)} joined")
    if len(merged) < 0.95 * min(len(ours), len(theirs)):
        print("  WARNING: the join lost more than 5% of clusters.")

    rows = []
    for mine, hers in PAIRS.items():
        if mine not in merged.columns or hers not in merged.columns:
            rows.append({"quantity": mine, "n": 0, "spearman": np.nan,
                         "verdict": "MISSING"})
            continue
        sub = merged[[mine, hers]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(sub) < 30:
            rows.append({"quantity": mine, "n": len(sub), "spearman": np.nan,
                         "verdict": "TOO FEW"})
            continue
        rho = sub[mine].corr(sub[hers], method="spearman")
        rows.append({"quantity": mine, "n": len(sub), "spearman": round(rho, 3),
                     "verdict": "pass" if rho >= RHO_FAIL else "FAIL"})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", help="two-letter DHS code; omit for all extracted")
    args = ap.parse_args()

    if args.country:
        countries = [args.country.upper()]
    else:
        countries = sorted({os.path.basename(p).split("_")[1][:2].upper()
                            for p in PROC.glob("covariates_*.csv")})
        if not countries:
            raise SystemExit(f"Nothing extracted yet in {PROC}.")

    all_rows = []
    for cc in countries:
        res = compare(cc)
        res.insert(0, "cc", cc)
        print(res.to_string(index=False))
        print()
        all_rows.append(res)

    df = pd.concat(all_rows, ignore_index=True)

    # Anything that is not an explicit pass is a failure.
    #
    # The first version tested only for "FAIL", so MISSING and TOO FEW fell
    # through to the success branch. Every single comparison came back MISSING,
    # because the column names were wrong, and the script reported that the
    # cross-check had passed. Nothing had been compared at all.
    #
    # A validation script that cannot fail is worse than no validation script,
    # and this one is guarding against precisely this class of error elsewhere
    # in the pipeline. A check that reports success on an empty comparison
    # would have let a broken extraction through to the sanity gate.
    failed = df[df["verdict"] != "pass"]
    print("=" * 60)
    if len(failed):
        print(f"CROSS-CHECK FAILED for {len(failed)} quantity/country pair(s).")
        print(failed.to_string(index=False))
        print()
        if (failed["verdict"] == "MISSING").any():
            print("MISSING means a named column was not found in one of the "
                  "two tables, so nothing was compared. Fix the column names "
                  "before reading anything into the result.")
        print("Investigate the buffers, the cluster join and the reducers "
              "before running the sanity gate. The year mismatch documented at "
              "the top of this file is a candidate explanation, but it must be "
              "demonstrated rather than assumed.")
    else:
        print("Cross-check passed. Our extraction agrees with DHS's own on "
              f"rank, at rho >= {RHO_FAIL}.")


if __name__ == "__main__":
    main()
