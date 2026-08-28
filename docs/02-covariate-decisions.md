# Covariate decisions, and why

Every choice here changes what the model can see. Recorded when made, so none
of it has to be reconstructed from memory later.

---

## Verified against real data, 8 August 2026

All six covariates were extracted over 5 km buffers at two Gambian sites before
any modelling work. The numbers agree with each other, which is the point of
running two sites rather than one.

| | Banjul (coastal) | Basse (inland) |
|---|---|---|
| nightlights, `average` | 1.31 | 0.35 |
| elevation, m | 0.76 | 26.4 |
| landcover mode | 80 (water) | 20 (shrubland) |
| water fraction | 0.807 | 0.020 |
| rainfall, mm | **null** | 713 |

Banjul is the capital and brighter; Basse is inland and higher; 713 mm is right
for inland Gambia. Nothing contradicts anything else, so the extraction path is
sound.

---

## Decision 1: rainfall is gap-filled near water, and the fill is flagged

**The problem.** CHIRPS is a land-only product. The Banjul buffer is 80.7%
water and returns null.

**Why it matters more here than elsewhere.** The Gambia is a narrow strip of
land wrapped around a river. It has a far higher share of water-adjacent
clusters than Mali, Burkina Faso or Nigeria. If null rainfall silently removed
those clusters, target-country clusters would drop out at a much higher rate
than training-country ones. The evaluation set would then differ from the
training set in a way we introduced, and the resulting miscalibration would look
like a finding.

**The decision.** Fill masked pixels with the mean of land rainfall within
20 km, using `unmask(focal_mean(20000))`. Rainfall is a smooth, large-scale
field, so a nearby land value is a reasonable estimate for a coastal cluster.

**The check.** `water_fraction` is extracted for every cluster, so we can
identify which ones relied on the fill and test whether excluding them changes
any conclusion. If it does, that goes in the paper.

## Decision 2: water fraction is a covariate, not just a diagnostic

Livelihood in a fishing settlement is not livelihood in an inland farming one.
The share of a cluster's buffer that is open water is real information about
economic activity, and the models are allowed to use it.

## Decision 3: land cover is summarised by mode, never mean

The band holds class codes (10 tree, 20 shrub, 40 crop, 80 water). Averaging
them produces a number that is not any class. An early test returned a mean of
79.65, which happened to be near the water class and was accidentally
informative, but only by coincidence. Mode is the only defensible summary.

## Decision 4: two nightlight bands, not one

`average_masked` has background noise removed, `average` does not. Which
predicts cluster wealth better is an empirical question, so both are carried and
the choice is made on validation data rather than asserted now.

## Decision 5: built surface is split residential and non-residential

`GHS_BUILT_S` provides `built_surface` and `built_surface_nres`. The
residential share of built area is plausibly informative about wealth in a way
the total is not, so both are kept.

---

## Open, to resolve when survey years are known

**VIIRS product version changes in 2022.** V21 covers the earlier years; V22
covers 2022 onwards, and the two are processed differently. If any country's
most recent survey falls in 2022 or later while the rest fall earlier, product
version becomes correlated with country. That is a confound we would be
introducing, in exactly the dimension the paper is measuring.

Resolve by either constraining all surveys to V21 years, or including product
version as a covariate and confirming it carries no signal. Decide once DHS
approval lands and the survey years are known.
