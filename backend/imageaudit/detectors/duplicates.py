"""Exact and perceptual duplicate detection.

Exact: identical SHA-256 (byte-identical files).
Perceptual: pHash Hamming distance <= T1 AND dHash distance <= T2 (two independent hashes must
agree, which cuts false positives). Candidate pairs come from multi-index bucketing: the 64-bit
pHash is split into 8 chunks of 8 bits; two hashes within distance 7 must share at least one
identical chunk (pigeonhole), so only same-bucket pairs are compared instead of all O(n^2) pairs.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations

from ..analyzers import hashing
from ..core.config import DuplicateConfig
from ..core.models import DuplicateGroup, DuplicateMember, ImageRecord
from ..datasets.base import SPLIT_PRIORITY

_CHUNKS = 8
_MAX_BUCKET = 5000


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _split_key(split: str) -> tuple[int, str]:
    return (SPLIT_PRIORITY.get(split, 9), split)


class DuplicateDetector:
    def __init__(self, cfg: DuplicateConfig) -> None:
        self.cfg = cfg
        self.skipped_buckets = 0

    def detect(self, images: Sequence[ImageRecord]) -> list[DuplicateGroup]:
        eligible = [i for i in images if i.status == "ok" and i.sha256]
        by_id = {i.id: i for i in eligible}
        uf = _UnionFind()
        edge_distance: dict[str, int] = defaultdict(int)  # root-agnostic: max per member id

        by_sha: dict[str, list[ImageRecord]] = defaultdict(list)
        for img in eligible:
            by_sha[img.sha256 or ""].append(img)
        for members in by_sha.values():
            for other in members[1:]:
                uf.union(members[0].id, other.id)

        if self.cfg.enabled:
            self._perceptual_edges(by_sha, uf, edge_distance)

        components: dict[str, list[str]] = defaultdict(list)
        for image_id in list(uf.parent):
            components[uf.find(image_id)].append(image_id)

        groups: list[DuplicateGroup] = []
        for ids in components.values():
            if len(ids) < 2:
                continue
            members = sorted((by_id[i] for i in ids),
                             key=lambda r: (_split_key(r.split), r.path))
            shas = {m.sha256 for m in members}
            splits = sorted({m.split for m in members}, key=_split_key)
            gid = "g_" + hashlib.sha1("|".join(sorted(ids)).encode()).hexdigest()[:10]
            groups.append(DuplicateGroup(
                id=gid,
                kind="exact" if len(shas) == 1 else "perceptual",
                scope="cross_split" if len(splits) > 1 else "within_split",
                splits=splits,
                members=[DuplicateMember(m.id, m.path, m.split, m.sha256) for m in members],
                unique_files=len(shas),
                max_distance=max((edge_distance.get(i, 0) for i in ids), default=0),
            ))
        groups.sort(key=lambda g: (-len(g.members), g.members[0].path))
        return groups

    def _perceptual_edges(self, by_sha: dict[str, list[ImageRecord]], uf: _UnionFind,
                          edge_distance: dict[str, int]) -> None:
        reps = [m[0] for m in by_sha.values() if m[0].hash_reliable and m[0].phash and m[0].dhash]
        reps.sort(key=lambda r: r.path)
        p = [hashing.from_hex(r.phash or "0") for r in reps]
        d = [hashing.from_hex(r.dhash or "0") for r in reps]
        buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for idx, value in enumerate(p):
            for c in range(_CHUNKS):
                buckets[(c, (value >> (8 * c)) & 0xFF)].append(idx)
        seen: set[tuple[int, int]] = set()
        for members in buckets.values():
            if len(members) < 2:
                continue
            if len(members) > _MAX_BUCKET:
                self.skipped_buckets += 1
                continue
            for i, j in combinations(members, 2):
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                dp = hashing.hamming(p[i], p[j])
                if dp <= self.cfg.phash_max_distance and \
                        hashing.hamming(d[i], d[j]) <= self.cfg.dhash_max_distance:
                    uf.union(reps[i].id, reps[j].id)
                    for r in (reps[i], reps[j]):
                        edge_distance[r.id] = max(edge_distance[r.id], dp)


def summarize_duplicates(groups: Sequence[DuplicateGroup]) -> dict:
    """Counts used by statistics, scoring and findings.

    ``redundant_within_split`` counts, per split, images beyond the first in each group -
    i.e. how many images could be deleted to leave one representative per split.
    """
    redundant = 0
    by_split: dict[str, int] = defaultdict(int)
    for g in groups:
        per_split: dict[str, int] = defaultdict(int)
        for m in g.members:
            per_split[m.split] += 1
        for split, n in per_split.items():
            by_split[split] += n - 1
            redundant += n - 1
    return {
        "groups": len(groups),
        "exact_groups": sum(1 for g in groups if g.kind == "exact"),
        "perceptual_groups": sum(1 for g in groups if g.kind == "perceptual"),
        "within_split_groups": sum(1 for g in groups if g.scope == "within_split"),
        "cross_split_groups": sum(1 for g in groups if g.scope == "cross_split"),
        "images_in_groups": sum(len(g.members) for g in groups),
        "redundant_within_split": redundant,
        "redundant_by_split": dict(by_split),
    }
