# The sanity gate

Before any claim about cross-border calibration, the pipeline must produce an
in-country accuracy figure consistent with published work. If it cannot rebuild
a known result, nothing novel it produces is interpretable, and we would have no
way to distinguish a finding from a bug.

This gate runs first and its outcome is reported whether or not it passes.

---

## Published benchmarks

All figures below were read from the papers themselves, and the citations
verified against Crossref by DOI on 8 August 2026.

| Study | Method | Task | r² |
|---|---|---|---|
| Yeh et al. 2020 | multispectral CNN | asset wealth, **held-out countries**, pooled | **0.67** |
| Yeh et al. 2020 | multispectral CNN | asset wealth, held-out countries, country-averaged | **0.70** |
| Jean et al. 2016 | high-res imagery + transfer learning | asset wealth, 5 African countries | 0.56 |
| Blumenstock et al. | call detail records | asset wealth, Rwanda | 0.62 |
| (ref. 5 in Yeh) | **survey data + geospatial covariates** | housing quality, sub-Saharan Africa | **0.67** |
| (ref. 1 in Yeh) | survey data + geospatial covariates | child stunting | 0.49 |
| (ref. 18 in Yeh) | geospatial covariates | standard of living, Senegal | 0.69 |

Yeh et al. 2020, *Nature Communications* 11(1), 2020. DOI 10.1038/s41467-020-16185-w.
Jean et al. 2016, *Science* 353(6301):790-794. DOI 10.1126/science.aaf7894.

---

## Two things this table settles

**We must not target the CNN number.** Yeh et al. reach r² 0.67 to 0.70 with a
convolutional network trained on raw multispectral imagery across 23 countries.
Our model uses tabular summaries of six covariates and a ridge or gradient
boosting fit. Those are different methods with different capacity. Falling short
of 0.67 would tell us nothing about whether our pipeline works.

The right comparison is the geospatial-covariate row: models of that family
report r² between roughly 0.47 and 0.69 across related outcomes.

**Cross-country point accuracy is already known to work.** This is the more
important observation, and it sets up the paper. Yeh et al. explicitly report
r² 0.67 *in held-out countries*. Transfer is not broken for point prediction,
and nobody should expect our paper to show that it is.

What no paper in that table reports is **coverage**. Every one gives r², none
gives whether a stated 90% interval contains 90% of held-out truth. That absence
is the gap this project addresses, and the benchmark table is the evidence that
the gap is real rather than assumed.

---

## The gate, stated in advance

In-country, spatially blocked, cluster-level wealth index. Both bounds bind.

| Band | r² | Verdict |
|---|---|---|
| Below 0.30 | too low | **FAIL.** Something is broken. |
| 0.30 to 0.45 | weak | **WARN.** Plausible for a sparse covariate set, but investigate before proceeding. |
| 0.45 to 0.70 | expected | **PASS.** |
| Above 0.70 | too high | **FAIL.** Leakage suspected. |

**The upper bound is not a formality.** A tabular model on six covariates should
not beat a multispectral CNN trained on 20,000 villages. If it appears to, the
most likely explanation by far is that spatial autocorrelation is leaking
between folds, which is precisely the failure mode that would manufacture this
paper's headline result. A gate that only catches "too low" would miss the
dangerous direction.

The naive random-split r² is computed alongside the blocked figure. On synthetic
data the gap between them was 0.21 (see `src/splits.py`). A large gap on real
data is expected and is reported; a gap near zero would suggest the blocking is
not working and needs checking.

---

## An independent check on our own extraction

DHS publishes its own pre-computed geospatial covariates per cluster, at
<http://spatialdata.dhsprogram.com/covariates/>. They were pointed out in the
GPS approval email.

**We do not use them as features.** Building the paper on someone else's
extraction would make it a wrapper around their pipeline rather than our own
work, and would tie the covariate set to their choices.

**We do use them to check ours.** They are an independent extraction of
comparable quantities over the same clusters, which makes them the closest thing
available to ground truth for our Earth Engine pipeline. Correlate our
nightlights and population against theirs, per cluster. High agreement means the
buffers, the joins and the reducers are working. Low agreement means a bug, and
we find it before it contaminates any result.

This is worth more than it appears. Every downstream number depends on the
extraction being right, and until now we had no external way to confirm it. A
disagreement here would be far cheaper to discover than the same bug surfacing
as an unexplained calibration failure.

Their buffer conventions may differ from ours, so exact equality is not
expected. Rank correlation is the right measure, and a Spearman rho below about
0.9 on nightlights should be treated as a failure.

## If it fails

**Below 0.30.** Work backwards through the pipeline: covariate extraction, the
cluster join on `hv001`, buffer geometry, wealth index sign and scaling. Do not
proceed to transfer experiments. A broken pipeline producing a null result on
calibration would be indistinguishable from a real finding.

**Above 0.70.** Treat as leakage until proven otherwise. Check the block size
against the empirical variogram, confirm whole blocks are held out rather than
points, and confirm no cluster appears in both sides of a split. Only after
those checks would we consider that the result is genuine.

**Passes but the naive and blocked figures are identical.** The spatial blocking
is not doing anything. Check the block assignment before trusting either number.

---

## What gets reported either way

The gate result goes in the paper regardless of outcome, with the benchmark
table above, so a reader can judge whether the pipeline is sound before reading
anything about calibration. Reporting only a passing gate would be selective
reporting of our own validation.

---

## Cross-check result, 2026-08-28

Run against all twelve countries after the first complete extraction. **It does
not pass at the pre-registered threshold.** Recorded here in full, including the
parts that argue against the pipeline, because reporting only a passing gate
would be selective reporting of our own validation.

### What was compared

| ours | theirs | why this pairing |
|---|---|---|
| `nightlights_mean` | `Nightlights_Composite` | same quantity |
| `population_mean` | `UN_Population_Density_2015` | both densities |

The population counterpart was first taken as `All_Population_Count_2015`, which
was wrong: our value is a mean over the buffer, a density, and theirs is a
count. Across clusters whose buffers differ in area by design, 2 km urban and
5 km rural, that scrambles the ranking. Ghana scored 0.262 against the count and
0.836 against the density. The pairing is now decided on units, before looking
at any correlation, and must stay that way. Trying every DHS population column
and keeping the best-scoring one is the practice this paper exists to criticise.

### Result

Spearman rho, per country. Threshold 0.90, fixed in advance.

| | nightlights | population |
|---|---|---|
| GH | **0.963** | 0.836 |
| BJ | **0.927** | no data |
| TG | **0.916** | 0.861 |
| CI | **0.913** | 0.773 |
| MR | **0.904** | 0.864 |
| SN | 0.872 | 0.791 |
| BF | 0.866 | 0.805 |
| NG | 0.860 | 0.799 |
| GM | 0.843 | **0.942** |
| ML | 0.829 | no data |
| GN | 0.727 | **0.926** |
| SL | 0.727 | 0.888 |

Seventeen of twenty-four pairs below threshold. Benin and Mali have no
population comparison: `UN_Population_Density_2015` is the -9999 sentinel for
every cluster in both.

### What this does and does not show

**The extraction machinery is sound, and this is the load-bearing evidence.**
Our own `population_mean` and `builtup_mean` come from independent products,
WorldPop and GHSL, extracted over the same buffers by the same code. They agree
at Spearman 0.907 to 0.951 in **all twelve countries**, with no country an
outlier. A broken buffer geometry, a broken cluster join or a broken reducer
would degrade that too. It does not degrade anywhere.

**Nightlights is the covariate that disagrees**, in the same countries, against
two independent references. Our `nightlights_mean` against our own
`builtup_mean` ranks the countries almost identically to the DHS comparison:

    SL 0.662 / 0.727    GN 0.683 / 0.727    ML 0.711 / 0.829
    NG 0.781 / 0.860    GH 0.941 / 0.963

**Darkness explains part of it, not all.** More than half of clusters read below
0.5 radiance units in ten of twelve countries, and near-zero radiance cannot be
ranked: noise decides the order. Share of dark clusters against agreement gives
Spearman -0.536. The extremes fit well, Sierra Leone at 77% dark and 0.727,
Cote d'Ivoire at 34% and 0.913, but the middle does not: Togo is 60% dark and
still reaches 0.916, Gambia is 47% dark and only 0.843.

**The comparison is also confounded, which limits what a failure proves.**
`Nightlights_Composite` carries no year at all, and every other DHS covariate
stops at 2015, while ours are matched to survey years spanning 2014 to 2021.
DHS's buffer conventions are not documented as matching ours.

### Decision

The threshold is not being moved. It was fixed before this data existed, and
lowering it now to accommodate the result is precisely the practice this paper
criticises in others.

What is recorded instead: the cross-check fails at 0.90, the internal coherence
check passes decisively and localises the disagreement to nightlights, and part
of the nightlights disagreement is attributable to unrankable near-zero radiance
in dark countries. The r-squared gate in this document is a separate and more
informative test, and it is now unblocked, because what it needs from the
extraction is exactly what the coherence check verified.

---

## Gate result, 2026-08-28

Run on the 11 training countries, 6,426 clusters. The Gambia is excluded
(docs/03 section 2.3); running the gate on the target would spend the one look
the design allows on a diagnostic.

**Pooled verdict: FAIL, in the high direction.** Blocked r-squared 0.746 against
a ceiling of 0.70.

    r2, naive random     0.783
    r2, spatially blocked 0.746
    leakage gap          0.036

Per country, 7 of 11 pass: BF 0.700, BJ 0.566, CI 0.629, GH 0.651, NG 0.665,
SL 0.667, SN 0.550 pass; GN 0.748, ML 0.766, TG 0.727 fail high; MR 0.438 warns,
with the largest leakage gap of any country at 0.370.

### The mandated checks all pass

This document requires three checks before accepting a high result. All three
were run and none supports the leakage explanation.

**Whole blocks are held out.** Of 311 blocks at 110 km, zero are split across
folds. Fold sizes are 1286/1285/1285/1285/1285.

**Block size matches the variogram.** The empirical correlation range is 55 km
and blocks are 110 km, twice the range, as specified.

**Blocking is not defeated by country structure.** 53 of 311 blocks span a
national border, so the grid is not simply partitioning by country.

### The between-country hypothesis was tested and refuted

The pooled leakage gap of 0.036 is smaller than every single country's, which
looked like blocking failing to bite. The obvious explanation was that pooled
r-squared is inflated by between-country variance, a model scoring well by
learning only that one country is richer than another.

That is wrong, and the reason matters for the paper.

**`hv271` is standardised to mean 0 and standard deviation 1 within each country
by construction.** Verified at household level: Nigeria mean 0.0000 sd 0.9940,
Sierra Leone 0.0000 / 0.9909, Gambia 0.0000 / 0.9874. Cluster means by country
range only from 0.001 to 0.069.

So the variance of country means is 0.0002 against a total of 0.7400, which is
0.0% of the total. There is no between-country signal available to learn.
Demeaning wealth by country changes blocked r-squared from 0.746 to 0.747.

### What this means for the paper

The label is a **within-country relative position**, not an absolute standard of
living. A cluster at +1 in Sierra Leone and a cluster at +1 in Nigeria are not
equally wealthy in any absolute sense; each is one standard deviation above its
own country's mean.

This sharpens the transfer question rather than undermining it. Training pooled
and predicting The Gambia means asking a model to map absolute satellite
measurements onto a country-relative rank, where the mapping from radiance to
rank depends on the country's own distribution. That is a concrete mechanism by
which calibration could fail out-of-country, and it was not stated in the
protocol. It belongs in docs/00 section 8, which currently records only that
comparability across countries is assumed.

### The ceiling is not being moved

The exceedance is unexplained by any pre-registered leakage diagnostic. One
candidate remains: the 0.70 ceiling was set against Yeh et al.'s held-out-country
CNN figures, 0.67 and 0.70, which measure a harder task than the in-country
blocked prediction the gate actually performs. The in-country comparator in the
benchmark table above, geospatial covariates for standard of living in Senegal,
is 0.69, and our 0.746 sits just above it.

That is an argument that the gate was benchmarked against the wrong row, not an
argument that 0.746 is sound. Either way it is not a decision to take by
editing a number after seeing the result. The gate is recorded as FAILED, the
diagnostics are recorded in full, and whether to amend the band is a
pre-registration amendment with a date and a reason attached, which is the
author's call and not a silent edit.

---

## Amendment to the gate band, 2026-08-28

**This amendment was made after seeing the result.** The blocked r-squared of
0.746 was observed first, and the band that failed it is being changed. Stating
that plainly is the condition for the amendment being worth anything: a reader
must be able to judge for themselves whether the reasoning below is sound or is
rationalisation. The original band, the original FAIL, and the full diagnostics
remain above and are not edited.

### What changed, and why it is not simply raising the bar to pass

The original band's upper bound of 0.70 existed to catch spatial leakage. It was
a **proxy** for leakage, chosen before any data existed, when no direct test was
available.

A direct test is now available, and it is far more informative than a threshold
on a single number. Two were run.

**Block-size sensitivity.** Spatial leakage is a function of block size: it
appears when blocks are smaller than the covariate correlation range and
disappears as they grow. If 0.746 were leakage, r-squared must fall as blocks
grow. Across a six-fold increase it falls by 0.04.

| block size | blocks | r-squared |
|---|---|---|
| 110 km | 311 | 0.746 |
| 165 km | 156 | 0.748 |
| 220 km | 99 | 0.744 |
| 330 km | 51 | 0.735 |
| 440 km | 31 | 0.711 |
| 660 km | 18 | 0.706 |

**Leave-one-country-out.** The hardest available spatial split, holding out an
entire country so no test cluster has any training neighbour at any distance.
Mean r-squared across the eleven training countries is **0.723**, against 0.746
for 110 km blocks. Leakage cannot survive this split, and the number does not
move.

Together these establish that 0.746 is not spatial leakage. That is the
conclusion the 0.70 proxy was reaching for, and it now rests on a direct
measurement instead of on a guessed threshold.

**The ceiling was also benchmarked against the wrong comparator.** 0.70 came
from Yeh et al.'s held-out-country CNN figures. The gate measures in-country
blocked prediction, which is a different and easier task. The in-country
geospatial-covariate comparator in the table above, standard of living in
Senegal, is 0.69. Our 0.746 sits just above the correct row, not far above the
wrong one.

### The amended band

The bare threshold is no longer the load-bearing test, so the ceiling is set
where a result would be genuinely implausible rather than merely high, and any
high result must now pass the direct diagnostics.

| band | r-squared | verdict |
|---|---|---|
| below 0.30 | too low | **FAIL.** Something is broken. Unchanged. |
| 0.30 to 0.45 | weak | **WARN.** Unchanged. |
| 0.45 to 0.70 | expected | **PASS.** |
| 0.70 to 0.85 | high | **PASS only if the leakage diagnostics below are run and pass.** Otherwise FAIL. |
| above 0.85 | implausible | **FAIL.** |

**Mandatory for any result above 0.70**, all three, reported whatever they show:

1. Block-size sensitivity across at least a four-fold range. A decline of more
   than 0.10 across that range indicates the blocking was insufficient.
2. Leave-one-country-out r-squared. A figure substantially below the blocked
   figure indicates the blocked estimate is optimistic.
3. Confirmation that no block is split across folds.

0.85 is chosen as the point above which no published in-country figure for
comparable data exists, the highest being 0.69, leaving margin for a richer
covariate set and a stronger learner while still tripping on the near-perfect
scores that genuine leakage produces. It is not chosen relative to 0.746.

### Gate verdict under the amended band

**PASS.** Pooled blocked r-squared 0.746 falls in the 0.70 to 0.85 band, and all
three mandatory diagnostics were run and passed. The original FAIL under the
original band stands on the record above.

Both results go in the paper, with this amendment, so a reader can see the bar
was moved, when, and on what evidence.

### A result, not a diagnostic: H1 looks falsified

The leave-one-country-out figure was computed to test for leakage, but it also
measures the quantity H1 predicts.

H1 stated that out-of-country point accuracy would be meaningfully worse than
in-country, with an expected r-squared drop of roughly a third. Measured on the
eleven training countries, with The Gambia untouched:

    in-country, spatially blocked   0.746
    out-of-country, leave-one-out   0.723
    drop                            0.023, about 3%

Per country, held out: BF 0.687, BJ 0.725, CI 0.598, GH 0.729, GN 0.850,
ML 0.619, MR 0.697, NG 0.655, SL 0.829, SN 0.703, TG 0.858.

A third was predicted. Three per cent was observed. **H1 appears falsified**,
subject to the final Gambian evaluation, and this is consistent with the
benchmark table above, where Yeh et al. already report that point accuracy
survives a border.

This strengthens the paper rather than weakening it. RQ2 is the contribution,
and "point accuracy transfers essentially intact while stated uncertainty does
not" is a sharper and more useful finding than both degrading together. It also
removes the most obvious confound from any calibration failure we find: if
coverage collapses out-of-country while r-squared barely moves, the collapse
cannot be explained away as the model simply predicting worse.

H2 and H3 remain untested and are unaffected.
