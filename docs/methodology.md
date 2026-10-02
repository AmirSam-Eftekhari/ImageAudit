# Methodology and limits

All thresholds are **heuristics** with defaults that suit typical detection datasets; they are configurable
(`examples/imageaudit.example.yaml`) and every finding states which rule fired.

## Image integrity
* Per file: extension check, zero-byte check, SHA-256 (streamed), Pillow `verify()` **and** a full decode
  (truncated files often pass `verify()` but fail decode). Reported width/height follow the EXIF orientation (a 90-degree-rotated photo reports its displayed size, which is what labels refer to); hashes and quality metrics are computed on the stored pixels.
* Statuses: `ok`, `corrupted`, `zero_byte`, `unsupported` (extension or decoded format outside JPEG/PNG/BMP/WebP/TIFF),
  `too_large` (decompression-bomb guard on pixel count / file size).
* JPEGs are decoded with Pillow *draft mode* (DCT-domain downscale) when large, bounding memory and time.

## Image quality (computed on a grayscale copy, longest side <= 1024 px)
| Metric | Rule (default) | Caveat |
|---|---|---|
| Blur | variance of the Laplacian < 100 | Scales with contrast and resolution; dark, flat or low-texture images also score low. Tune `quality.blur_threshold` per dataset. |
| Low resolution | shorter side < 64 px | |
| Extreme aspect ratio | max(w/h, h/w) > 4 | |
| Dark / bright | mean gray < 35 / > 220 | |
| Low contrast | gray std < 20 | |
| Grayscale | single-channel, or RGB whose channels are (near-)identical | |

On the bundled sample, 4 images are blurred deliberately but 7 are flagged: the dark/bright/low-contrast images
also have low Laplacian variance. This is the known weakness of the metric, not a bug to hide.

## Perceptual hashing (implemented with NumPy/OpenCV, no `imagehash`)
* **pHash**: 32x32 grayscale (area-resampled) -> 2-D DCT -> top-left 8x8 block -> bits = coefficient > median of the
  64 block coefficients -> 64 bits.
* **dHash**: 9x8 grayscale -> horizontal gradient sign -> 64 bits.
* Two images are **near-duplicates** if `hamming(pHash) <= 6` **and** `hamming(dHash) <= 10`; requiring both reduces
  false positives. Near-flat images (gray std < 2) are excluded because their hashes carry no information
  (identical flat files are still caught as *exact* duplicates).
* Candidate search is sub-quadratic: unique SHA-256 representatives are bucketed with the pigeonhole principle
  (the pHash is split into 8 chunks of 8 bits; two hashes within distance <= 7 must agree exactly on at least one chunk),
  then candidates are verified with a vectorised popcount. This is why `duplicates.phash_max_distance` is capped at 7. Oversized buckets are reported rather than silently skipped.
* Groups are connected components (union-find), so group membership and ids are deterministic.

## Duplicate vs. leakage vocabulary
| Term | Meaning |
|---|---|
| exact duplicate | identical SHA-256 |
| perceptual duplicate | not byte-identical; pHash/dHash within thresholds |
| within-split duplicate | all members in one split: redundancy, not leakage |
| cross-split leakage | members in two or more splits |

**Not detected:** semantic leakage - the same scene from another angle, adjacent video frames, heavy crops, flips,
rotations, colour-shifted copies. Hash matching cannot establish these and ImageAudit does not claim to.

## YOLO annotation validation
Each non-empty line must be `class cx cy w h` (normalised) or a polygon `class x1 y1 x2 y2 x3 y3 ...` (>= 3 points,
reduced to its bounding box). Detected, with file + line number: malformed lines (wrong field count, non-numeric/NaN),
invalid class ids (non-integer, negative, >= class count), negative coordinates, values > 1, negative sizes,
zero-area boxes, boxes past the image edge, tiny boxes (area < 0.04 %), near-whole-image boxes (> 95 %), and
same-class near-identical boxes (IoU >= 0.95). Missing label files, empty label files (valid background images)
and orphan label files are reported separately. Invalid lines never become boxes and are never dropped silently.

## Dataset discovery
`data.yaml` split paths are honoured when they resolve **inside** the dataset root; otherwise layouts
`images/<split>/`, `<split>/images/` and flat `images/` are inferred (`valid`/`validation` -> `val`).
Directory symlinks are never followed and file symlinks pointing outside the root are ignored.

## Determinism
Files are processed in sorted order, ids are content/path derived, and results are independent of worker count
(`test_analysis_is_deterministic`). Only timestamps and the audit id differ between runs.
