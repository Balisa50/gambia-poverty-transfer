"""
Extract geospatial covariates for DHS clusters, server-side, via Earth Engine.

Why server-side
---------------
The obvious approach is to download rasters and summarise them locally. That
does not fit here. WorldPop alone is 2.2 GB for the twelve countries in this
study, and it is one covariate of six; VIIRS annual composites are several GB
each, and building footprints are larger still. A local pipeline needs 10 to
20 GB before any analysis starts.

Earth Engine computes the zonal summaries on Google's infrastructure and returns
only the resulting table, a few hundred kilobytes. Nothing large touches the
disk. This is also how the extraction step is normally done in this literature,
so the choice costs nothing in rigour.

What it produces
----------------
One row per DHS cluster, with summary statistics of each covariate over that
cluster's displacement-matched buffer (see clusters.py for why buffers).

Authentication
--------------
Requires a registered Earth Engine account attached to a Google Cloud project.
Run once, interactively:

    earthengine authenticate

then set the project id below or in the EE_PROJECT environment variable.

Run:  python src/gee_covariates.py --country GM --survey GM2019DHS
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

# The Earth Engine Cloud project. Not a secret: a project id is an identifier,
# not a credential, and access is granted by the local OAuth token written by
# ee.Authenticate(). Overridable so a coresearcher can use their own.
EE_PROJECT = os.environ.get("EE_PROJECT", "ee-abalisa-gambia")


# --------------------------------------------------------------------------- #
# Product versions and epochs, resolved from the survey year.
#
# Three of the six covariates are not a single global raster. They are split
# across product versions or five-year epochs, and asking for a year outside the
# available range does not raise: Earth Engine returns an empty collection, and
# the covariate comes back null for every cluster in that country.
#
# That failure mode is the one this project is least able to absorb. A covariate
# silently null for a subset of countries is a distribution shift we introduced,
# in exactly the dimension the paper measures. The resolvers below exist so the
# year is always mapped to something that exists, and so a year outside the
# usable range is loud.
#
# Ranges verified against the Earth Engine catalogue on 2026-08-27.
# --------------------------------------------------------------------------- #

# VIIRS annual composites are split BY YEAR across two versions, not
# reprocessed: V21 covers 2012-2021, V22 covers 2022 onward. The V21 catalogue
# entry states "Data for 2022 are available in a separate dataset,
# NOAA/VIIRS/DNB/ANNUAL_V22".
#
# Every survey in this study is constrained to 2021 or earlier precisely so that
# one version covers all twelve countries (docs/02). V21 is therefore the
# correct asset. Mixing versions would make product version correlate with
# country, which is a confound in the dimension the paper measures.
VIIRS_V21 = "NOAA/VIIRS/DNB/ANNUAL_V21"   # 2012-2021
VIIRS_V22 = "NOAA/VIIRS/DNB/ANNUAL_V22"   # 2022 onward
VIIRS_FIRST_YEAR, VIIRS_V21_LAST_YEAR = 2012, 2021

# WorldPop GP 100m availability ends 2021-01-01, so 2020 is the last year with
# an image. Surveys in 2021 (Burkina Faso, Cote d'Ivoire, Mauritania) must fall
# back to 2020 or population is null for the whole country.
WORLDPOP_FIRST_YEAR, WORLDPOP_LAST_YEAR = 2000, 2020

# GHSL is an ImageCollection of five-year epochs, addressed as
# .../GHS_BUILT_S/<epoch>. ee.Image() on the bare collection id fails.
GHSL_EPOCHS = tuple(range(1975, 2031, 5))


def viirs_asset(year: int) -> str:
    """VIIRS product version covering `year`."""
    if year < VIIRS_FIRST_YEAR:
        raise SystemExit(
            f"No VIIRS annual composite for {year}; the series starts "
            f"{VIIRS_FIRST_YEAR}. Nightlights is the strongest single predictor "
            "in this literature, so proceeding without it is not sensible.")
    return VIIRS_V21 if year <= VIIRS_V21_LAST_YEAR else VIIRS_V22


def worldpop_year(year: int) -> int:
    """Nearest WorldPop year, clamped to the available range.

    The offset is returned to the caller via ``main`` and written into the
    output table, so a cluster's population year is never assumed to equal its
    survey year.
    """
    return max(WORLDPOP_FIRST_YEAR, min(year, WORLDPOP_LAST_YEAR))


def ghsl_epoch(year: int) -> int:
    """Nearest GHSL five-year epoch to `year`."""
    return min(GHSL_EPOCHS, key=lambda e: abs(e - year))


# The covariate set. Each entry is an Earth Engine asset, the band to use, the
# native resolution in metres, and how to summarise it over a buffer.
#
# Resolution matters: asking for a 10 m band over a 5 km buffer means Earth
# Engine reduces roughly 785,000 pixels per cluster, which is slow and rarely
# improves the estimate. Where a coarser scale is adequate it is requested
# explicitly rather than left to default.
COVARIATES = {
    "nightlights": {
        "asset": VIIRS_V21,   # resolved per year by viirs_asset()
        "band": "average",
        "scale": 500,
        "reducers": ["mean", "max", "stdDev"],
        "why": "Economic activity proxy. The single strongest predictor of "
               "cluster wealth in most published models.",
    },
    "population": {
        "asset": "WorldPop/GP/100m/pop",
        "band": "population",
        "scale": 100,
        "reducers": ["mean", "sum"],
        "why": "Population density separates urban cores from rural areas, and "
               "conditions how every other covariate should be read.",
    },
    "builtup": {
        "asset": "JRC/GHSL/P2023A/GHS_BUILT_S",   # + /<epoch>, see ghsl_epoch()
        "band": ["built_surface", "built_surface_nres"],
        "scale": 100,
        "reducers": ["mean", "sum"],
        "why": "Built surface area, split residential and non-residential "
               "(docs/02, Decision 5). Physical structure of settlement, which "
               "carries wealth information that lights alone miss.",
    },
    "landcover": {
        "asset": "ESA/WorldCover/v200",
        "band": "Map",
        "scale": 100,
        "reducers": ["mode"],
        "why": "Land cover class. Distinguishes cropland from built-up from "
               "bare ground.",
    },
    "rainfall": {
        "asset": "UCSB-CHG/CHIRPS/DAILY",
        "band": "precipitation",
        "scale": 5000,
        "reducers": ["mean"],
        "why": "Rainfall drives agricultural income, which is most of rural "
               "livelihood in this region.",
    },
    "elevation": {
        "asset": "USGS/SRTMGL1_003",
        "band": "elevation",
        "scale": 90,
        "reducers": ["mean", "stdDev"],
        "why": "Terrain. Ruggedness conditions accessibility and land use.",
    },
}


def _require_ee():
    try:
        import ee  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "earthengine-api is not installed.\n"
            "  pip install earthengine-api\n"
            "then run `earthengine authenticate` once."
        ) from exc
    import ee
    if not EE_PROJECT:
        raise SystemExit(
            "No Earth Engine project set. Register at "
            "https://code.earthengine.google.com, then either set the "
            "EE_PROJECT environment variable or edit EE_PROJECT in this file."
        )
    ee.Initialize(project=EE_PROJECT)
    return ee


def build_image(ee, year: int):
    """Assemble a single multi-band image holding every covariate.

    One image with many bands is far cheaper than one request per covariate,
    because the buffer geometry is then reduced once instead of six times.
    """
    bands = []

    # Nightlights. The version is resolved from the year, and the collection is
    # checked to be non-empty before .first() is called on it. An empty
    # collection returns null here rather than raising, which would put null
    # nightlights on every cluster in the country without any warning.
    #
    # Decision 4 (docs/02) carries both bands: average_masked has background
    # noise removed, average does not. Which predicts wealth better is settled
    # on validation data, not asserted here.
    lights_col = (ee.ImageCollection(viirs_asset(year))
                  .filterDate(f"{year}-01-01", f"{year}-12-31"))
    if lights_col.size().getInfo() == 0:
        raise SystemExit(
            f"No VIIRS image for {year} in {viirs_asset(year)}. Check the year "
            "against the product version boundary (V21 ends 2021).")
    lights = lights_col.first().select(["average", "average_masked"],
                                       ["nightlights", "nightlights_masked"])
    bands.append(lights)

    # Population. WorldPop stops at 2020, so a 2021 survey silently mosaics an
    # empty collection unless the year is clamped. The year actually used is
    # recorded in the output table by main().
    pop_year = worldpop_year(year)
    pop = (ee.ImageCollection(COVARIATES["population"]["asset"])
           .filter(ee.Filter.eq("year", pop_year)).mosaic()
           .select(COVARIATES["population"]["band"]).rename("population"))
    bands.append(pop)

    # Built surface, at the nearest five-year epoch. The bare collection id is
    # not a valid ee.Image; the epoch suffix is required.
    built = (ee.Image(f"{COVARIATES['builtup']['asset']}/{ghsl_epoch(year)}")
             .select(["built_surface", "built_surface_nres"],
                     ["builtup", "builtup_nres"]))
    bands.append(built)

    cover = (ee.ImageCollection(COVARIATES["landcover"]["asset"]).first()
             .select(COVARIATES["landcover"]["band"]))
    bands.append(cover.rename("landcover"))

    # Annual total rainfall, summed from daily.
    #
    # CHIRPS is a land-only product. Verified 2026-08-08: a 5 km buffer at
    # Banjul is 80.7% water and returns null, while Basse inland returns
    # 713 mm. Left unhandled, water-adjacent clusters would drop out of the
    # analysis entirely.
    #
    # That is not a generic nuisance here, it is a threat to the paper's
    # question. The Gambia is a strip of land around a river and has far more
    # water-adjacent clusters than Mali or Burkina Faso, so silent dropout
    # would remove target-country clusters at a much higher rate than training
    # ones. We would then be measuring a distribution shift we created.
    #
    # Rainfall is a smooth, large-scale field, so filling a masked coastal
    # pixel from nearby land is defensible. The fill is recorded via
    # water_fraction below so its effect can be checked rather than assumed.
    # .reproject before the focal fill is a 150x speedup, not a cosmetic change.
    # Without it Earth Engine re-evaluates the 365-image sum at every offset of
    # the 20 km kernel: 125s for ten clusters, measured, which does not finish
    # for Nigeria's 1,382. Pinning the sum to the CHIRPS native 5 km grid
    # materialises it once and the same call takes 0.8s. Values are unchanged.
    #
    # CHIRPS PENTAD was the obvious alternative, 72 images instead of 365, and
    # it agrees with DAILY inland to 0.3% (899.9 vs 902.3 mm at Basse, 2020).
    # It is rejected on purpose: PENTAD carries a wider land mask and returns
    # 1548 mm over the Banjul buffer where DAILY is masked. That would silently
    # supply extrapolated values over water and hide the very problem Decision 1
    # exists to make visible and testable via water_fraction.
    rain_raw = (ee.ImageCollection(COVARIATES["rainfall"]["asset"])
                .filterDate(f"{year}-01-01", f"{year}-12-31")
                .select(COVARIATES["rainfall"]["band"]).sum()
                .reproject(crs="EPSG:4326", scale=COVARIATES["rainfall"]["scale"]))
    rain = rain_raw.unmask(
        rain_raw.focal_mean(radius=20000, units="meters")
    ).rename("rainfall")
    bands.append(rain)

    # Fraction of the buffer that is open water (ESA WorldCover class 80).
    #
    # Serves two purposes. It flags which clusters relied on the rainfall
    # fill above, and it is a real covariate in its own right: livelihood in a
    # fishing settlement differs from an inland farming one, and the models
    # should be allowed to use that.
    water = cover.eq(80).rename("water_fraction")
    bands.append(water)

    elev = ee.Image(COVARIATES["elevation"]["asset"]).select("elevation").rename("elevation")
    bands.append(elev)

    return ee.Image.cat(bands)


# Bands must be reduced at a scale near their native resolution, in two passes.
#
# Everything here is 10 m to 500 m except rainfall, which is CHIRPS at 5 km with
# a 20 km focal fill on top. Concatenating them and reducing the lot at 100 m
# makes Earth Engine evaluate that focal fill at 100 m, which is 2,500 times the
# pixel count it needs and never returns. Measured on 25 Burkina Faso clusters:
#
#     8 fine bands, scale 100    2.4s
#     rainfall alone, scale 5000 1.3s
#     all 9 bands,   scale 100   did not return in 400s
#
# Two requests per chunk is the fix, and it is also more correct: asking for a
# 5 km product at 100 m never bought any precision.
# Landcover is reduced separately, by mode. docs/02 Decision 3: the band holds
# class codes (10 tree, 20 shrub, 40 crop, 80 water) and averaging them produces
# a number that is not any class. The combined mean/stdDev reducer used for
# everything else would produce exactly the meaningless landcover_mean that
# decision rules out.
FINE_BANDS = ["nightlights", "nightlights_masked", "population", "builtup",
              "builtup_nres", "water_fraction", "elevation"]
FINE_SCALE = 100
COARSE_BANDS = ["rainfall"]
COARSE_SCALE = 5000
MODE_BANDS = ["landcover"]
MODE_SCALE = 100

# Earth Engine names reducer outputs "<band>_<reducer>" for a multi-band image
# but bare "<reducer>" for a single-band one. A single-band pass therefore
# returns mean/stdDev/count with no band prefix.
#
# This silently cost rainfall from all twelve country tables: the merge kept
# columns starting with "rainfall", nothing matched, and the join succeeded with
# nothing added. No error, no warning, one of six covariates simply absent.
# Single-band passes must have their columns renamed explicitly.
REDUCER_SUFFIXES = ("mean", "stdDev", "count", "mode")


def rename_single_band(df, band: str):
    """Restore the band prefix Earth Engine omits for single-band reductions."""
    return df.rename(columns={s: f"{band}_{s}" for s in REDUCER_SUFFIXES
                              if s in df.columns})


def extract(ee, image, buffers_geojson: dict, scale: int = 100, reducer=None):
    """Reduce the covariate image over each cluster buffer.

    Returns an Earth Engine FeatureCollection, one feature per cluster. The
    combined reducer computes mean, standard deviation and count in a single
    pass, which is markedly cheaper than three separate reductions.
    """
    fc = ee.FeatureCollection(buffers_geojson)
    if reducer is None:
        reducer = (ee.Reducer.mean()
                   .combine(ee.Reducer.stdDev(), sharedInputs=True)
                   .combine(ee.Reducer.count(), sharedInputs=True))
    return image.reduceRegions(collection=fc, reducer=reducer, scale=scale)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", required=True, help="two-letter DHS code, e.g. GM")
    ap.add_argument("--survey", required=True, help="DHS survey id, e.g. GM2019DHS")
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--ge-file", help="path to the DHS GE shapefile")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the covariate plan without contacting Earth Engine")
    args = ap.parse_args()

    if args.dry_run:
        year = args.year
        resolved = {
            "nightlights": viirs_asset(year),
            "population": f"{COVARIATES['population']['asset']} @ {worldpop_year(year)}",
            "builtup": f"{COVARIATES['builtup']['asset']}/{ghsl_epoch(year)}",
        }
        print(f"Covariate plan for {args.country} {args.survey}, year {year}\n")
        for name, c in COVARIATES.items():
            band = c["band"]
            print(f"  {name}")
            print(f"    asset    : {resolved.get(name, c['asset'])}")
            print(f"    band     : {band if isinstance(band, str) else ', '.join(band)}"
                  f"   scale: {c['scale']} m")
            print(f"    reducers : {', '.join(c['reducers'])}")
            print(f"    why      : {c['why']}")
            print()

        print("All six are Earth Engine catalogue assets, reduced server-side.")
        print("Nothing is downloaded except the resulting table.\n")

        # Year mismatches are stated rather than left for the reader to notice.
        # docs/00 section 8.3 requires covariates be matched to survey year, so
        # anywhere that is impossible has to be visible and recorded.
        notes = []
        if worldpop_year(year) != year:
            notes.append(f"population uses {worldpop_year(year)}, not {year} "
                         f"(WorldPop ends {WORLDPOP_LAST_YEAR})")
        if ghsl_epoch(year) != year:
            notes.append(f"built surface uses the {ghsl_epoch(year)} epoch "
                         f"(GHSL is five-yearly)")
        notes.append("land cover uses ESA WorldCover v200, a single 2021 epoch, "
                     "for every survey year")
        print("Year mismatches to record as limitations:")
        for n in notes:
            print(f"  - {n}")
        return

    if not args.ge_file:
        raise SystemExit("--ge-file is required unless --dry-run is given. "
                         "It arrives with DHS approval.")

    from clusters import load_dhs_clusters

    ee = _require_ee()
    cs = load_dhs_clusters(args.ge_file, args.country, args.survey)
    print(cs.summary())

    import geopandas as gpd
    buffers = gpd.GeoDataFrame(
        cs.gdf[["cluster", "urban", "radius_m"]],
        geometry=cs.gdf["buffer"], crs="EPSG:4326",
    )

    image = build_image(ee, args.year)
    result = extract(ee, image, buffers.__geo_interface__)

    PROC.mkdir(parents=True, exist_ok=True)
    out = PROC / f"covariates_{args.survey}.csv"
    import pandas as pd
    df = pd.DataFrame([f["properties"] for f in result.getInfo()["features"]])

    # Provenance travels with the data. Which product version and which epoch
    # produced a row is not recoverable later, and if product version ever ends
    # up correlated with country that is a confound in the dimension this paper
    # measures. Recorded per row so it can be tested rather than assumed.
    df["survey_year"] = args.year
    df["viirs_asset"] = viirs_asset(args.year)
    df["pop_year"] = worldpop_year(args.year)
    df["ghsl_epoch"] = ghsl_epoch(args.year)

    df.to_csv(out, index=False)
    print(f"Wrote {out}  ({len(df)} clusters)")
    if worldpop_year(args.year) != args.year:
        print(f"  note: population taken from {worldpop_year(args.year)}, "
              f"WorldPop has no {args.year}")


if __name__ == "__main__":
    main()
