# Health score methodology (formula version 1)

The score is a **weighted mean of eight component scores**. Nothing is learned, hidden or smoothed:
every component is a *measured rate* mapped linearly to 0-100, and the API/UI/reports expose the rate,
the weight and the `zero_at` constant that produced each number.

```
component_score = 100 * (1 - min(1, rate / zero_at))          # linear; 0 when rate >= zero_at
overall         = sum(weight_i * score_i) / sum(weight_i)      # over *applicable* components only
```

| Component (`key`) | Measured rate | default `zero_at` | default weight |
|---|---|---|---|
| Image integrity (`integrity`) | corrupted + zero-byte + unsupported + oversized files / all files | 5 % | 20 |
| Split leakage (`leakage`) | val/test images with an exact or perceptual match in another split / val+test images | 5 % | 20 |
| Annotation validity (`annotation_validity`) | label lines failing validation (error-level issues) / all label lines | 5 % | 20 |
| Duplicates (`duplicates`) | redundant copies *inside* a split / valid images | 20 % | 10 |
| Annotation coverage (`annotation_coverage`) | images with no label file / valid images | 25 % | 10 |
| Class balance (`class_balance`) | max/min class count ratio (classes with >= 1 annotation) | ratio 100 | 10 |
| Sharpness (`blur`) | images below the blur threshold / measured images | 30 % | 5 |
| Image statistics (`image_stats`) | images that are low-res, extreme aspect, dark, bright or low-contrast / valid images | 30 % | 5 |

`class_balance` is the one non-rate component. It uses a logarithmic scale so that going from 1:1 to
10:1 costs as much as going from 10:1 to 100:1:

```
class_balance = 100 * (1 - min(1, ln(ratio) / ln(zero_at)))        # ratio = max_count / min_count
```

## Not applicable != perfect

A component that cannot be measured is **excluded** and the remaining weights are renormalised:

* leakage: fewer than two splits, or the scan ran in `validate` mode;
* duplicates / blur: `validate` mode skips pixel analysis;
* annotation validity / coverage: dataset has no labels;
* class balance: fewer than two classes with annotations.

The UI shows these as "n/a" with an effective weight of 0.

## Grades

`A` >= 90, `B` >= 80, `C` >= 70, `D` >= 60, otherwise `F`.

## Worked example

`corrupt rate = 2.5 %` -> `integrity = 100 * (1 - 0.025/0.05) = 50`. With only integrity (weight 20 -> 50)
and everything else perfect: `overall = (20*50 + 80*100) / 100 = 90`.
Equivalent weighted-mean and linear-penalty arithmetic is asserted in `backend/tests/test_health.py`.

## Configuration

Weights and `zero_at` values are configurable (`scoring.weights`, `scoring.zero_at` in `imageaudit.yaml`; see
`examples/imageaudit.example.yaml`). Unknown component names are rejected. Weights need not sum to 100.

## What the score is *not*

* It is **not** a prediction of model accuracy.
* It does not replace reading the findings: a 2 % cross-split leak lowers the overall score by about 8 points,
  yet it is a **critical** finding. For CI gating prefer `--fail-on critical|high` (severity based) in addition
  to or instead of `--fail-under`.
* The linear penalties and `zero_at` defaults are judgement calls, documented here so you can disagree with them.
