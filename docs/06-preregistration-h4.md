# Pre-registration: H4, coverage reliability across a border

**Written 2026-08-28. The Gambian wealth labels have not been loaded, examined,
summarised or plotted at any point before this document was finalised.**

The commit that contains this file and `src/evaluate_gambia.py` is the
specification. Its hash goes in the paper. Nothing in the procedure may be
changed after that commit without a further dated amendment stating what changed
and why, exactly as with the gate band in docs/04.

---

## Why this document exists

The pre-registered central claim, H2, is answered and not supported. A nominal
90% interval covers 88.7% out-of-country against a nominal 90%. That is settled
on eleven country pairs and The Gambia cannot add to it.

What the training pool also showed, **after** the fact, is that the mean hides
a large spread: per-country coverage ranged 0.821 to 0.979, with a dispersion
3.7 times what sampling noise allows. That observation is post-hoc and is
recorded as such in docs/05.

A post-hoc observation and a tested hypothesis are different things. The Gambia
is the one dataset in this project that has never been looked at, and it can
convert the first into the second exactly once. This document spends that look
deliberately, in advance, rather than by loading the data and then deciding what
it shows.

---

## H4, stated

> **H4.** Out-of-country conformal coverage is unreliable for an individual
> country. For The Gambia, a nominal 90% prediction interval built and
> calibrated entirely on the eleven training countries will cover a fraction of
> Gambian clusters that differs from 0.90 by more than sampling variation alone
> can explain.

**No direction is predicted.** The claim is unreliability, not systematic
shortfall. Predicting a direction would restate H2, which is already answered.
A result substantially above 0.90 confirms H4 exactly as one substantially
below does. This is fixed here so that neither outcome can be described as
confirmation after the fact.

---

## The threshold

The Gambian modelling table has **280 clusters**. That count comes from the GPS
file and the covariate extraction, not from any wealth value, and is known
without reading the label.

If true coverage were exactly 0.90, the observed fraction over 280 clusters
would have a binomial standard error of 0.0179. A two-sided 95% interval is
therefore:

    [0.865, 0.935]

**Confirmatory:** Gambian coverage at nominal 90% falls **outside** [0.865, 0.935].

**Disconfirmatory:** it falls **inside**.

Rounding is to three decimals, and a value landing exactly on a boundary counts
as inside, which is the conservative direction.

---

## Power, stated in advance because it is not good

With one country this test is weak, and saying so now is part of the point.

Decomposing the training-pool dispersion at nominal 90%: observed standard
deviation across countries 0.0531, binomial component 0.0142, implied
between-country standard deviation **0.0512**. Adding Gambia's own binomial term
gives a predictive standard deviation of 0.0542 around the training-pool mean of
0.887.

| | probability of a confirmatory result |
|---|---|
| if coverage is exactly nominal (H4 false) | **0.050** |
| if the training-pool dispersion holds (H4 true) | **0.529** |

Likelihood ratio 10.6. A confirmatory result is therefore meaningful evidence.
**A disconfirmatory result is much weaker evidence**, because the test misses a
true effect roughly half the time. If the result is disconfirmatory the paper
must say that H4 was not confirmed on a test with 53% power, and must not report
it as evidence that coverage is reliable.

This asymmetry is the price of having one target country, and it is the reason
the eleven-country dispersion estimate stays in the paper as the primary
evidence for the observation, with The Gambia as a single out-of-sample check.

---

## Secondary predictions, fixed now

Reported whatever they show. They are **not independent** of the primary test,
since the intervals at different levels are nested and built from the same
calibration scores, so they cannot simply be counted as additional confirmations.

1. Same test at nominal 80%: binomial 95% interval under exact coverage is
   [0.753, 0.847].
2. Same test at nominal 95%: [0.924, 0.976].
3. The same three tests using conformalized quantile regression instead of split
   conformal.
4. Gambian coverage is compared with the eleven training-country values. Where
   it falls in that spread is descriptive and is reported, not tested.

---

## The procedure, frozen

Implemented in `src/evaluate_gambia.py` in this same commit. Prose here,
executable there; if they disagree the code is what ran and the discrepancy is
reported.

- **Features:** the twelve in `run_gate.FEATURES`, unchanged since the gate.
- **Model:** `GradientBoostingRegressor(random_state=0)`, scikit-learn defaults,
  as used throughout.
- **Training data:** all clusters from the eleven training countries. The
  Gambia contributes nothing to fitting or calibration.
- **Fit and calibration split:** spatial blocks at 110 km, `blocked_kfold` with
  `n_folds=10, seed=42`. Folds 0 to 2 calibrate, folds 3 to 9 fit. This differs
  from docs/05, where folds 8 and 9 were reserved for in-country testing; that
  set is not needed here, so it returns to fitting. The change is recorded
  because it is a change.
- **Conformal:** `SplitConformal` with absolute-residual scores, and
  `ConformalizedQuantile` with quantile models at 0.05 and 0.95, both from
  `conformal.py`, unmodified.
- **Calibration guard:** `exclude="GM"` is passed, so calibrating on the target
  raises rather than silently proceeding.
- **No domain adaptation.** CORAL degraded both accuracy and interval score on
  the training pool and is not part of this test.
- **One run.** Seeds are fixed and the script is deterministic. It is executed
  once. If it is executed again for any reason, that fact is reported.

---

## What is reported regardless of outcome

Coverage at all four nominal levels for both methods, mean interval width,
interval score, r-squared on the Gambian clusters, and the position of the
Gambian value within the eleven training-country coverages.

The r-squared figure is context and is not a test. H1 is already falsified, and
a Gambian r-squared near 0.72 would be consistent with that rather than news.

---

## Falsification, restated plainly

If Gambian coverage at nominal 90% lands inside [0.865, 0.935], H4 is not
confirmed. Combined with H1 falsified and H2 not supported, that would leave the
project with three negative results and one post-hoc observation that failed its
only out-of-sample test.

That outcome gets written up. docs/00 section 4 committed to it, Paper A's first
two hypotheses were published as failures, and the same standard applies here.
A paper reporting that satellite poverty models transfer better than the
literature's caution implies, on eleven country pairs with a pre-registered
design and an honest account of what was tested, is a smaller contribution than
the one intended but it is not nothing, and it is true.
