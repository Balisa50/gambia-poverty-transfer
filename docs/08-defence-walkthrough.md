# Walkthrough: what was done, why, and where every number comes from

Written to be read before defending this work. It is organised as the questions
you are likely to be asked rather than as a narrative, because that is how a
viva or a reviewer proceeds.

Every number here was re-derived from the committed result files while writing
this document. Where two numbers in the paper look inconsistent, this document
says why, because those are the questions that get asked.

---

## 1. The one-paragraph answer

If someone asks what the paper does, this is the answer:

> Satellite-based poverty models are validated on countries that have surveys
> and then used on countries that do not. Those models increasingly publish
> prediction intervals alongside their estimates. I tested whether those
> intervals keep their stated coverage when the model crosses a border. Using
> twelve West African DHS surveys, I registered four hypotheses before I had
> the data, held The Gambia back entirely, and evaluated it once against a
> threshold fixed in advance. None of the four hypotheses was supported. Point
> accuracy and average interval coverage both transferred better than I
> predicted. The residual risk turned out to be in the spread across countries
> and in the shape of the intervals rather than in average coverage.

The important word is **registered**. Almost anyone can produce a poverty map.
The thing that makes this defensible is that the design was fixed and committed
to version control before the data existed, and the record survives.

---

## 2. The data, exactly

**Twelve West African DHS surveys. 6,706 clusters. 155,796 households.**

| Country | Survey | Year used | Clusters |
|---|---|---|---|
| The Gambia (target) | 2019-20 | 2020 | 280 |
| Senegal | 2019 Continuous | 2019 | 214 |
| Mali | 2018 | 2018 | 328 |
| Nigeria | 2018 | 2018 | 1,382 |
| Ghana | 2014 | 2014 | 423 |
| Burkina Faso | 2021 | 2021 | 514 |
| Côte d'Ivoire | 2021 | 2021 | 539 |
| Mauritania | 2019-21 | 2020 | 1,198 |
| Sierra Leone | 2019 | 2019 | 557 |
| Guinea | 2018 | 2018 | 401 |
| Benin | 2017-18 | 2017 | 540 |
| Togo | 2013-14 | 2014 | 330 |

Training pool is 6,426 clusters across eleven countries. The Gambia's 280 are
the target.

**The unit** is the DHS cluster, an enumeration area. It is the finest spatial
unit at which DHS releases wealth.

**The label** is the cluster mean of `hv271`, the DHS wealth index factor score,
divided by 100,000 because DHS stores it scaled.

### Why the "year used" is not always the survey label

Four surveys span more than one calendar year and the interviews are not split
evenly. The year used is the **modal interview year in `hv007`**, which is the
year most households were actually observed in.

    Gambia 2019-20      1,948 in 2019, 4,601 in 2020   -> 2020
    Mauritania 2019-21  2,806 / 7,094 / 1,758          -> 2020
    Benin 2017-18       7,455 in 2017, 6,701 in 2018   -> 2017
    Togo 2013-14        3,686 in 2013, 5,863 in 2014   -> 2014

Taking the last year of the label would put Benin on 2018, where most
interviewing happened in 2017. This matters because covariates are matched to
the survey year.

**I got this wrong first.** The first Gambia extraction ran with 2019 because
the survey is labelled 2019-20. It was caught by checking `hv007` rather than
trusting the label, and rerun.

---

## 3. Why these twelve surveys and not the most recent ones

Four countries have newer surveys that were deliberately not used: Nigeria
2023-24, Senegal 2023, Mali 2023, Ghana 2022.

**The reason is the VIIRS nightlights product boundary.** Version 2.1 covers
2012 to 2021. Version 2.2 covers 2022 onward. They are separate products, not a
reprocessing of the same one. The V2.1 catalogue entry states that data for 2022
are in a separate dataset.

Had those four been used, nightlight product version would have been perfectly
correlated with country for exactly those four, in the one dimension the paper
measures. Constraining every survey to 2021 or earlier keeps one product across
all twelve.

**The cost** is recency. Ghana falls from 2022 to 2014, which is the largest
loss.

**This decision was made before any data was downloaded**, and is recorded as a
dated amendment in `docs/00` section 5. That timing matters if challenged: it
was not a response to a result.

---

## 4. The covariates, and the displacement problem

Twelve features, all from open sources, extracted in Google Earth Engine:

- VIIRS nightlights: mean, standard deviation, and background-masked mean
- WorldPop population: mean, standard deviation
- GHSL built surface: total and non-residential
- ESA WorldCover land cover: mode
- CHIRPS annual rainfall
- Open water fraction
- SRTM elevation: mean, standard deviation

**Survey metadata is excluded.** The urban/rural flag, the buffer radius and the
buffer area all come from DHS rather than from imagery, and the last two encode
the first exactly. A model given them is partly reading the survey's own
classification of a place rather than the satellite record of it.

### Displacement

DHS deliberately moves cluster coordinates before release, up to 2 km in urban
areas and 5 km in rural, with 1% of rural clusters moved up to 10 km. This
protects respondent confidentiality. Extracting a covariate at the recorded
point therefore reads the wrong place.

**The fix is to summarise over a buffer matched to the displacement**: 2 km
urban, 5 km rural, computed in a local UTM projection so the radius is metric.

**Why 5 km and not 10 km for rural.** The 1% displaced further cannot be
identified in the released data. Applying 10 km to every rural cluster would
inflate 99% of them to roughly four times the necessary area and blur the
signal. The choice accepts a known error on 1% in exchange for a sharper
measurement on the other 99%. This is a defensible trade rather than an
oversight, and it is recorded.

DHS's own documentation says direct distance measurements from a displaced
point are not appropriate, which is the practice the buffer avoids.

### The rainfall problem

CHIRPS is a land-only product and returns nothing over water. The Gambia is a
narrow strip of land wrapped around a river, so it has an unusually high share
of water-adjacent clusters. Verified: a 5 km buffer at Banjul is 80.7% water and
returns null, while Basse inland returns a value.

Left unhandled, target-country clusters would have dropped out at a higher rate
than training-country ones, which is a distribution shift introduced by me, in
the dimension the paper measures.

**The fix** fills masked pixels with the mean of land rainfall within 20 km, and
carries water fraction as a covariate so the affected clusters can be identified
and excluded in a robustness check.

**Independent corroboration:** DHS's own covariate extraction fails on the same
clusters. 42 of 280 Gambian clusters have a nodata sentinel for rainfall in the
DHS file. That is not my bug, it is a property of the product.

---

## 5. Where the numbers come from

### Point accuracy

| Setting | R² | Source |
|---|---|---|
| In-country, random split (naive) | 0.783 | `run_gate.py` |
| In-country, spatially blocked | 0.746 | `run_gate.py` |
| Out-of-country, leave-one-country-out | 0.723 | `run_gate.py` diagnostics |
| The Gambia | 0.673 | `gambia_evaluation.json` |

### Coverage, nominal 90%, split conformal

| Quantity | Value | Source |
|---|---|---|
| In-country, mean of 11 | 0.913 (sd 0.019) | `h2_h3_results.csv` |
| Out-of-country, mean of 11 | 0.887 (sd 0.053) | `h2_h3_results.csv` |
| Out-of-country range | 0.821 to 0.979 | `h2_h3_results.csv` |
| The Gambia | 0.893 | `gambia_evaluation.json` |

### The Gambia, all levels, split conformal

| Nominal | Coverage | z | Registered band |
|---|---|---|---|
| 50% | 0.371 | −4.30 | none |
| 80% | 0.704 | −4.03 | outside [0.753, 0.847] |
| 90% | 0.893 | −0.40 | inside [0.865, 0.935] |
| 95% | 0.961 | +0.82 | inside [0.924, 0.976] |

---

## 6. The question about 0.723 versus 0.709

**You will be asked this.** The paper reports leave-one-country-out R² as 0.723
in Table 2 and as 0.709 in the H3 section.

Both are correct and they are computed on different training sets:

- **0.723** fits each held-out country's model on all ten remaining countries.
  That is the honest estimate of transfer accuracy, so it is the one in Table 2.
- **0.709** comes from the conformal experiment, which must reserve part of the
  source data to calibrate the intervals on. It fits on five of ten spatial
  folds and holds three for calibration, roughly half the data, which costs
  about 0.014 in R².

The paper now states this explicitly. The reason both are kept rather than
reconciled to one is that each is the correct baseline for its own comparison:
CORAL must be compared against a model trained the same way CORAL was.

The same logic explains why Figure 5's target panel matches 0.673 only when
fitted on folds 3 to 9. Fitted on all eleven countries it gives 0.696.

---

## 7. Why spatial blocking, and why it is the most important control

DHS clusters are spatially autocorrelated. Two clusters 8 km apart share
nightlights, land cover, roads and market access. A random train/test split puts
near neighbours on both sides, so the model is partly tested on places it has
effectively already seen.

**For this paper that is not a minor inefficiency.** The entire claim is a
comparison between in-country and out-of-country performance. An inflated
in-country baseline would manufacture the result I was looking for.

All within-country validation uses spatially blocked k-fold: whole blocks held
out, block size set to twice the empirical variogram range. The range is 55 km,
so blocks are 110 km.

**The naive figure is reported alongside** so the size of the correction is
visible: 0.783 random against 0.746 blocked.

The simulation in Section 4.4 demonstrates the mechanism on synthetic data where
leakage exists by construction: 0.809 random against 0.594 blocked, a gap of
0.214.

---

## 8. Why conformal prediction specifically

Split conformal gives a **finite-sample coverage guarantee** for any underlying
model, with no distributional assumptions. It requires one thing:
**exchangeability** between the calibration data and the test data.

Cross-border transfer is exactly where that assumption fails.

That is why conformal was chosen over quantile regression or a bootstrap.
Watching a method that carries a proof lose its coverage is much easier to
attribute than watching a heuristic degrade, because with a heuristic nobody
expected a guarantee in the first place.

**The calibration set must come from training countries.** Calibrating on
Gambian clusters would restore coverage by construction and destroy the
experiment. The implementation raises an error if target-country data reaches
the calibration step, so this is enforced rather than left to discipline.

Conformalized quantile regression is also fitted, because its interval width
varies with the input. This was included in advance, with the reasoning written
in the module docstring before extraction began: if the constant-width method
loses coverage and the adaptive one does not, the failure is about interval
shape rather than level.

That prediction is what happened.

---

## 9. The four hypotheses and their fates

| | Prediction | Result |
|---|---|---|
| H1 | out-of-country accuracy drops by roughly a third | **falsified**: it drops about 3% |
| H2 | a nominal 90% interval covers substantially less than 90% | **not supported**: 0.887 pooled, 0.893 on target |
| H3 | adaptation improves accuracy but not calibration | **premise fails**: CORAL degrades accuracy, 0.709 to 0.646 |
| H4 | target coverage deviates beyond sampling noise | **not confirmed**, at 53% power |

**If asked whether four negative results means the project failed:** no, and the
protocol committed in advance to reporting them. The question of whether these
intervals stay calibrated across a border had not been answered. It now has an
answer, on eleven country pairs plus a held-out target, with a design that makes
the answer interpretable. A negative answer to a real question is a result.

---

## 10. H4 and its 53% power

This is the part to be most careful about.

H4 predicted that Gambian coverage at nominal 90% would fall outside
[0.865, 0.935], the two-sided 95% binomial interval at n = 280 under exactly
nominal coverage. It came in at 0.893, inside the band. **Not confirmed.**

**Power was computed and stated before the test ran:**

- between-country standard deviation, from the training pool: 0.0512
- plus Gambia's own binomial term: predictive sd 0.0542
- P(confirmatory | coverage exactly nominal) = 0.050
- P(confirmatory | dispersion hypothesis true) = 0.529

So the test misses a true effect roughly half the time.

**The wording is binding.** The pre-registration requires reporting this as "not
confirmed at 53% power", never as evidence that coverage is reliable. If someone
tries to read the null as proof of reliability, that is the answer: the test was
not powerful enough to establish that.

**Why so weak:** one target country with 280 clusters. That was known and stated
in advance rather than discovered afterwards.

---

## 11. The two leads, and why they are not results

### Dispersion across countries

Out-of-country coverage ranged 0.821 to 0.979 with sd 0.053, against 0.019
in-country. If true coverage were exactly 0.90 everywhere, binomial sampling at
these cluster counts would give 0.014, so observed dispersion is 3.7 times that.
Nine of eleven countries fall outside an 88 to 92% band.

**Post-hoc.** It was found after the registered questions were answered. H4 was
its out-of-sample test and returned a null.

### Interval shape: proposed, tested, withdrawn

On The Gambia, split conformal undercovered at nominal 50% and 80% while
adaptive CQR did not. Against binomial sampling that is z = -4.30 and -4.03.

**It was tested on the eleven training countries and it does not replicate.**
Split and CQR are indistinguishable at every level, Wilcoxon p between 0.37 and
0.90, and split is the closer of the two more often than not.

**And the reference distribution was wrong.** Those z values presume every
country's coverage is exactly nominal. It is not, by a factor of three to five.
Against the observed between-country distribution The Gambia sits at z = -1.08,
-0.91, +0.11, +0.62. A typical draw.

**If asked about this, the answer is that we tested our own lead and reported
that it failed.** That is a stronger position than having left it untested, and
it is why the dispersion result is stated with confidence while this one is
withdrawn.

### The geographic gradient

Sahelian countries undercover, coastal ones overcover. Latitude correlates with
coverage at Spearman −0.564 (p = 0.071), rainfall at 0.655 (p = 0.029).

**Weakest of the three.** Found by looking at the map, tested afterwards on the
same eleven numbers, two covariates tried, and the rank test on latitude does
not reach conventional significance. It is in the paper as a proposition for a
future study, explicitly not as a finding.

---

## 12. Things that went wrong, and why they belong in the defence

Do not hide these. They are the strongest evidence that the pipeline was
actually checked rather than assumed to work.

**The wrong VIIRS product.** The code pointed at V2.2, which covers 2022 onward,
while every survey used is 2021 or earlier. Verified against the live catalogue:
V2.1 for 2019 returns one image, V2.2 returns zero. Left unfixed, nightlights
would have been null for all twelve countries, and nightlights is the strongest
single predictor in this literature. It would not have raised an error.

**WorldPop stops at 2020.** Three surveys are 2021. `Filter.eq("year", 2021)`
returns an empty collection, which mosaics to nothing. Population would have
been silently null for Burkina Faso, Côte d'Ivoire and Mauritania. The year is
now clamped and the year actually used is written into every row.

**GHSL is a collection, not an image.** It needs an epoch suffix. Without it the
call fails.

**The rainfall fill never finished.** A 20 km focal mean over the summed daily
CHIRPS made Earth Engine re-evaluate a 365-image sum at every kernel offset: 125
seconds for ten clusters, so Nigeria's 1,382 would never have completed. Pinning
the sum to the CHIRPS 5 km grid first computes it once: 0.8 seconds, identical
values, a 150-fold speedup.

**And the alternative was rejected on purpose.** CHIRPS PENTAD is 72 images
instead of 365 and agrees with the daily product inland to 0.3%. It was not
adopted because it carries a wider land mask and returns values over the Banjul
buffer where the daily product is masked. Using it would have supplied
extrapolated over-water values and hidden the very problem the gap-fill exists
to expose.

**The inventory script lied.** Its filename pattern required the version field to
be digits, but real DHS codes are often alphanumeric: `SNHR8BFL`, `MLHR7AFL`.
Roughly a third of the countries would have been reported as "not downloaded"
while sitting in the folder.

**The cross-check against DHS's own covariates did not reach its threshold.**
This is reported as a failure in the paper rather than omitted. Two internal
checks bound what it means: our WorldPop and GHSL summaries, from independent
products through the same buffers and code, agree at Spearman 0.907 to 0.951 in
all twelve countries, which is inconsistent with broken buffer geometry or a
broken cluster join. And the DHS composite carries no year while ours is matched
to survey year.

---

## 13. The gate amendment, which will be challenged

The sanity gate had a pre-registered upper bound of 0.70. The pipeline returned
0.746. **The band was changed after seeing that number**, and the paper says so
in those words.

**Why this is defensible, and how to explain it:**

The 0.70 was a **proxy** for spatial leakage, adopted when no direct test was
available. Direct tests now exist and all three were run:

1. **Block-size sensitivity.** Leakage is a function of block size. Across a
   sixfold increase, 110 km to 660 km, R² falls only 0.746 to 0.706.
2. **Leave-one-country-out**, which removes every spatial neighbour at any
   distance, gives 0.723.
3. **No block was split across folds**, zero of 311.

Leakage does not survive any of those. That is the conclusion the 0.70 proxy was
reaching for, now resting on direct measurement.

**The ceiling was also benchmarked against the wrong comparator.** 0.70 came
from Yeh et al.'s held-out-country CNN results. The gate measures in-country
blocked prediction, an easier task, whose published comparator is 0.69.

**The new band does not pass on a number alone.** Between 0.70 and 0.85 the
result passes only if the three diagnostics are run and reported, and the code
computes them and feeds the actual result into the verdict. The self-test proves
it: identical 0.746 inputs give FAIL without diagnostics and PASS with them.

**The original band, the original FAIL and every diagnostic remain in `docs/04`,
unedited, above the amendment.** A reader judges the reasoning rather than
taking it.

---

## 14. Hard questions, with answers

**"Your label is standardised within each country. Doesn't that make
cross-country comparison meaningless?"**

It makes it a comparison of *relative position*, which is what the paper says.
Verified at household level: Nigeria mean 0.0000 sd 0.9940, Sierra Leone
0.0000/0.9909, Gambia 0.0000/0.9874. Country means account for 0.0% of total
variance. This is a limitation and it is in `docs/00` section 8 as an amendment.
It also sharpens the question: transfer asks a model to map absolute satellite
measurements onto a country-relative rank whose scaling depends on the target
country's own distribution, which is a concrete mechanism for calibration
failure.

**"Why should I believe your extraction is correct?"**

Three reasons, in increasing strength. The covariates were verified at two
Gambian sites against expectation before any modelling. Our WorldPop and GHSL
summaries agree at Spearman 0.907 to 0.951 with DHS's independent extraction in
all twelve countries. And the sanity gate reproduces published in-country
accuracy for geospatial-covariate models. The nightlights cross-check did not
reach its threshold and that is reported as a failure.

**"Isn't a null result just a failed project?"**

The question had not been answered. It now has an answer on eleven country pairs
plus a held-out target. The design was fixed in advance, so the null cannot be
explained away as a failure to look hard enough. And a concurrent paper finds
conformal coverage collapsing to 65.3% on African satellite data under spatial
shift, which makes this result a contrast worth explaining rather than a
foregone conclusion.

**"Why only twelve countries?"**

DHS access is granted by country and each requires justification. Twelve West
African countries with GPS data, constrained to 2021 or earlier for the VIIRS
reason. Extending the region would change the shift structure, which is exactly
why the paper scopes its conclusion to neighbouring countries with a common
survey instrument.

**"Did you use the DHS pre-computed covariates?"**

Only as a cross-check, never as features. Building the model on someone else's
extraction would make the paper a wrapper around their pipeline and tie the
covariate set to their choices.

**"What would change your conclusion?"**

Applying it to a more distant region. These are neighbouring countries sharing a
survey instrument, so this measures transfer under a modest shift and the
results are a lower bound on the problem. Adjei et al. finding collapse at
continental scale is consistent with that reading.

---

## 15. What to say you do not know

Being straight about these is stronger than improvising.

- **Why coverage holds here and collapses in Adjei et al.** Three candidate
  explanations are given in the discussion and none can be separated with this
  data.
- **Whether the shape failure generalises.** It is one country. The follow-up
  design is specified in the paper and has not been run.
- **Whether the geographic gradient is real.** n = 11, found by inspection,
  marginal significance.
- **Whether the adversarial domain adaptation variant would behave like CORAL.**
  Only second-moment alignment was tested. The protocol named an adversarial
  variant and it was not run. That is stated in the paper rather than glossed.

---

## 16. The record, if anyone wants to check

- **Public code, protocol and amendments:**
  <https://github.com/Balisa50/gambia-poverty-transfer>
- **Pre-registration commit for the single target evaluation:**
  `bfa32ce277b2d21944b1f04912ba716a95dfe52b`, made before any Gambian wealth
  label was read.
- **Every design document** in `docs/`, numbered in the order written, with both
  substantive amendments dated and reasoned.
- **DHS microdata is not in the repository** and cannot be, under the terms of
  access. Anyone reproducing this applies for the same datasets under their own
  account.

The single most defensible thing about this work is that the record shows what
was decided when. Point at it.
