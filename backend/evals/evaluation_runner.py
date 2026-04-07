"""Deterministic local evaluation runner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.evals.schemas import EvalFixtureSet, EvalRunResult, EvalSectionResult
from backend.app.services.clustering.similarity import cosine_similarity
from backend.app.services.embeddings.embedding_service import generate_embedding
from backend.app.services.ranking.event_classifier import classify_event_type
from backend.app.services.ranking.ranking_service import EVENT_TYPE_BOOSTS, SOURCE_CREDIBILITY
from backend.app.services.summarization.openai_cluster_summarizer import ClusterSummaryStructuredOutput

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "core_eval_fixture.json"
RANKING_REFERENCE_TIME = datetime(2026, 4, 6, 12, 0, tzinfo=UTC)


def run_local_evaluations(selected: list[str] | None = None) -> dict[str, Any]:
    fixtures = _load_fixtures()
    requested = set(selected or ["clustering", "classifier", "ranking", "summary"])

    clustering_results = (
        _run_clustering_eval(fixtures) if "clustering" in requested else _skipped_result("clustering")
    )
    classifier_results = (
        _run_classifier_eval(fixtures) if "classifier" in requested else _skipped_result("classifier")
    )
    ranking_results = _run_ranking_eval(fixtures) if "ranking" in requested else _skipped_result("ranking")
    summary_results = _run_summary_eval(fixtures) if "summary" in requested else _skipped_result("summary")

    result = EvalRunResult(
        clustering_results=clustering_results,
        classifier_results=classifier_results,
        ranking_results=ranking_results,
        summary_results=summary_results,
        overall_passed=all(
            section.passed
            for section in [clustering_results, classifier_results, ranking_results, summary_results]
        ),
        generated_at=datetime.now(UTC),
    )
    return result.model_dump(mode="json")


def _load_fixtures() -> EvalFixtureSet:
    return EvalFixtureSet.model_validate(json.loads(FIXTURE_PATH.read_text()))


def _run_clustering_eval(fixtures: EvalFixtureSet) -> EvalSectionResult:
    predicted_pairs = 0
    exact_matches = 0
    items = fixtures.clustering
    embeddings = {item.article_id: generate_embedding(item.text) for item in items}
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            similarity = cosine_similarity(embeddings[left.article_id], embeddings[right.article_id])
            predicted_same = similarity >= 0.5
            expected_same = left.expected_cluster == right.expected_cluster
            predicted_pairs += 1
            if predicted_same == expected_same:
                exact_matches += 1
    accuracy = exact_matches / predicted_pairs if predicted_pairs else 1.0
    return EvalSectionResult(
        name="clustering",
        passed=accuracy >= 0.66,
        metrics={"pair_count": predicted_pairs, "exact_match_count": exact_matches, "accuracy": round(accuracy, 4)},
    )


def _run_classifier_eval(fixtures: EvalFixtureSet) -> EvalSectionResult:
    correct = 0
    for item in fixtures.event_classification:
        if classify_event_type(item.text) == item.expected_label:
            correct += 1
    total = len(fixtures.event_classification)
    accuracy = correct / total if total else 1.0
    return EvalSectionResult(
        name="classifier",
        passed=accuracy >= 0.66,
        metrics={"total": total, "correct": correct, "accuracy": round(accuracy, 4)},
    )


def _run_ranking_eval(fixtures: EvalFixtureSet) -> EvalSectionResult:
    scored = []
    for item in fixtures.ranking:
        event_type = classify_event_type(item.text) or "other"
        credibility = SOURCE_CREDIBILITY.get(item.source_name, 0.5)
        cluster_size_score = min(item.article_count / 4, 1.0)
        novelty = max(0.2, 1.0 - min((RANKING_REFERENCE_TIME - item.first_seen_at).total_seconds() / 3600 / 24, 0.8))
        event_boost = EVENT_TYPE_BOOSTS.get(event_type, EVENT_TYPE_BOOSTS["other"])
        score = round(0.20 * cluster_size_score + 0.30 * credibility + 0.20 * novelty + 0.30 * event_boost, 4)
        scored.append((item.cluster_id, item.expected_rank_group, score))
    scored.sort(key=lambda value: value[2], reverse=True)
    expected_order = [item.cluster_id for item in sorted(fixtures.ranking, key=lambda item: item.expected_rank_group)]
    observed_order = [cluster_id for cluster_id, _, _ in scored]
    passed = observed_order == expected_order
    return EvalSectionResult(
        name="ranking",
        passed=passed,
        metrics={"expected_order": expected_order, "observed_order": observed_order, "scores": scored},
    )


def _run_summary_eval(fixtures: EvalFixtureSet) -> EvalSectionResult:
    valid_count = 0
    invalid_count = 0
    issues: list[str] = []
    for index, item in enumerate(fixtures.summary_grounding):
        try:
            output = ClusterSummaryStructuredOutput.model_validate(item.output)
            if any(cited < 0 or cited >= item.source_count for cited in output.cited_source_indices):
                raise ValueError("cited_source_indices out of bounds")
            valid_count += 1
        except Exception as exc:
            invalid_count += 1
            issues.append(f"fixture_{index}: {type(exc).__name__}: {exc}")
    passed = invalid_count == 1 and valid_count >= 1
    return EvalSectionResult(
        name="summary",
        passed=passed,
        metrics={"valid_count": valid_count, "invalid_count": invalid_count, "issues": issues},
    )


def _skipped_result(name: str) -> EvalSectionResult:
    return EvalSectionResult(name=name, passed=True, metrics={"skipped": True})
