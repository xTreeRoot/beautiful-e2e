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
from app.models import Project, Repository
from app.schemas import (
    BootstrapOut,
    DomModuleCompileRequest,
    ProjectCreate,
    ProjectFromDirectoryRequest,
    ProjectOut,
    ProjectUpdate,
)
from app.services.ai_settings import AI_USAGE_DOM_COMPILATION, settings_for_ai_usage
from app.services.dom_preview_compiler import (
    DomPreviewCompilationError,
    compile_dom_module_preview,
    module_compile_source,
    static_compile_dom_module_preview,
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


@router.post("/projects/{project_id}/dom-modules/compile/stream")
def compile_dom_module_stream(
    project_id: str,
    payload: DomModuleCompileRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """在 DOM 图谱内手动触发单个页面/组件模块预览编译。"""

    def events() -> Iterator[str]:
        try:
            yield sse_event(
                "start",
                {
                    "message": "收到 DOM 模块编译请求。",
                    "stage": "start",
                    "percent": 5,
                    "mode": payload.mode,
                },
            )
            project = require_project(project_id, db)
            repository = db.scalar(
                select(Repository).where(
                    Repository.id == payload.repository_id,
                    Repository.project_id == project.id,
                )
            )
            if repository is None:
                raise HTTPException(status_code=404, detail="DOM 模块所在仓库不存在")

            summary = dict(repository.index_summary or {})
            modules = [
                dict(module)
                for module in summary.get("dom_modules", [])
                if isinstance(module, dict)
            ]
            module_index, module = _dom_module_by_id(modules, payload.module_id)
            yield sse_event(
                "progress",
                {
                    "message": "正在解析页面源码。",
                    "stage": "source",
                    "percent": 20,
                    "mode": payload.mode,
                },
            )
            compile_source = module_compile_source(Path(repository.path), module)
            compile_module = {
                **module,
                "compile_source_file": compile_source.source_file,
                "compile_source_files": compile_source.source_files,
            }

            if payload.mode == "ai":
                yield sse_event(
                    "progress",
                    {
                        "message": "正在调用 DOM 页面编译/修复 AI。",
                        "stage": "ai_compile",
                        "percent": 45,
                        "mode": payload.mode,
                    },
                )
                app_settings = settings_for_ai_usage(
                    get_settings(),
                    db,
                    AI_USAGE_DOM_COMPILATION,
                )
                preview = compile_dom_module_preview(
                    compile_module,
                    source_text=compile_source.source_text,
                    settings=app_settings,
                )
            else:
                yield sse_event(
                    "progress",
                    {
                        "message": "正在执行系统内静态编译。",
                        "stage": "static_compile",
                        "percent": 45,
                        "mode": payload.mode,
                    },
                )
                preview = static_compile_dom_module_preview(
                    compile_module,
                    source_text=compile_source.source_text,
                )
            preview = {
                **preview,
                "source_file": compile_source.source_file,
                "source_files": compile_source.source_files,
            }

            yield sse_event(
                "progress",
                {
                    "message": "正在写回 DOM 图谱索引。",
                    "stage": "persist",
                    "percent": 80,
                    "mode": payload.mode,
                },
            )
            modules[module_index] = {**module, "preview": preview}
            repository.index_summary = {**summary, "dom_modules": modules}
            db.add(repository)
            db.commit()
            db.refresh(project)
            compiled = project_out(project, db)
            yield sse_event(
                "project",
                {
                    "message": "DOM 模块编译已完成。",
                    "stage": "project",
                    "percent": 100,
                    "mode": payload.mode,
                    "project": compiled.model_dump(mode="json"),
                },
            )
            yield sse_event(
                "done",
                {
                    "message": "DOM 模块编译流式更新完成。",
                    "stage": "done",
                    "percent": 100,
                    "mode": payload.mode,
                },
            )
        except HTTPException as exc:
            db.rollback()
            yield sse_event(
                "error",
                {"message": str(exc.detail), "stage": "request", "status_code": exc.status_code},
            )
        except DomPreviewCompilationError as exc:
            db.rollback()
            yield sse_event(
                "error",
                {"message": str(exc), "stage": "compile", "status_code": 502},
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


def _dom_module_by_id(
    modules: list[dict[str, Any]],
    module_id: str,
) -> tuple[int, dict[str, Any]]:
    for index, module in enumerate(modules):
        if str(module.get("id") or "") == module_id:
            return index, module
    raise HTTPException(status_code=404, detail="DOM 模块不存在，请重新分析项目后再试")
