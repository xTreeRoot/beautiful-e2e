from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha1
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ProjectKnowledgeGraph, Repository

PROJECT_KNOWLEDGE_GRAPH_VERSION = "project_knowledge_graph.v1"
REVIEW_STATUS_DRAFT = "draft"
REVIEW_STATUS_REVIEWED = "reviewed"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_VALUES = {REVIEW_STATUS_DRAFT, REVIEW_STATUS_REVIEWED}
MAX_GRAPH_MODULES = 32
MAX_GRAPH_ROUTES_PER_MODULE = 24
MAX_GRAPH_RELATIONSHIPS = 120


def upsert_candidate_knowledge_graph(
    project_id: str,
    repositories: Sequence[Repository],
    db: Session,
    actor: str | None = "developer",
) -> ProjectKnowledgeGraph:
    """把项目扫描结果固化为待审核知识图谱。

    重新分析项目会刷新候选事实，并把图谱状态重置为草稿。这样可以避免旧的
    人工结论在仓库接口已经变化后继续作为强事实参与生成。
    """

    graph = build_candidate_knowledge_graph(project_id, repositories)
    row = db.scalar(
        select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project_id)
    )
    if row is None:
        row = ProjectKnowledgeGraph(
            project_id=project_id,
            review_status=REVIEW_STATUS_DRAFT,
            graph=graph,
        )
        db.add(row)
    else:
        row.review_status = REVIEW_STATUS_DRAFT
        row.review_notes = None
        row.graph = graph
    db.flush()
    db.add(
        AuditEvent(
            project_id=project_id,
            actor=actor,
            action="project_knowledge_graph.rebuilt",
            entity_type="project_knowledge_graph",
            entity_id=row.id,
            payload={
                "review_status": row.review_status,
                "module_count": len(graph.get("modules") or []),
                "relationship_count": len(graph.get("relationships") or []),
            },
        )
    )
    return row


def build_candidate_knowledge_graph(
    project_id: str,
    repositories: Sequence[Repository],
) -> dict[str, Any]:
    """把仓库级 route analysis 归并为项目级候选事实图谱。"""

    modules: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    route_count = 0
    for repository in repositories:
        summary = repository.index_summary if isinstance(repository.index_summary, dict) else {}
        routes = summary.get("routes") if isinstance(summary.get("routes"), list) else []
        route_count += len(routes)
        analysis = summary.get("analysis") if isinstance(summary.get("analysis"), dict) else {}
        for module in _analysis_list(analysis.get("modules")):
            modules.append(_knowledge_module(repository, module))
        for relationship in _analysis_list(analysis.get("relationships")):
            relationships.append(_knowledge_relationship(repository, relationship))

    modules = modules[:MAX_GRAPH_MODULES]
    relationships = sorted(
        relationships[:MAX_GRAPH_RELATIONSHIPS],
        key=lambda item: float(item.get("confidence") or 0),
        reverse=True,
    )
    return with_review_status(
        {
            "version": PROJECT_KNOWLEDGE_GRAPH_VERSION,
            "project_id": project_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "review": {
                "status": REVIEW_STATUS_DRAFT,
                "fact_strength": "candidate",
                "human_review_required": True,
                "guidance": (
                    "当前图谱来自代码证据的候选归纳。人工审核前只能辅助排序和排除相邻子域，"
                    "不能作为生成 DSL 的强事实。"
                ),
            },
            "summary": {
                "repository_count": len(repositories),
                "route_count": route_count,
                "module_count": len(modules),
                "relationship_count": len(relationships),
            },
            "modules": modules,
            "relationships": relationships,
            "generation_policy": _generation_policy(REVIEW_STATUS_DRAFT),
        },
        REVIEW_STATUS_DRAFT,
    )


def with_review_status(graph: dict[str, Any], review_status: str) -> dict[str, Any]:
    """同步图谱审核状态与生成策略。

    批准整张图谱时，模块、接口和未被人工排除的关系都要一起提升为强事实；
    单条关系的 rejected 状态保留为可审查反例，避免整图批准覆盖人工校正。
    """

    status = normalized_review_status(review_status)
    next_graph = dict(graph)
    review = dict(next_graph.get("review") if isinstance(next_graph.get("review"), dict) else {})
    review.update(
        {
            "status": status,
            "fact_strength": "strong" if status == REVIEW_STATUS_REVIEWED else "candidate",
            "human_review_required": status != REVIEW_STATUS_REVIEWED,
        }
    )
    next_graph["review"] = review
    summary = dict(next_graph.get("summary") if isinstance(next_graph.get("summary"), dict) else {})
    summary["review_status"] = status
    next_graph["summary"] = summary
    next_graph["modules"] = _reviewed_modules(next_graph.get("modules"), status)
    next_graph["relationships"] = _reviewed_relationships(next_graph.get("relationships"), status)
    next_graph["generation_policy"] = _generation_policy(status)
    return next_graph


def normalized_review_status(value: str | None) -> str:
    status = str(value or REVIEW_STATUS_DRAFT).strip().lower()
    return status if status in REVIEW_STATUS_VALUES else REVIEW_STATUS_DRAFT


def reviewed_knowledge_graph_for_project(project_id: str, db: Session) -> dict[str, Any] | None:
    """读取 DSL 生成阶段可作为强事实使用的项目图谱。"""

    row = db.scalar(
        select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project_id)
    )
    if row is None or row.review_status != REVIEW_STATUS_REVIEWED:
        return None
    graph = row.graph if isinstance(row.graph, dict) else {}
    return with_review_status(graph, REVIEW_STATUS_REVIEWED)


def _reviewed_modules(value: Any, review_status: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _reviewed_module(module, review_status)
        for module in value
        if isinstance(module, dict)
    ]


def _reviewed_module(module: dict[str, Any], review_status: str) -> dict[str, Any]:
    next_module = dict(module)
    if review_status == REVIEW_STATUS_REVIEWED and next_module.get("review_status") != REVIEW_STATUS_REJECTED:
        next_module["review_status"] = REVIEW_STATUS_REVIEWED
    routes = next_module.get("routes")
    if isinstance(routes, list):
        next_module["routes"] = [
            _reviewed_route(route, review_status)
            for route in routes
            if isinstance(route, dict)
        ]
    else:
        next_module["routes"] = []
    return next_module


def _reviewed_route(route: dict[str, Any], review_status: str) -> dict[str, Any]:
    next_route = dict(route)
    if review_status == REVIEW_STATUS_REVIEWED and next_route.get("review_status") != REVIEW_STATUS_REJECTED:
        next_route["review_status"] = REVIEW_STATUS_REVIEWED
    return next_route


def _reviewed_relationships(value: Any, review_status: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _reviewed_relationship(relationship, review_status)
        for relationship in value
        if isinstance(relationship, dict)
    ]


def _reviewed_relationship(
    relationship: dict[str, Any],
    review_status: str,
) -> dict[str, Any]:
    next_relationship = dict(relationship)
    if review_status != REVIEW_STATUS_REVIEWED:
        return next_relationship
    if next_relationship.get("review_status") == REVIEW_STATUS_REJECTED:
        next_relationship["confirmed"] = False
        return next_relationship
    next_relationship["review_status"] = REVIEW_STATUS_REVIEWED
    next_relationship["confirmed"] = True
    return next_relationship


def _knowledge_module(repository: Repository, module: dict[str, Any]) -> dict[str, Any]:
    routes = _analysis_list(module.get("routes"))[:MAX_GRAPH_ROUTES_PER_MODULE]
    entrypoints = _analysis_list(module.get("entrypoint_candidates"))
    route_items = [
        _knowledge_route(repository, module, route)
        for route in routes
    ]
    return {
        "id": _module_id(repository, module),
        "source_module_id": module.get("id"),
        "name": module.get("name") or "未归类接口",
        "domain": module.get("domain") or "general",
        "repository_id": repository.id,
        "repository_kind": repository.kind,
        "review_status": module.get("review_status") or REVIEW_STATUS_DRAFT,
        "route_count": module.get("route_count") or len(routes),
        "entrypoint_route_ids": [
            _route_id(repository.kind, route)
            for route in entrypoints
            if isinstance(route, dict)
        ],
        "routes": route_items,
        "scope_boundary": module.get("scope_boundary"),
        "evidence": _string_list(module.get("evidence"), limit=10),
    }


def _knowledge_route(
    repository: Repository,
    module: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    source = str(route.get("source") or "")
    scope_boundary = str(module.get("scope_boundary") or "").strip()
    excluded_scenarios = _string_list(route.get("excluded_scenarios"), limit=8)
    if scope_boundary:
        excluded_scenarios.append(scope_boundary)
    return {
        "id": _route_id(repository.kind, route),
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": route.get("summary"),
        "handler": route.get("handler"),
        "source": source,
        "source_file": _source_file(source),
        "source_line": _source_line(source),
        "role": route.get("role") or "request",
        "produces": _string_list(route.get("produces"), limit=12),
        "consumes": _string_list(route.get("consumes"), limit=12),
        "request_body_fields": _string_list(route.get("request_body_fields"), limit=16),
        "applicable_scenarios": _applicable_scenarios(route),
        "excluded_scenarios": list(dict.fromkeys(excluded_scenarios)),
        "evidence": _string_list(route.get("evidence"), limit=8) or [source],
        "review_status": route.get("review_status") or REVIEW_STATUS_DRAFT,
    }


def _knowledge_relationship(
    repository: Repository,
    relationship: dict[str, Any],
) -> dict[str, Any]:
    from_route = relationship.get("from_route") if isinstance(relationship.get("from_route"), dict) else {}
    to_route = relationship.get("to_route") if isinstance(relationship.get("to_route"), dict) else {}
    return {
        "id": _relationship_id(repository.kind, relationship),
        "type": relationship.get("type") or "variable_flow",
        "variable": relationship.get("variable"),
        "from_route": _route_ref(repository.kind, from_route),
        "to_route": _route_ref(repository.kind, to_route),
        "from_module": _prefixed_module_id(repository.kind, relationship.get("from_module")),
        "to_module": _prefixed_module_id(repository.kind, relationship.get("to_module")),
        "confidence": relationship.get("confidence"),
        "confirmed": bool(relationship.get("confirmed")),
        "reason": relationship.get("reason"),
        "evidence": _string_list(relationship.get("evidence"), limit=8),
        "review_status": REVIEW_STATUS_REVIEWED
        if relationship.get("confirmed")
        else REVIEW_STATUS_DRAFT,
    }


def _route_ref(repository_kind: str, route: dict[str, Any]) -> dict[str, Any]:
    source = str(route.get("source") or "")
    return {
        "id": _route_id(repository_kind, route),
        "method": route.get("method"),
        "path": route.get("path"),
        "summary": route.get("summary"),
        "source": source,
        "source_file": _source_file(source),
        "source_line": _source_line(source),
    }


def _applicable_scenarios(route: dict[str, Any]) -> list[str]:
    configured = _string_list(route.get("applicable_scenarios"), limit=8)
    if configured:
        return configured
    role = str(route.get("role") or "request")
    labels = {
        "discovery": "适合作为搜索、分页、列表或候选实体发现入口。",
        "detail": "适合在已有业务 ID 后读取详情、首页或状态。",
        "action": "适合在前置变量齐备后执行提交、创建或状态变更。",
    }
    return [labels.get(role, "适合在模块边界和路由契约匹配时使用。")]


def _generation_policy(review_status: str) -> dict[str, Any]:
    if review_status == REVIEW_STATUS_REVIEWED:
        return {
            "fact_strength": "strong",
            "route_selection": "DSL 生成必须优先使用已审核模块、入口标记、排除场景和变量流关系。",
            "unreviewed_usage": "未在图谱中的接口仍可作为候选，但必须保留路由证据并说明不确定性。",
        }
    return {
        "fact_strength": "candidate",
        "route_selection": "未审核图谱只能辅助排序、排除明显子域误选，不能覆盖真实路由契约。",
        "unreviewed_usage": "生成 DSL 时必须把候选事实写入 route_decision 或 missing_upstream_steps，等待人工复查。",
    }


def _analysis_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value[:limit] if str(item).strip()]


def _module_id(repository: Repository, module: dict[str, Any]) -> str:
    return _prefixed_module_id(repository.kind, module.get("id"))


def _prefixed_module_id(repository_kind: str, module_id: Any) -> str:
    return f"{_slug(repository_kind)}_{_slug(str(module_id or 'module_general'))}"


def _route_id(repository_kind: str, route: dict[str, Any]) -> str:
    method = str(route.get("method") or "GET").upper()
    path = str(route.get("path") or "/")
    digest = sha1(f"{repository_kind}:{method}:{path}".encode("utf-8")).hexdigest()[:12]
    return f"route_{digest}"


def _relationship_id(repository_kind: str, relationship: dict[str, Any]) -> str:
    from_route = relationship.get("from_route") if isinstance(relationship.get("from_route"), dict) else {}
    to_route = relationship.get("to_route") if isinstance(relationship.get("to_route"), dict) else {}
    key = ":".join(
        [
            repository_kind,
            str(relationship.get("variable") or ""),
            str(from_route.get("path") or ""),
            str(to_route.get("path") or ""),
        ]
    )
    return f"rel_{sha1(key.encode('utf-8')).hexdigest()[:12]}"


def _source_file(source: str) -> str | None:
    if not source:
        return None
    return source.rsplit(":", 1)[0]


def _source_line(source: str) -> int | None:
    if not source or ":" not in source:
        return None
    raw = source.rsplit(":", 1)[1]
    return int(raw) if raw.isdigit() else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return slug or "item"
