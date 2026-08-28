# The Gambian evaluation

Run 2026-08-28 against the specification committed at
`bfa32ce277b2d21944b1f04912ba716a95dfe52b`, which contains
docs/06-preregistration-h4.md and `src/evaluate_gambia.py` and was written
before any Gambian wealth label was read. Executed once. Raw output in
`data/processed/gambia_evaluation.json`.

---

## Primary result: H4 is not confirmed

| | |
|---|---|
| coverage, split conformal, nominal 90% | **0.893** |
| pre-registered band | [0.865, 0.935] |
| deviation | z = -0.40, p = 0.69 |
| verdict | **NOT CONFIRMED** |

Gambian coverage sits well inside the interval that sampling variation alone
would produce if true coverage were exactly 0.90.

**This must be reported as "H4 not confirmed on a test with 53% power", and not
as evidence that out-of-country coverage is reliable.** docs/06 fixed that
wording in advance precisely so it could not be softened afterwards. The test
misses a true effect roughly half the time; a null from it is weak evidence.

Gambia ranks 7th of 12 against the eleven training countries, whose
out-of-country coverage spanned 0.821 to 0.979. It is an unremarkable member of
that spread, which is consistent both with the dispersion observation and with
coverage simply being nominal. The single draw does not separate them. That is
the limitation the pre-registration named in advance.

Context, not a test: r-squared on the Gambian clusters is **0.673**, against
0.723 mean leave-one-country-out on the training pool. Consistent with H1 being
falsified.

---

## Secondary results, and a pattern that is not noise

All six pre-specified tests, reported whatever they show, as docs/06 requires.

| method | nominal | coverage | z | p | band | |
|---|---|---|---|---|---|---|
| split | 0.50 | 0.3714 | **-4.30** | 1.7e-05 | none registered | |
| split | 0.80 | 0.7036 | **-4.03** | 5.5e-05 | [0.753, 0.847] | **OUTSIDE** |
| split | 0.90 | 0.8929 | -0.40 | 0.69 | [0.865, 0.935] | inside |
| split | 0.95 | 0.9607 | 0.82 | 0.41 | [0.924, 0.976] | inside |
| cqr | 0.50 | 0.4750 | -0.84 | 0.40 | none registered | |
| cqr | 0.80 | 0.7750 | -1.05 | 0.30 | [0.753, 0.847] | inside |
| cqr | 0.90 | 0.8964 | -0.20 | 0.84 | [0.865, 0.935] | inside |
| cqr | 0.95 | 0.9679 | 1.37 | 0.17 | [0.924, 0.976] | inside |

One of six pre-specified tests falls outside its band. At a 5% false positive
rate each, one miss in six correlated tests is close to what multiplicity alone
produces, and on that count alone it would not be worth remarking on.

**The magnitude is the reason it is.** A nominal 80% interval covering 70.4% of
Gambian clusters is four standard errors from nominal, p = 5.5e-05. That is not
a marginal boundary crossing. The 50% level, which carries no registered band,
is 4.3 standard errors low in the same direction.

**And the pattern is coherent rather than scattered.** Split conformal
undercovers severely at nominal 50% and 80% and is indistinguishable from
nominal at 90% and 95%. Conformalized quantile regression is within 1.4 standard
errors at every level.

### What that pattern means

Split conformal with absolute-residual scores produces **constant-width**
intervals: the same width at every cluster, set by one quantile of the
calibration residuals. CQR produces intervals whose width varies with the input.

Coverage that fails in the middle of the distribution and holds in the tails is
what a width that is the wrong *shape* looks like, not a width that is uniformly
too small. If the Gambian residual distribution is more concentrated near zero
and heavier in the tails than the training-country calibration distribution, a
single constant width chosen at the 90th percentile will still capture 90%,
while the widths implied at the 50th and 80th percentiles will be too narrow.
An adaptive interval can absorb that; a constant one cannot.

**This contrast was reasoned out in advance, though not registered as a
hypothesis with a threshold.** `conformal.py`, committed before extraction
began, gives as the reason for including CQR at all:

> Included because adaptivity is the property most likely to survive a
> distribution shift. If constant-width conformal loses coverage but CQR does
> not, that is informative; if both lose it, the failure is about the shift
> rather than about interval shape.

That is a design rationale in a module docstring. It is not H4, it carried no
threshold, and it is not being promoted to a pre-registered prediction here. It
does establish that the comparison was set up deliberately rather than found by
searching, which is the difference between a lead and a fishing expedition.

### What it is not

It is not confirmation of H4. H4 was a claim about coverage at 90% deviating
from nominal, and coverage at 90% did not. Recasting a 90%-level hypothesis as
an 80%-level one after seeing which level moved is the practice this project
exists to criticise.

It is also a single country. The training pool showed no comparable low-level
undercoverage: split conformal there averaged 0.491 at nominal 0.50 and 0.785 at
nominal 0.80, both close to nominal. Whether The Gambia is unusual, or whether
the training-pool average again hides per-country structure, is not answerable
from one draw and the per-level per-country breakdown was not computed before
this document was fixed.

---

## Where the project stands

Four hypotheses, four negative results.

| | prediction | result |
|---|---|---|
| H1 | out-of-country accuracy drops by a third | falsified: 3% |
| H2 | nominal 90% covers substantially less than 90% | not supported: 0.887 pooled, 0.893 Gambia |
| H3 | adaptation improves accuracy, not calibration | premise fails: CORAL degrades accuracy |
| H4 | Gambian coverage deviates beyond sampling noise | not confirmed at 53% power |

The paper the protocol set out to write does not exist. docs/00 section 4
committed to reporting that rather than reframing it, and this document is that
commitment being kept.

What is defensible to report:

1. **Point accuracy transfers essentially intact.** 0.746 in-country blocked,
   0.723 leave-one-country-out, 0.673 on The Gambia. Eleven country pairs plus
   one held-out target, with spatially blocked validation throughout and a
   documented sanity gate. This contradicts the field's caution and is a real,
   if unglamorous, contribution.

2. **Mean interval coverage also transfers.** 0.887 pooled, 0.893 on the target.
   No study in the benchmark table reported coverage at all, so measuring it and
   finding it holds is worth stating.

3. **Coverage dispersion across countries is large**, 3.7 times sampling noise,
   range 0.821 to 0.979. Post-hoc, and its one out-of-sample test came back
   null. Reportable as an observation with that null attached, not as a finding.

4. **Constant-width conformal appears to fail in interval shape on the target
   while adaptive CQR does not**, at four standard errors. Post-hoc as a result,
   though the comparison was designed in advance. This is the strongest lead the
   project has and it is a lead, not a result.

Item 4 is the honest candidate for follow-up work: it has a mechanism, it has a
prior written before the data, and it is testable per country across the eleven
training countries at every nominal level, which is a design with real power
rather than a single draw. That test has not been run and would need
pre-registering like this one.
