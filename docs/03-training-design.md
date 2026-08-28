# Training design

Written before any data arrived, deliberately. Once the labels are in hand,
every choice made here becomes contestable as something tuned to get a result.
Fixing the design first is what makes the finding worth anything.

---

## 1. What has to be true for the result to mean anything

The claim is that satellite poverty models report uncertainty that stops being
honest across a border. For that to be a finding rather than an artefact, three
things must hold.

**The in-country baseline must not be inflated.** If the within-country
validation number is optimistic, the drop at the border looks larger than it is,
and the whole paper measures our own sloppiness. This is the biggest threat and
Section 2 exists to address it.

**The Gambia must not influence anything before the final evaluation.** Not
feature selection, not hyperparameters, not the decision of which model to
report. One look, at the end.

**A negative result must be publishable.** If out-of-country coverage turns out
close to nominal, that is the answer and it gets written up. Paper A's first two
hypotheses failed and were reported as failures; the same standard applies here.

---

## 2. Splitting, at three levels

### 2.1 Within a country: spatial blocks, not random folds

DHS clusters are spatially autocorrelated. Two clusters 8 km apart share
nightlights, land cover, roads and market access. A random train/test split puts
near-neighbours on both sides, so the model is partly being tested on places it
has effectively seen. Published in-country accuracy figures are routinely
inflated this way.

Since our entire claim is a comparison between in-country and out-of-country
performance, an inflated in-country baseline manufactures the result we are
looking for. This is the single most important methodological control in the
paper.

**Decision.** Within-country validation uses spatially blocked k-fold: cluster
the survey's points into contiguous spatial blocks and hold out whole blocks.
Block size is set to comfortably exceed the covariate correlation range, which
is estimated empirically from a variogram of the residuals rather than assumed.

**Reported alongside it.** The naive random-split number, for the same model and
data. The gap between random-split and spatially-blocked in-country accuracy is
worth reporting in its own right, because it quantifies how much of the
published literature's reported accuracy is spatial leakage.

### 2.2 Across countries: leave-one-country-out

Train on 10 countries, validate on the 11th, rotate. This is the honest estimate
of cross-border performance and it is computed entirely within the training
pool, with The Gambia excluded throughout.

Leave-one-country-out serves two purposes: it estimates transfer degradation
from 11 independent country pairs rather than a single one, and it is how all
model selection happens.

### 2.3 The Gambia: touched once

Not in training. Not in validation. Not in hyperparameter search. Not in the
decision of which model to report.

The full specification, including which model and which uncertainty method, is
committed to git before Gambian labels are loaded. The commit hash goes in the
paper. That is as close to pre-registration as an undergraduate project can get,
and it costs nothing to do.

---

## 3. Models, in increasing order of ambition

Each step must earn its place by beating the one before it on
leave-one-country-out performance. If gradient boosting does not beat ridge,
ridge is what gets reported.

1. **Ridge regression** on the covariate summaries. Transparent, fast, and a
   surprisingly strong baseline in this literature.
2. **Gradient boosting.** Captures interactions ridge cannot.
3. **Domain adaptation.** MMD-based feature alignment, then an adversarial
   variant. These target the covariate shift between countries directly.

**The prediction worth stating in advance:** domain adaptation improves point
accuracy but does not fix calibration, because aligning feature distributions
contains no mechanism that acts on interval width. If that holds, it is the more
interesting half of the paper, because it means a technique the field treats as
the fix for distribution shift does not address the failure that matters most
for decision-making.

---

## 4. Uncertainty, and why conformal prediction

Three methods, in increasing strength of guarantee.

1. **Quantile regression.** Predicts intervals directly. No guarantee.
2. **Bootstrap ensembles.** Interval from the spread of resampled models.
3. **Conformal prediction.** Comes with a finite-sample coverage guarantee.

Conformal is the centrepiece, chosen precisely because its guarantee rests on
**exchangeability** between calibration and test data, and cross-border transfer
is exactly the situation where exchangeability fails. Watching a method with a
proof attached lose its coverage is a much cleaner demonstration than watching a
heuristic method degrade, because with a heuristic nobody expected the guarantee
in the first place.

**Calibration set placement matters and is easy to get wrong.** The conformal
calibration set must come from training countries. Calibrating on Gambian
clusters would restore coverage by construction and destroy the experiment.
Stated here so it cannot be quietly changed later.

---

## 5. What gets measured

Point accuracy is reported but is not the finding.

| Metric | What it answers |
|---|---|
| R², MAE | Point accuracy. Comparable to published work. |
| **Empirical coverage** | Does a nominal 90% interval contain 90% of held-out truth? |
| **Interval width** | Are intervals honest, or merely wide? |
| Calibration curve | Coverage across the whole nominal range, not just 90%. |
| Interval score | Coverage and sharpness in one number. |

Coverage and width must always be read together. An interval covering 90% by
being uselessly wide is not calibrated in any useful sense, and reporting
coverage alone would hide that.

**The headline comparison** is in-country coverage under spatial blocking versus
out-of-country coverage, both at the same nominal level, for the same model.

---

## 6. The sanity gate

Before any transfer claim, the pipeline must reproduce a published in-country
accuracy figure for a country where one exists, within a reasonable margin.

If our pipeline cannot rebuild a known result, then any novel result it produces
is uninterpretable, and we would have no way to tell a real finding from a bug.
This gate comes first and its outcome is reported whether or not it passes.

---

## 7. How this fails

Stated now so it cannot be quietly redefined later.

- **Out-of-country coverage is close to nominal.** The central hypothesis is
  wrong. Reported as such.
- **The in-country versus out-of-country gap disappears under spatial
  blocking.** Then the apparent transfer failure was spatial leakage all along.
  That is a useful finding about the literature and gets written up as one.
- **Domain adaptation does fix calibration.** The secondary hypothesis is wrong,
  and that is a genuinely useful result for practitioners.
- **The sanity gate fails.** No transfer claims are made at all until it passes.

---

## 8. Sequence

1. Extract covariates for all 12 countries.
2. Sanity gate against a published figure.
3. Estimate the spatial correlation range; set block size.
4. Ridge, spatially blocked in-country. Report the naive-versus-blocked gap.
5. Leave-one-country-out across the 11 training countries.
6. Add gradient boosting, then domain adaptation. Each must earn its place.
7. Add the three uncertainty methods; measure coverage in-country and
   out-of-country.
8. **Commit the full specification. Record the hash.**
9. Load The Gambia. Evaluate once. Report whatever it says.
