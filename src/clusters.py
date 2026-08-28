"""
DHS survey clusters: loading, quality filtering, and displacement-aware buffers.

Why buffers rather than points
------------------------------
DHS never publishes the true location of a survey cluster. Coordinates are
randomly displaced before release, to protect respondent confidentiality:

    urban clusters   up to  2 km
    rural clusters   up to  5 km
    1% of rural      up to 10 km

The displacement is applied within the survey's second-level administrative
area, so a cluster never moves across that boundary, but within it the recorded
point can be several kilometres from where the households actually are.

Extracting a satellite covariate at the recorded coordinate therefore reads the
wrong place. The standard correction is to summarise each covariate over a
buffer whose radius matches the displacement distance, so that the true location
is somewhere inside the area being summarised. This module builds those buffers.

Getting this wrong is the most common error in the poverty-mapping literature
and the first thing a careful reviewer checks.

Buffers are computed in a local UTM projection rather than in degrees, because a
degree of longitude is about 108 km at the equator and shrinks towards the
poles; buffering in degrees would produce ellipses of the wrong size that vary
with latitude.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

WGS84 = "EPSG:4326"

# Displacement distances published by DHS, in metres.
URBAN_RADIUS_M = 2_000
RURAL_RADIUS_M = 5_000
RURAL_TAIL_RADIUS_M = 10_000   # applies to 1% of rural clusters
RURAL_TAIL_FRACTION = 0.01

# DHS writes (0, 0) into the coordinate fields when a cluster was not
# georeferenced. Left in place, these become a point in the Gulf of Guinea and
# silently poison every covariate extracted for them.
MISSING_SENTINEL = 0.0


@dataclass(frozen=True)
class ClusterSet:
    """Survey clusters for one country-year, with buffers attached."""

    country: str
    survey: str
    gdf: gpd.GeoDataFrame

    def __len__(self) -> int:
        return len(self.gdf)

    def summary(self) -> str:
        urban = int((self.gdf["urban"]).sum())
        return (f"{self.country} {self.survey}: {len(self.gdf)} clusters "
                f"({urban} urban, {len(self.gdf) - urban} rural)")


def utm_epsg(lon: float, lat: float) -> str:
    """EPSG code of the UTM zone containing a point.

    Buffers are metric operations, so they must be done in a projected CRS.
    UTM is accurate to well under a percent over the few-kilometre distances
    used here, which is far below the uncertainty introduced by displacement
    itself.
    """
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def buffer_radius_m(urban: bool | np.ndarray) -> np.ndarray:
    """Displacement-matched buffer radius in metres.

    Rural clusters use 5 km rather than 10 km. The 1% displaced further are not
    identifiable in the released data, so a 10 km radius for every rural cluster
    would inflate 99% of them to cover roughly four times the necessary area,
    diluting the covariate signal badly. Using 5 km accepts a known error on 1%
    of clusters in exchange for a much sharper signal on the rest. Record the
    choice; it is a defensible trade-off but it is a choice.
    """
    urban = np.asarray(urban, dtype=bool)
    return np.where(urban, URBAN_RADIUS_M, RURAL_RADIUS_M).astype(float)


def drop_ungeoreferenced(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, int]:
    """Remove clusters DHS could not georeference, flagged as (0, 0)."""
    lon = gdf.geometry.x.to_numpy()
    lat = gdf.geometry.y.to_numpy()
    bad = (np.isclose(lon, MISSING_SENTINEL) & np.isclose(lat, MISSING_SENTINEL))
    bad |= ~np.isfinite(lon) | ~np.isfinite(lat)
    return gdf.loc[~bad].copy(), int(bad.sum())


def add_buffers(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach a metric buffer polygon to each cluster.

    Clusters are grouped by UTM zone so that each group is projected once
    rather than once per row, which matters at the scale of tens of thousands
    of clusters across twelve countries.
    """
    if gdf.crs is None:
        raise ValueError("clusters have no CRS; expected EPSG:4326")
    gdf = gdf.to_crs(WGS84).copy()
    gdf["radius_m"] = buffer_radius_m(gdf["urban"].to_numpy())
    gdf["utm"] = [utm_epsg(p.x, p.y) for p in gdf.geometry]

    pieces = []
    for epsg, grp in gdf.groupby("utm", sort=False):
        projected = grp.to_crs(epsg)
        buffered = projected.geometry.buffer(projected["radius_m"].to_numpy())
        out = grp.copy()
        out["buffer"] = gpd.GeoSeries(buffered, crs=epsg).to_crs(WGS84).to_numpy()
        # Area is computed in the projected CRS, where it is meaningful.
        out["buffer_km2"] = buffered.area.to_numpy() / 1e6
        pieces.append(out)

    return pd.concat(pieces).loc[gdf.index]


def load_dhs_clusters(ge_path: str | Path, country: str,
                      survey: str) -> ClusterSet:
    """Load a DHS geographic (GE) shapefile and prepare it for extraction.

    The GE file carries one point per cluster with these fields:
        DHSCLUST   cluster number, the join key to the household recode
        URBAN_RURA 'U' or 'R'
        LATNUM     latitude
        LONGNUM    longitude
    """
    gdf = gpd.read_file(ge_path)
    cols = {c.upper(): c for c in gdf.columns}

    required = ["DHSCLUST", "URBAN_RURA"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"{ge_path} is missing expected DHS fields: {missing}")

    gdf = gdf.rename(columns={cols["DHSCLUST"]: "cluster",
                              cols["URBAN_RURA"]: "urban_rural"})
    gdf["urban"] = gdf["urban_rural"].astype(str).str.upper().str.startswith("U")

    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)

    gdf, n_dropped = drop_ungeoreferenced(gdf)
    if n_dropped:
        print(f"  {country} {survey}: dropped {n_dropped} ungeoreferenced clusters")

    gdf = add_buffers(gdf)
    keep = ["cluster", "urban", "radius_m", "buffer_km2", "geometry", "buffer"]
    return ClusterSet(country=country, survey=survey,
                      gdf=gdf[keep].reset_index(drop=True))


def _selftest() -> None:
    """Check the geometry on synthetic clusters, before any DHS data exists.

    Everything here is verifiable without the survey data: buffer radii should
    come out at the requested distance in metres, areas should match pi r^2,
    and (0, 0) clusters should be removed.
    """
    from shapely.geometry import Point

    print("=== clusters.py self-test (synthetic points) ===\n")

    # Banjul, Dakar, Bamako, Lagos, plus one deliberate missing-coordinate row.
    rows = [
        ("GM", -16.578, 13.454, True),
        ("SN", -17.444, 14.693, True),
        ("ML",  -7.999, 12.639, False),
        ("NG",   3.379,  6.524, True),
        ("XX",   0.000,  0.000, False),
    ]
    gdf = gpd.GeoDataFrame(
        {"DHSCLUST": range(1, len(rows) + 1),
         "URBAN_RURA": ["U" if r[3] else "R" for r in rows]},
        geometry=[Point(r[1], r[2]) for r in rows],
        crs=WGS84,
    )

    print("UTM zone assignment:")
    for _, lon, lat, _u in rows:
        print(f"  ({lon:>8.3f}, {lat:>6.3f}) -> {utm_epsg(lon, lat)}")

    gdf2, dropped = drop_ungeoreferenced(gdf)
    print(f"\nungeoreferenced dropped: {dropped} (expected 1)")
    assert dropped == 1, "the (0,0) row should have been removed"

    gdf2["urban"] = gdf2["URBAN_RURA"].str.startswith("U")
    out = add_buffers(gdf2)

    print(f"\n{'cluster':<9}{'urban':>7}{'radius_m':>10}{'area_km2':>10}"
          f"{'expected':>10}{'err_%':>8}")
    ok = True
    for _, r in out.iterrows():
        expected = np.pi * (r.radius_m / 1000.0) ** 2
        err = abs(r.buffer_km2 - expected) / expected * 100
        ok &= err < 1.0
        print(f"{int(r.DHSCLUST):<9}{str(bool(r.urban)):>7}{r.radius_m:>10.0f}"
              f"{r.buffer_km2:>10.2f}{expected:>10.2f}{err:>8.3f}")

    assert ok, "buffer areas deviate from pi*r^2 by more than 1%"
    # The residual is ~0.16% and is not projection error. Shapely approximates a
    # circle with 16 segments per quarter, giving a 64-gon whose area is
    # (n / 2pi) sin(2pi / n) = 0.9984 of the true circle. That the observed
    # error matches this exactly is evidence the UTM step is essentially exact.
    print("\nAll buffer areas within 1% of pi*r^2.")
    print("Urban buffers 2 km, rural 5 km, matching DHS displacement.")


if __name__ == "__main__":
    _selftest()
