"""
Extract covariates for every downloaded country, one table per country.

Survey year is read from the data, not asserted
----------------------------------------------
Covariates must be matched to each survey's year (docs/00 section 8.3), so the
year cannot be a hardcoded table that drifts from what was actually downloaded.
It is taken as the modal interview year in the household recode, `hv007`.

The mode matters rather than the label or the maximum. Four surveys span two or
three calendar years and the split is not even:

    Gambia 2019-20    1,948 in 2019 but 4,601 in 2020  -> 2020
    Mauritania 19-21  2,806 / 7,094 / 1,758            -> 2020
    Benin 2017-18     7,455 in 2017, 6,701 in 2018     -> 2017
    Togo 2013-14      3,686 in 2013, 5,863 in 2014     -> 2014

Taking the last year of the label would put Gambia on 2020 correctly but Benin
on 2018, where most interviewing happened in 2017. The mode is the year most
households were actually observed in, which is the quantity the covariates
should describe.

Requests are chunked
--------------------
reduceRegions returns one feature per cluster and getInfo pulls the whole
collection in a single synchronous response. That is slow at 280 clusters and
does not survive Nigeria's 1,382 or Mauritania's 1,198. Clusters are sent in
chunks so each response is small, progress is visible, and one failure does not
cost the whole country.

Already-written countries are skipped, so the run is resumable.

Run:  python src/extract_all.py
      python src/extract_all.py --countries GM,BJ --force
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from clusters import load_dhs_clusters
from gee_covariates import (_require_ee, build_image, extract, viirs_asset,
                            worldpop_year, ghsl_epoch, FINE_BANDS, FINE_SCALE,
                            COARSE_BANDS, COARSE_SCALE, MODE_BANDS, MODE_SCALE,
                            rename_single_band)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dhs"
PROC = ROOT / "data" / "processed"

# Clusters per Earth Engine request.
#
# This is a reliability knob, not a speed one. Each request holds an HTTPS
# connection open for as long as the server takes to reduce that many buffers,
# so a large chunk means a long-lived connection. On a link dropping two thirds
# of its packets a 60s connection rarely survives, and every failure discards
# the whole chunk. Smaller chunks finish sooner, checkpoint more often, and lose
# less when they do fail.
CHUNK = 100


def survey_year(hr_path: Path) -> int:
    """Modal interview year from the household recode."""
    y = pd.read_stata(hr_path, columns=["hv007"], convert_categoricals=False)
    y = pd.to_numeric(y["hv007"], errors="coerce").dropna().astype(int)
    return int(y.value_counts().idxmax())


def country_files() -> dict[str, dict[str, Path]]:
    """Every country with both a household recode and a GPS shapefile."""
    out: dict[str, dict[str, Path]] = {}
    for p in RAW.glob("*.DTA"):
        if p.name[2:4].upper() == "HR":
            out.setdefault(p.name[:2].upper(), {})["hr"] = p
    for p in RAW.glob("*.shp"):
        if p.name[2:4].upper() == "GE":
            out.setdefault(p.name[:2].upper(), {})["ge"] = p
    return {k: v for k, v in sorted(out.items()) if "hr" in v and "ge" in v}


def extract_country(ee, cc: str, files: dict[str, Path],
                    chunk: int = CHUNK) -> pd.DataFrame:
    year = survey_year(files["hr"])
    cs = load_dhs_clusters(files["ge"], cc, str(year))
    print(f"  {cs.summary()}   year={year}  "
          f"viirs={viirs_asset(year).rsplit('/', 1)[-1]}  "
          f"pop={worldpop_year(year)}  ghsl={ghsl_epoch(year)}")

    buffers = gpd.GeoDataFrame(
        cs.gdf[["cluster", "urban", "radius_m", "buffer_km2"]],
        geometry=cs.gdf["buffer"], crs="EPSG:4326")

    image = build_image(ee, year)

    # Completed chunks are cached to disk. This runs on a home connection over
    # 6,723 clusters, and a DNS failure has already cost a country mid-run.
    # Without a checkpoint every drop discards the work already paid for.
    cache = PROC / "_chunks" / cc
    cache.mkdir(parents=True, exist_ok=True)

    frames = []
    for start in range(0, len(buffers), chunk):
        part = buffers.iloc[start:start + chunk]
        chunk_file = cache / f"{start:05d}.csv"
        if chunk_file.exists():
            frames.append(pd.read_csv(chunk_file))
            print(f"    {min(start + chunk, len(buffers))}/{len(buffers)} (cached)")
            continue

        for attempt in range(6):
            try:
                # Two passes, each at its own scale. See FINE_BANDS in
                # gee_covariates: reducing rainfall at 100m does not return.
                geo = part.__geo_interface__
                fine = pd.DataFrame(
                    [f["properties"] for f in
                     extract(ee, image.select(FINE_BANDS), geo,
                             FINE_SCALE).getInfo()["features"]])

                # Single-band passes. Earth Engine returns bare mean/stdDev/
                # count for these, so the band prefix is restored explicitly.
                coarse = rename_single_band(pd.DataFrame(
                    [f["properties"] for f in
                     extract(ee, image.select(COARSE_BANDS), geo,
                             COARSE_SCALE).getInfo()["features"]]), "rainfall")
                mode = rename_single_band(pd.DataFrame(
                    [f["properties"] for f in
                     extract(ee, image.select(MODE_BANDS), geo, MODE_SCALE,
                             reducer=ee.Reducer.mode()).getInfo()["features"]]),
                    "landcover")

                part_df = fine
                for extra, prefix in ((coarse, "rainfall"), (mode, "landcover")):
                    keep = [c for c in extra.columns
                            if c == "cluster" or c.startswith(prefix)]
                    # A pass that contributed no columns means the rename above
                    # did not match, which is how rainfall went missing before.
                    if len(keep) < 2:
                        raise RuntimeError(
                            f"{prefix} pass returned no {prefix}_* columns; "
                            f"got {sorted(extra.columns)}")
                    part_df = part_df.merge(extra[keep], on="cluster",
                                            how="left", validate="one_to_one")
                part_df.to_csv(chunk_file, index=False)
                frames.append(part_df)
                break
            except Exception as e:  # noqa: BLE001 - retry with backoff
                if attempt == 5:
                    raise
                wait = min(60, 5 * 2 ** attempt)
                print(f"    chunk {start} failed ({type(e).__name__}), "
                      f"retry {attempt + 1}/5 in {wait}s")
                time.sleep(wait)
        print(f"    {min(start + chunk, len(buffers))}/{len(buffers)}")

    df = pd.concat(frames, ignore_index=True)

    # Provenance. Which product year each covariate actually came from is not
    # recoverable from the numbers, and the population year in particular
    # differs from the survey year for the 2021 surveys.
    df["country"] = cc
    df["survey_year"] = year
    df["pop_year"] = worldpop_year(year)
    df["ghsl_epoch"] = ghsl_epoch(year)
    df["viirs_version"] = viirs_asset(year).rsplit("/", 1)[-1]
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--countries", help="comma-separated codes; default all")
    ap.add_argument("--force", action="store_true",
                    help="re-extract countries that already have a table")
    ap.add_argument("--chunk", type=int, default=CHUNK,
                    help=f"clusters per request (default {CHUNK}); lower it on "
                         "an unreliable connection")
    args = ap.parse_args()

    found = country_files()
    if args.countries:
        want = {c.strip().upper() for c in args.countries.split(",")}
        found = {k: v for k, v in found.items() if k in want}
    if not found:
        raise SystemExit("No countries with both HR and GE files.")

    PROC.mkdir(parents=True, exist_ok=True)
    ee = _require_ee()

    done, failed = [], []
    for cc, files in found.items():
        out = PROC / f"covariates_{cc}.csv"
        if out.exists() and not args.force:
            print(f"{cc}: already extracted, skipping")
            done.append(cc)
            continue
        print(f"{cc}:")
        t0 = time.time()
        try:
            df = extract_country(ee, cc, files, args.chunk)
        except Exception as e:  # noqa: BLE001 - one country must not stop the run
            print(f"  FAILED: {type(e).__name__}: {str(e)[:200]}")
            failed.append(cc)
            continue
        df.to_csv(out, index=False)
        print(f"  wrote {out.name}  {len(df)} clusters, {df.shape[1]} cols, "
              f"{time.time() - t0:.0f}s")
        done.append(cc)

    print(f"\n{len(done)}/{len(found)} extracted -> {PROC}")
    if failed:
        print(f"  failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
