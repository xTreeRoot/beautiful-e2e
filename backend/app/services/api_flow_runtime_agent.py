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


@dataclass(frozen=True)
class ApiFlowFailureAttempt:
    attempt: int
    status_code: int | None
    expected_status: int
    error: str | None
    response_preview: str
    response_content_type: str | None
    request: dict[str, Any]

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "status_code": self.status_code,
            "expected_status": self.expected_status,
            "error": self.error,
            "response_preview": self.response_preview[:4000],
            "response_content_type": self.response_content_type,
            "request": self.request,
        }


@dataclass(frozen=True)
class RuntimeRequestRepair:
    confidence: float
    source: str
    reason: str
    variable_updates: dict[str, Any]
    body_patch: dict[str, Any]
    body: Any | None = None

    def has_changes(self) -> bool:
        return self.body is not None or bool(self.body_patch) or bool(self.variable_updates)

    def event_payload(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "source": self.source,
            "reason": self.reason,
            "variable_names": sorted(self.variable_updates),
            "body_patch_keys": sorted(self.body_patch),
            "body_replaced": self.body is not None,
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
            if parsed is not None:
                found = _find_first_alias(parsed, aliases)
                if found is not None:
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
            text_found = _find_first_alias_in_text(history.response_preview, aliases)
            if text_found is None:
                continue
            path, value = text_found
            return RuntimeVariableInference(
                variable=variable,
                value=value,
                confidence=0.82,
                source="deterministic_response_alias",
                source_step_label=history.label,
                source_json_path=path,
                reason="前序响应预览不是完整 JSON，已按变量名字段从原始响应文本匹配。",
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
                "source_json_path": "来源 JSONPath|null；枚举对象必须指向 key/code/value/id 这类标量叶子",
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

    def repair_failed_request(
        self,
        *,
        step: TestStep,
        known_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
        failed_attempts: list[ApiFlowFailureAttempt],
    ) -> RuntimeRequestRepair | None:
        """根据失败响应为下一次请求准备业务数据修复。

        修复只作用于变量和请求体，不改认证请求头；每次调用都会看到完整失败尝试，
        让 AI 或确定性规则能基于上一次返回继续收敛参数。
        """

        if not failed_attempts:
            return None

        deterministic = self._deterministic_request_repair(failed_attempts[-1])
        if deterministic is not None:
            return deterministic

        if self.ai_client is None:
            return None
        ai_result = self._ai_request_repair(step, known_variables, response_history, failed_attempts)
        if ai_result is None or ai_result.confidence < self.min_confidence:
            return None
        return ai_result

    def _deterministic_request_repair(
        self,
        failed_attempt: ApiFlowFailureAttempt,
    ) -> RuntimeRequestRepair | None:
        body = failed_attempt.request.get("body")
        changed, repaired_body = _enum_like_body_scalars(body)
        if not changed:
            return None
        return RuntimeRequestRepair(
            confidence=0.88,
            source="deterministic_enum_body_leaf",
            reason="失败请求体包含枚举/选项对象，下一次尝试改用其中的稳定标量值。",
            variable_updates={},
            body_patch={},
            body=repaired_body,
        )

    def _ai_request_repair(
        self,
        step: TestStep,
        known_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
        failed_attempts: list[ApiFlowFailureAttempt],
    ) -> RuntimeRequestRepair | None:
        system = (
            "你是接口测试运行期失败重试 agent。只能根据当前步骤、已执行响应、"
            "本接口每次失败响应和已知变量，为下一次请求准备业务参数。"
            "不要修改认证 header，不要编造外部固定值，不要输出真实请求头。"
            "如果无法从失败上下文或前序响应确定修复值，返回空修复和低置信度。"
            "只返回 JSON 对象。"
        )
        payload = {
            "project_context": self.project_context,
            "current_step": {
                "label": step.label,
                "target_url": step.target_url,
                "data": step.data or {},
            },
            "known_variable_names": sorted(known_variables),
            "previous_responses": [item.as_prompt_dict() for item in response_history[-8:]],
            "failed_attempts": [item.as_prompt_dict() for item in failed_attempts[-3:]],
            "json_schema": {
                "confidence": "0 到 1",
                "variables": "需要覆盖或补充的变量对象；只写业务变量",
                "body_patch": "需要浅合并到请求 body 的字段对象",
                "body": "需要替换整个请求 body 时返回对象/数组/字符串，否则为 null",
                "reason": "中文说明，必须指出使用了哪次失败响应或前序响应",
            },
        }
        try:
            raw = self.ai_client.complete(system=system, prompt=json.dumps(payload, ensure_ascii=False))
            obj = parse_case_generation_json(raw, "runtime_request_repair_agent")
        except Exception:
            return None

        repair = RuntimeRequestRepair(
            confidence=_float_confidence(obj.get("confidence")),
            source="ai_failure_context_repair",
            reason=str(obj.get("reason") or "AI 根据失败响应准备下一次请求数据。"),
            variable_updates=_dict_or_empty(obj.get("variables")),
            body_patch=_dict_or_empty(obj.get("body_patch")),
            body=obj.get("body") if obj.get("body") is not None else None,
        )
        return repair if repair.has_changes() else None


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
    aliases = [variable, normalized, _camel_case(parts)]
    if parts:
        aliases.append(parts[-1])
    if parts and parts[-1] == "id":
        aliases.extend([_camel_case(parts[-2:]), "id"])
    if "token" in parts:
        aliases.extend(["accessToken", "token", "saToken", "satoken", "Authorization"])
    return _unique_aliases(aliases)


def _unique_aliases(aliases: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        if not alias:
            continue
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(alias)
    return result


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
                matched_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                scalar_leaf = _preferred_object_scalar_leaf(payload[key])
                if scalar_leaf is not None:
                    leaf_key, leaf_value = scalar_leaf
                    return f"{matched_path}.{leaf_key}", leaf_value
                return matched_path, payload[key]
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


def _preferred_object_scalar_leaf(value: Any) -> tuple[str, Any] | None:
    """同名字段是枚举/选项对象时，优先返回可直接放入请求参数的稳定标量。

    运行期变量通常用于 path、query、headers 或 body 字段；如果把整个
    `{key,label,value}` 对象塞回请求体，后端 DTO 往往会绑定失败。
    """

    if not isinstance(value, dict):
        return None

    lowered = {str(key).lower(): key for key in value}
    for preferred in ("key", "code", "value", "id"):
        key = lowered.get(preferred)
        if key is None:
            continue
        scalar = value.get(key)
        if _is_non_null_scalar(scalar):
            return str(key), scalar

    scalar_entries = [
        (str(key), item)
        for key, item in value.items()
        if _is_non_null_scalar(item)
    ]
    if len(scalar_entries) == 1:
        return scalar_entries[0]
    return None


def _is_non_null_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def _enum_like_body_scalars(value: Any) -> tuple[bool, Any]:
    """把请求体里明显的枚举/选项对象替换成可被 DTO 接收的标量。"""

    if isinstance(value, dict):
        scalar_leaf = _preferred_enum_like_scalar_leaf(value)
        if scalar_leaf is not None:
            return True, scalar_leaf[1]

        changed = False
        next_value: dict[str, Any] = {}
        for key, item in value.items():
            item_changed, next_item = _enum_like_body_scalars(item)
            changed = changed or item_changed
            next_value[str(key)] = next_item
        return changed, next_value

    if isinstance(value, list):
        changed = False
        next_items: list[Any] = []
        for item in value:
            item_changed, next_item = _enum_like_body_scalars(item)
            changed = changed or item_changed
            next_items.append(next_item)
        return changed, next_items

    return False, value


def _preferred_enum_like_scalar_leaf(value: Any) -> tuple[str, Any] | None:
    if not isinstance(value, dict):
        return None

    lowered = {str(key).lower(): key for key in value}
    descriptor_keys = {"label", "name", "title", "desc", "description", "text"}
    has_descriptor = any(key in lowered for key in descriptor_keys)
    has_value_pair = "value" in lowered and len(value) > 1
    if not has_descriptor and not has_value_pair:
        return None

    for preferred in ("key", "code", "value"):
        key = lowered.get(preferred)
        if key is None:
            continue
        scalar = value.get(key)
        if _is_non_null_scalar(scalar):
            return str(key), scalar
    return None


def _find_first_alias_in_text(text: str, aliases: list[str]) -> tuple[str, Any] | None:
    """从被截断的 JSON 预览中按字段名提取基础值。

    运行面板只保留响应预览，大分页响应尾部被截断时无法整体解析为 JSON；
    这里只接受 JSON 对象字段的字符串、数字、布尔和 null，避免从任意文本里猜值。
    """

    if not text.strip():
        return None
    value_pattern = r'"((?:\\.|[^"\\])*)"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null'
    for alias in aliases:
        pattern = re.compile(
            rf'"(?P<key>{re.escape(alias)})"\s*:\s*(?P<value>{value_pattern})',
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match is None:
            continue
        value = _parse_json_scalar(match.group("value"))
        if value is not None:
            return f"$..{match.group('key')}", value
    return None


def _parse_json_scalar(token: str) -> Any | None:
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        return None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if str(key).strip()
    }


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
