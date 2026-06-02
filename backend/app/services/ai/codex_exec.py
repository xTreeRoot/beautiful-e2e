from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread
import time
from typing import Any

from app.core.config import Settings
from app.services.ai.base import CaseGenerationContext, CaseGenerationError
from app.services.ai.case_completion import CompletionCaseProvider
from app.services.ai.payload_compaction import compact_codex_exec_payload

CODEX_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
CODEX_LOCAL_PROVIDERS = {"lmstudio", "ollama"}

CODEX_APP_EXECUTABLES = (
    Path("/Applications/Codex.app/Contents/Resources/codex"),
)


@dataclass(frozen=True)
class CodexExecConfig:
    """`codex exec` 调用配置。

    默认不强制指定模型，让 Codex CLI 复用本机配置；如果需要固定模型，可通过
    `CODEX_EXEC_MODEL` 或 `AI_PROVIDER_CONFIG.model` 显式覆盖。
    """

    executable: str = "codex"
    model: str | None = None
    profile: str | None = None
    profile_v2: str | None = None
    cwd: Path | None = None
    sandbox: str | None = None
    ephemeral: bool = False
    skip_git_repo_check: bool = False
    ignore_user_config: bool = False
    ignore_rules: bool = False
    strict_config: bool = False
    output_schema_enabled: bool = True
    oss: bool = False
    local_provider: str | None = None
    image_paths: tuple[Path, ...] = field(default_factory=tuple)
    add_dirs: tuple[Path, ...] = field(default_factory=tuple)
    config_overrides: tuple[str, ...] = field(default_factory=tuple)
    enabled_features: tuple[str, ...] = field(default_factory=tuple)
    disabled_features: tuple[str, ...] = field(default_factory=tuple)
    dangerously_bypass_approvals_and_sandbox: bool = False
    dangerously_bypass_hook_trust: bool = False
    timeout_seconds: int = 300
    extra_args: tuple[str, ...] = field(default_factory=tuple)


class CodexExecCompletionClient:
    """通过 `codex exec` 获取模型最终回复。"""

    def __init__(self, config: CodexExecConfig) -> None:
        self.config = config

    def complete(self, system: str, prompt: str) -> str:
        executable = self._resolve_executable()
        cwd = self._resolve_cwd()

        with tempfile.TemporaryDirectory(prefix="beautiful-e2e-codex-exec-") as temp_dir:
            output_path = Path(temp_dir) / "last-message.txt"
            schema_path = self._write_output_schema(temp_dir)
            command = self._build_command(executable, cwd, output_path, schema_path=schema_path)
            try:
                result = subprocess.run(
                    command,
                    input=build_codex_exec_prompt(system, prompt),
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CaseGenerationError("codex exec 生成超时") from exc
            except OSError as exc:
                raise CaseGenerationError(f"无法启动 codex exec：{exc}") from exc

            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or "codex exec 调用失败"
                raise CaseGenerationError(detail)

            final_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
            return final_text or result.stdout.strip()

    def stream_complete(self, system: str, prompt: str) -> Iterator[dict[str, Any]]:
        executable = self._resolve_executable()
        cwd = self._resolve_cwd()

        with tempfile.TemporaryDirectory(prefix="beautiful-e2e-codex-exec-") as temp_dir:
            output_path = Path(temp_dir) / "last-message.txt"
            schema_path = self._write_output_schema(temp_dir)
            command = self._build_command(
                executable,
                cwd,
                output_path,
                json_events=True,
                schema_path=schema_path,
            )
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                raise CaseGenerationError(f"无法启动 codex exec：{exc}") from exc

            stderr_lines: list[str] = []
            stderr_thread = Thread(
                target=_drain_text_stream,
                args=(process.stderr, stderr_lines),
                daemon=True,
            )
            stderr_thread.start()

            if process.stdin is not None:
                process.stdin.write(build_codex_exec_prompt(system, prompt))
                process.stdin.close()

            try:
                yield from self._stream_process_stdout(process, stderr_lines)
            finally:
                stderr_thread.join(timeout=1)

            final_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
            if not final_text:
                raise CaseGenerationError("codex exec 未写入最终回复")
            yield {"type": "provider_final", "text": final_text}

    def _stream_process_stdout(
        self,
        process: subprocess.Popen[str],
        stderr_lines: list[str],
    ) -> Iterator[dict[str, Any]]:
        if process.stdout is None:
            raise CaseGenerationError("codex exec 未提供 JSON 事件输出")

        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            if time.monotonic() > deadline:
                process.kill()
                raise CaseGenerationError("codex exec 生成超时")

            line = process.stdout.readline()
            if not line:
                break
            event = parse_codex_exec_event(line)
            provider_event = codex_exec_event_to_provider_delta(event)
            if provider_event is not None:
                yield provider_event

        remaining = max(0.1, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            raise CaseGenerationError("codex exec 生成超时") from exc

        if returncode != 0:
            detail = "".join(stderr_lines).strip() or "codex exec 调用失败"
            raise CaseGenerationError(detail)

    def _resolve_executable(self) -> str:
        resolved = resolve_codex_executable(self.config.executable)
        if not resolved:
            raise CaseGenerationError("未找到 codex CLI，请确认 Codex 已安装，或把 CODEX_EXEC_COMMAND 配成绝对路径")
        return resolved

    def _resolve_cwd(self) -> Path:
        cwd = (self.config.cwd or Path.cwd()).expanduser()
        if not cwd.exists() or not cwd.is_dir():
            raise CaseGenerationError(f"codex exec 工作目录不存在：{cwd}")
        return cwd

    def _build_command(
        self,
        executable: str,
        cwd: Path,
        output_path: Path,
        *,
        json_events: bool = False,
        schema_path: Path | None = None,
    ) -> list[str]:
        command = [
            executable,
            "exec",
        ]
        if self.config.ephemeral:
            command.append("--ephemeral")
        if self.config.dangerously_bypass_approvals_and_sandbox:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        elif self.config.sandbox:
            command.extend(["--sandbox", _validated_sandbox(self.config.sandbox)])
        if self.config.dangerously_bypass_hook_trust:
            command.append("--dangerously-bypass-hook-trust")
        if self.config.strict_config:
            command.append("--strict-config")
        for path in self.config.image_paths:
            command.extend(["--image", str(path.expanduser())])
        for override in self.config.config_overrides:
            command.extend(["--config", override])
        for feature in self.config.enabled_features:
            command.extend(["--enable", feature])
        for feature in self.config.disabled_features:
            command.extend(["--disable", feature])
        command.extend(["--cd", str(cwd)])
        for path in self.config.add_dirs:
            command.extend(["--add-dir", str(path.expanduser())])
        if self.config.skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if self.config.ignore_user_config:
            command.append("--ignore-user-config")
        if self.config.ignore_rules:
            command.append("--ignore-rules")
        command.extend(["--color", "never"])
        if json_events:
            command.append("--json")
        if schema_path is not None:
            command.extend(["--output-schema", str(schema_path)])
        command.extend(["--output-last-message", str(output_path)])
        if self.config.model:
            command.extend(["--model", self.config.model])
        if self.config.oss:
            command.append("--oss")
        if self.config.local_provider:
            command.extend(["--local-provider", _validated_local_provider(self.config.local_provider)])
        if self.config.profile:
            command.extend(["--profile", self.config.profile])
        if self.config.profile_v2:
            command.extend(["--profile-v2", self.config.profile_v2])
        command.extend(self.config.extra_args)
        command.append("-")
        return command

    def _write_output_schema(self, temp_dir: str) -> Path | None:
        if not self.config.output_schema_enabled:
            return None
        schema_path = Path(temp_dir) / "case-generation.schema.json"
        schema_path.write_text(
            json.dumps(codex_exec_case_output_schema(), ensure_ascii=False),
            encoding="utf-8",
        )
        return schema_path


class CodexExecCaseProvider(CompletionCaseProvider):
    name = "codex_exec"

    def __init__(self, config: CodexExecConfig) -> None:
        super().__init__(
            name=self.name,
            mode="codex_exec",
            client=CodexExecCompletionClient(config),
            model=config.model,
            wire_api="codex_exec",
        )
        self.config = config

    def _client_for_context(self, context: CaseGenerationContext) -> CodexExecCompletionClient:
        return CodexExecCompletionClient(_config_for_generation_context(self.config, context))

    def _build_prompt_payload(self, context: CaseGenerationContext) -> dict[str, Any]:
        payload = super()._build_prompt_payload(context)
        return compact_codex_exec_payload(payload, execution_mode=context.execution_mode)

    @classmethod
    def from_settings(cls, settings: Settings) -> "CodexExecCaseProvider":
        config = settings.ai_provider_config or {}
        return cls(
            CodexExecConfig(
                executable=str(config.get("executable") or settings.codex_exec_command),
                model=_optional_string(_config_value(config, "model", settings.codex_exec_model)),
                profile=_optional_string(_config_value(config, "profile", settings.codex_exec_profile)),
                profile_v2=_optional_string(
                    _config_value(config, "profile_v2", settings.codex_exec_profile_v2)
                ),
                cwd=_optional_path(_config_value(config, "cwd", settings.codex_exec_cwd)),
                sandbox=_optional_sandbox(_config_value(config, "sandbox", settings.codex_exec_sandbox)),
                ephemeral=_bool_value(
                    _config_value(config, "ephemeral", settings.codex_exec_ephemeral),
                ),
                skip_git_repo_check=_bool_value(
                    _config_value(
                        config,
                        "skip_git_repo_check",
                        settings.codex_exec_skip_git_repo_check,
                    )
                ),
                ignore_user_config=_bool_value(
                    _config_value(config, "ignore_user_config", settings.codex_exec_ignore_user_config)
                ),
                ignore_rules=_bool_value(
                    _config_value(config, "ignore_rules", settings.codex_exec_ignore_rules)
                ),
                strict_config=_bool_value(
                    _config_value(config, "strict_config", settings.codex_exec_strict_config)
                ),
                output_schema_enabled=_bool_value(
                    _config_value(
                        config,
                        "output_schema_enabled",
                        settings.codex_exec_output_schema_enabled,
                    ),
                    default=True,
                ),
                oss=_bool_value(_config_value(config, "oss", settings.codex_exec_oss)),
                local_provider=_optional_string(
                    _config_value(config, "local_provider", settings.codex_exec_local_provider)
                ),
                image_paths=_path_tuple(
                    _config_value(config, "image_paths", settings.codex_exec_image_paths)
                ),
                add_dirs=_path_tuple(_config_value(config, "add_dirs", settings.codex_exec_add_dirs)),
                config_overrides=_string_tuple(
                    _config_value(
                        config,
                        "config_overrides",
                        settings.codex_exec_config_overrides,
                    )
                ),
                enabled_features=_string_tuple(
                    _config_value(config, "enabled_features", settings.codex_exec_enabled_features)
                ),
                disabled_features=_string_tuple(
                    _config_value(config, "disabled_features", settings.codex_exec_disabled_features)
                ),
                dangerously_bypass_approvals_and_sandbox=_bool_value(
                    _config_value(
                        config,
                        "dangerously_bypass_approvals_and_sandbox",
                        settings.codex_exec_dangerously_bypass_approvals_and_sandbox,
                    )
                ),
                dangerously_bypass_hook_trust=_bool_value(
                    _config_value(
                        config,
                        "dangerously_bypass_hook_trust",
                        settings.codex_exec_dangerously_bypass_hook_trust,
                    )
                ),
                timeout_seconds=int(
                    config.get("timeout_seconds")
                    or settings.codex_exec_timeout_seconds
                    or settings.ai_timeout_seconds
                ),
                extra_args=_string_tuple(config.get("extra_args")),
            )
        )


def build_codex_exec_prompt(system: str, prompt: str) -> str:
    """把 system/payload 合并为 `codex exec` 的单次非交互式输入。"""
    return "\n\n".join(
        [
            "你现在是 Beautiful E2E 后端的一次性 AI 生成进程。",
            "不要修改文件，不要运行命令，不要解释过程；最终回复必须只包含 JSON 对象。",
            "<system>",
            system,
            "</system>",
            "<payload>",
            prompt,
            "</payload>",
        ]
    )


def codex_exec_case_output_schema() -> dict[str, Any]:
    """返回 `codex exec --output-schema` 使用的用例 JSON 结构。

    Codex CLI 会把该 schema 透传给上游结构化输出；当前供应商要求声明过的
    对象字段全部出现在 required 中。可选标量字段用 null 表达，扩展上下文字段
    `data` 固定为空对象或业务对象，避免接口模式下模型把 method 容器整体置空。
    """
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "description", "priority", "steps"],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
            "steps": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "kind",
                        "label",
                        "action",
                        "selector",
                        "target_url",
                        "value",
                        "expected",
                        "data",
                    ],
                    "properties": {
                        "kind": {"type": ["string", "null"]},
                        "label": {"type": "string", "minLength": 1},
                        "action": {
                            "type": "string",
                            "enum": [
                                "goto",
                                "fill",
                                "click",
                                "expect_visible",
                                "expect_not_visible",
                                "expect_text",
                                "api_request",
                            ],
                        },
                        "selector": {"type": ["string", "null"]},
                        "target_url": {"type": ["string", "null"]},
                        "value": {"type": ["string", "null"]},
                        "expected": {"type": ["string", "null"]},
                        "data": {
                            "type": "object",
                            "properties": _codex_exec_step_data_schema_properties(),
                            "required": list(_codex_exec_step_data_schema_properties()),
                            "additionalProperties": True,
                        },
                    },
                },
            },
        },
    }


def _codex_exec_step_data_schema_properties() -> dict[str, Any]:
    """声明接口 DSL 常用扩展字段，兼容结构化输出的 required-all 子集。

    上游结构化输出不会稳定生成未声明的 additionalProperties 字段；把 method、
    extract 和路由证据这些常用键显式列出，模型才能在 backend_api 模式返回
    可执行接口步骤。未使用字段统一允许 null。
    """

    nullable_string = {"type": ["string", "null"]}
    nullable_object = {"type": ["object", "null"], "additionalProperties": True}
    nullable_array = {"type": ["array", "null"], "items": {"type": "object", "additionalProperties": True}}
    return {
        "method": {
            "type": ["string", "null"],
            "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", None],
        },
        "expected_status": {"type": ["integer", "null"]},
        "body": {"type": ["object", "string", "null"], "additionalProperties": True},
        "headers": nullable_object,
        "extract": nullable_object,
        "depends_on": nullable_array,
        "parameter_links": nullable_array,
        "unresolved_parameters": nullable_array,
        "missing_upstream_steps": nullable_array,
        "route_source": nullable_string,
        "route_summary": nullable_string,
        "route_parameters": nullable_array,
        "route_request_body": nullable_object,
        "route_responses": nullable_array,
        "reference_source": nullable_string,
        "reference_excerpt": nullable_string,
        "flow_reason": nullable_string,
    }


def _config_for_generation_context(
    config: CodexExecConfig,
    context: CaseGenerationContext,
) -> CodexExecConfig:
    if config.cwd is not None:
        return config
    inferred_cwd, inferred_add_dirs = _infer_codex_exec_paths(context)
    if inferred_cwd is None and not inferred_add_dirs:
        return config
    add_dirs = _unique_paths((*config.add_dirs, *inferred_add_dirs))
    return CodexExecConfig(
        executable=config.executable,
        model=config.model,
        profile=config.profile,
        profile_v2=config.profile_v2,
        cwd=inferred_cwd,
        sandbox=config.sandbox,
        ephemeral=config.ephemeral,
        skip_git_repo_check=config.skip_git_repo_check,
        ignore_user_config=config.ignore_user_config,
        ignore_rules=config.ignore_rules,
        strict_config=config.strict_config,
        output_schema_enabled=config.output_schema_enabled,
        oss=config.oss,
        local_provider=config.local_provider,
        image_paths=config.image_paths,
        add_dirs=add_dirs,
        config_overrides=config.config_overrides,
        enabled_features=config.enabled_features,
        disabled_features=config.disabled_features,
        dangerously_bypass_approvals_and_sandbox=(
            config.dangerously_bypass_approvals_and_sandbox
        ),
        dangerously_bypass_hook_trust=config.dangerously_bypass_hook_trust,
        timeout_seconds=config.timeout_seconds,
        extra_args=config.extra_args,
    )


def _infer_codex_exec_paths(context: CaseGenerationContext) -> tuple[Path | None, tuple[Path, ...]]:
    repo_paths = [
        _existing_directory(context.frontend.path),
        _existing_directory(context.backend.path),
    ]
    frontend_path, backend_path = repo_paths
    if context.execution_mode == "backend_api" and backend_path is not None:
        cwd = backend_path
    else:
        cwd = frontend_path or backend_path
    add_dirs = tuple(path for path in repo_paths if path is not None and path != cwd)
    return cwd, add_dirs


def _existing_directory(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    return path if path.exists() and path.is_dir() else None


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def parse_codex_exec_event(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def codex_exec_event_to_provider_delta(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    candidates = list(_codex_event_candidates(event))
    event_type = _codex_event_type(candidates)
    if not event_type:
        return None

    normalized_type = event_type.lower()
    if _is_codex_reasoning_event(normalized_type):
        channel = "reasoning"
    elif _is_codex_content_event(normalized_type):
        channel = "content"
    else:
        return None

    delta = _codex_event_text(candidates)
    if not delta:
        return None

    # `codex exec --json` 是 Codex CLI 对供应商 SSE 的事件映射。这里只展示 CLI
    # 明确暴露的 reasoning/content 增量，不从普通日志或工具输出里推测思考内容。
    label = "供应商思考" if channel == "reasoning" else "供应商输出"
    return {
        "type": "provider_delta",
        "channel": channel,
        "delta": delta,
        "message": delta,
        "label": label,
        "vendor_event_type": event_type,
        "collect": channel == "content",
    }


def _codex_event_candidates(event: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from _nested_codex_event_candidates(event, depth=0)


def _nested_codex_event_candidates(event: dict[str, Any], *, depth: int) -> Iterator[dict[str, Any]]:
    yield event
    if depth >= 3:
        return
    for key in ("msg", "params", "event", "payload", "item"):
        value = event.get(key)
        if isinstance(value, dict):
            yield from _nested_codex_event_candidates(value, depth=depth + 1)


def _codex_event_type(candidates: list[dict[str, Any]]) -> str:
    fallback = ""
    for item in candidates:
        for key in ("type", "method", "event", "name"):
            value = item.get(key)
            if isinstance(value, str) and value:
                normalized = value.lower()
                if _is_codex_reasoning_event(normalized) or _is_codex_content_event(normalized):
                    return value
                # Codex CLI 0.133 会把最终文本包在 `item.completed.item` 内层。
                # 外层只是生命周期事件，继续扫描内层才能拿到可展示内容。
                if value in {
                    "event_msg",
                    "item.completed",
                    "item.started",
                    "response_item",
                    "raw_response_item",
                }:
                    fallback = value
                    continue
                if not fallback:
                    fallback = value
    return fallback


def _codex_event_text(candidates: list[dict[str, Any]]) -> str:
    for item in candidates:
        for key in ("delta", "text", "content", "message", "summary_text", "raw_content"):
            value = item.get(key)
            text = _codex_text_value(value)
            if text:
                return text
    return ""


def _is_codex_reasoning_event(event_type: str) -> bool:
    return (
        "reasoning" in event_type
        or "thinking" in event_type
        or event_type == "item/reasoning/textdelta"
        or event_type == "item/reasoning/summarytextdelta"
    )


def _is_codex_content_event(event_type: str) -> bool:
    return (
        "agent_message_content_delta" in event_type
        or event_type == "agent_message"
        or "output_text_delta" in event_type
        or "output_text.delta" in event_type
    )


def _codex_text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                nested = _codex_text_value(
                    item.get("text") or item.get("summary_text") or item.get("content")
                )
                if nested:
                    parts.append(nested)
        return "".join(parts)
    return ""


def _drain_text_stream(stream: Any, sink: list[str]) -> None:
    if stream is None:
        return
    for line in stream:
        sink.append(str(line))


def resolve_codex_executable(command: str) -> str | None:
    """解析 `codex exec` 可执行文件。

    后端服务常由 GUI 或守护进程启动，PATH 不一定等于用户交互式终端。这里额外
    检查 Codex.app 内置 CLI，避免页面把终端可用的 Codex 误判为不可用。
    """
    normalized = command.strip() or "codex"
    if "/" in normalized:
        path = Path(normalized).expanduser()
        return str(path) if path.exists() and path.is_file() else None

    resolved = shutil.which(normalized)
    if resolved:
        return resolved

    if normalized == "codex":
        for candidate in CODEX_APP_EXECUTABLES:
            if candidate.exists() and candidate.is_file():
                return str(candidate)

    return None


def _config_value(config: dict[str, Any], key: str, fallback: Any) -> Any:
    return config[key] if key in config else fallback


def _validated_sandbox(value: str) -> str:
    normalized = value.strip() or "read-only"
    if normalized not in CODEX_SANDBOX_MODES:
        raise CaseGenerationError(
            f"codex exec sandbox 不支持：{normalized}，可选值：{', '.join(sorted(CODEX_SANDBOX_MODES))}"
        )
    return normalized


def _optional_sandbox(value: object) -> str | None:
    text = _optional_string(value)
    if text is None or text == "inherit":
        return None
    return _validated_sandbox(text)


def _validated_local_provider(value: str) -> str:
    normalized = value.strip()
    if normalized not in CODEX_LOCAL_PROVIDERS:
        raise CaseGenerationError(
            f"codex exec local provider 不支持：{normalized}，可选值：{', '.join(sorted(CODEX_LOCAL_PROVIDERS))}"
        )
    return normalized


def _bool_value(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    return Path(text) if text else None


def _path_tuple(value: object) -> tuple[Path, ...]:
    return tuple(
        path
        for path in (_optional_path(item) for item in _raw_string_items(value))
        if path is not None
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(_raw_string_items(value))


def _raw_string_items(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ()
    separators = "\n" if "\n" in text else ","
    if separators in text:
        return tuple(item.strip() for item in text.split(separators) if item.strip())
    return tuple(text.split())
