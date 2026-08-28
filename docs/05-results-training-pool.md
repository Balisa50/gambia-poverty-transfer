# Results on the training pool: H1, H2, H3

Run 2026-08-28 on the eleven training countries, 6,426 clusters, by
leave-one-country-out. **The Gambia was not loaded.** It remains unspent, which
matters more after these results than before them.

All three hypotheses came out differently from the protocol's predictions. This
document reports that plainly. docs/00 section 4 committed in advance to
reporting a null result rather than reframing it, and the substance of that
commitment is tested here rather than in the easy case.

---

## H1: falsified

> **H1.** Out-of-country point accuracy will be meaningfully worse than
> in-country, but not catastrophically so. Expected r-squared drop of roughly a
> third.

| | r-squared |
|---|---|
| in-country, spatially blocked | 0.746 |
| out-of-country, leave-one-country-out | 0.723 |
| drop | 0.023, about 3% |

A third was predicted. Three per cent was observed. **H1 is falsified.**

This is consistent with the benchmark table in docs/04: Yeh et al. already
report r-squared 0.67 in held-out countries, and nobody should have expected
point accuracy to break at a border. The protocol's expectation was too
pessimistic.

---

## H2: not supported as stated

> **H2.** Calibration will degrade more than accuracy. A nominal 90% interval
> will cover substantially less than 90% of Gambian clusters. **This is the
> central claim.**

Split conformal, mean across the eleven held-out countries:

| nominal | coverage in-country | coverage out-of-country | shortfall |
|---|---|---|---|
| 0.50 | 0.524 | 0.491 | 0.033 |
| 0.80 | 0.825 | 0.785 | 0.041 |
| 0.90 | 0.913 | **0.887** | 0.026 |
| 0.95 | 0.956 | 0.943 | 0.013 |

A nominal 90% interval covers 88.7% out-of-country. That is 1.3 points below
nominal. It is not "substantially less than 90%".

**By the criterion fixed in docs/00 section 4, the central claim is not
supported.** That section states that if out-of-country coverage is close to
nominal there is no finding, and that this outcome would be reported rather than
reframed. Mean coverage is close to nominal.

Conformalized quantile regression gives the same answer: 0.881 at nominal 0.90.

---

## What the mean hides, stated as post-hoc

**This subsection is post-hoc.** It was not predicted, it was found by looking at
the per-country numbers after the mean had already answered the pre-registered
question. It is reported as a hypothesis for testing, not as a result.

Per held-out country, nominal 90%, split conformal:

| held out | n | coverage in | coverage out |
|---|---|---|---|
| TG | 330 | 0.929 | 0.979 |
| SL | 557 | 0.869 | 0.953 |
| GN | 401 | 0.890 | 0.945 |
| GH | 423 | 0.912 | 0.905 |
| BJ | 540 | 0.910 | 0.896 |
| BF | 514 | 0.909 | 0.872 |
| NG | 1382 | 0.926 | 0.866 |
| CI | 539 | 0.925 | 0.846 |
| ML | 328 | 0.924 | 0.838 |
| SN | 214 | 0.932 | 0.836 |
| MR | 1198 | 0.919 | 0.821 |

The mean is 0.887 because 0.979 and 0.821 average out. Individually:

- Out-of-country coverage ranges **0.821 to 0.979** for a nominal 90% interval.
- Standard deviation across countries is **0.053** out-of-country against
  **0.019** in-country, a factor of 2.8.
- If true coverage were exactly 0.90 in every country, binomial sampling at
  these sample sizes would give a standard deviation of 0.014. Observed is
  **3.7 times** that.
- Chi-square test of the hypothesis that coverage equals 0.90 in every country:
  chi-square 195.1 on 10 degrees of freedom, p below machine precision.
- **9 of 11 countries** fall outside a 88 to 92% band. In-country, 6 of 11 do,
  and none by nearly as much.

So the dispersion is far larger than sampling noise and far larger than the
in-country dispersion. What crossing a border appears to damage is not the
average level of coverage but its **reliability for any particular country**.

Why that would matter if it holds up: a practitioner never applies a model to
eleven countries and averages. They apply it to one. Being told an interval
covers 90% on average, when for the country in front of them it might cover 82%
or 98% and there is no way to know which, is not a usable guarantee. The
guarantee has not shifted; it has become uninformative.

**This must not be presented as if it were H2.** It is a different claim,
arrived at after seeing the data, and on this evidence alone it is an
observation in search of a test.

---

## H3: premise fails, mechanism holds

> **H3.** Domain adaptation will improve H1 more than it improves H2. Methods
> that align feature distributions have no mechanism that targets interval
> width, so they should leave the model confidently wrong rather than
> appropriately uncertain.

CORAL, out-of-country, nominal 90%:

| method | variant | mean coverage | sd | r-squared |
|---|---|---|---|---|
| split | baseline | 0.887 | 0.053 | 0.709 |
| split | CORAL | 0.865 | 0.055 | 0.646 |
| cqr | baseline | 0.881 | 0.060 | 0.709 |
| cqr | CORAL | 0.907 | 0.062 | 0.646 |

Interval score, lower is better: split 1.998 to 2.242, CQR 1.990 to 2.011.
CORAL is worse on both.

**The premise fails.** H3 assumed domain adaptation would improve point
accuracy. CORAL degrades it, r-squared 0.709 to 0.646. There is no accuracy gain
to compare a calibration gain against.

**The mechanism claim survives, and is the part worth keeping.** H3's reasoning
was that aligning feature distributions contains nothing that acts on interval
width. That is exactly what is observed: the dispersion of coverage is
unchanged, 0.053 to 0.055 for split and 0.060 to 0.062 for CQR. Alignment moved
the mean coverage around, in opposite directions for the two methods, and left
the spread untouched.

CORAL is one member of the family named in the protocol and the adversarial
variant has not been run. That absence is recorded rather than glossed: H3 is
tested against second-moment alignment only.

---

## Where this leaves the paper

The pre-registered central claim is not supported. Three findings stand:

1. Point accuracy transfers essentially intact, 3% loss, contradicting H1 and
   confirming what the literature already reports.
2. Mean interval coverage also transfers, 0.887 against a nominal 0.90,
   contradicting H2.
3. Coverage **reliability** does not transfer, on a post-hoc reading: 3.7 times
   the dispersion sampling noise allows, 2.8 times the in-country dispersion,
   and 9 of 11 countries outside a two-point band.

The honest position is that (1) and (2) are results and (3) is a hypothesis.

**The Gambia is the test, and it has not been spent.** The design reserved one
look at the target for the pre-registered claim. That claim is now answered on
eleven country pairs and the target is not needed to answer it again. What the
target can do, exactly once, is test claim (3) out of sample, on a country whose
data has never been examined.

That requires writing the dispersion claim down as a prediction with a threshold
before the Gambian labels are loaded, in the same way the original hypotheses
were fixed. Doing anything else with that one look, in particular loading the
data and then deciding what it shows, would discard the only genuinely
untouched test this project has left.

That decision is the author's and is not taken here.
