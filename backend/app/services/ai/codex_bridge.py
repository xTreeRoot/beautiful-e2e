from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.ai.base import CaseGenerationError
from app.services.ai.case_completion import CompletionCaseProvider
from app.services.ai.codex_http_bridge import (
    CodexHttpBridgeConfig,
    CodexHttpBridgeError,
    CodexProviderHttpBridge,
)


class CodexHttpCompletionClient:
    """Codex/OpenAI 兼容 HTTP 文本补全客户端。

    本类只处理连接配置和 HTTP 调用错误；用例提示词、步骤结构和解析规则统一由
    `case_completion` 模块负责，避免桥接层混入业务语义。
    """

    def __init__(
        self,
        *,
        model: str,
        wire_api: str = "responses",
        reasoning_effort: str = "xhigh",
        timeout_seconds: int = 180,
        max_tokens: int = 3000,
        api_key: str | None = None,
        base_url: str | None = None,
        codex_home: Path | None = None,
    ) -> None:
        self.config = CodexHttpBridgeConfig(
            model=model,
            wire_api=wire_api,
            api_key=api_key,
            base_url=base_url,
            codex_home=codex_home,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )

    def complete(self, system: str, prompt: str) -> str:
        try:
            return CodexProviderHttpBridge(self.config).complete(system=system, prompt=prompt)
        except CodexHttpBridgeError as exc:
            raise CaseGenerationError(str(exc)) from exc

    def stream_complete(self, system: str, prompt: str) -> Iterator[dict[str, Any]]:
        try:
            yield from CodexProviderHttpBridge(self.config).stream_complete(system=system, prompt=prompt)
        except CodexHttpBridgeError as exc:
            raise CaseGenerationError(str(exc)) from exc


class CodexBridgeCaseProvider(CompletionCaseProvider):
    name = "codex_bridge"

    def __init__(
        self,
        *,
        model: str,
        wire_api: str = "responses",
        reasoning_effort: str = "xhigh",
        timeout_seconds: int = 180,
        max_tokens: int = 3000,
        api_key: str | None = None,
        base_url: str | None = None,
        codex_home: Path | None = None,
    ) -> None:
        super().__init__(
            name=self.name,
            mode="gpt_http_bridge",
            client=CodexHttpCompletionClient(
                model=model,
                wire_api=wire_api,
                reasoning_effort=reasoning_effort,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                api_key=api_key,
                base_url=base_url,
                codex_home=codex_home,
            ),
            model=model,
            wire_api=wire_api,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "CodexBridgeCaseProvider":
        config = settings.ai_provider_config or {}
        return cls(
            model=str(config.get("model") or settings.codex_bridge_model or settings.ai_model),
            wire_api=str(config.get("wire_api") or settings.codex_bridge_wire_api or settings.ai_wire_api),
            reasoning_effort=str(
                config.get("reasoning_effort")
                or settings.codex_bridge_reasoning_effort
                or settings.ai_reasoning_effort
            ),
            timeout_seconds=int(
                config.get("timeout_seconds")
                or settings.codex_bridge_timeout_seconds
                or settings.ai_timeout_seconds
            ),
            max_tokens=int(config.get("max_tokens") or settings.ai_max_tokens),
            api_key=str(config.get("api_key") or settings.ai_api_key or "") or None,
            base_url=str(config.get("base_url") or settings.ai_base_url or "") or None,
            codex_home=settings.ai_codex_home,
        )


class OpenAICompatibleCaseProvider(CompletionCaseProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        model: str,
        wire_api: str = "responses",
        reasoning_effort: str = "xhigh",
        timeout_seconds: int = 180,
        max_tokens: int = 3000,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            name=self.name,
            mode="openai_compatible_http",
            client=CodexHttpCompletionClient(
                model=model,
                wire_api=wire_api,
                reasoning_effort=reasoning_effort,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                api_key=api_key,
                base_url=base_url,
            ),
            model=model,
            wire_api=wire_api,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAICompatibleCaseProvider":
        config = settings.ai_provider_config or {}
        return cls(
            model=str(config.get("model") or settings.ai_model),
            wire_api=str(config.get("wire_api") or settings.ai_wire_api),
            reasoning_effort=str(config.get("reasoning_effort") or settings.ai_reasoning_effort),
            timeout_seconds=int(config.get("timeout_seconds") or settings.ai_timeout_seconds),
            max_tokens=int(config.get("max_tokens") or settings.ai_max_tokens),
            api_key=str(config.get("api_key") or settings.ai_api_key or "") or None,
            base_url=str(config.get("base_url") or settings.ai_base_url or "") or None,
        )
