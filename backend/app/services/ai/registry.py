from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from app.core.config import Settings
from app.services.api_generation_feedback import attach_api_generation_feedback
from app.services.api_flow_diagnostics import annotate_api_flow_diagnostics
from app.services.api_route_contract_enforcer import enforce_api_route_contracts
from app.services.ai.base import CaseGenerationContext, CaseGenerationError, CaseGenerationProvider
from app.services.ai.codex_bridge import CodexBridgeCaseProvider, OpenAICompatibleCaseProvider
from app.services.ai.codex_exec import CodexExecCaseProvider
from app.services.ai.rule_based import RuleBasedCaseProvider
from app.services.ai_case_generator import CaseGenerator, GeneratedCase

ProviderFactory = Callable[[Settings], CaseGenerationProvider]


@dataclass(frozen=True)
class ProviderDescriptor:
    """前端 AI 配置弹窗消费的供应商元信息。"""

    name: str
    label: str
    description: str
    mode: str
    protocol: str
    configurable: bool
    env_vars: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "mode": self.mode,
            "protocol": self.protocol,
            "configurable": self.configurable,
            "env_vars": list(self.env_vars),
        }


def available_provider_names() -> list[str]:
    return sorted(_builtin_factories())


def available_provider_descriptors(settings: Settings) -> list[dict[str, Any]]:
    """返回内置供应商和当前自定义入口的展示信息。"""
    descriptors = [descriptor.as_dict() for descriptor in _builtin_descriptors().values()]
    if settings.ai_provider_entrypoint:
        descriptors.append(
            {
                "name": "custom_entrypoint",
                "label": "自定义 Python 供应商",
                "description": "通过 AI_PROVIDER_ENTRYPOINT 注入团队内部供应商工厂。",
                "mode": "custom",
                "protocol": "python_entrypoint",
                "configurable": True,
                "env_vars": ["AI_PROVIDER_ENTRYPOINT"],
                "entrypoint": settings.ai_provider_entrypoint,
            }
        )
    return sorted(descriptors, key=lambda item: str(item["name"]))


def build_case_generation_provider(settings: Settings) -> CaseGenerationProvider:
    """构建已配置的供应商，并避免把供应商细节泄漏到 API 路由。"""
    if settings.ai_provider_entrypoint:
        return _load_entrypoint_provider(settings.ai_provider_entrypoint, settings)

    provider_name = settings.ai_provider.strip() or "codex_exec"
    factories = _builtin_factories()
    factory = factories.get(provider_name)
    if factory is None:
        raise CaseGenerationError(
            f"未知 AI 供应商：{provider_name}。"
            f"内置供应商：{', '.join(sorted(factories))}"
        )
    return factory(settings)


def generate_case_with_provider(
    settings: Settings,
    context: CaseGenerationContext,
) -> GeneratedCase:
    provider = build_case_generation_provider(settings)
    try:
        return _annotate_generated_case(provider.generate(context), context)
    except Exception as exc:
        if provider.name == "rule_based" or not settings.ai_fallback_rule_based:
            if isinstance(exc, CaseGenerationError):
                raise
            raise CaseGenerationError(str(exc)) from exc
        fallback = RuleBasedCaseProvider().generate(context)
        if fallback.code_context is not None:
            fallback.code_context["generation_mode"] = f"rule_based_after_{provider.name}_error"
            fallback.code_context["ai_provider_error"] = str(exc)
            fallback.code_context["failed_ai_provider"] = provider.name
            if provider.name == "codex_bridge":
                fallback.code_context["codex_bridge_error"] = str(exc)
        return _annotate_generated_case(fallback, context)


def stream_case_with_provider(
    settings: Settings,
    context: CaseGenerationContext,
) -> Iterator[dict[str, Any]]:
    """流式调用供应商，并在最终事件中返回 `GeneratedCase`。

    支持 SSE 的供应商会把显式返回的 reasoning/content 增量透传给 API 层；
    不支持流式明细的供应商仍走同步生成，保持既有回退语义。
    """
    provider = build_case_generation_provider(settings)
    try:
        stream_generate = getattr(provider, "stream_generate", None)
        if callable(stream_generate):
            for event in stream_generate(context):
                yield _annotate_provider_event(event, context)
            return
        yield {
            "type": "progress",
            "message": f"{provider.name} 不支持供应商 SSE 明细，等待最终生成结果。",
            "stage": "provider_stream_unavailable",
            "provider": provider.name,
        }
        yield {
            "type": "generated_case",
            "case": _annotate_generated_case(provider.generate(context), context),
        }
    except Exception as exc:
        if provider.name == "rule_based" or not settings.ai_fallback_rule_based:
            if isinstance(exc, CaseGenerationError):
                raise
            raise CaseGenerationError(str(exc)) from exc
        fallback = RuleBasedCaseProvider().generate(context)
        if fallback.code_context is not None:
            fallback.code_context["generation_mode"] = f"rule_based_after_{provider.name}_error"
            fallback.code_context["ai_provider_error"] = str(exc)
            fallback.code_context["failed_ai_provider"] = provider.name
            if provider.name == "codex_bridge":
                fallback.code_context["codex_bridge_error"] = str(exc)
        yield {
            "type": "progress",
            "message": f"{provider.name} 供应商失败，已切换本地规则生成器。",
            "stage": "provider_fallback",
            "provider": provider.name,
        }
        yield {"type": "generated_case", "case": _annotate_generated_case(fallback, context)}


def _annotate_provider_event(
    event: dict[str, Any],
    context: CaseGenerationContext,
) -> dict[str, Any]:
    if event.get("type") != "generated_case":
        return event
    generated = event.get("case")
    if not isinstance(generated, GeneratedCase):
        return event
    return {**event, "case": _annotate_generated_case(generated, context)}


def _annotate_generated_case(
    generated: GeneratedCase,
    context: CaseGenerationContext,
) -> GeneratedCase:
    if context.execution_mode != "backend_api":
        return generated
    enforced = enforce_api_route_contracts(
        generated,
        context.backend.routes,
        context.reference_documents,
    )
    enforced = GeneratedCase(
        title=enforced.title,
        description=enforced.description,
        priority=enforced.priority,
        steps=enforced.steps,
        graph=CaseGenerator()._graph_for_steps(
            enforced.steps,
            context.frontend,
            context.backend,
            execution_mode=context.execution_mode,
        ),
        code_context=enforced.code_context,
    )
    diagnosed = annotate_api_flow_diagnostics(enforced, context.backend.routes)
    return attach_api_generation_feedback(diagnosed)


def _builtin_factories() -> dict[str, ProviderFactory]:
    return {
        "codex_bridge": lambda settings: CodexBridgeCaseProvider.from_settings(settings),
        "codex_exec": lambda settings: CodexExecCaseProvider.from_settings(settings),
        "openai_compatible": lambda settings: OpenAICompatibleCaseProvider.from_settings(settings),
        "rule_based": lambda settings: RuleBasedCaseProvider(),
    }


def _builtin_descriptors() -> dict[str, ProviderDescriptor]:
    return {
        "codex_exec": ProviderDescriptor(
            name="codex_exec",
            label="Codex Exec",
            description="直接调用本机 codex exec，由 Codex CLI 复用当前账号、模型和配置。",
            mode="codex_exec",
            protocol="codex_cli",
            configurable=True,
            env_vars=(
                "AI_PROVIDER=codex_exec",
                "CODEX_EXEC_COMMAND",
                "CODEX_EXEC_MODEL",
                "CODEX_EXEC_PROFILE",
                "CODEX_EXEC_PROFILE_V2",
                "CODEX_EXEC_CWD",
                "CODEX_EXEC_SANDBOX",
                "CODEX_EXEC_EPHEMERAL",
                "CODEX_EXEC_IMAGE_PATHS",
                "CODEX_EXEC_ADD_DIRS",
                "CODEX_EXEC_CONFIG_OVERRIDES",
            ),
        ),
        "codex_bridge": ProviderDescriptor(
            name="codex_bridge",
            label="GPT HTTP 桥接",
            description="使用系统内置的 OpenAI 兼容 HTTP 桥接，可读取 Codex 本地配置作为兜底。",
            mode="gpt_http_bridge",
            protocol="openai_http",
            configurable=True,
            env_vars=(
                "AI_PROVIDER=codex_bridge",
                "AI_API_KEY",
                "AI_BASE_URL",
                "AI_MODEL",
                "AI_WIRE_API",
            ),
        ),
        "openai_compatible": ProviderDescriptor(
            name="openai_compatible",
            label="自定义 OpenAI 兼容",
            description="接入互联网上通用的 OpenAI 兼容 chat/completions 或 responses 协议。",
            mode="openai_compatible_http",
            protocol="openai_http",
            configurable=True,
            env_vars=(
                "AI_PROVIDER=openai_compatible",
                "AI_API_KEY",
                "AI_BASE_URL",
                "AI_MODEL",
                "AI_WIRE_API",
            ),
        ),
        "rule_based": ProviderDescriptor(
            name="rule_based",
            label="本地规则生成器",
            description="离线确定性生成器，适合作为兜底，不依赖外部模型。",
            mode="local",
            protocol="deterministic",
            configurable=False,
            env_vars=("AI_PROVIDER=rule_based",),
        ),
    }


def _load_entrypoint_provider(entrypoint: str, settings: Settings) -> CaseGenerationProvider:
    """从 `module:function` 加载自定义供应商工厂。

    这里故意保持扩展契约很小：工厂接收 Settings，并返回任意带
    `generate(context)` 方法和 `name` 属性的对象。
    """
    module_name, separator, attr_name = entrypoint.partition(":")
    if not separator or not module_name or not attr_name:
        raise CaseGenerationError("AI_PROVIDER_ENTRYPOINT 必须使用 'module:function' 格式")

    try:
        module = import_module(module_name)
        factory = getattr(module, attr_name)
        provider = factory(settings)
    except Exception as exc:
        raise CaseGenerationError(f"加载 AI 供应商入口失败 {entrypoint}: {exc}") from exc

    if not _looks_like_provider(provider):
        raise CaseGenerationError(
            f"AI 供应商入口 {entrypoint} 未返回兼容的供应商对象"
        )
    return provider


def _looks_like_provider(candidate: Any) -> bool:
    return isinstance(getattr(candidate, "name", None), str) and callable(
        getattr(candidate, "generate", None)
    )
