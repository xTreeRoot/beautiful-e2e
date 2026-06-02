from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.api.common import first_group_id, load_case, load_group
from app.models import AuditEvent, Repository, TestCase, TestStep
from app.schemas import GenerateCaseRequest
from app.services.ai_case_generator import GeneratedCase
from app.services.repo_reader import RepoReader, RepoSummary


def target_case_for_generation(
    project_id: str,
    payload: GenerateCaseRequest,
    db: Session,
) -> TestCase | None:
    """校验重新生成目标用例，确保跨项目请求不会误写数据。"""
    if not payload.target_case_id:
        return None
    case = load_case(payload.target_case_id, db)
    if case.project_id != project_id:
        raise HTTPException(status_code=400, detail="目标用例不属于当前项目")
    return case


def group_id_for_generation(
    project_id: str,
    payload: GenerateCaseRequest,
    target_case: TestCase | None,
    db: Session,
) -> str | None:
    """确定生成结果的分组归属，重新生成默认沿用原用例分组。

    `group_id` 显式传入 null 时表示移动到未分组；完全未传时，重新生成保留
    原分组，新建生成沿用历史行为放入第一个分组。
    """
    if payload.group_id is not None:
        return case_group_id_for_project(project_id, payload.group_id, db)
    if target_case is not None:
        if "group_id" in payload.model_fields_set:
            return None
        return target_case.group_id
    return first_group_id(project_id, db)


def save_generated_case(
    *,
    project_id: str,
    payload: GenerateCaseRequest,
    generated: GeneratedCase,
    group_id: str | None,
    execution_mode: str,
    target_case: TestCase | None,
    db: Session,
) -> TestCase:
    """把生成结果写入用例、步骤和审计记录。

    调用方负责统一提交事务；这里只维护同一个业务动作内的 ORM 状态，避免路由
    函数同时关心字段覆盖规则和步骤关系刷新。
    """
    title_override = payload.title.strip() if payload.title and payload.title.strip() else None
    description_override = (payload.case_description or "").strip()
    action = "case.regenerated" if target_case is not None else "case.generated"

    if target_case is None:
        case = TestCase(
            project_id=project_id,
            group_id=group_id,
            title=title_override or generated.title,
            description=description_override or generated.description,
            priority=generated.priority,
            source_prompt=payload.description,
            created_by=payload.created_by,
            code_context=generated.code_context,
            graph=generated.graph,
        )
        db.add(case)
        db.flush()
    else:
        case = target_case
        case.group_id = group_id
        case.title = title_override or case.title
        case.description = description_override or generated.description
        case.priority = payload.priority or case.priority or generated.priority
        case.source_prompt = payload.description
        case.created_by = payload.created_by or case.created_by
        case.code_context = generated.code_context
        case.graph = generated.graph
        # 重新生成后旧 Playwright spec 已经不能代表当前步骤，避免界面继续引用旧产物。
        case.playwright_spec_path = None
        case.steps.clear()
        db.flush()

    for index, step in enumerate(generated.steps, start=1):
        # 重新生成接口会在同一个 Session 里立即序列化返回值；直接维护关系集合，
        # 避免 identity map 保留旧 steps，导致前端必须刷新页面才读到新 DSL。
        case.steps.append(
            TestStep(
                order_index=index,
                kind=step.kind,
                label=step.label,
                action=step.action,
                selector=step.selector,
                target_url=step.target_url,
                value=step.value,
                expected=step.expected,
                data=step.data,
            )
        )

    code_context = generated.code_context or {}
    db.add(
        AuditEvent(
            project_id=project_id,
            actor=payload.created_by,
            action=action,
            entity_type="test_case",
            entity_id=case.id,
            payload={
                "group_id": group_id,
                "execution_mode": execution_mode,
                "mode": code_context.get("generation_mode", "natural_language"),
                "target_case_id": target_case.id if target_case is not None else None,
            },
        )
    )
    return case


def case_group_id_for_project(project_id: str, group_id: str | None, db: Session) -> str | None:
    if group_id is None:
        return None
    group = load_group(group_id, db)
    if group.project_id != project_id:
        raise HTTPException(status_code=400, detail="分组不属于当前项目")
    return group.id


def effective_execution_mode(selected_mode: str, prompt: str) -> str:
    """把项目选择的执行模式作为真实依据。

    在后端接口模式下，“客户端流程”这类表述通常指客户端实际使用的接口链路，
    而不是浏览器自动化。这里切换模式会悄悄把接口流程请求变成页面步骤。
    """
    return selected_mode


def repo_summary_for_generation(
    project_id: str,
    kind: str,
    raw_path: str | None,
    reader: RepoReader,
    db: Session,
) -> RepoSummary:
    """按项目仓库缓存、本次显式路径和 workspace 摘要选择生成上下文。"""
    repo = db.scalar(
        select(Repository).where(Repository.project_id == project_id, Repository.kind == kind)
    )
    if repo is not None and repo.index_summary and (not raw_path or raw_path == repo.path):
        return RepoSummary.from_dict(repo.index_summary)

    if raw_path:
        return reader.summarize(raw_path)

    workspace = db.scalar(
        select(Repository).where(Repository.project_id == project_id, Repository.kind == "workspace")
    )
    if workspace is not None and workspace.index_summary:
        return RepoSummary.from_dict(workspace.index_summary)

    return reader.summarize(None)
