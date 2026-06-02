from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    DEFAULT_PROJECT_SETTINGS,
    delete_project_dependents,
    ensure_project_defaults,
    mark_project_current,
    ordered_projects_query,
    project_out,
    project_settings_with_repositories,
    readable_project_name,
    read_project_meta,
    require_project,
    sync_project_environments,
    unique_project_name,
    upsert_repository,
    workspace_out,
    write_project_meta,
)
from app.api.sse import sse_event
from app.core.config import get_settings
from app.db import get_db
from app.models import Project
from app.schemas import (
    BootstrapOut,
    ProjectCreate,
    ProjectFromDirectoryRequest,
    ProjectOut,
    ProjectUpdate,
)
from app.services.project_analyzer import ProjectAnalyzer
from app.services.repo_reader import RepoReader

router = APIRouter(tags=["projects"])


@router.post("/bootstrap", response_model=BootstrapOut)
def bootstrap(db: Session = Depends(get_db)) -> BootstrapOut:
    created_project = False
    project = db.scalar(
        select(Project)
        .where(Project.is_current.is_(True))
        .order_by(Project.updated_at.desc(), Project.created_at.desc())
    )
    if project is None:
        project = db.scalar(
            select(Project).order_by(Project.updated_at.desc(), Project.created_at.desc())
        )
    if project is None:
        project = Project(name="Beautiful E2E")
        write_project_meta(
            project,
            "AI 辅助端到端回归测试平台",
            DEFAULT_PROJECT_SETTINGS,
        )
        db.add(project)
        db.flush()
        created_project = True
    if created_project:
        ensure_project_defaults(project.id, db)
    mark_project_current(project.id, db)
    db.commit()
    return workspace_out(project.id, db)


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectOut:
    project = Project(name=unique_project_name(payload.name, db))
    settings = {**DEFAULT_PROJECT_SETTINGS, **(payload.settings or {})}
    write_project_meta(project, payload.description, settings)
    db.add(project)
    db.flush()
    sync_project_environments(project.id, settings, db)
    ensure_project_defaults(project.id, db)
    if payload.analyze_on_create:
        _analyze_project(project.id, settings, db)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


@router.post("/projects/from-directory", response_model=ProjectOut)
def create_project_from_directory(
    payload: ProjectFromDirectoryRequest,
    db: Session = Depends(get_db),
) -> ProjectOut:
    root = Path(payload.path).expanduser()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="所选路径不是目录")

    settings: dict[str, Any] = dict(DEFAULT_PROJECT_SETTINGS)
    settings["workspace_path"] = str(root)
    settings["frontend_repo_path"] = ""
    settings["backend_repo_path"] = ""

    project = Project(
        name=unique_project_name(payload.name or readable_project_name(root.name), db)
    )
    write_project_meta(project, f"从本地目录 {root} 选择的项目", settings)
    db.add(project)
    db.flush()
    upsert_repository(project.id, "workspace", str(root), db)
    sync_project_environments(project.id, settings, db)
    ensure_project_defaults(project.id, db)
    if payload.analyze_on_create:
        _analyze_project(project.id, settings, db)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectOut]:
    projects = db.scalars(ordered_projects_query()).all()
    return [project_out(project, db) for project in projects]


@router.get("/projects/{project_id}/workspace", response_model=BootstrapOut)
def get_project_workspace(project_id: str, db: Session = Depends(get_db)) -> BootstrapOut:
    require_project(project_id, db)
    return workspace_out(project_id, db)


@router.post("/projects/{project_id}/select", response_model=BootstrapOut)
def select_project_workspace(project_id: str, db: Session = Depends(get_db)) -> BootstrapOut:
    require_project(project_id, db)
    mark_project_current(project_id, db)
    db.commit()
    return workspace_out(project_id, db)


@router.post("/projects/{project_id}/analyze", response_model=ProjectOut)
def analyze_project(project_id: str, db: Session = Depends(get_db)) -> ProjectOut:
    project = require_project(project_id, db)
    _, settings = read_project_meta(project)
    settings = project_settings_with_repositories(project, db, settings)
    _analyze_project(project.id, settings, db)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


@router.post("/projects/{project_id}/analyze/stream")
def analyze_project_stream(project_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """通过 SSE 流式返回项目分析进度，避免长扫描期间前端只能等待。"""

    def events() -> Iterator[str]:
        try:
            yield sse_event(
                "start",
                {
                    "message": "收到项目分析请求，开始读取项目配置。",
                    "stage": "start",
                },
            )
            project = require_project(project_id, db)
            _, settings = read_project_meta(project)
            settings = project_settings_with_repositories(project, db, settings)
            app_settings = get_settings()
            analyzer = ProjectAnalyzer(RepoReader(max_files=app_settings.workspace_scan_max_files))
            for event in analyzer.analyze_events(project.id, settings, db):
                yield sse_event("progress", _public_analysis_event(event))
            db.commit()
            db.refresh(project)
            analyzed = project_out(project, db)
            yield sse_event(
                "project",
                {
                    "message": f"项目分析已更新：{analyzed.name}。",
                    "stage": "project",
                    "project": analyzed.model_dump(mode="json"),
                },
            )
            yield sse_event("done", {"message": "项目分析流式更新完成。", "stage": "done"})
        except HTTPException as exc:
            db.rollback()
            yield sse_event(
                "error",
                {"message": str(exc.detail), "stage": "request", "status_code": exc.status_code},
            )
        except Exception as exc:
            db.rollback()
            yield sse_event(
                "error",
                {"message": str(exc), "stage": "unknown", "status_code": 500},
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectOut:
    project = require_project(project_id, db)
    description, settings = read_project_meta(project)
    settings = project_settings_with_repositories(project, db, settings)

    if payload.name is not None and payload.name != project.name:
        project.name = unique_project_name(payload.name, db, exclude_id=project.id)
    if "description" in payload.model_fields_set:
        description = payload.description
    if payload.settings:
        settings.update(payload.settings)

    field_map = {
        "execution_mode": payload.execution_mode,
        "frontend_repo_path": payload.frontend_repo_path,
        "backend_repo_path": payload.backend_repo_path,
        "workspace_path": payload.workspace_path,
        "active_environment": payload.active_environment,
        "active_frontend_environment": payload.active_frontend_environment,
        "active_api_environment": payload.active_api_environment,
        "base_url": payload.base_url,
        "api_base_url": payload.api_base_url,
    }
    for key, value in field_map.items():
        if value is not None:
            settings[key] = value

    upsert_repository(project.id, "workspace", settings.get("workspace_path") or "", db)
    upsert_repository(project.id, "frontend", settings.get("frontend_repo_path") or "", db)
    upsert_repository(project.id, "backend", settings.get("backend_repo_path") or "", db)
    sync_project_environments(project.id, settings, db)
    write_project_meta(project, description, settings)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    project = require_project(project_id, db)
    deleting_current = project.is_current
    delete_project_dependents(project.id, db)
    db.delete(project)
    db.flush()
    if deleting_current:
        fallback = db.scalar(
            select(Project)
            .where(Project.id != project_id)
            .order_by(Project.updated_at.desc(), Project.created_at.desc())
        )
        if fallback is not None:
            mark_project_current(fallback.id, db)
    db.commit()
    return {"id": project_id, "status": "deleted"}


def _analyze_project(project_id: str, settings: dict[str, Any], db: Session) -> None:
    app_settings = get_settings()
    ProjectAnalyzer(
        RepoReader(max_files=app_settings.workspace_scan_max_files)
    ).analyze(project_id, settings, db)


def _public_analysis_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if not key.startswith("_")}
