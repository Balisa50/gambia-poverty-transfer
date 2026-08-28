# Research protocol

**Paper B of a three-paper programme.** Written 2026-08-07, before any data was
downloaded or any model fitted. The point of writing it first is that it fixes
what counts as a positive and a negative result, so the analysis cannot drift
toward whatever the data happens to show.

Abdoulie Balisa, BSc Statistics, KNUST.

---

## 1. The programme this belongs to

Paper A found that mortality forecasts for countries without death registration
report intervals that are too narrow, because the innovation variance is
estimated from a series that was smoothed during reconstruction. The general
shape of that finding is:

> Reported uncertainty is conditional on an assumption that nobody checks, and
> the assumption fails precisely where the data is weakest.

Paper B asks whether the same thing happens in poverty mapping, for a different
reason. There the assumption is not about smoothing but about **where the model
was validated**. Satellite-based poverty models are almost always validated by
holding out clusters from the same countries they were trained on. They are then
applied to countries with no survey at all. If the uncertainty they report is
estimated in-domain and the application is out-of-domain, the reported
uncertainty will be too small, and nobody would notice.

That is the thread. Both papers are about intervals that are narrow for reasons
that have nothing to do with how much is actually known.

## 2. The problem

The Gambia has two DHS surveys, 2013 and 2019-20. Many countries have none, or
none recent. The standard response is to train a model on satellite imagery in
countries that do have surveys and apply it where they do not. The published
literature reports how accurate such models are. It rarely reports whether their
uncertainty is honest when the target country was never in the training set.

## 3. Research questions

**RQ1.** How much point accuracy is lost when a satellite-based wealth model
trained on other West African countries is applied to The Gambia, compared with
a model trained on The Gambia itself?

**RQ2.** Is the model's stated uncertainty still valid out-of-country? That is,
does a nominal 90% prediction interval estimated in-domain actually contain 90%
of Gambian cluster values?

**RQ3.** Do domain adaptation methods, which are designed to improve point
accuracy under distribution shift, also repair calibration? Or do they improve
the estimate while leaving the uncertainty just as wrong?

RQ2 is the contribution. RQ1 is necessary context and is largely known. RQ3 is
what makes the paper more than a negative result.

## 4. Hypotheses, stated before seeing results

- **H1.** Out-of-country point accuracy will be meaningfully worse than
  in-country, but not catastrophically so. Expected $R^2$ drop of roughly a
  third.
- **H2.** Calibration will degrade more than accuracy. A nominal 90% interval
  will cover substantially less than 90% of Gambian clusters. **This is the
  central claim.**
- **H3.** Domain adaptation will improve H1 more than it improves H2. Methods
  that align feature distributions have no mechanism that targets interval
  width, so they should leave the model confidently wrong rather than
  appropriately uncertain.

**What would falsify the paper.** If out-of-country coverage is close to
nominal, there is no finding and the paper does not exist. That outcome will be
reported rather than reframed. Paper A's first two hypotheses failed and were
published as failures; the same standard applies here.

## 5. Design

**Target.** The Gambia, DHS 2019-20, cluster-level wealth index.

**Source countries.** West African DHS with GPS, 2013 onward.

> **Amendment, 2026-08-28.** This section originally listed Senegal 2023, Mali
> 2023, Nigeria 2024, Ghana 2022, Burkina Faso 2021, Côte d'Ivoire 2021,
> Mauritania 2020, Sierra Leone 2019, Guinea 2018, Benin 2017, Togo 2013, taken
> from the DHS API before access was granted.
>
> Four of those were replaced with earlier surveys **before any data was
> downloaded and before any model was fitted**. The reason is the VIIRS product
> boundary recorded as an open question in docs/02: V2.1 covers 2012-2021 and
> V2.2 covers 2022 onward, and they are separate products, not a reprocessing.
> The V2.1 catalogue entry states "Data for 2022 are available in a separate
> dataset, NOAA/VIIRS/DNB/ANNUAL_V22". Verified against the Earth Engine
> catalogue on 2026-08-27.
>
> Had Senegal 2023, Mali 2023, Nigeria 2024 and Ghana 2022 been used, nightlight
> product version would have been perfectly correlated with country for those
> four, in the one dimension this paper measures. Constraining every survey to
> 2021 or earlier keeps one product across all twelve.
>
> The cost is recency for four countries. Ghana falls from 2022 to 2014, the
> largest single loss.

The twelve surveys actually used, with the survey year taken as the modal
interview year in `hv007` rather than the survey label, since four surveys span
more than one calendar year and the split is uneven:

| country | survey | year used | clusters |
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

6,706 clusters after removing those DHS could not georeference. Every household
recode joins its GPS file on `hv001` with no orphans on either side.

**Unit of analysis.** The DHS cluster (an enumeration area), which is the
finest spatial unit at which wealth is released.

**Label.** The DHS wealth index, a household asset index produced by principal
component analysis, averaged to the cluster. Its known weaknesses are recorded
in Section 8.

**Evaluation.** Leave-one-country-out. Train on all source countries, test on
The Gambia, with The Gambia never seen in training or in hyperparameter
selection. An in-country model trained on Gambian clusters gives the ceiling
that out-of-country performance is measured against.

**Displacement.** DHS randomly displaces cluster coordinates, up to 2 km in
urban areas and 5 km in rural, with 1% of rural clusters displaced up to 10 km.
Covariates must therefore be extracted over a buffer rather than at a point.
This is not optional and is a common error in this literature.

## 6. Covariates

All from open sources requiring no application.

| Source | What it gives | Access |
|---|---|---|
| VIIRS night-time lights | economic activity, electrification | open |
| WorldPop | population density and structure | open |
| Google/Microsoft Open Buildings | building count, footprint area, density | open |
| OpenStreetMap | road density, distance to road, market access | open |
| CHIRPS | rainfall, relevant to agricultural livelihoods | open |
| ESA WorldCover | land cover composition | open |
| Sentinel-2 composites | surface reflectance, vegetation indices | open, via Earth Engine |

## 7. Methods

Fitted in this order, each a baseline for the next.

1. **Ridge regression** on the covariate table. Deliberately simple. If a linear
   model transfers as well as anything else, that is the result.
2. **Gradient boosting.** The standard strong tabular baseline.
3. **Domain adaptation.** Two families, both established rather than novel:
   maximum mean discrepancy alignment, and adversarial domain-invariant
   representation learning.

**Uncertainty, which is the point of the paper.** Every model must produce a
predictive distribution, not a point estimate. Quantile regression and
conformal prediction, since conformal gives finite-sample coverage guarantees
under exchangeability, and out-of-country transfer is exactly where
exchangeability fails. Watching a guaranteed method fail is a cleaner
demonstration than watching a heuristic one fail.

**Metrics.** For accuracy, $R^2$ and Spearman correlation. For calibration,
empirical coverage of nominal 50, 80, 90 and 95% intervals; the calibration
curve; and interval score, which penalises width and miscoverage together so a
model cannot win by being vague.

## 8. Known weaknesses, recorded now

1. **The wealth index is an asset index, not consumption or income.** It travels
   badly across countries because the same assets mean different things in
   different economies. Comparability across countries is assumed, and this
   assumption is itself a candidate explanation for anything we find.

   **Amendment, 2026-08-28, once the data was in hand.** The assumption is
   stronger than "assumed comparable". `hv271` is standardised to mean 0 and
   standard deviation 1 **within each country by construction**. Verified at
   household level: Nigeria 0.0000 / 0.9940, Sierra Leone 0.0000 / 0.9909, The
   Gambia 0.0000 / 0.9874. Across the twelve, cluster-mean wealth by country
   ranges only from 0.001 to 0.069, and the variance of country means is 0.0002
   against a total of 0.7400, which is 0.0% of the total.

   The label is therefore a **within-country relative position**, not an
   absolute standard of living. A cluster at +1 in Sierra Leone and a cluster at
   +1 in Nigeria are not equally wealthy; each is one standard deviation above
   its own country's mean.

   This sharpens RQ2 rather than weakening it, and supplies a concrete mechanism
   for the calibration failure H2 predicts. Transfer asks a model to map
   absolute satellite measurements onto a country-relative rank, where the
   mapping from radiance to rank depends on the target country's own
   distribution. A model fitted where that distribution is one shape, applied
   where it is another, has no way to know the rescaling changed. Point
   predictions can absorb this; interval widths estimated in the source
   countries have no mechanism to.

6. **Households per cluster differ by survey design, not at random.** Mauritania
   2019-21 sampled about 10 households per cluster across 1,200 clusters, where
   every other survey sampled 20 to 30 across far fewer. The label is a cluster
   mean, so its standard error scales with the inverse square root of that
   count, and Mauritanian cluster means carry roughly 1.6 times the noise. That
   is label noise correlated with country, in the dimension this paper measures.
   `n_households` is carried in the modelling table so this can be controlled or
   reported rather than mistaken for transfer failure.

7. **Land cover is a single 2021 epoch applied to every survey year.** ESA
   WorldCover v200 has no earlier epoch, so Togo 2014 is described by land cover
   observed eight years later. This contradicts the requirement in item 3 that
   covariates be matched to survey year, and is accepted only because no
   alternative product covers the full span at comparable resolution.
2. **Cluster displacement adds noise** and blurs the link between covariates and
   label.
3. **Survey years differ**, so covariates must be matched to each survey's year
   and any residual mismatch is a confounder.
4. **The Gambia is small,** so the target sample is a few hundred clusters and
   coverage estimates will have wide confidence intervals of their own. Coverage
   estimates will be reported with intervals rather than as point values.
5. **Source countries are neighbours,** so this measures transfer across a
   modest distribution shift. Transfer to a very different region would likely
   be worse, making our result a lower bound on the problem.

## 9. Sequence

1. Build the covariate pipeline against open data, using an open stand-in label
   so the pipeline can be tested before survey access arrives.
2. Apply for DHS data access. **Blocking, and only Abdoulie can do it.**
3. Reproduce a published in-country accuracy figure as a sanity check on the
   pipeline before making any claim about transfer.
4. Run the leave-one-country-out design.
5. Calibration analysis. This is the paper.
6. Domain adaptation, and re-test calibration.

Step 3 is not optional. If the pipeline cannot reproduce a known result, any
novel result it produces is uninterpretable.

## 10. Target venue

A workshop at NeurIPS or ICLR concerned with machine learning for development,
plus an arXiv preprint. No submission fee, and decisions in about six weeks
rather than nine months. If the result is strong, a journal version follows.
