from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import models
from app.api.cases import create_case, generate_case, router, update_case_graph
from app.core.config import get_settings
from app.db import get_db
from app.schemas import CaseCreate, CaseGraphUpdate, GenerateCaseRequest
from app.services.api_flow_runtime_agent import ApiFlowResponseHistory, ApiFlowRuntimeAgent
from app.services.api_flow_variables import MissingApiFlowVariableError
from app.services.case_runner import ApiCaseRunner, ApiHttpResponse
from app.services.playwright_emitter import PlaywrightEmitter


def test_create_case_persists_blank_case_in_selected_group(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="case-create")
        group = models.TestGroup(project=project, name="核心链路组", sort_order=10)
        db.add_all([project, group])
        db.commit()

        created = create_case(
            project.id,
            CaseCreate(
                title="审核提交人工用例",
                description="覆盖审核提交前的基础路径",
                group_id=group.id,
                priority="P0",
            ),
            db,
        )

        audit = db.scalar(select(models.AuditEvent).where(models.AuditEvent.entity_id == created.id))

    assert created.title == "审核提交人工用例"
    assert created.description == "覆盖审核提交前的基础路径"
    assert created.group_id == group.id
    assert created.priority == "P0"
    assert created.graph == {"nodes": [], "edges": []}
    assert audit is not None
    assert audit.action == "case.created"


def test_create_case_rejects_group_from_another_project(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="project-a")
        other_project = models.Project(name="project-b")
        group = models.TestGroup(project=other_project, name="其他项目分组", sort_order=10)
        db.add_all([project, other_project, group])
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            create_case(
                project.id,
                CaseCreate(title="跨项目分组用例", group_id=group.id),
                db,
            )

    assert exc_info.value.status_code == 400


def test_update_case_graph_persists_case_bound_prompt(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="prompt-binding")
        db.add(project)
        db.commit()
        created = create_case(project.id, CaseCreate(title="绑定 Prompt 用例"), db)

        saved = update_case_graph(
            created.id,
            CaseGraphUpdate(
                graph={"nodes": [], "edges": []},
                steps=[],
                source_prompt="登录后进入记录列表并校验状态",
            ),
            db,
        )

    assert saved.source_prompt == "登录后进入记录列表并校验状态"


def test_generate_case_with_target_replaces_existing_case(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    get_settings.cache_clear()

    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="case-regenerate")
        first_group = models.TestGroup(project=project, name="首个分组", sort_order=10)
        target_group = models.TestGroup(project=project, name="目标分组", sort_order=20)
        db.add_all([project, first_group, target_group])
        db.commit()
        target_group_id = target_group.id

        created = create_case(
            project.id,
            CaseCreate(title="OIOI 全流程客户端测试", group_id=target_group_id, priority="P0"),
            db,
        )
        created_id = created.id
        created.playwright_spec_path = "runner/tests/generated/old.spec.ts"
        db.add(
            models.TestStep(
                case_id=created.id,
                order_index=1,
                kind="action",
                label="旧步骤",
            )
        )
        db.commit()

        regenerated = generate_case(
            project.id,
            GenerateCaseRequest(
                description="重新生成 OIOI 全流程客户端测试",
                target_case_id=created_id,
                title=created.title,
                case_description=created.description,
                execution_mode="fullstack",
                priority=created.priority,
            ),
            db,
        )

        case_count = db.scalar(
            select(func.count(models.TestCase.id)).where(models.TestCase.project_id == project.id)
        )
        audit = db.scalar(
            select(models.AuditEvent).where(
                models.AuditEvent.entity_id == created_id,
                models.AuditEvent.action == "case.regenerated",
            )
        )

    assert regenerated.id == created_id
    assert case_count == 1
    assert regenerated.group_id == target_group_id
    assert regenerated.title == "OIOI 全流程客户端测试"
    assert regenerated.priority == "P0"
    assert regenerated.playwright_spec_path is None
    assert regenerated.steps
    assert {step.label for step in regenerated.steps} != {"旧步骤"}
    assert audit is not None
    get_settings.cache_clear()


def test_stream_generate_case_emits_progress_and_persisted_case(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    get_settings.cache_clear()

    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="stream-generation")
        group = models.TestGroup(project=project, name="流式生成组", sort_order=10)
        db.add_all([project, group])
        db.commit()
        project_id = project.id
        group_id = group.id

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/projects/{project_id}/cases/generate/stream",
            json={
                "description": "登录后进入工作台并看到业务数据",
                "group_id": group_id,
                "execution_mode": "fullstack",
            },
        ) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    event_names = [name for name, _payload in events]
    case_payload = next(payload for name, payload in events if name == "case")["case"]

    assert response.status_code == 200
    assert event_names[0] == "start"
    assert "progress" in event_names
    assert event_names[-1] == "done"
    assert case_payload["group_id"] == group_id
    assert case_payload["steps"]

    with Session(engine) as db:
        case_count = db.scalar(select(models.TestCase).where(models.TestCase.project_id == project_id))

    assert case_count is not None
    get_settings.cache_clear()


def test_stream_regenerate_case_returns_fresh_steps_and_graph(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    get_settings.cache_clear()

    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="stream-regeneration")
        group = models.TestGroup(project=project, name="流式重生成组", sort_order=10)
        db.add_all([project, group])
        db.commit()
        created = create_case(
            project.id,
            CaseCreate(title="旧接口用例", description="旧步骤", group_id=group.id),
            db,
        )
        created_id = created.id
        project_id = project.id
        group_id = group.id
        created.graph = {
            "nodes": [{"id": "old-node", "data": {"label": "旧节点"}, "position": {"x": 0, "y": 0}}],
            "edges": [],
        }
        created.steps.clear()
        created.steps.append(
            models.TestStep(order_index=1, kind="action", label="旧步骤", action="click")
        )
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/projects/{project_id}/cases/generate/stream",
            json={
                "description": "重新生成登录后进入工作台并看到业务数据",
                "target_case_id": created_id,
                "group_id": group_id,
                "execution_mode": "fullstack",
            },
        ) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    case_payload = next(payload for name, payload in events if name == "case")["case"]

    assert response.status_code == 200
    assert case_payload["id"] == created_id
    assert case_payload["steps"]
    assert {step["label"] for step in case_payload["steps"]} != {"旧步骤"}
    assert case_payload["graph"]["nodes"]
    assert {node["id"] for node in case_payload["graph"]["nodes"]} != {"old-node"}
    get_settings.cache_clear()


def test_stream_backend_api_run_emits_request_results(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(
            name="backend-api-run",
            is_current=True,
        )
        group = models.TestGroup(project=project, name="接口运行组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="客户端接口链路",
            description="验证接口可以返回成功状态。",
            priority="P1",
            source_prompt="接口运行",
            code_context={"execution_mode": "backend_api"},
            graph={"nodes": [], "edges": []},
        )
        db.add(case)
        db.flush()
        db.add(
            models.TestStep(
                case_id=case.id,
                order_index=1,
                kind="api",
                label="查询访问凭证",
                action="api_request",
                target_url="/api/private/demo/credential",
                expected="200",
                data={"method": "GET", "expected_status": 200},
            )
        )
        db.commit()
        case_id = case.id

    def fake_send(_runner, spec):
        assert spec.method == "GET"
        assert spec.url == "http://localhost:8000/api/private/demo/credential"
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"success":true}',
        )

    monkeypatch.setattr("app.services.case_runner.ApiCaseRunner._send_with_urllib", fake_send)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream("POST", f"/cases/{case_id}/run/backend-api/stream", json={}) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    event_names = [name for name, _payload in events]
    result_payload = next(payload for name, payload in events if name == "result")
    done_payload = next(payload for name, payload in events if name == "done")

    assert response.status_code == 200
    assert event_names == ["start", "request", "result", "done"]
    assert result_payload["ok"] is True
    assert result_payload["status_code"] == 200
    assert result_payload["response_preview"] == '{"success":true}'
    assert done_payload["status"] == "passed"


def test_stream_backend_api_run_can_debug_single_step(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine
    requested_urls: list[str] = []

    with Session(engine) as db:
        project = models.Project(name="backend-api-node-debug")
        group = models.TestGroup(project=project, name="接口调试组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="接口单节点调试",
            description="验证只执行被选中的接口节点。",
            priority="P1",
            source_prompt="接口运行",
            code_context={"execution_mode": "backend_api"},
            graph={"nodes": [], "edges": []},
        )
        db.add(case)
        db.flush()
        first = models.TestStep(
            case_id=case.id,
            order_index=1,
            kind="api",
            label="不应执行的接口",
            action="api_request",
            target_url="/first",
            expected="200",
            data={"method": "GET", "expected_status": 200},
        )
        second = models.TestStep(
            case_id=case.id,
            order_index=2,
            kind="api",
            label="单节点目标接口",
            action="api_request",
            target_url="/second",
            expected="200",
            data={"method": "POST", "expected_status": 200},
        )
        db.add_all([first, second])
        db.commit()
        case_id = case.id
        second_id = second.id

    def fake_send(_runner, spec):
        requested_urls.append(spec.url)
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"debug":true}',
        )

    monkeypatch.setattr("app.services.case_runner.ApiCaseRunner._send_with_urllib", fake_send)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/cases/{case_id}/run/backend-api/stream",
            json={"step_id": second_id, "fail_fast": True},
        ) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    result_payload = next(payload for name, payload in events if name == "result")
    done_payload = next(payload for name, payload in events if name == "done")

    assert response.status_code == 200
    assert requested_urls == ["http://localhost:8000/second"]
    assert result_payload["step_id"] == second_id
    assert result_payload["label"] == "单节点目标接口"
    assert done_payload["total"] == 1
    assert done_payload["status"] == "passed"


def test_stream_backend_api_single_step_debug_does_not_use_runtime_agent(
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="backend-api-node-debug-no-agent")
        group = models.TestGroup(project=project, name="接口调试组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="接口单节点调试不推导变量",
            description="单节点调试缺变量时应直接提示手动填写。",
            priority="P1",
            source_prompt="接口运行",
            code_context={"execution_mode": "backend_api"},
            graph={"nodes": [], "edges": []},
        )
        db.add(case)
        db.flush()
        step = models.TestStep(
            case_id=case.id,
            order_index=1,
            kind="api",
            label="需要手工参数的接口",
            action="api_request",
            target_url="/orders/{{order_id}}",
            expected="200",
            data={"method": "GET", "expected_status": 200},
        )
        db.add(step)
        db.commit()
        case_id = case.id
        step_id = step.id

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/cases/{case_id}/run/backend-api/stream",
            json={"step_id": step_id, "fail_fast": True},
        ) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    event_names = [name for name, _payload in events]
    result_payload = next(payload for name, payload in events if name == "result")
    done_payload = next(payload for name, payload in events if name == "done")

    assert response.status_code == 200
    assert event_names == ["start", "result", "done"]
    assert "单节点调试未填写变量：order_id" in result_payload["error"]
    assert done_payload["total"] == 1
    assert done_payload["status"] == "failed"


def test_stream_backend_api_run_emits_runtime_inference_events(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine
    captured_headers: list[dict[str, str]] = []

    with Session(engine) as db:
        project = models.Project(name="backend-api-runtime-inference")
        group = models.TestGroup(project=project, name="接口运行组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="运行期变量推导",
            description="验证运行期 agent 会可视化推导变量。",
            priority="P1",
            source_prompt="接口运行",
            code_context={"execution_mode": "backend_api"},
            graph={"nodes": [], "edges": []},
        )
        db.add(case)
        db.flush()
        db.add_all(
            [
                models.TestStep(
                    case_id=case.id,
                    order_index=1,
                    kind="api",
                    label="登录",
                    action="api_request",
                    target_url="/login",
                    expected="200",
                    data={"method": "POST", "expected_status": 200},
                ),
                models.TestStep(
                    case_id=case.id,
                    order_index=2,
                    kind="api",
                    label="获取用户信息",
                    action="api_request",
                    target_url="/user/info",
                    expected="200",
                    data={
                        "method": "GET",
                        "expected_status": 200,
                        "headers": {"Authorization": "{{customer_token}}"},
                    },
                ),
            ]
        )
        db.commit()
        case_id = case.id

    def fake_send(_runner, spec):
        captured_headers.append(spec.headers)
        if spec.order_index == 1:
            return ApiHttpResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=b'{"data":{"token":"runtime-token"}}',
            )
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"success":true}',
        )

    monkeypatch.setattr("app.services.case_runner.ApiCaseRunner._send_with_urllib", fake_send)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream("POST", f"/cases/{case_id}/run/backend-api/stream", json={}) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    inference_events = [payload for name, payload in events if name == "inference"]
    request_events = [payload for name, payload in events if name == "request"]

    assert response.status_code == 200
    assert [payload["inference_status"] for payload in inference_events] == ["running", "resolved"]
    assert inference_events[1]["runtime_inference"]["variable"] == "customer_token"
    assert request_events[1]["runtime_inferences"][0]["variable"] == "customer_token"
    assert captured_headers[1]["Authorization"] == "runtime-token"


def test_api_runner_passes_extracted_response_variable_to_later_body() -> None:
    sent_bodies: list[dict] = []

    def fake_sender(spec):
        sent_bodies.append(spec.body)
        if spec.order_index == 1:
            return ApiHttpResponse(
                status_code=200,
                headers={"Content-Type": "application/json"},
                body=b'{"data":{"accessCredential":"credential-123"}}',
            )
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"success":true}',
        )

    runner = ApiCaseRunner(request_sender=fake_sender)
    variables: dict[str, object] = {}
    first = models.TestStep(
        id="step-1",
        order_index=1,
        kind="api",
        label="查询访问凭证",
        action="api_request",
        target_url="/api/private/demo/credential",
        data={
            "method": "GET",
            "expected_status": 200,
            "extract": {"accessCredential": "$.data.accessCredential"},
        },
    )
    second = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="执行业务动作",
        action="api_request",
        target_url="/api/private/demo/execute",
        data={
            "method": "POST",
            "expected_status": 200,
            "body": {"credential": "{{accessCredential}}"},
        },
    )

    first_result = runner.run_request(runner.build_request(first, variables))
    variables.update(first_result.extracted_variables or {})
    second_result = runner.run_request(runner.build_request(second, variables))

    assert first_result.extracted_variables == {"accessCredential": "credential-123"}
    assert sent_bodies == [None, {"credential": "credential-123"}]
    assert second_result.ok is True


def test_api_runner_omits_missing_optional_header_variable() -> None:
    runner = ApiCaseRunner()
    step = models.TestStep(
        id="step-public",
        order_index=1,
        kind="api",
        label="公开资源详情",
        action="api_request",
        target_url="/api/public/resources/1/overview",
        data={
            "method": "GET",
            "expected_status": 200,
            "headers": {"Authorization": "{{access_token}}"},
            "depends_on": [
                {
                    "variable": "access_token",
                    "field": "headers.Authorization",
                    "required": False,
                }
            ],
        },
    )

    spec = runner.build_request(step, variables={})

    assert "Authorization" not in spec.headers


def test_api_runner_uses_environment_header_when_dsl_auth_variable_is_missing() -> None:
    runner = ApiCaseRunner(request_headers={"X-Customer-Token": "manual-token"})
    step = models.TestStep(
        id="step-private",
        order_index=1,
        kind="api",
        label="小程序登录态接口",
        action="api_request",
        target_url="/customer/api/pd/user/info",
        data={
            "method": "GET",
            "expected_status": 200,
            "headers": {"X-Customer-Token": "{{customer_token}}"},
        },
    )

    spec = runner.build_request(step, variables={})

    assert spec.headers["X-Customer-Token"] == "manual-token"


def test_api_runner_still_requires_missing_business_variable_in_body() -> None:
    runner = ApiCaseRunner(request_headers={"X-Customer-Token": "manual-token"})
    step = models.TestStep(
        id="step-body",
        order_index=1,
        kind="api",
        label="兑换权益",
        action="api_request",
        target_url="/customer/api/pd/prize/exchange",
        data={
            "method": "POST",
            "expected_status": 200,
            "body": {"entitlement_id": "{{entitlement_id}}"},
        },
    )

    with pytest.raises(MissingApiFlowVariableError) as error:
        runner.build_request(step, variables={})

    assert "entitlement_id" in str(error.value)


def test_runtime_agent_inferrs_missing_variable_from_previous_response() -> None:
    agent = ApiFlowRuntimeAgent()
    step = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="需要登录态的后续接口",
        action="api_request",
        target_url="/api/private/profile/info",
        data={"headers": {"Authorization": "{{access_token}}"}},
    )

    inference = agent.infer_missing_variable(
        variable="access_token",
        step=step,
        known_variables={},
        response_history=[
            ApiFlowResponseHistory(
                step_id="step-1",
                order_index=1,
                label="登录",
                status_code=200,
                response_preview='{"success":true,"data":{"token":"token-from-login"}}',
                extracted_variables={},
            )
        ],
    )

    assert inference is not None
    assert inference.value == "token-from-login"
    assert inference.source == "deterministic_response_alias"
    assert inference.source_step_label == "登录"


def test_runtime_agent_prompt_receives_shared_project_context() -> None:
    class CaptureClient:
        prompt = ""

        def complete(self, system: str, prompt: str) -> str:
            self.prompt = prompt
            return json.dumps({"value": None, "confidence": 0, "reason": "未找到"})

    client = CaptureClient()
    agent = ApiFlowRuntimeAgent(
        ai_client=client,
        project_context={
            "version": "project_llm_context.v1",
            "auth": {
                "effective_mode": "environment_headers",
                "likely_auth_header_keys": ["X-Customer-Token"],
                "redacted": True,
            },
        },
    )
    step = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="兑换权益",
        action="api_request",
        target_url="/customer/api/pd/prize/exchange",
        data={"body": {"entitlement_id": "{{entitlement_id}}"}},
    )

    inference = agent.infer_missing_variable(
        variable="entitlement_id",
        step=step,
        known_variables={},
        response_history=[
            ApiFlowResponseHistory(
                step_id="step-1",
                order_index=1,
                label="获取用户信息",
                status_code=200,
                response_preview='{"success":true}',
                extracted_variables={},
            )
        ],
    )

    assert inference is None
    assert "project_llm_context.v1" in client.prompt
    assert "environment_headers" in client.prompt


def test_playwright_preview_keeps_api_variable_chain_executable(tmp_path) -> None:
    case = models.TestCase(
        id="case-1",
        project_id="project-1",
        title="接口变量链路",
        description="验证导出脚本保留接口变量传递。",
        priority="P1",
        source_prompt="接口变量链路",
        code_context={"execution_mode": "backend_api"},
        graph={"nodes": [], "edges": []},
    )
    case.steps = [
        models.TestStep(
            id="step-1",
            order_index=1,
            kind="api",
            label="查询访问凭证",
            action="api_request",
            target_url="/api/private/demo/credential",
            data={
                "method": "GET",
                "expected_status": 200,
                "extract": {"accessCredential": "$.data.accessCredential"},
            },
        ),
        models.TestStep(
            id="step-2",
            order_index=2,
            kind="api",
            label="执行业务动作",
            action="api_request",
            target_url="/api/private/demo/execute",
            data={
                "method": "POST",
                "expected_status": 200,
                "body": {"credential": "{{accessCredential}}"},
            },
        ),
    ]

    preview = PlaywrightEmitter(tmp_path).preview(case)

    assert "const apiVars = {};" in preview
    assert "await applyExtract(response1" in preview
    assert "headersWithoutEnvironmentOverrides" in preview
    assert 'resolveValue({"credential": "{{accessCredential}}"}, apiVars)' in preview


def test_stream_fullstack_run_emits_visual_browser_events(
    monkeypatch: pytest.MonkeyPatch,
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="fullstack-run")
        group = models.TestGroup(project=project, name="浏览器运行组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="登录后进入工作台",
            description="验证浏览器动作可以被平台可视化运行。",
            priority="P1",
            source_prompt="浏览器运行",
            code_context={"execution_mode": "fullstack"},
            graph={"nodes": [], "edges": []},
        )
        db.add(case)
        db.flush()
        db.add(
            models.TestStep(
                case_id=case.id,
                order_index=1,
                kind="setup",
                label="打开首页",
                action="goto",
                target_url="/",
                expected="应用外壳可见",
            )
        )
        db.commit()
        case_id = case.id

    def fake_stream(self, case):
        assert self.base_url == "http://localhost:5173"
        yield {
            "type": "start",
            "message": "开始执行浏览器流程。",
            "case_id": case.id,
            "case_title": case.title,
            "base_url": self.base_url,
            "environment": self.environment,
            "total": 1,
        }
        yield {
            "type": "action",
            "step_id": case.steps[0].id,
            "order_index": 1,
            "label": "打开首页",
            "action": "goto",
            "target_url": "/",
        }
        yield {
            "type": "result",
            "step_id": case.steps[0].id,
            "order_index": 1,
            "label": "打开首页",
            "action": "goto",
            "duration_ms": 32,
            "ok": True,
            "page_url": "http://localhost:5173/",
            "screenshot_data_url": "data:image/jpeg;base64,AA==",
        }
        yield {"type": "done", "status": "passed", "total": 1, "passed": 1, "failed": 0}

    monkeypatch.setattr("app.services.browser_case_runner.BrowserCaseRunner.stream", fake_stream)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream("POST", f"/cases/{case_id}/run/fullstack/stream", json={}) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    event_names = [name for name, _payload in events]
    result_payload = next(payload for name, payload in events if name == "result")

    assert response.status_code == 200
    assert event_names == ["start", "action", "result", "done"]
    assert result_payload["ok"] is True
    assert result_payload["screenshot_data_url"].startswith("data:image/jpeg;base64,")


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events
