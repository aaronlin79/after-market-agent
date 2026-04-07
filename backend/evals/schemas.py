"""Schemas for local evaluation fixtures and results."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ClusteringFixtureArticle(BaseModel):
    article_id: str
    text: str
    expected_cluster: str


class EventClassificationFixture(BaseModel):
    text: str
    expected_label: str


class RankingFixtureCluster(BaseModel):
    cluster_id: str
    text: str
    source_name: str
    article_count: int
    first_seen_at: datetime
    expected_rank_group: int


class SummaryGroundingFixture(BaseModel):
    output: dict
    source_count: int


class EvalFixtureSet(BaseModel):
    clustering: list[ClusteringFixtureArticle]
    event_classification: list[EventClassificationFixture]
    ranking: list[RankingFixtureCluster]
    summary_grounding: list[SummaryGroundingFixture]


class EvalSectionResult(BaseModel):
    name: str
    passed: bool
    metrics: dict


class EvalRunResult(BaseModel):
    clustering_results: EvalSectionResult
    classifier_results: EvalSectionResult
    ranking_results: EvalSectionResult
    summary_results: EvalSectionResult
    overall_passed: bool
    generated_at: datetime
