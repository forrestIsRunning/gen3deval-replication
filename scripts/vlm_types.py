from __future__ import annotations

from typing import Literal

from typing_extensions import NotRequired, TypedDict


class AssetScores(TypedDict):
    text_fidelity: float
    appearance: float
    surface_quality: float
    geometry_coherence: float
    texture_material: float
    multi_view_consistency: float
    overall: float


class AssetScoreResult(TypedDict):
    scores: AssetScores
    reason: str
    issues: list[str]
    strengths: NotRequired[list[str]]
    observability: NotRequired[dict]


class ManifestRow(TypedDict, total=False):
    uid: str
    category: str
    prompt: str
    local_path: str


class PairObject(TypedDict, total=False):
    uid: str
    prompt: str
    category: str


class PairRow(TypedDict):
    pair_id: str
    object_a: PairObject
    object_b: PairObject


class PairwiseJudgeResult(TypedDict):
    winner: Literal["A", "B", "tie"]
    confidence: float
    reason: str
