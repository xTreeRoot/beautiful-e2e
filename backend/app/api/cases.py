from __future__ import annotations

from collections.abc import Iterator
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.common import (
    delete_case_dependents,
    load_case,
    load_group,
    project_settings_with_repositories,
    require_project,
)
from app.api.sse import sse_event
from app.api.case_generation_helpers import (
    case_group_id_for_project as _case_group_id_for_project,
    effective_execution_mode as _effective_execution_mode,
    group_id_for_generation as _group_id_for_generation,
    repo_summary_for_generation as _repo_summary_for_generation,
    save_generated_case as _save_generated_case,
    target_case_for_generation as _target_case_for_generation,
)
from app.api.case_run_environment import project_settings_for_case_run
from app.core.config import get_settings
from app.db import get_db
from app.models import AuditEvent, TestCase, TestStep
from app.schemas import (
    CaseCreate,
    CaseGraphUpdate,
    CaseRunRequest,
    CaseRunStepOverride,
    CaseOut,
    CaseUpdate,
    GenerateCaseRequest,
    GraphOut,
    PlaywrightExportOut,
)
from app.services.ai import (
    CaseGenerationContext,
    CaseGenerationError,
    generate_case_with_provider,
    stream_case_with_provider,
)
from app.services.ai_settings import (
    AI_USAGE_API_RUNTIME,
    AI_USAGE_DSL_GENERATION,
    settings_for_ai_usage,
)
from app.services.api_flow_runtime_agent import (
    ApiFlowResponseHistory,
    RuntimeVariableInference,
    build_api_flow_runtime_agent,
)
from app.services.api_flow_variables import MissingApiFlowVariableError
from app.services.ai_case_generator import GeneratedCase
from app.services.browser_case_runner import BrowserCaseRunner
from app.services.case_runner import ApiCaseRunner
from app.services.generation_context import build_generation_context
from app.services.playwright_emitter import PlaywrightEmitter
from app.services.project_llm_context import build_project_llm_context
from app.services.prompt_references import PromptReferenceReader
from app.services.project_environments import active_environment_settings
from app.services.repo_reader import RepoReader

router = APIRouter(tags=["cases"])

PROVIDER_WAIT_MESSAGES = [
    "生成供应商仍在处理，保持流式连接。",
    "继续等待结构化用例结果，已保留当前请求上下文。",
    "供应商仍在推理步骤和断言，完成后会立即写入工作台。",
    "长耗时生成仍在进行，流式连接正常。",
]


@router.get("/projects/{project_id}/cases", response_model=list[CaseOut])
def list_cases(
    project_id: str,
    group_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TestCase]:
    require_project(project_id, db)
    filters = [TestCase.project_id == project_id]
    if group_id:
        filters.append(TestCase.group_id == group_id)

    # MySQL 对包含大 JSON 字段的整行排序可能超过排序内存。
    # 先只排序轻量 id，再加载 ORM 行，并在 Python 中保持同样顺序。
    case_ids = list(
        db.scalars(
            select(TestCase.id)
            .where(*filters)
            .order_by(TestCase.created_at.desc(), TestCase.id.desc())
        ).all()
    )
    if not case_ids:
        return []

    cases = list(
        db.scalars(
            select(TestCase)
            .options(selectinload(TestCase.steps), selectinload(TestCase.group))
            .where(TestCase.id.in_(case_ids))
        ).all()
    )
    cases_by_id = {case.id: case for case in cases}
    return [cases_by_id[case_id] for case_id in case_ids if case_id in cases_by_id]


@router.post("/projects/{project_id}/cases", response_model=CaseOut)
def create_case(project_id: str, payload: CaseCreate, db: Session = Depends(get_db)) -> TestCase:
    require_project(project_id, db)
    group_id = _case_group_id_for_project(project_id, payload.group_id, db)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="用例标题不能为空")
    description = (payload.description or "").strip() or title
    case = TestCase(
        project_id=project_id,
        group_id=group_id,
        title=title,
        description=description,
        priority=payload.priority,
        status=payload.status,
        source_prompt=description,
        created_by=payload.created_by,
        code_context={"generation_mode": "manual"},
        graph={"nodes": [], "edges": []},
    )
    db.add(case)
    db.flush()
    db.add(
        AuditEvent(
            project_id=project_id,
            actor=payload.created_by,
            action="case.created",
            entity_type="test_case",
            entity_id=case.id,
            payload={"group_id": group_id, "mode": "blank"},
        )
    )
    db.commit()
    return load_case(case.id, db)


@router.post("/projects/{project_id}/cases/generate", response_model=CaseOut)
def generate_case(
    project_id: str,
    payload: GenerateCaseRequest,
    db: Session = Depends(get_db),
) -> TestCase:
    project = require_project(project_id, db)
    target_case = _target_case_for_generation(project_id, payload, db)
    group_id = _group_id_for_generation(project_id, payload, target_case, db)
    settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_DSL_GENERATION)
    reader = RepoReader(max_files=settings.workspace_scan_max_files)
    reference_documents = PromptReferenceReader().collect(payload.description)
    execution_mode = _effective_execution_mode(payload.execution_mode, payload.description)
    project_settings = project_settings_with_repositories(project, db)
    frontend = _repo_summary_for_generation(
        project_id,
        "frontend",
        payload.frontend_repo_path or project_settings.get("frontend_repo_path"),
        reader,
        db,
    )
    backend = _repo_summary_for_generation(
        project_id,
        "backend",
        payload.backend_repo_path or project_settings.get("backend_repo_path"),
        reader,
        db,
    )
    generation_context = build_generation_context(
        project_id=project_id,
        execution_mode=execution_mode,
        agent_id=payload.agent_id,
        skill_ids=payload.skill_ids,
        db=db,
    )
    project_llm_context = build_project_llm_context(
        project_id,
        project_settings,
        db,
        repository_summaries={"frontend": frontend, "backend": backend},
    )
    provider_context = CaseGenerationContext(
        prompt=payload.description,
        frontend=frontend,
        backend=backend,
        priority=payload.priority,
        agent=generation_context.agent,
        skills=generation_context.skills,
        canvas_dsl=payload.canvas_dsl,
        execution_mode=execution_mode,
        reference_documents=[document.as_dict() for document in reference_documents],
        project_context=project_llm_context,
        auth_context=project_llm_context["auth"],
    )
    try:
        generated = generate_case_with_provider(settings, provider_context)
    except CaseGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    case = _save_generated_case(
        project_id=project_id,
        payload=payload,
        generated=generated,
        group_id=group_id,
        execution_mode=provider_context.execution_mode,
        target_case=target_case,
        db=db,
    )
    db.commit()

    return load_case(case.id, db)


@router.post("/projects/{project_id}/cases/generate/stream")
def generate_case_stream(
    project_id: str,
    payload: GenerateCaseRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """通过 SSE 流生成用例，让界面展示真实后端进度。"""

    def events() -> Iterator[str]:
        try:
            yield sse_event(
                "start",
                {
                    "message": "收到生成请求，开始准备项目上下文。",
                    "stage": "start",
                },
            )
            project = require_project(project_id, db)
            target_case = _target_case_for_generation(project_id, payload, db)
            group_id = _group_id_for_generation(project_id, payload, target_case, db)

            settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_DSL_GENERATION)
            reader = RepoReader(max_files=settings.workspace_scan_max_files)
            execution_mode = _effective_execution_mode(payload.execution_mode, payload.description)
            yield sse_event(
                "progress",
                {
                    "message": f"执行模式已确定：{execution_mode}。",
                    "stage": "execution_mode",
                    "execution_mode": execution_mode,
                },
            )

            yield sse_event(
                "progress",
                {
                    "message": "扫描提示词中引用的执行文档和需求材料。",
                    "stage": "references",
                },
            )
            reference_documents = PromptReferenceReader().collect(payload.description)
            if reference_documents:
                yield sse_event(
                    "progress",
                    {
                        "message": f"已读取 {len(reference_documents)} 份引用文档。",
                        "stage": "references",
                        "count": len(reference_documents),
                    },
                )

            project_settings = project_settings_with_repositories(project, db)
            yield sse_event(
                "progress",
                {
                    "message": "读取前端仓库摘要。",
                    "stage": "frontend_context",
                },
            )
            frontend = _repo_summary_for_generation(
                project_id,
                "frontend",
                payload.frontend_repo_path or project_settings.get("frontend_repo_path"),
                reader,
                db,
            )

            yield sse_event(
                "progress",
                {
                    "message": "读取后端仓库摘要和接口目录。",
                    "stage": "backend_context",
                },
            )
            backend = _repo_summary_for_generation(
                project_id,
                "backend",
                payload.backend_repo_path or project_settings.get("backend_repo_path"),
                reader,
                db,
            )

            yield sse_event(
                "progress",
                {
                    "message": "构建生成上下文和可用技能。",
                    "stage": "generation_context",
                },
            )
            generation_context = build_generation_context(
                project_id=project_id,
                execution_mode=execution_mode,
                agent_id=payload.agent_id,
                skill_ids=payload.skill_ids,
                db=db,
            )
            project_llm_context = build_project_llm_context(
                project_id,
                project_settings,
                db,
                repository_summaries={"frontend": frontend, "backend": backend},
            )
            provider_context = CaseGenerationContext(
                prompt=payload.description,
                frontend=frontend,
                backend=backend,
                priority=payload.priority,
                agent=generation_context.agent,
                skills=generation_context.skills,
                canvas_dsl=payload.canvas_dsl,
                execution_mode=execution_mode,
                reference_documents=[document.as_dict() for document in reference_documents],
                project_context=project_llm_context,
                auth_context=project_llm_context["auth"],
            )

            yield sse_event(
                "progress",
                {
                    "message": "调用生成供应商生成结构化用例。",
                    "stage": "provider",
                },
            )
            provider_queue: Queue[GeneratedCase | dict[str, Any] | BaseException] = Queue()

            def run_provider() -> None:
                try:
                    for provider_event in stream_case_with_provider(settings, provider_context):
                        if provider_event.get("type") == "generated_case":
                            generated_case = provider_event.get("case")
                            if not isinstance(generated_case, GeneratedCase):
                                raise CaseGenerationError("供应商流式生成未返回有效用例")
                            provider_queue.put(generated_case)
                            continue
                        provider_queue.put(provider_event)
                except BaseException as exc:
                    provider_queue.put(exc)

            Thread(target=run_provider, daemon=True).start()
            wait_index = 0
            while True:
                try:
                    provider_result = provider_queue.get(timeout=3)
                    if isinstance(provider_result, BaseException):
                        raise provider_result
                    if isinstance(provider_result, dict):
                        event_type = str(provider_result.get("type") or "progress")
                        event_payload = {
                            key: value
                            for key, value in provider_result.items()
                            if key != "type"
                        }
                        yield sse_event(event_type, event_payload)
                        continue
                    generated = provider_result
                    break
                except Empty:
                    message = PROVIDER_WAIT_MESSAGES[wait_index % len(PROVIDER_WAIT_MESSAGES)]
                    wait_index += 1
                    yield sse_event(
                        "progress",
                        {
                            "message": message,
                            "stage": "provider_wait",
                            "elapsed_seconds": wait_index * 3,
                        },
                    )

            yield sse_event(
                "progress",
                {
                    "message": "生成完成，正在写入用例、步骤和审计记录。",
                    "stage": "persist",
                },
            )
            case = _save_generated_case(
                project_id=project_id,
                payload=payload,
                generated=generated,
                group_id=group_id,
                execution_mode=provider_context.execution_mode,
                target_case=target_case,
                db=db,
            )
            db.commit()

            loaded = load_case(case.id, db)
            yield sse_event(
                "case",
                {
                    "message": f"用例已生成：{loaded.title}",
                    "stage": "case",
                    "case": CaseOut.model_validate(loaded).model_dump(mode="json"),
                },
            )
            yield sse_event("done", {"message": "流式生成完成。", "stage": "done"})
        except CaseGenerationError as exc:
            db.rollback()
            yield sse_event(
                "error",
                {"message": str(exc), "stage": "provider", "status_code": 502},
            )
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


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: str, db: Session = Depends(get_db)) -> TestCase:
    return load_case(case_id, db)


@router.put("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: str, payload: CaseUpdate, db: Session = Depends(get_db)) -> TestCase:
    case = load_case(case_id, db)
    if payload.group_id is not None:
        group = load_group(payload.group_id, db)
        if group.project_id != case.project_id:
            raise HTTPException(status_code=400, detail="分组不属于当前项目")
        case.group_id = group.id
    elif "group_id" in payload.model_fields_set:
        case.group_id = None
    if payload.title is not None:
        case.title = payload.title
    if "description" in payload.model_fields_set and payload.description is not None:
        case.description = payload.description
    if payload.priority is not None:
        case.priority = payload.priority
    if payload.status is not None:
        case.status = payload.status
    db.commit()
    return load_case(case.id, db)


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    case = load_case(case_id, db)
    delete_case_dependents(case.id, db)
    db.delete(case)
    db.commit()
    return {"id": case_id, "status": "deleted"}


@router.get("/cases/{case_id}/graph", response_model=GraphOut)
def get_case_graph(case_id: str, db: Session = Depends(get_db)) -> dict[str, list[dict[str, Any]]]:
    case = load_case(case_id, db)
    graph = case.graph or {"nodes": [], "edges": []}
    return {"nodes": graph.get("nodes", []), "edges": graph.get("edges", [])}


@router.put("/cases/{case_id}/graph", response_model=CaseOut)
def update_case_graph(
    case_id: str,
    payload: CaseGraphUpdate,
    db: Session = Depends(get_db),
) -> TestCase:
    case = load_case(case_id, db)
    case.graph = payload.graph
    context = dict(case.code_context or {})
    if payload.execution_mode:
        context["execution_mode"] = payload.execution_mode
        case.code_context = context
    if "source_prompt" in payload.model_fields_set:
        case.source_prompt = (payload.source_prompt or "").strip()
    case.steps.clear()
    db.flush()

    for index, item in enumerate(payload.steps, start=1):
        db.add(
            TestStep(
                case_id=case.id,
                order_index=index,
                kind=str(item.get("kind") or "action"),
                label=str(item.get("label") or f"步骤 {index}"),
                action=item.get("action"),
                selector=item.get("selector"),
                target_url=item.get("target_url"),
                value=item.get("value"),
                expected=item.get("expected"),
                data=item.get("data") if isinstance(item.get("data"), dict) else None,
            )
        )

    db.add(
        AuditEvent(
            project_id=case.project_id,
            actor=payload.actor,
            action="case.graph_updated",
            entity_type="test_case",
            entity_id=case.id,
            payload={
                "nodes": len(payload.graph.get("nodes", [])),
                "edges": len(payload.graph.get("edges", [])),
            },
        )
    )
    db.commit()
    return load_case(case.id, db)


@router.post("/cases/{case_id}/emit-playwright", response_model=PlaywrightExportOut)
def emit_playwright(case_id: str, db: Session = Depends(get_db)) -> PlaywrightExportOut:
    case = load_case(case_id, db)
    emitter = _playwright_emitter_for_case(case, db)
    path, content = emitter.emit(case)
    case.playwright_spec_path = str(path)
    db.add(
        AuditEvent(
            project_id=case.project_id,
            actor=case.created_by,
            action="case.playwright_emitted",
            entity_type="test_case",
            entity_id=case.id,
            payload={"path": str(path)},
        )
    )
    db.commit()
    return PlaywrightExportOut(case_id=case.id, spec_path=str(path), content=content)


@router.post("/cases/{case_id}/run/backend-api/stream")
def run_backend_api_case_stream(
    case_id: str,
    payload: CaseRunRequest = Body(default_factory=CaseRunRequest),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """流式执行后端接口用例，让前端逐步展示真实请求结果。"""

    case = load_case(case_id, db)
    project = require_project(case.project_id, db)
    project_settings = project_settings_for_case_run(
        project_settings_with_repositories(project, db),
        payload,
    )
    environment_settings = active_environment_settings(project_settings)
    runner = ApiCaseRunner(
        api_base_url=environment_settings["api_base_url"],
        request_headers=environment_settings["request_headers"],
        timeout_seconds=payload.timeout_seconds,
    )
    api_steps = _case_run_api_steps(case, runner, payload)
    if not api_steps:
        raise HTTPException(status_code=400, detail="当前用例没有可执行接口请求")
    is_single_step_debug = payload.step_id is not None or payload.step_override is not None
    project_llm_context = build_project_llm_context(project.id, project_settings, db)
    runtime_agent = None
    if not is_single_step_debug:
        settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_API_RUNTIME)
        runtime_agent = build_api_flow_runtime_agent(
            settings,
            project_context=project_llm_context,
        )

    def events() -> Iterator[str]:
        passed = 0
        failed = 0
        flow_variables: dict[str, Any] = {}
        response_history: list[ApiFlowResponseHistory] = []
        yield sse_event(
            "start",
            {
                "message": "开始调试单个接口节点。" if is_single_step_debug else "开始执行后端接口用例。",
                "stage": "start",
                "case_id": case.id,
                "case_title": case.title,
                "api_base_url": environment_settings["api_base_url"],
                "environment": environment_settings["environment"],
                "total": len(api_steps),
            },
        )

        for step in api_steps:
            runtime_inferences: list[RuntimeVariableInference] = []
            attempted_variables: set[str] = set()
            request_spec = None
            skip_step = False
            while True:
                try:
                    request_spec = runner.build_request(step, flow_variables)
                    break
                except MissingApiFlowVariableError as exc:
                    if is_single_step_debug:
                        failed += 1
                        error = (
                            f"单节点调试未填写变量：{exc.variable_name}，"
                            "请在 Path、Query 或 Body 中手动填入实际值。"
                        )
                        result = runner.build_step_error_result(step, error)
                        yield sse_event("result", result.event_payload())
                        skip_step = True
                        break
                    if exc.variable_name in attempted_variables:
                        failed += 1
                        result = runner.build_step_error_result(step, str(exc))
                        yield sse_event("result", result.event_payload())
                        if payload.fail_fast:
                            break
                        skip_step = True
                        break
                    attempted_variables.add(exc.variable_name)
                    yield sse_event(
                        "inference",
                        _runtime_inference_event_payload(
                            step,
                            variable=exc.variable_name,
                            status="running",
                            message=f"正在使用运行期 agent 推导变量：{exc.variable_name}",
                        ),
                    )
                    if runtime_agent is None:
                        failed += 1
                        result = runner.build_step_error_result(step, str(exc))
                        yield sse_event("result", result.event_payload())
                        if payload.fail_fast:
                            break
                        skip_step = True
                        break
                    inference = runtime_agent.infer_missing_variable(
                        variable=exc.variable_name,
                        step=step,
                        known_variables=flow_variables,
                        response_history=response_history,
                    )
                    if inference is None:
                        failed += 1
                        error = f"运行期 agent 无法从前序响应推导变量：{exc.variable_name}"
                        yield sse_event(
                            "inference",
                            _runtime_inference_event_payload(
                                step,
                                variable=exc.variable_name,
                                status="failed",
                                message=error,
                            ),
                        )
                        result = runner.build_step_error_result(step, error)
                        yield sse_event("result", result.event_payload())
                        if payload.fail_fast:
                            break
                        skip_step = True
                        break
                    flow_variables[exc.variable_name] = inference.value
                    runtime_inferences.append(inference)
                    yield sse_event(
                        "inference",
                        _runtime_inference_event_payload(
                            step,
                            variable=exc.variable_name,
                            status="resolved",
                            message=f"运行期 agent 已推导变量：{exc.variable_name}",
                            inference=inference,
                        ),
                    )
                except ValueError as exc:
                    failed += 1
                    result = runner.build_step_error_result(step, str(exc))
                    yield sse_event("result", result.event_payload())
                    if payload.fail_fast:
                        break
                    skip_step = True
                    break
            if skip_step:
                continue
            if request_spec is None:
                break

            yield sse_event(
                "request",
                {
                    "message": f"正在请求 {request_spec.method} {request_spec.url}",
                    "stage": "request",
                    **request_spec.event_payload(),
                    "runtime_inferences": [
                        inference.event_payload() for inference in runtime_inferences
                    ],
                },
            )
            result = runner.run_request(request_spec)
            if result.ok:
                passed += 1
                flow_variables.update(result.extracted_variables or {})
            else:
                failed += 1
            yield sse_event(
                "result",
                {
                    "message": "请求通过" if result.ok else result.error or "请求未通过",
                    "stage": "result",
                    **result.event_payload(),
                },
            )
            response_history.append(
                ApiFlowResponseHistory(
                    step_id=result.step_id,
                    order_index=result.order_index,
                    label=result.label,
                    status_code=result.status_code,
                    response_preview=result.response_preview,
                    extracted_variables=result.extracted_variables or {},
                )
            )
            if payload.fail_fast and not result.ok:
                break

        yield sse_event(
            "done",
            {
                "message": "单节点调试完成。" if is_single_step_debug else "接口运行完成。",
                "stage": "done",
                "status": "passed" if failed == 0 else "failed",
                "total": passed + failed,
                "passed": passed,
                "failed": failed,
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _case_run_api_steps(
    case: TestCase,
    runner: ApiCaseRunner,
    payload: CaseRunRequest,
) -> list[TestStep]:
    """根据运行请求挑选接口步骤，支持弹窗里的未保存节点临时调试。

    `step_override` 只用于本次运行，不写回数据库；它让用户在节点弹窗里改完 URL、
    方法或请求体后，可以先验证当前草稿，再决定是否保存整张画布。
    """

    if payload.step_override is not None:
        override_step = _step_from_run_override(case.id, payload.step_override)
        if payload.step_id and override_step.id != payload.step_id:
            raise HTTPException(status_code=400, detail="调试节点与步骤覆盖数据不一致")
        if override_step.action != "api_request":
            raise HTTPException(status_code=400, detail="当前节点不是可调试的接口请求")
        return [override_step]

    api_steps = runner.executable_steps(case)
    if not payload.step_id:
        return api_steps

    selected = [step for step in api_steps if step.id == payload.step_id]
    if not selected:
        raise HTTPException(status_code=404, detail="未找到可调试的接口节点")
    return selected


def _step_from_run_override(case_id: str, payload: CaseRunStepOverride) -> TestStep:
    step_id = (payload.id or "").strip()
    if not step_id:
        raise HTTPException(status_code=400, detail="调试节点缺少步骤 id")
    action = payload.action or ("api_request" if payload.kind == "api" else None)

    return TestStep(
        id=step_id,
        case_id=case_id,
        order_index=payload.order_index or 1,
        kind=payload.kind or "api",
        label=payload.label or "接口调试节点",
        action=action,
        selector=payload.selector,
        target_url=payload.target_url,
        value=payload.value,
        expected=payload.expected,
        data=payload.data,
    )


def _runtime_inference_event_payload(
    step: TestStep,
    *,
    variable: str,
    status: str,
    message: str,
    inference: RuntimeVariableInference | None = None,
) -> dict[str, Any]:
    data = step.data or {}
    payload: dict[str, Any] = {
        "message": message,
        "stage": "runtime_inference",
        "inference_status": status,
        "variable": variable,
        "step_id": step.id,
        "order_index": step.order_index,
        "label": step.label,
        "action": step.action,
        "method": str(data.get("method") or "GET").upper(),
        "target_url": step.target_url,
        "expected_status": data.get("expected_status") or step.expected or 200,
    }
    if inference is not None:
        payload["runtime_inference"] = inference.event_payload()
    return payload


@router.post("/cases/{case_id}/run/fullstack/stream")
def run_fullstack_case_stream(
    case_id: str,
    payload: CaseRunRequest = Body(default_factory=CaseRunRequest),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """流式执行全栈浏览器用例，让平台直接展示页面动作。"""

    case = load_case(case_id, db)
    project = require_project(case.project_id, db)
    project_settings = project_settings_for_case_run(
        project_settings_with_repositories(project, db),
        payload,
    )
    environment_settings = active_environment_settings(project_settings)
    runner = BrowserCaseRunner(
        base_url=environment_settings["base_url"],
        environment=environment_settings["environment"],
        request_headers=environment_settings["request_headers"],
        timeout_seconds=payload.timeout_seconds,
        fail_fast=payload.fail_fast,
    )
    if not runner.executable_steps(case):
        raise HTTPException(status_code=400, detail="当前用例没有可执行浏览器步骤")

    def events() -> Iterator[str]:
        try:
            for event in runner.stream(case):
                event_type = str(event.pop("type", "progress"))
                yield sse_event(event_type, event)
        except ValueError as exc:
            yield sse_event("error", {"message": str(exc), "stage": "runner", "status_code": 400})
        except Exception as exc:
            yield sse_event("error", {"message": str(exc), "stage": "runner", "status_code": 500})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cases/{case_id}/playwright-preview", response_model=PlaywrightExportOut)
def playwright_preview(case_id: str, db: Session = Depends(get_db)) -> PlaywrightExportOut:
    case = load_case(case_id, db)
    content = _playwright_emitter_for_case(case, db).preview(case)
    return PlaywrightExportOut(
        case_id=case.id,
        spec_path=case.playwright_spec_path or "",
        content=content,
    )


def _playwright_emitter_for_case(case: TestCase, db: Session) -> PlaywrightEmitter:
    project = require_project(case.project_id, db)
    project_settings = project_settings_with_repositories(project, db)
    environment_settings = active_environment_settings(project_settings)
    return PlaywrightEmitter(
        get_settings().generated_specs_dir,
        base_url=environment_settings["base_url"],
        api_base_url=environment_settings["api_base_url"],
        environment=environment_settings["environment"],
        request_headers=environment_settings["request_headers"],
    )
