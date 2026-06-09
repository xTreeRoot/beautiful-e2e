from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, delete, select, update
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AgentProfile,
    AuditEvent,
    CaseComment,
    Project,
    ProjectEnvironmentConfig,
    ProjectKnowledgeGraph,
    Repository,
    SkillProfile,
    TestCase,
    TestGroup,
    TestRun,
    TestRunResult,
    TestStep,
)
from app.schemas import BootstrapOut, ProjectOut

DEFAULT_GROUPS = [
    ("核心链路组", "登录、提交、发布、删除等阻断发布的核心流程。", 10),
    ("浏览组", "只读浏览、列表、详情和搜索覆盖。", 20),
    ("回归冒烟组", "每次构建都要快速通过的信心检查。", 30),
    ("异常路径组", "权限、校验、超时和错误恢复用例。", 40),
]

DEFAULT_PROJECT_SETTINGS: dict[str, Any] = {
    "execution_mode": "fullstack",
    "frontend_repo_path": "",
    "backend_repo_path": "",
    "workspace_path": "",
    "active_environment": "local",
    "active_frontend_environment": "local",
    "active_api_environment": "local",
    "base_url": "http://localhost:5173",
    "api_base_url": "http://localhost:8000",
}

DEFAULT_ENVIRONMENT_CONFIGS: list[dict[str, Any]] = [
    {
        "key": "local",
        "name": "本地",
        "base_url": "http://localhost:5173",
        "api_base_url": "http://localhost:8000",
        "request_headers": {},
    },
    {"key": "dev", "name": "开发", "base_url": "", "api_base_url": "", "request_headers": {}},
    {"key": "test", "name": "测试", "base_url": "", "api_base_url": "", "request_headers": {}},
    {"key": "staging", "name": "预发", "base_url": "", "api_base_url": "", "request_headers": {}},
    {"key": "prod", "name": "生产", "base_url": "", "api_base_url": "", "request_headers": {}},
]


def require_project(project_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def workspace_out(project_id: str, db: Session) -> BootstrapOut:
    project = require_project(project_id, db)
    projects = db.scalars(ordered_projects_query()).all()
    groups = db.scalars(
        select(TestGroup).where(TestGroup.project_id == project.id).order_by(TestGroup.sort_order)
    ).all()
    return BootstrapOut(
        project=project_out(project, db),
        projects=[project_out(item, db) for item in projects],
        groups=list(groups),
    )


def ensure_project_defaults(project_id: str, db: Session) -> None:
    """为新项目创建一次内置分组。

    已存在项目不能在工作区加载时重新补种，否则用户删除内置分组后会被恢复。
    旧本地数据库可能因为多次启动留下重复种子数据，因此这里在补种后按分组名去重。
    """
    for name, description, order in DEFAULT_GROUPS:
        group = db.scalar(
            select(TestGroup).where(TestGroup.project_id == project_id, TestGroup.name == name)
        )
        if group is None:
            db.add(
                TestGroup(
                    project_id=project_id,
                    name=name,
                    description=description,
                    sort_order=order,
                )
            )

    db.flush()
    dedupe_named_rows(project_id, db, TestGroup)


def dedupe_named_rows(project_id: str, db: Session, model: type[Any]) -> None:
    rows = list(
        db.scalars(
            select(model).where(model.project_id == project_id).order_by(model.created_at, model.id)
        ).all()
    )
    seen: set[str] = set()
    for row in rows:
        if row.name in seen:
            db.delete(row)
        else:
            seen.add(row.name)


def delete_project_dependents(project_id: str, db: Session) -> None:
    """删除项目前，按依赖顺序删除项目拥有的数据行。"""
    case_ids = list(db.scalars(select(TestCase.id).where(TestCase.project_id == project_id)).all())
    run_ids = list(db.scalars(select(TestRun.id).where(TestRun.project_id == project_id)).all())

    if run_ids:
        db.execute(delete(TestRunResult).where(TestRunResult.run_id.in_(run_ids)))
    if case_ids:
        db.execute(delete(TestRunResult).where(TestRunResult.case_id.in_(case_ids)))
        db.execute(delete(CaseComment).where(CaseComment.case_id.in_(case_ids)))
        db.execute(delete(TestStep).where(TestStep.case_id.in_(case_ids)))

    db.execute(delete(TestRun).where(TestRun.project_id == project_id))
    db.execute(delete(TestCase).where(TestCase.project_id == project_id))
    db.execute(delete(TestGroup).where(TestGroup.project_id == project_id))
    db.execute(delete(ProjectEnvironmentConfig).where(ProjectEnvironmentConfig.project_id == project_id))
    db.execute(delete(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project_id))
    db.execute(delete(Repository).where(Repository.project_id == project_id))
    db.execute(delete(AgentProfile).where(AgentProfile.project_id == project_id))
    db.execute(delete(SkillProfile).where(SkillProfile.project_id == project_id))
    db.execute(delete(AuditEvent).where(AuditEvent.project_id == project_id))


def delete_case_dependents(case_id: str, db: Session) -> None:
    db.execute(delete(TestRunResult).where(TestRunResult.case_id == case_id))
    db.execute(delete(CaseComment).where(CaseComment.case_id == case_id))
    db.execute(delete(TestStep).where(TestStep.case_id == case_id))
    db.execute(
        delete(AuditEvent).where(AuditEvent.entity_type == "test_case", AuditEvent.entity_id == case_id)
    )


def project_out(project: Project, db: Session) -> ProjectOut:
    description, settings = read_project_meta(project)
    settings = project_settings_with_repositories(project, db, settings)
    repositories = _ordered_project_repositories(project.id, db)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=description,
        is_current=bool(project.is_current),
        settings=settings,
        repositories=[
            {
                "id": repo.id,
                "project_id": repo.project_id,
                "name": repo.name,
                "kind": repo.kind,
                "path": repo.path,
                "index_summary": repo.index_summary,
                "created_at": repo.created_at,
                "updated_at": repo.updated_at,
            }
            for repo in repositories
        ],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _ordered_project_repositories(project_id: str, db: Session) -> list[Repository]:
    """读取项目仓库并按响应契约排序。

    `index_summary` 会保存仓库扫描后的大 JSON。MySQL 对这类行做 filesort 时容易触发
    sort buffer 限制，所以这里避免数据库排序，改在通常只有少量仓库行的应用层排序。
    """
    repositories = list(db.scalars(select(Repository).where(Repository.project_id == project_id)).all())
    return sorted(
        repositories,
        key=lambda repo: (
            repo.kind,
            repo.created_at.isoformat() if repo.created_at else "",
            repo.id,
        ),
    )


def ordered_projects_query() -> Select[tuple[Project]]:
    return select(Project).order_by(
        Project.is_current.desc(), Project.updated_at.desc(), Project.created_at.desc()
    )


def mark_project_current(project_id: str, db: Session) -> None:
    db.execute(update(Project).values(is_current=False))
    db.execute(update(Project).where(Project.id == project_id).values(is_current=True))


def read_project_meta(project: Project) -> tuple[str | None, dict[str, Any]]:
    if not project.description:
        return None, dict(DEFAULT_PROJECT_SETTINGS)
    try:
        meta = json.loads(project.description)
    except json.JSONDecodeError:
        return project.description, dict(DEFAULT_PROJECT_SETTINGS)
    if not isinstance(meta, dict) or "settings" not in meta:
        return project.description, dict(DEFAULT_PROJECT_SETTINGS)
    description = meta.get("description")
    settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
    return (str(description) if description is not None else None), {
        **DEFAULT_PROJECT_SETTINGS,
        **settings,
    }


def write_project_meta(
    project: Project,
    description: str | None,
    settings: dict[str, Any] | None,
) -> None:
    project.description = json.dumps(
        {
            "description": description,
            "settings": {**DEFAULT_PROJECT_SETTINGS, **(settings or {})},
        },
        ensure_ascii=False,
    )


def project_settings_with_repositories(
    project: Project,
    db: Session,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {**DEFAULT_PROJECT_SETTINGS, **(settings or {})}
    repositories = db.scalars(select(Repository).where(Repository.project_id == project.id)).all()
    for repo in repositories:
        if repo.kind == "workspace":
            merged["workspace_path"] = repo.path
        if repo.kind == "frontend":
            merged["frontend_repo_path"] = repo.path
        if repo.kind == "backend":
            merged["backend_repo_path"] = repo.path
    return project_settings_with_environments(project.id, merged, db)


def project_settings_with_environments(
    project_id: str,
    settings: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    """把规范化后的环境行合并进项目设置契约。"""

    rows = list(
        db.scalars(
            select(ProjectEnvironmentConfig)
            .where(ProjectEnvironmentConfig.project_id == project_id)
            .order_by(ProjectEnvironmentConfig.sort_order, ProjectEnvironmentConfig.env_key)
        ).all()
    )
    environments = (
        [environment_row_to_settings(row) for row in rows]
        if rows
        else normalize_environment_payload(settings)
    )
    merged = {**settings, "environments": environments}
    frontend_key = _active_environment_key(
        environments,
        merged.get("active_frontend_environment") or merged.get("active_environment"),
    )
    api_key = _active_environment_key(
        environments,
        merged.get("active_api_environment")
        or merged.get("active_backend_environment")
        or merged.get("active_environment"),
    )
    frontend_env = next((item for item in environments if item["key"] == frontend_key), environments[0])
    api_env = next((item for item in environments if item["key"] == api_key), environments[0])
    merged["active_frontend_environment"] = frontend_key
    merged["active_api_environment"] = api_key
    merged["active_environment"] = frontend_key if frontend_key == api_key else f"{frontend_key}/{api_key}"
    merged["base_url"] = frontend_env.get("base_url") or ""
    merged["api_base_url"] = api_env.get("api_base_url") or ""
    return merged


def sync_project_environments(project_id: str, settings: dict[str, Any], db: Session) -> None:
    """把设置里的环境载荷持久化为项目拥有的环境行。"""

    environments = normalize_environment_payload(settings)
    existing = {
        row.env_key: row
        for row in db.scalars(
            select(ProjectEnvironmentConfig).where(ProjectEnvironmentConfig.project_id == project_id)
        ).all()
    }
    for index, environment in enumerate(environments):
        row = existing.pop(environment["key"], None)
        if row is None:
            row = ProjectEnvironmentConfig(project_id=project_id, env_key=environment["key"])
            db.add(row)
        row.name = environment["name"]
        row.frontend_base_url = environment.get("base_url") or ""
        row.api_base_url = environment.get("api_base_url") or ""
        row.request_headers = _json_object(environment.get("request_headers"), "request_headers")
        row.request_variables = {}
        row.sort_order = index
    for stale_row in existing.values():
        db.delete(stale_row)
    settings["environments"] = environments


def normalize_environment_payload(settings: dict[str, Any]) -> list[dict[str, Any]]:
    raw_environments = settings.get("environments")
    source = raw_environments if isinstance(raw_environments, list) else DEFAULT_ENVIRONMENT_CONFIGS
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_environment in enumerate(source):
        if not isinstance(raw_environment, dict):
            continue
        default = DEFAULT_ENVIRONMENT_CONFIGS[index] if index < len(DEFAULT_ENVIRONMENT_CONFIGS) else {}
        key = str(raw_environment.get("key") or raw_environment.get("id") or default.get("key") or f"env-{index + 1}")
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "key": key,
                "name": str(raw_environment.get("name") or raw_environment.get("label") or default.get("name") or key),
                "base_url": str(raw_environment.get("base_url") or raw_environment.get("baseUrl") or default.get("base_url") or ""),
                "api_base_url": str(raw_environment.get("api_base_url") or raw_environment.get("apiBaseUrl") or default.get("api_base_url") or ""),
                "request_headers": _json_object(
                    _first_present(raw_environment, "request_headers", "headers"),
                    "request_headers",
                ),
            }
        )
    if not normalized:
        normalized = [dict(DEFAULT_ENVIRONMENT_CONFIGS[0])]
    return normalized


def environment_row_to_settings(row: ProjectEnvironmentConfig) -> dict[str, Any]:
    return {
        "key": row.env_key,
        "name": row.name,
        "base_url": row.frontend_base_url or "",
        "api_base_url": row.api_base_url or "",
        "request_headers": _json_object(row.request_headers, "request_headers", strict=False),
    }


def _active_environment_key(environments: list[dict[str, Any]], raw_key: Any) -> str:
    keys = {str(environment["key"]) for environment in environments}
    key = str(raw_key or "local")
    return key if key in keys else str(environments[0]["key"])


def _first_present(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


def _json_object(value: Any, field_name: str, *, strict: bool = True) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value.strip() or "{}")
        except json.JSONDecodeError as exc:
            if not strict:
                return {}
            raise HTTPException(status_code=400, detail=f"{field_name} 必须是 JSON 对象") from exc
    if isinstance(value, dict):
        return value
    if not strict:
        return {}
    raise HTTPException(status_code=400, detail=f"{field_name} 必须是 JSON 对象")


def upsert_repository(project_id: str, kind: str, path: str, db: Session) -> None:
    repo = db.scalar(
        select(Repository).where(Repository.project_id == project_id, Repository.kind == kind)
    )
    clean_path = path.strip()
    if not clean_path:
        if repo is not None:
            db.delete(repo)
        return

    name = Path(clean_path).name or kind
    if repo is None:
        db.add(
            Repository(
                project_id=project_id,
                name=name,
                kind=kind,
                path=clean_path,
                index_summary=None,
            )
        )
    else:
        repo.name = name
        repo.path = clean_path


def unique_project_name(name: str, db: Session, exclude_id: str | None = None) -> str:
    base = name.strip() or "本地项目"
    candidate = base[:120]
    index = 2
    while True:
        query = select(Project).where(Project.name == candidate)
        if exclude_id:
            query = query.where(Project.id != exclude_id)
        exists = db.scalar(query)
        if exists is None:
            return candidate
        suffix = f" {index}"
        candidate = f"{base[:120 - len(suffix)]}{suffix}"
        index += 1


def readable_project_name(raw_name: str) -> str:
    words = [word for word in re.split(r"[-_\s]+", raw_name.strip()) if word]
    if not words:
        return "本地项目"
    return " ".join(word[:1].upper() + word[1:] for word in words)[:120]


def first_group_id(project_id: str, db: Session) -> str | None:
    group = db.scalar(
        select(TestGroup).where(TestGroup.project_id == project_id).order_by(TestGroup.sort_order)
    )
    return group.id if group else None


def load_group(group_id: str, db: Session) -> TestGroup:
    group = db.get(TestGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="分组不存在")
    return group


def load_case(case_id: str, db: Session) -> TestCase:
    case = db.scalar(
        select(TestCase)
        .options(selectinload(TestCase.steps), selectinload(TestCase.group))
        .where(TestCase.id == case_id)
    )
    if case is None:
        raise HTTPException(status_code=404, detail="用例不存在")
    return case
