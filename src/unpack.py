"""
Unpack DHS download bundles into data/raw/dhs, flat.

DHS does not hand you the files you ticked. It bundles them into one archive
named after the request, like GM_2019-20_DHS_08272026_1244_255413.zip, holding
one folder per dataset:

    GMHR81DT/GMHR81FL.DTA      household recode, the label
    GMGE81FL/GMGE81FL.shp      cluster locations, plus sidecars
    GMGC82FL/GMGC82FL.csv      DHS's own covariates, for the cross-check

Only the data files are extracted. The Stata bundle also ships .DO, .DCT, .MAP,
.FRQ and .FRW support files that together are larger than the dataset and are
not used here.

Nothing is renamed. inventory.py parses the original DHS filenames, and the
version code in them identifies the survey.

Nothing extracted here is committed. .gitignore excludes data/raw/ entirely;
DHS microdata must never be redistributed and losing access is permanent.

Run:  python src/unpack.py
      python src/unpack.py --downloads "D:/some/other/folder"
"""

from __future__ import annotations

import argparse
import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "dhs"

# A bundle is identified by what is inside it, not by what it is called.
#
# The name was tried first and failed three times. DHS names bundles
# <CC>_<survey>_<TYPE>_<MMDDYYYY>_<HHMM>_<project id>.zip, but the type is DHS
# for a Standard survey and CONTINUOUSDHS for a continuous one, and the time
# field drops its leading zero before 10am, so ML_2018_DHS_08272026_133_...
# has three digits where GM_..._1244_... has four. Every pattern tightened
# enough to be meaningful excluded a real bundle, and the failure was silent:
# the country simply read as "not downloaded".
#
# Looking inside is both simpler and self-validating. A zip counts if it holds
# a file named the way DHS names its data files. Only the central directory is
# read, so this is cheap even for large unrelated archives.
DATA_RE = re.compile(
    r"^[A-Z]{2}(HR|GE|GC)[0-9][0-9A-Z][A-Z]{2}\.(DTA|shp|csv)$", re.I)

# Data files worth keeping. The shapefile sidecars are not optional: the
# attributes, including the coordinates and the cluster number, live in the
# .dbf, so a lone .shp is unreadable.
KEEP = {".dta", ".csv", ".shp", ".dbf", ".shx", ".prj", ".cpg", ".sbn", ".sbx"}


def default_downloads() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"


def is_dhs_bundle(path: Path) -> bool:
    """True if the zip holds at least one DHS-named data file.

    Anything unreadable as a zip is simply not a bundle. Downloads folders hold
    all sorts of things and none of them should stop the run.
    """
    try:
        with zipfile.ZipFile(path) as z:
            return any(DATA_RE.match(Path(i.filename).name)
                       for i in z.infolist() if not i.is_dir())
    except (zipfile.BadZipFile, OSError):
        return False


def unpack(bundle: Path, dest: Path) -> list[str]:
    """Extract the data files from one bundle, flattening the folders."""
    written = []
    with zipfile.ZipFile(bundle) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if Path(name).suffix.lower() not in KEEP:
                continue
            target = dest / name
            with z.open(info) as src, open(target, "wb") as out:
                out.write(src.read())
            written.append(name)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--downloads", type=Path, default=None,
                    help="folder holding the DHS bundles (default: ~/Downloads)")
    args = ap.parse_args()

    src_dir = args.downloads or default_downloads()
    if not src_dir.is_dir():
        raise SystemExit(f"No such folder: {src_dir}")

    candidates = sorted(p for p in src_dir.glob("*.zip"))
    bundles = [p for p in candidates if is_dhs_bundle(p)]
    if not bundles:
        raise SystemExit(
            f"No DHS bundles found in {src_dir}.\n"
            f"Looked inside {len(candidates)} zip file(s); none held a DHS data "
            "file such as GMHR81FL.DTA or GMGE81FL.shp.")

    RAW.mkdir(parents=True, exist_ok=True)
    total = 0
    for b in bundles:
        written = unpack(b, RAW)
        total += len(written)
        print(f"{b.name}")
        for n in sorted(written):
            print(f"    {n}")

    print(f"\n{len(bundles)} bundle(s), {total} files -> {RAW}")
    print("Now run:  python src/inventory.py")


if __name__ == "__main__":
    main()
