from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Protocol

from app.core.config import Settings
from app.models import TestStep
from app.services.ai.case_completion import parse_case_generation_json
from app.services.ai.codex_bridge import CodexHttpCompletionClient


class RuntimeInferenceClient(Protocol):
    """运行期变量推导使用的最小 AI 客户端契约。"""

    def complete(self, system: str, prompt: str) -> str:
        """根据前序响应和缺失变量返回 JSON 推导结果。"""


@dataclass(frozen=True)
class ApiFlowResponseHistory:
    step_id: str
    order_index: int
    label: str
    status_code: int | None
    response_preview: str
    extracted_variables: dict[str, Any]

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "order_index": self.order_index,
            "label": self.label,
            "status_code": self.status_code,
            "response_preview": self.response_preview[:4000],
            "extracted_variable_names": sorted(self.extracted_variables),
        }


@dataclass(frozen=True)
class RuntimeVariableInference:
    variable: str
    value: Any
    confidence: float
    source: str
    source_step_label: str | None
    source_json_path: str | None
    reason: str

    def event_payload(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "confidence": self.confidence,
            "source": self.source,
            "source_step_label": self.source_step_label,
            "source_json_path": self.source_json_path,
            "reason": self.reason,
        }


class ApiFlowRuntimeAgent:
    """接口运行期参数推导 agent。

    它只能从已经执行过的响应中提取变量；没有前序响应时直接失败，避免把缺失
    上游步骤伪装成环境变量或固定值。
    """

    def __init__(
        self,
        *,
        ai_client: RuntimeInferenceClient | None = None,
        min_confidence: float = 0.65,
        project_context: dict[str, Any] | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.min_confidence = min_confidence
        self.project_context = project_context or {}

    def infer_missing_variable(
        self,
        *,
        variable: str,
        step: TestStep,
        known_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
    ) -> RuntimeVariableInference | None:
        if variable in known_variables or not response_history:
            return None

        deterministic = self._deterministic_inference(variable, response_history)
        if deterministic is not None:
            return deterministic

        if self.ai_client is None:
            return None
        ai_result = self._ai_inference(variable, step, known_variables, response_history)
        if ai_result is None or ai_result.confidence < self.min_confidence:
            return None
        return ai_result

    def _deterministic_inference(
        self,
        variable: str,
        response_history: list[ApiFlowResponseHistory],
    ) -> RuntimeVariableInference | None:
        aliases = _variable_aliases(variable)
        for history in reversed(response_history):
            parsed = _json_from_preview(history.response_preview)
            if parsed is None:
                continue
            found = _find_first_alias(parsed, aliases)
            if found is None:
                continue
            path, value = found
            return RuntimeVariableInference(
                variable=variable,
                value=value,
                confidence=0.9,
                source="deterministic_response_alias",
                source_step_label=history.label,
                source_json_path=path,
                reason="根据变量名和前序响应字段别名自动匹配。",
            )
        return None

    def _ai_inference(
        self,
        variable: str,
        step: TestStep,
        known_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
    ) -> RuntimeVariableInference | None:
        system = (
            "你是接口测试运行期参数推导 agent。只允许从已执行接口响应中抽取缺失变量，"
            "不能编造、不能使用外部知识、不能猜固定 ID。"
            "如果 project_context.auth 表明登录态来自环境请求头，不要把认证 header 当作前序响应变量推导。"
            "只返回 JSON 对象。"
        )
        payload = {
            "project_context": self.project_context,
            "missing_variable": variable,
            "current_step": {
                "label": step.label,
                "target_url": step.target_url,
                "data": step.data or {},
            },
            "known_variable_names": sorted(known_variables),
            "previous_responses": [item.as_prompt_dict() for item in response_history[-8:]],
            "json_schema": {
                "variable": variable,
                "value": "从 previous_responses 中找到的值；找不到返回 null",
                "confidence": "0 到 1",
                "source_step_label": "来源步骤 label|null",
                "source_json_path": "来源 JSONPath|null",
                "reason": "中文说明，必须指出来自哪条响应",
            },
        }
        try:
            raw = self.ai_client.complete(system=system, prompt=json.dumps(payload, ensure_ascii=False))
            obj = parse_case_generation_json(raw, "runtime_inference_agent")
        except Exception:
            return None

        value = obj.get("value")
        if value is None:
            return None
        confidence = _float_confidence(obj.get("confidence"))
        return RuntimeVariableInference(
            variable=str(obj.get("variable") or variable),
            value=value,
            confidence=confidence,
            source="ai_response_inference",
            source_step_label=_string_or_none(obj.get("source_step_label")),
            source_json_path=_string_or_none(obj.get("source_json_path")),
            reason=str(obj.get("reason") or "AI 从前序响应中推导变量。"),
        )


def build_api_flow_runtime_agent(
    settings: Settings,
    *,
    project_context: dict[str, Any] | None = None,
) -> ApiFlowRuntimeAgent:
    """按当前 AI 配置构建运行期推导 agent。"""

    client: RuntimeInferenceClient | None = None
    if settings.api_runtime_ai_inference_enabled:
        client = _runtime_ai_client_from_settings(settings)
    return ApiFlowRuntimeAgent(
        ai_client=client,
        min_confidence=settings.api_runtime_ai_inference_min_confidence,
        project_context=project_context,
    )


def _runtime_ai_client_from_settings(settings: Settings) -> RuntimeInferenceClient | None:
    provider_name = settings.ai_provider.strip()
    if provider_name not in {"codex_bridge", "openai_compatible"}:
        return None

    config = settings.ai_provider_config or {}
    return CodexHttpCompletionClient(
        model=str(config.get("model") or settings.codex_bridge_model or settings.ai_model),
        wire_api=str(config.get("wire_api") or settings.codex_bridge_wire_api or settings.ai_wire_api),
        reasoning_effort=str(
            config.get("reasoning_effort")
            or settings.codex_bridge_reasoning_effort
            or settings.ai_reasoning_effort
        ),
        timeout_seconds=int(
            config.get("runtime_timeout_seconds")
            or settings.api_runtime_ai_inference_timeout_seconds
        ),
        max_tokens=min(int(config.get("runtime_max_tokens") or 900), int(settings.ai_max_tokens)),
        api_key=str(config.get("api_key") or settings.ai_api_key or "") or None,
        base_url=str(config.get("base_url") or settings.ai_base_url or "") or None,
        codex_home=settings.ai_codex_home if provider_name == "codex_bridge" else None,
    )


def _variable_aliases(variable: str) -> list[str]:
    normalized = _normalize_name(variable)
    parts = [part for part in re.split(r"[_\-.]+", normalized) if part]
    aliases = {variable, normalized, _camel_case(parts)}
    if parts:
        aliases.add(parts[-1])
    if parts and parts[-1] == "id":
        aliases.add("id")
        aliases.add(_camel_case(parts[-2:]))
    if "token" in parts:
        aliases.update({"token", "accessToken", "saToken", "satoken", "Authorization"})
    return [alias for alias in aliases if alias]


def _normalize_name(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return text.replace("-", "_").replace(".", "_").lower()


def _camel_case(parts: list[str]) -> str:
    if not parts:
        return ""
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _json_from_preview(preview: str) -> Any | None:
    text = preview.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([index for index in [text.find("{"), text.find("[")] if index >= 0], default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def _find_first_alias(payload: Any, aliases: list[str], path: str = "$") -> tuple[str, Any] | None:
    if isinstance(payload, dict):
        lowered = {str(key).lower(): key for key in payload}
        for alias in aliases:
            key = lowered.get(alias.lower())
            if key is not None:
                return f"{path}.{key}" if path != "$" else f"$.{key}", payload[key]
        for key, value in payload.items():
            found = _find_first_alias(value, aliases, f"{path}.{key}" if path != "$" else f"$.{key}")
            if found is not None:
                return found
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            found = _find_first_alias(item, aliases, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _float_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    try:
        return max(0.0, min(float(str(value)), 1.0))
    except ValueError:
        return 0.0


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
