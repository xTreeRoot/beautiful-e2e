from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import require_project
from app.db import get_db
from app.models import AuditEvent, ProjectKnowledgeGraph, Repository
from app.schemas import ProjectKnowledgeGraphOut, ProjectKnowledgeGraphUpdate
from app.services.project_knowledge_graph import (
    normalized_review_status,
    upsert_candidate_knowledge_graph,
    with_review_status,
)

router = APIRouter(tags=["project_knowledge_graph"])


@router.get(
    "/projects/{project_id}/knowledge-graph",
    response_model=ProjectKnowledgeGraphOut,
)
def get_project_knowledge_graph(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectKnowledgeGraph:
    require_project(project_id, db)
    graph = db.scalar(
        select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project_id)
    )
    if graph is None:
        raise HTTPException(status_code=404, detail="项目知识图谱尚未生成，请先运行项目分析")
    return graph


@router.post(
    "/projects/{project_id}/knowledge-graph/rebuild",
    response_model=ProjectKnowledgeGraphOut,
)
def rebuild_project_knowledge_graph(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectKnowledgeGraph:
    require_project(project_id, db)
    repositories = list(
        db.scalars(select(Repository).where(Repository.project_id == project_id)).all()
    )
    graph = upsert_candidate_knowledge_graph(project_id, repositories, db)
    db.commit()
    db.refresh(graph)
    return graph


@router.put(
    "/projects/{project_id}/knowledge-graph",
    response_model=ProjectKnowledgeGraphOut,
)
def update_project_knowledge_graph(
    project_id: str,
    payload: ProjectKnowledgeGraphUpdate,
    db: Session = Depends(get_db),
) -> ProjectKnowledgeGraph:
    require_project(project_id, db)
    row = db.scalar(
        select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project_id)
    )
    review_status = normalized_review_status(payload.review_status)
    graph = with_review_status(payload.graph, review_status)
    if row is None:
        row = ProjectKnowledgeGraph(
            project_id=project_id,
            review_status=review_status,
            review_notes=payload.review_notes,
            graph=graph,
        )
        db.add(row)
        db.flush()
    else:
        row.review_status = review_status
        row.review_notes = payload.review_notes
        row.graph = graph
    db.add(
        AuditEvent(
            project_id=project_id,
            actor=payload.actor,
            action="project_knowledge_graph.updated",
            entity_type="project_knowledge_graph",
            entity_id=row.id,
            payload={
                "review_status": row.review_status,
                "module_count": len(graph.get("modules") or []),
                "relationship_count": len(graph.get("relationships") or []),
            },
        )
    )
    db.commit()
    db.refresh(row)
    return row
