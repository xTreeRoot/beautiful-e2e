from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import models
from app.api.cases import router
from app.db import get_db
from app.services.case_runner import ApiCaseRunner, ApiHttpResponse


def test_api_runner_rebases_absolute_node_url_to_current_environment() -> None:
    sent_headers: list[dict[str, str]] = []

    def fake_sender(spec):
        sent_headers.append(spec.headers)
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok":true}',
        )

    runner = ApiCaseRunner(
        api_base_url="https://api.runtime.test/gateway",
        request_headers={"X-Env": "runtime"},
        request_sender=fake_sender,
    )
    step = models.TestStep(
        id="step-1",
        order_index=1,
        kind="api",
        label="查询记录",
        action="api_request",
        target_url="http://node-old.test/api/records?page=1",
        data={"method": "GET", "expected_status": 200},
    )

    spec = runner.build_request(step)
    result = runner.run_request(spec)

    assert spec.url == "https://api.runtime.test/gateway/api/records?page=1"
    assert sent_headers == [{"X-Env": "runtime"}]
    assert result.ok is True


def test_api_runner_does_not_duplicate_matching_base_path() -> None:
    runner = ApiCaseRunner(api_base_url="https://api.runtime.test/api")
    step = models.TestStep(
        id="step-1",
        order_index=1,
        kind="api",
        label="查询记录",
        action="api_request",
        target_url="/api/records",
        data={"method": "GET", "expected_status": 200},
    )

    spec = runner.build_request(step)

    assert spec.url == "https://api.runtime.test/api/records"


def test_backend_api_run_uses_runtime_environment_snapshot(
    monkeypatch,
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine
    captured_headers: list[dict[str, str]] = []
    captured_urls: list[str] = []

    with Session(engine) as db:
        project = models.Project(name="runtime-env-run")
        project.environment_configs = [
            models.ProjectEnvironmentConfig(
                env_key="local",
                name="本地",
                api_base_url="http://database-old.test",
                request_headers={"X-Env": "database"},
                sort_order=0,
            )
        ]
        group = models.TestGroup(project=project, name="接口运行组", sort_order=10)
        db.add_all([project, group])
        db.flush()
        case = models.TestCase(
            project_id=project.id,
            group_id=group.id,
            title="接口环境切换",
            description="验证运行时环境快照覆盖旧配置。",
            priority="P1",
            source_prompt="运行接口",
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
                label="查询记录",
                action="api_request",
                target_url="http://node-old.test/api/records?page=1",
                expected="200",
                data={"method": "GET", "expected_status": 200},
            )
        )
        db.commit()
        case_id = case.id

    def fake_send(_runner, spec):
        captured_urls.append(spec.url)
        captured_headers.append(spec.headers)
        return ApiHttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok":true}',
        )

    monkeypatch.setattr("app.services.case_runner.ApiCaseRunner._send_with_urllib", fake_send)

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    payload = {
        "environment_settings": {
            "active_api_environment": "runtime",
            "environments": [
                {
                    "key": "runtime",
                    "name": "运行环境",
                    "api_base_url": "https://api.runtime.test/gateway",
                    "request_headers": {"X-Env": "runtime"},
                }
            ],
        }
    }

    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/cases/{case_id}/run/backend-api/stream",
            json=payload,
        ) as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    start_payload = next(item for name, item in events if name == "start")
    result_payload = next(item for name, item in events if name == "result")

    assert response.status_code == 200
    assert start_payload["api_base_url"] == "https://api.runtime.test/gateway"
    assert captured_urls == ["https://api.runtime.test/gateway/api/records?page=1"]
    assert captured_headers == [{"X-Env": "runtime"}]
    assert result_payload["ok"] is True


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))
        elif not line and data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = "message"
            data_lines = []
    return events
