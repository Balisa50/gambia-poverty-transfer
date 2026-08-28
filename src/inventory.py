"""
Inventory whatever DHS files have been downloaded, and check they are usable.

Run this before anything else. It answers three questions that are cheap now and
expensive later: which countries actually arrived, whether each has both the
household recode and the GPS file, and whether the two join on cluster number.

A silent join failure is the worst outcome available here. It does not raise, it
just produces fewer rows, and fewer rows in a way that correlates with whatever
made the join fail. That would look like a data problem in the results and could
easily be mistaken for a finding.

Nothing in this file is committed to git. See .gitignore: DHS microdata must
never be redistributed, and the terms of use are explicit that redistribution
ends access.

Run:  python src/inventory.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dhs"

# The twelve approved countries. The Gambia is the target; the rest train.
COUNTRIES = {
    "GM": "Gambia (TARGET)", "SN": "Senegal", "ML": "Mali", "NG": "Nigeria",
    "GH": "Ghana", "BF": "Burkina Faso", "CI": "Cote d'Ivoire",
    "MR": "Mauritania", "SL": "Sierra Leone", "GN": "Guinea",
    "BJ": "Benin", "TG": "Togo",
}

# DHS names files as <CC><TT><VV><FF>.<ext>, e.g. GMHR81FL.DTA
# CC country, TT type (HR household recode, GE geographic), VV version.
#
# Note the download packaging: the Stata archive is offered as GMHR81DT.ZIP but
# unzips to GMHR81FL.DTA. DT names the package, FL names the file. Nothing
# should be renamed.
# The version field is two characters, and the second is NOT always a digit:
# phase plus subversion, as in 81 (Gambia 2019-20) but also 8B (Senegal 2019)
# and 7A (Mali 2018, Nigeria 2018, Sierra Leone 2019). Requiring \d+ there
# matched only the all-numeric codes and silently skipped the rest, reporting
# files that were sitting in the folder as "not downloaded".
HR_RE = re.compile(r"^([A-Z]{2})HR([0-9][0-9A-Z])([A-Z]{2})\.(DTA|SAV|DAT)$", re.I)
GE_RE = re.compile(r"^([A-Z]{2})GE([0-9][0-9A-Z])([A-Z]{2})\.(shp)$", re.I)

# DHS's own pre-computed geospatial covariates, one row per cluster.
#
# These are NOT features. Building on someone else's extraction would make this
# a wrapper around their pipeline. They are an independent extraction of
# comparable quantities over the same clusters, which makes them the only
# external check available on our Earth Engine output (docs/04). Tracked here so
# a missing one is visible now rather than when the cross-check is run.
GC_RE = re.compile(r"^([A-Z]{2})GC([0-9][0-9A-Z])([A-Z]{2})\.(csv)$", re.I)

# The shapefile sidecars. A lone .shp is unreadable: the attributes, including
# the coordinates and the cluster number, live in the .dbf. Downloading the zip
# and extracting only the .shp is an easy mistake and produces a file that looks
# present and fails at the join.
SHP_SIDECARS = (".dbf", ".shx")

WEALTH_COL = "hv271"    # wealth index factor score, scaled by 100000
CLUSTER_COL = "hv001"   # cluster number, the join key


def find_files() -> dict[str, dict]:
    """Locate the household recode, GPS shapefile and DHS covariates per country."""
    found: dict[str, dict] = {c: {} for c in COUNTRIES}
    if not RAW.exists():
        return found

    for p in RAW.rglob("*"):
        if not p.is_file():
            continue
        for key, rx in (("hr", HR_RE), ("ge", GE_RE), ("gc", GC_RE)):
            if (m := rx.match(p.name)):
                cc = m.group(1).upper()
                if cc in found:
                    found[cc][key] = p
                break
    return found


def missing_sidecars(shp: Path) -> list[str]:
    """Sidecars absent next to a .shp, which make it unreadable."""
    return [s for s in SHP_SIDECARS if not shp.with_suffix(s).exists()]


def check_join(hr_path: Path, ge_path: Path) -> dict:
    """Load both files and confirm they join on cluster number.

    Reports the overlap rather than assuming it. A partial overlap is a real
    finding worth investigating, not something to silently drop.
    """
    import geopandas as gpd

    out: dict = {}
    try:
        hr = pd.read_stata(hr_path, columns=[CLUSTER_COL, WEALTH_COL],
                           convert_categoricals=False)
    except Exception:
        # Fall back to a full read if the column subset is not available.
        hr = pd.read_stata(hr_path, convert_categoricals=False)
        keep = [c for c in (CLUSTER_COL, WEALTH_COL) if c in hr.columns]
        if len(keep) < 2:
            out["error"] = f"missing {set([CLUSTER_COL, WEALTH_COL]) - set(hr.columns)}"
            return out
        hr = hr[keep]

    ge = gpd.read_file(ge_path)

    # Counted before the columns are uppercased below, which renames "geometry"
    # and leaves the frame with no active geometry column.
    #
    # DHS writes (0, 0) where a cluster could not be georeferenced, but not
    # always exactly: Mali 2018 stores 5.684342e-14, which is 2^-44, the residue
    # of a coordinate transform applied to zero. An equality test against 0
    # missed all 17 of them while clusters.py, which tests with a tolerance,
    # dropped them. Two modules disagreeing about the same defect is worse than
    # either being wrong, so the test lives in one place and both use it.
    from clusters import drop_ungeoreferenced
    _, zeros = drop_ungeoreferenced(ge)

    ge.columns = [c.upper() for c in ge.columns]

    hr_clusters = set(pd.to_numeric(hr[CLUSTER_COL], errors="coerce").dropna().astype(int))
    ge_clusters = set(pd.to_numeric(ge["DHSCLUST"], errors="coerce").dropna().astype(int))


    out.update({
        "households": len(hr),
        "hr_clusters": len(hr_clusters),
        "ge_clusters": len(ge_clusters),
        "matched": len(hr_clusters & ge_clusters),
        "hr_only": len(hr_clusters - ge_clusters),
        "ge_only": len(ge_clusters - hr_clusters),
        "ungeoref": zeros,
        "wealth_null": int(hr[WEALTH_COL].isna().sum()),
        # The label is the cluster mean, so its standard error scales with
        # 1/sqrt(households per cluster). Mauritania 2019-21 sampled 10 per
        # cluster where every other survey sampled 22 to 30, giving its cluster
        # means roughly 1.6 times the noise. That is label noise correlated
        # with country, in the dimension this paper measures, so it has to be
        # visible rather than discovered as a country that fits badly.
        "hh_per_cluster": len(hr) / max(1, len(hr_clusters)),
    })
    return out


def main() -> None:
    print(f"Looking in {RAW}\n")
    found = find_files()

    print(f"{'cc':<4}{'country':<20}{'HR':>4}{'GE':>4}{'GC':>4}   status")
    print("-" * 66)
    complete, broken_shp, no_gc = [], [], []
    for cc, name in COUNTRIES.items():
        f = found[cc]
        hr = "yes" if "hr" in f else "-"
        ge = "yes" if "ge" in f else "-"
        gc = "yes" if "gc" in f else "-"

        # A .shp without its sidecars is present but unreadable, so it must not
        # be reported as ready.
        lost = missing_sidecars(f["ge"]) if "ge" in f else []
        if lost:
            broken_shp.append((cc, lost))
            ge = "BAD"

        if "hr" in f and "ge" in f and not lost:
            status = "ready"
            complete.append(cc)
            if "gc" not in f:
                no_gc.append(cc)
        elif f:
            status = "INCOMPLETE"
        else:
            status = "not downloaded"
        print(f"{cc:<4}{name:<20}{hr:>4}{ge:>4}{gc:>4}   {status}")

    print(f"\n{len(complete)}/{len(COUNTRIES)} countries ready.")

    for cc, lost in broken_shp:
        print(f"  {cc}: shapefile is missing {', '.join(lost)}. The attributes, "
              "including coordinates and cluster number, live in the .dbf. "
              "Re-extract the whole GE zip.")
    if no_gc:
        print(f"  No DHS covariate file (GC) for: {', '.join(no_gc)}. Not "
              "needed to proceed, but docs/04 uses it as the only external "
              "check on our own extraction.")
    if not complete:
        print("\nNothing to check yet. Download the HR and GE files, unzip them")
        print(f"into {RAW}, then run this again.")
        return

    print("\n--- join check (cluster numbers must match across HR and GE) ---")
    print(f"{'cc':<4}{'houses':>8}{'HR cl':>7}{'GE cl':>7}{'match':>7}"
          f"{'HRonly':>8}{'GEonly':>8}{'no geo':>8}{'w.null':>8}{'hh/cl':>7}")
    rows = []
    for cc in complete:
        try:
            r = check_join(found[cc]["hr"], found[cc]["ge"])
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"{cc:<4}  ERROR: {e!r}")
            continue
        if "error" in r:
            print(f"{cc:<4}  ERROR: {r['error']}")
            continue
        r["cc"] = cc
        rows.append(r)
        print(f"{cc:<4}{r['households']:>8}{r['hr_clusters']:>7}"
              f"{r['ge_clusters']:>7}{r['matched']:>7}{r['hr_only']:>8}"
              f"{r['ge_only']:>8}{r['ungeoref']:>8}{r['wealth_null']:>8}"
              f"{r['hh_per_cluster']:>7.1f}")

    if rows:
        df = pd.DataFrame(rows)
        bad = df[df["hr_only"] > 0]
        print()
        if len(bad):
            print("  WARNING: some HR clusters have no GPS record, in "
                  f"{', '.join(bad['cc'])}. Those clusters cannot be used and "
                  "their loss is not random. Check before proceeding.")
        else:
            print("  Every HR cluster has a matching GPS record.")
        # An ungeoreferenced cluster joins on cluster number like any other, so
        # it survives the match count above while having no usable location.
        # clusters.py drops these, so counting them here would overstate what
        # actually reaches the model.
        ungeo = df["ungeoref"].clip(lower=0)
        matched = df["matched"]
        total = int((matched - ungeo).sum())

        lost = df[ungeo > 0]
        if len(lost):
            print("  Clusters with no coordinates, dropped downstream:")
            for _, r in lost.iterrows():
                print(f"    {r['cc']}: {int(r['ungeoref'])} of {int(r['matched'])}")

        print(f"  Usable clusters across {len(df)} countries: {total:,}")


if __name__ == "__main__":
    main()
