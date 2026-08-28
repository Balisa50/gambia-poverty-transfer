# Do prediction intervals for satellite-based poverty estimates survive a national border?

Code and documentation for a pre-registered evaluation of cross-border transfer
in satellite-based poverty estimation, using twelve West African Demographic and
Health Surveys.

Abdoulie Balisa, Department of Statistics and Actuarial Science, Kwame Nkrumah
University of Science and Technology.

The paper is in [`paper/paper.pdf`](paper/paper.pdf).

## What was asked, and what was found

Four hypotheses were fixed before data access was granted. None was supported.

| | prediction | result |
|---|---|---|
| H1 | out-of-country accuracy drops by about a third | falsified: it drops about 3% |
| H2 | a nominal 90% interval covers substantially less than 90% | not supported: 88.7% pooled, 89.3% on the target |
| H3 | adaptation improves accuracy but not calibration | premise fails: CORAL degrades accuracy |
| H4 | target coverage deviates beyond sampling noise | not confirmed, on a test with 53% power |

Two observations are carried as leads rather than results, and are labelled as
post-hoc wherever they appear: coverage varies across countries by 3.7 times what
sampling noise permits, and constant-width conformal intervals appear to fail in
shape on the target where adaptive ones do not.

## The pre-registration

`docs/` holds the protocol, the training design, the sanity gate and its bands,
and the target-country pre-registration, in the order they were written.

The specification for the single evaluation of the target country was committed
at **`bfa32ce277b2d21944b1f04912ba716a95dfe52b`** in the private working
repository, before any Gambian wealth label was read. It fixes the threshold,
the power, and the wording required for each outcome.

Amendments are dated, state what changed and why, and leave the original text in
place. Two are substantive and both were made after seeing a result:

- `docs/04` raises the sanity gate's upper band from 0.70 to 0.85 and makes three
  named leakage diagnostics mandatory above 0.70. The amendment says plainly
  that 0.746 was observed first.
- `docs/00` section 5 records that four countries were moved to earlier surveys,
  before any download, to keep one VIIRS product version across all twelve.

## Data

**No DHS data is in this repository and none may be added to it.** The terms of
access forbid redistribution, and losing access is permanent.

The surveys used are listed in the paper. To reproduce, apply for the same
datasets at <https://dhsprogram.com> under your own account, and download for
each country the Household Recode in Stata format, the Geographic Data
shapefile, and the Geospatial Covariates file.

Covariates come from open sources requiring no application: VIIRS nightlights,
WorldPop, GHSL built surface, ESA WorldCover, CHIRPS and SRTM, all through
Google Earth Engine.

## Reproducing

```
pip install pandas geopandas scikit-learn matplotlib earthengine-api
earthengine authenticate
export EE_PROJECT=your-earth-engine-project
```

Then, in order:

```
python src/unpack.py           # extract DHS download bundles into data/raw/dhs
python src/inventory.py        # check every HR file joins its GPS file
python src/extract_all.py      # covariates for all countries, resumable
python src/build_table.py      # join wealth to covariates, one row per cluster
python src/run_gate.py         # sanity gate plus its leakage diagnostics
python src/experiment_h2_h3.py # H2 and H3 on the training countries
python src/dhs_crosscheck.py   # our extraction against DHS's own
python src/make_figures.py
python src/make_sim_figure.py
```

The target-country evaluation is deliberately awkward to run:

```
python src/evaluate_gambia.py --i-have-read-the-preregistration
```

It refuses without the flag, warns if a result already exists, and raises if
target-country data reaches the calibration set.

## Checking the instruments

Four modules demonstrate their own behaviour on synthetic data, with no DHS
input:

```
python src/splits.py       # random splits overstate accuracy; blocking exposes it
python src/conformal.py    # coverage holds under exchangeability, fails under shift
python src/sanity_gate.py  # the gate fires correctly in all eight conditions
python src/clusters.py     # displacement-matched buffers
```

## Licence

Code is released for inspection and reuse under the MIT licence. The DHS data it
processes is not covered by that licence and is not included.
