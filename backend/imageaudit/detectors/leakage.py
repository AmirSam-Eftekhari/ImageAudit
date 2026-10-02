"""Cross-split leakage derived from duplicate groups.

Reports only what hashing can establish: byte-identical files and perceptually near-identical
images appearing in more than one split. It does not detect semantic leakage (same scene or
object from a different photo, video-frame neighbours, augmented crops/flips).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations

from ..core.models import DuplicateGroup, ImageRecord
from ..datasets.base import SPLIT_PRIORITY

LIMITATION_NOTE = (
    "Leakage is established from SHA-256 and perceptual hashes only. Semantically related "
    "images (same scene, video-frame neighbours, crops, flips, rotations) are not detected."
)


def _prio(split: str) -> tuple[int, str]:
    return (SPLIT_PRIORITY.get(split, 9), split)


class LeakageDetector:
    def analyze(self, groups: Sequence[DuplicateGroup], images: Sequence[ImageRecord]) -> dict:
        cross = [g for g in groups if g.scope == "cross_split"]
        pairs: dict[tuple[str, str], dict] = {}
        leaked_ids: dict[str, set[str]] = defaultdict(set)  # split -> image ids

        for g in cross:
            by_split: dict[str, list] = defaultdict(list)
            for m in g.members:
                by_split[m.split].append(m)
            ordered = sorted(by_split, key=_prio)
            # Images outside the highest-priority split of the group are the "leaked" copies.
            for split in ordered[1:]:
                leaked_ids[split].update(m.image_id for m in by_split[split])
            for a, b in combinations(ordered, 2):
                entry = pairs.setdefault((a, b), {
                    "a": a, "b": b, "exact_groups": 0, "perceptual_groups": 0,
                    "image_ids_a": set(), "image_ids_b": set(), "examples": []})
                shared = {m.sha256 for m in by_split[a]} & {m.sha256 for m in by_split[b]}
                kind = "exact" if shared else "perceptual"
                entry["exact_groups" if kind == "exact" else "perceptual_groups"] += 1
                entry["image_ids_a"].update(m.image_id for m in by_split[a])
                entry["image_ids_b"].update(m.image_id for m in by_split[b])
                if len(entry["examples"]) < 12:
                    entry["examples"].append({"group_id": g.id, "kind": kind})

        pair_list = []
        for entry in sorted(pairs.values(), key=lambda e: (_prio(e["a"]), _prio(e["b"]))):
            pair_list.append({
                "a": entry["a"], "b": entry["b"],
                "exact_groups": entry["exact_groups"],
                "perceptual_groups": entry["perceptual_groups"],
                "total_groups": entry["exact_groups"] + entry["perceptual_groups"],
                "images_a": len(entry["image_ids_a"]), "images_b": len(entry["image_ids_b"]),
                "image_ids": sorted(entry["image_ids_a"] | entry["image_ids_b"]),
                "examples": entry["examples"],
            })

        valid = [i for i in images if i.status == "ok"]
        eval_valid = [i for i in valid if i.split != "train"]
        leaked_total = sum(len(v) for v in leaked_ids.values())
        return {
            "pairs": pair_list,
            "cross_split_groups": len(cross),
            "exact_groups": sum(1 for g in cross if g.kind == "exact"),
            "perceptual_groups": sum(1 for g in cross if g.kind == "perceptual"),
            "leaked_images": leaked_total,
            "leaked_by_split": {k: len(v) for k, v in sorted(leaked_ids.items(), key=lambda kv: _prio(kv[0]))},
            "leaked_image_ids": sorted({i for v in leaked_ids.values() for i in v}),
            "eval_images": len(eval_valid),
            "leakage_rate": (leaked_total / len(eval_valid)) if eval_valid else None,
            "applicable": len({i.split for i in valid}) > 1,
            "note": LIMITATION_NOTE,
        }
