from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import load_group, require_project
from app.db import get_db
from app.models import TestCase, TestGroup
from app.schemas import GroupCreate, GroupOut, GroupUpdate

router = APIRouter(tags=["groups"])


@router.post("/projects/{project_id}/groups", response_model=GroupOut)
def create_group(project_id: str, payload: GroupCreate, db: Session = Depends(get_db)) -> TestGroup:
    require_project(project_id, db)
    group = TestGroup(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        sort_order=payload.sort_order,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/projects/{project_id}/groups", response_model=list[GroupOut])
def list_groups(project_id: str, db: Session = Depends(get_db)) -> list[TestGroup]:
    require_project(project_id, db)
    return list(
        db.scalars(
            select(TestGroup).where(TestGroup.project_id == project_id).order_by(TestGroup.sort_order)
        ).all()
    )


@router.put("/groups/{group_id}", response_model=GroupOut)
def update_group(group_id: str, payload: GroupUpdate, db: Session = Depends(get_db)) -> TestGroup:
    group = load_group(group_id, db)
    if payload.name is not None:
        group.name = payload.name
    if "description" in payload.model_fields_set:
        group.description = payload.description
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order
    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}")
def delete_group(group_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    group = load_group(group_id, db)
    cases = db.scalars(select(TestCase).where(TestCase.group_id == group.id)).all()
    for case in cases:
        case.group_id = None
    db.delete(group)
    db.commit()
    return {"id": group_id, "status": "deleted"}
