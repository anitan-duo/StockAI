"""API contracts for cross-sectional relative rankings (ACC-001)."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from packages.schemas.base import BaseSchema


class RankingEntryResponse(BaseSchema):
    instrument_id: UUID
    symbol: str
    exchange: str
    rank: int = Field(..., ge=1)
    score: float = Field(..., ge=0, le=1)
    percentile: float = Field(..., ge=0, le=100)
    quintile: int = Field(..., ge=1, le=5)
    relative_label: str


class RankingSnapshotResponse(BaseSchema):
    market: str | None = None
    horizon: str = Field(..., pattern="^(1d|5d|10d)$")
    as_of_date: date
    generated_at: datetime
    objective: str
    model_version: str
    artifact_sha: str
    feature_version: str
    universe_size: int = Field(..., ge=0)
    market_universe_size: int = Field(..., ge=0)
    ranked_count: int = Field(..., ge=0)
    excluded: dict[str, Any] = Field(default_factory=dict)
    entries: list[RankingEntryResponse]
    evaluation: dict[str, Any] = Field(default_factory=dict)
    caveats: list[str] = Field(default_factory=list)
    score_semantics: str | None = None


class RankingQuintilePerformance(BaseSchema):
    n: int = Field(..., ge=0)
    hit_rate: float | None = None


class RankingPerformanceResponse(BaseSchema):
    market: str
    horizon: str
    n_outcomes: int = Field(..., ge=0)
    hit_rate: float | None = None
    reliable: bool = False
    mean_snapshot_rank_ic: float | None = None
    by_quintile: dict[str, RankingQuintilePerformance] = Field(default_factory=dict)
