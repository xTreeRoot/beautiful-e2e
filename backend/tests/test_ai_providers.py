from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.system import ai_provider, update_ai_provider
from app.core.config import Settings, get_settings
from app.models import AiProviderConfig
from app.schemas import AiProviderUpdate
from app.services.ai.base import CaseGenerationContext
from app.services.ai.codex_bridge import CodexBridgeCaseProvider, CodexHttpCompletionClient
from app.services.ai.codex_exec import (
    CodexExecCompletionClient,
    CodexExecConfig,
    codex_exec_case_output_schema,
    codex_exec_event_to_provider_delta,
    resolve_codex_executable,
)
from app.services.ai.codex_http_bridge import (
    CodexHttpBridgeConfig,
    CodexHttpBridgeError,
    CodexProviderHttpBridge,
)
from app.services.ai.payload_compaction import compact_codex_exec_payload, compact_http_bridge_payload
from app.services.ai.registry import available_provider_names, build_case_generation_provider
from app.services.ai_settings import (
    AI_USAGE_API_RUNTIME,
    AI_USAGE_DSL_GENERATION,
    AI_USAGE_PROJECT_ANALYSIS,
    settings_for_ai_usage,
)
from app.services.repo_reader import RepoSummary


def test_codex_exec_client_reads_last_message_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        command: list[str],
        input: str,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"title":"ok","steps":[]}', encoding="utf-8")

        assert command[:2] == [str(fake_codex), "exec"]
        assert "--ephemeral" not in command
        assert "--sandbox" not in command
        assert command[-1] == "-"
        assert "<system>" in input
        assert "<payload>" in input
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")

    client = CodexExecCompletionClient(
        CodexExecConfig(executable=str(fake_codex), cwd=tmp_path, timeout_seconds=120)
    )

    assert client.complete("系统提示", '{"prompt":"生成"}') == '{"title":"ok","steps":[]}'


def test_codex_exec_client_stream_reads_json_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    class FakeProcess:
        def __init__(self, command: list[str], **kwargs) -> None:
            commands.append(command)
            self.command = command
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                "\n".join(
                    [
                        json.dumps({"type": "reasoning_content_delta", "delta": "先分析 DSL"}),
                        json.dumps({"type": "agent_message_content_delta", "delta": '{"title":"ok"'}),
                    ]
                )
                + "\n"
            )
            self.stderr = io.StringIO("")

        def wait(self, timeout=None) -> int:
            output_path = Path(self.command[self.command.index("--output-last-message") + 1])
            output_path.write_text('{"title":"ok","steps":[]}', encoding="utf-8")
            return 0

        def kill(self) -> None:
            return None

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")
    client = CodexExecCompletionClient(
        CodexExecConfig(executable=str(fake_codex), cwd=tmp_path, timeout_seconds=120)
    )

    events = list(client.stream_complete("系统提示", '{"prompt":"生成"}'))

    assert "--json" in commands[0]
    assert events[0]["channel"] == "reasoning"
    assert events[0]["delta"] == "先分析 DSL"
    assert events[1]["channel"] == "content"
    assert events[-1] == {"type": "provider_final", "text": '{"title":"ok","steps":[]}'}


def test_codex_exec_client_passes_explicit_execution_options(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        input: str,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"title":"ok","steps":[]}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fake_codex = tmp_path / "codex"
    fake_codex.write_text("#!/bin/sh\n", encoding="utf-8")
    add_dir = tmp_path / "shared"
    add_dir.mkdir()
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"png")

    client = CodexExecCompletionClient(
        CodexExecConfig(
            executable=str(fake_codex),
            cwd=tmp_path,
            sandbox="workspace-write",
            ephemeral=True,
            skip_git_repo_check=True,
            image_paths=(image_path,),
            add_dirs=(add_dir,),
            config_overrides=("model_reasoning_effort=\"high\"",),
            enabled_features=("fast-path",),
            disabled_features=("legacy-mode",),
        )
    )

    assert client.complete("系统提示", '{"prompt":"生成"}') == '{"title":"ok","steps":[]}'
    command = commands[0]
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("--image") + 1] == str(image_path)
    assert command[command.index("--add-dir") + 1] == str(add_dir)
    assert command[command.index("--config") + 1] == 'model_reasoning_effort="high"'
    assert command[command.index("--enable") + 1] == "fast-path"
    assert command[command.index("--disable") + 1] == "legacy-mode"
    assert "--skip-git-repo-check" in command


def test_codex_exec_output_schema_requires_declared_fields() -> None:
    schema = codex_exec_case_output_schema()
    step_schema = schema["properties"]["steps"]["items"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert step_schema["additionalProperties"] is False
    assert set(step_schema["required"]) == set(step_schema["properties"])
    assert step_schema["properties"]["data"]["type"] == "object"
    assert "method" in step_schema["properties"]["data"]["properties"]
    assert set(step_schema["properties"]["data"]["required"]) == set(
        step_schema["properties"]["data"]["properties"]
    )
    assert step_schema["properties"]["data"]["additionalProperties"] is True


def test_codex_exec_output_schema_avoids_unsupported_composition_keywords() -> None:
    schema = codex_exec_case_output_schema()
    encoded = json.dumps(schema)

    # Codex CLI 会把 schema 透传给上游结构化输出；条件组合关键字会被部分
    # 供应商拒绝，接口步骤的 URL/method 严格性改由解析层校验。
    for keyword in ["allOf", "oneOf", "anyOf", "if", "then", "else"]:
        assert f'"{keyword}"' not in encoded


def test_codex_exec_payload_compaction_keeps_route_contract_under_limit() -> None:
    large_schema = {
        "type": "object",
        "required": ["recordId"],
        "properties": {
            f"field_{index}": {"type": "string", "description": "字段说明" * 80}
            for index in range(90)
        },
    }
    route = {
        "method": "POST",
        "path": "/api/pd/records/create",
        "summary": "创建记录",
        "handler": "create",
        "source": "RecordController.java:42",
        "request_body": {"schema": large_schema, "java_type": "RecordCreateRequest"},
        "log": "扫描日志" * 2_000,
    }
    payload = {
        "natural_language": "生成客户端接口链路",
        "execution_mode": "backend_api",
        "frontend_repository_summary": {
            "path": "/repo",
            "exists": True,
            "files": ["a.ts"] * 200,
            "signals": [],
            "routes": [route] * 80,
            "dom_targets": [],
        },
        "backend_repository_summary": {
            "path": "/repo",
            "exists": True,
            "files": ["a.java"] * 200,
            "signals": [],
            "routes": [route] * 80,
            "dom_targets": [],
        },
        "project_context": {"repositories": [], "rules": []},
        "current_canvas_dsl": {"nodes": [{"data": {"note": "x" * 1_000}}] * 100},
        "reference_documents": [{"content": "文档" * 10_000}],
    }

    compacted = compact_codex_exec_payload(payload, execution_mode="backend_api", target_chars=60_000)
    compacted_text = json.dumps(compacted, ensure_ascii=False)
    compacted_route = compacted["backend_repository_summary"]["routes"][0]

    assert len(compacted_text) <= 60_000
    assert compacted["context_compaction"]["provider"] == "codex_exec"
    assert compacted_route["path"] == "/api/pd/records/create"
    assert compacted_route["request_body"]["fields"][:2] == ["field_0", "field_1"]
    assert "properties" not in compacted_route["request_body"]


def test_http_bridge_payload_compaction_keeps_relevant_route_under_limit() -> None:
    route = {
        "method": "POST",
        "path": "/api/records/search",
        "summary": "查询目标记录",
        "handler": "searchRecords",
        "source": "RecordController.java:42",
        "request_body": {
            "schema": {
                "type": "object",
                "properties": {
                    f"field_{index}": {"type": "string", "description": "字段说明" * 80}
                    for index in range(80)
                },
            },
            "java_type": "RecordSearchRequest",
        },
    }
    noisy_route = {
        "method": "GET",
        "path": "/api/noisy/items",
        "summary": "无关列表",
        "handler": "listNoisyItems",
        "source": "NoisyController.java:12",
        "description": "噪声说明" * 500,
    }
    payload = {
        "natural_language": "从查询目标记录开始生成接口链路",
        "execution_mode": "backend_api",
        "frontend_repository_summary": {
            "path": "/repo",
            "exists": True,
            "files": ["a.ts"] * 200,
            "signals": [],
            "routes": [noisy_route] * 160,
            "dom_targets": [],
        },
        "backend_repository_summary": {
            "path": "/repo",
            "exists": True,
            "files": ["a.java"] * 200,
            "signals": [],
            "routes": [noisy_route] * 160 + [route],
            "dom_targets": [],
        },
        "project_context": {"repositories": [], "rules": []},
        "current_canvas_dsl": {"nodes": [{"data": {"note": "x" * 1_000}}] * 80},
        "reference_documents": [{"content": "查询目标记录" + "文档" * 8_000}],
    }

    compacted = compact_http_bridge_payload(
        payload,
        execution_mode="backend_api",
        target_chars=38_000,
    )
    compacted_text = json.dumps(compacted, ensure_ascii=False)
    backend_paths = [route["path"] for route in compacted["backend_repository_summary"]["routes"]]

    assert len(compacted_text) <= 38_000
    assert compacted["context_compaction"]["provider"] == "codex_bridge"
    assert "/api/records/search" in backend_paths


def test_codex_bridge_stream_retries_with_smaller_payload_on_context_limit(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_stream_complete(self, system, prompt):
        calls.append(json.loads(prompt))
        if len(calls) == 1:
            raise CodexHttpBridgeError(
                '{"error":{"code":"context_length_exceeded","message":"input too long"}}'
            )
        yield {
            "type": "provider_final",
            "text": json.dumps(
                {
                    "title": "查询记录",
                    "description": "查询记录",
                    "priority": "P1",
                    "steps": [
                        {
                            "kind": "api",
                            "label": "查询记录",
                            "action": "api_request",
                            "target_url": "/api/records/search",
                            "data": {"method": "POST", "expected_status": 200, "body": {}},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        }

    monkeypatch.setattr(CodexProviderHttpBridge, "stream_complete", fake_stream_complete)
    route = {
        "method": "POST",
        "path": "/api/records/search",
        "summary": "查询记录",
        "handler": "searchRecords",
        "source": "RecordController.java:42",
        "request_body": {
            "schema": {
                "type": "object",
                "properties": {
                    f"field_{index}": {"type": "string", "description": "字段说明" * 120}
                    for index in range(100)
                },
            }
        },
    }
    context = CaseGenerationContext(
        prompt="从查询记录开始生成接口链路",
        execution_mode="backend_api",
        frontend=RepoSummary(path="/repo", exists=True, files=[], signals=[]),
        backend=RepoSummary(
            path="/repo",
            exists=True,
            files=["RecordController.java"] * 160,
            signals=[],
            routes=[route] * 220,
        ),
        reference_documents=[{"title": "执行单", "content": "查询记录" + "文档" * 12_000}],
    )
    provider = CodexBridgeCaseProvider(
        model="demo-model",
        api_key="secret",
        base_url="https://vendor.example",
    )

    events = list(provider.stream_generate(context))

    assert len(calls) == 2
    assert calls[0]["context_compaction"]["provider"] == "codex_bridge"
    assert calls[1]["context_compaction"]["retry"] is True
    assert len(json.dumps(calls[1], ensure_ascii=False)) < len(
        json.dumps(calls[0], ensure_ascii=False)
    )
    assert any(event.get("stage") == "provider_context_retry" for event in events)
    assert events[-1]["type"] == "generated_case"
    assert events[-1]["case"].steps[0].target_url == "/api/records/search"


def test_codex_exec_nested_reasoning_event_is_forwarded() -> None:
    event = {
        "type": "event_msg",
        "msg": {
            "method": "item/reasoning/summaryTextDelta",
            "params": {"delta": "检查接口顺序"},
        },
    }

    provider_event = codex_exec_event_to_provider_delta(event)

    assert provider_event is not None
    assert provider_event["channel"] == "reasoning"
    assert provider_event["delta"] == "检查接口顺序"


def test_codex_exec_item_completed_agent_message_is_forwarded() -> None:
    event = {
        "type": "item.completed",
        "item": {
            "id": "item_0",
            "type": "agent_message",
            "text": '{"title":"ok","steps":[]}',
        },
    }

    provider_event = codex_exec_event_to_provider_delta(event)

    assert provider_event is not None
    assert provider_event["channel"] == "content"
    assert provider_event["delta"] == '{"title":"ok","steps":[]}'


def test_codex_exec_turn_completed_usage_is_not_reasoning_delta() -> None:
    event = {
        "type": "turn.completed",
        "usage": {"output_tokens": 36, "reasoning_output_tokens": 21},
    }

    assert codex_exec_event_to_provider_delta(event) is None


def test_http_bridge_responses_stream_forwards_vendor_reasoning(monkeypatch) -> None:
    def fake_post_json(url, api_key, payload, accept, timeout_seconds):
        assert url == "https://vendor.example/v1/responses"
        assert api_key == "secret"
        assert payload["stream"] is True
        assert accept == "text/event-stream"
        return iter(
            [
                _sse_data({"type": "response.reasoning_summary_text.delta", "delta": "先梳理接口"}),
                "\n",
                _sse_data({"type": "response.output_text.delta", "delta": '{"title":"ok",'}),
                "\n",
                _sse_data({"type": "response.output_text.delta", "delta": '"steps":[]}'}),
                "\n",
            ]
        )

    monkeypatch.setattr("app.services.ai.codex_http_bridge.post_json", fake_post_json)
    bridge = CodexProviderHttpBridge(
        CodexHttpBridgeConfig(
            model="demo-model",
            wire_api="responses",
            api_key="secret",
            base_url="https://vendor.example",
        )
    )

    events = list(bridge.stream_complete("系统提示", "用户提示"))

    assert events[0]["type"] == "provider_delta"
    assert events[0]["channel"] == "reasoning"
    assert events[0]["delta"] == "先梳理接口"
    assert events[1]["channel"] == "content"
    assert events[-1] == {"type": "provider_final", "text": '{"title":"ok","steps":[]}'}


def test_codex_http_completion_client_exposes_stream(monkeypatch) -> None:
    def fake_stream_complete(self, system, prompt):
        yield {"type": "provider_delta", "channel": "content", "delta": "{}", "message": "{}"}
        yield {"type": "provider_final", "text": "{}"}

    monkeypatch.setattr(CodexProviderHttpBridge, "stream_complete", fake_stream_complete)
    client = CodexHttpCompletionClient(
        model="demo-model",
        api_key="secret",
        base_url="https://vendor.example",
    )

    assert list(client.stream_complete("系统提示", "用户提示"))[-1]["text"] == "{}"


def test_registry_includes_codex_exec_and_openai_compatible() -> None:
    assert {"codex_exec", "codex_bridge", "openai_compatible", "rule_based"}.issubset(
        set(available_provider_names())
    )


def test_registry_builds_codex_exec_provider_from_settings(tmp_path: Path) -> None:
    provider = build_case_generation_provider(
        Settings(
            ai_provider="codex_exec",
            ai_provider_config={"executable": "/usr/local/bin/codex", "cwd": str(tmp_path)},
        )
    )

    assert provider.name == "codex_exec"


def test_resolve_codex_executable_checks_codex_app_when_path_misses(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app_cli = tmp_path / "Codex.app" / "Contents" / "Resources" / "codex"
    app_cli.parent.mkdir(parents=True)
    app_cli.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("app.services.ai.codex_exec.shutil.which", lambda command: None)
    monkeypatch.setattr(
        "app.services.ai.codex_exec.CODEX_APP_EXECUTABLES",
        (app_cli,),
    )

    assert resolve_codex_executable("codex") == str(app_cli)


def test_ai_provider_status_and_runtime_update(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    monkeypatch.setattr("app.api.system.resolve_codex_executable", lambda command: "/mock/codex")
    get_settings.cache_clear()


def test_ai_provider_update_persists_usage_plan(mysql_engine, monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    monkeypatch.setattr("app.api.system.resolve_codex_executable", lambda command: "/mock/codex")
    get_settings.cache_clear()

    usage_plan = {
        AI_USAGE_PROJECT_ANALYSIS: "codex_exec",
        AI_USAGE_DSL_GENERATION: "codex_exec",
        AI_USAGE_API_RUNTIME: "openai_compatible",
    }
    with Session(mysql_engine) as db:
        status = update_ai_provider(
            AiProviderUpdate(
                provider="codex_exec",
                codex_exec_command="codex",
                usage_plan=usage_plan,
            ),
            db,
        )

        rows = {
            row.provider_key: row
            for row in db.scalars(select(AiProviderConfig)).all()
        }
        assert status["active_provider"] == "codex_exec"
        assert status["usage_plan"] == usage_plan
        assert rows["codex_exec"].is_active is True
        assert rows["codex_exec"].config == {"executable": "codex"}
        assert set(rows["codex_exec"].usage_keys) == {
            AI_USAGE_PROJECT_ANALYSIS,
            AI_USAGE_DSL_GENERATION,
        }

        runtime_settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_API_RUNTIME)
        dsl_settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_DSL_GENERATION)
        assert runtime_settings.ai_provider == "openai_compatible"
        assert dsl_settings.ai_provider == "codex_exec"

    get_settings.cache_clear()


def test_ai_provider_switch_rebinds_stale_usage_plan(mysql_engine, monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "rule_based")
    monkeypatch.delenv("AI_PROVIDER_ENTRYPOINT", raising=False)
    monkeypatch.setattr("app.api.system.resolve_codex_executable", lambda command: "/mock/codex")
    get_settings.cache_clear()

    old_plan = {
        AI_USAGE_PROJECT_ANALYSIS: "codex_bridge",
        AI_USAGE_DSL_GENERATION: "codex_bridge",
        AI_USAGE_API_RUNTIME: "codex_bridge",
    }
    with Session(mysql_engine) as db:
        update_ai_provider(
            AiProviderUpdate(provider="codex_bridge", usage_plan=old_plan),
            db,
        )

        status = update_ai_provider(
            AiProviderUpdate(
                provider="codex_exec",
                codex_exec_command="codex",
                usage_plan=old_plan,
            ),
            db,
        )

        assert status["active_provider"] == "codex_exec"
        assert status["usage_plan"] == {
            AI_USAGE_PROJECT_ANALYSIS: "codex_exec",
            AI_USAGE_DSL_GENERATION: "codex_exec",
            AI_USAGE_API_RUNTIME: "codex_exec",
        }
        dsl_settings = settings_for_ai_usage(get_settings(), db, AI_USAGE_DSL_GENERATION)
        assert dsl_settings.ai_provider == "codex_exec"

    get_settings.cache_clear()


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n"

    before = ai_provider()
    assert before["active_provider"] == "rule_based"
    assert any(provider["name"] == "codex_exec" for provider in before["providers"])

    after = update_ai_provider(AiProviderUpdate(provider="codex_exec", codex_exec_command="codex"))

    assert after["active_provider"] == "codex_exec"
    assert after["provider"] == "codex_exec"
    assert after["codex_exec_available"] is True
    assert after["codex_exec_path"] == "/mock/codex"
    get_settings.cache_clear()
