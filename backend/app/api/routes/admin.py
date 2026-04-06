"""Admin inspection and evaluation routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.evals.evaluation_runner import run_local_evaluations
from backend.app.services.admin.admin_service import (
    get_admin_cluster_detail,
    get_pipeline_run,
    get_source_item,
    list_admin_clusters,
    list_admin_digests,
    list_admin_summaries,
    list_pipeline_runs,
    list_source_items,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pipeline-runs")
def get_pipeline_runs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_pipeline_runs(db)


@router.get("/pipeline-runs/{run_id}")
def get_pipeline_run_detail(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = get_pipeline_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pipeline run {run_id} was not found.")
    return run


@router.get("/source-items")
def get_admin_source_items(
    source_type: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    cluster_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_source_items(db, source_type=source_type, symbol=symbol, cluster_id=cluster_id)


@router.get("/source-items/{source_item_id}")
def get_admin_source_item(source_item_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = get_source_item(db, source_item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source item {source_item_id} was not found.")
    return item


@router.get("/clusters")
def get_admin_clusters(
    sort_by: str = Query(default="importance"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return list_admin_clusters(db, sort_by=sort_by)


@router.get("/clusters/{cluster_id}")
def get_admin_cluster(cluster_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    cluster = get_admin_cluster_detail(db, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Cluster {cluster_id} was not found.")
    return cluster


@router.get("/summaries")
def get_admin_summaries(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_admin_summaries(db)


@router.get("/digests")
def get_admin_digests(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_admin_digests(db)


@router.post("/evals/run")
def run_admin_evals(selected: list[str] | None = None) -> dict[str, Any]:
    return run_local_evaluations(selected)
