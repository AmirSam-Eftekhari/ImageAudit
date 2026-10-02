# Sample dataset (synthetic, intentionally problematic)

Generated deterministically by `imageaudit demo` (seed 7). All images are drawn programmatically
(coloured shapes on random textured backgrounds): no copyrighted or sensitive data.

Injected defects (the test-suite asserts ImageAudit finds every one):

| Defect | Where |
|---|---|
| exact duplicate inside train | `train_dup_a` / `train_dup_b` (+ one more pair) |
| exact cross-split leak (train -> val) | `val_leak_exact` |
| near-duplicate cross-split leak (train -> test, re-encoded + resized) | `test_leak_near` |
| near-duplicate inside train | `train_near_*` |
| blurry images | `*_blurry*` |
| corrupted (truncated) JPEGs, zero-byte file, unsupported `.gif` | `train/` |
| dark, bright, 60x45 low-resolution, 4.2:1 panorama, grayscale images | `train/` |
| malformed / invalid-class / negative / >1 / zero-area / tiny / huge / duplicate boxes | `labels/train/train_010.txt` and others |
| missing label files, empty label files, orphan label file | various |
| class imbalance (`square` dominates), `star` declared but never used | `data.yaml`, labels |

Regenerate: `imageaudit demo ./somewhere` or `python scripts/make_sample_dataset.py`.
