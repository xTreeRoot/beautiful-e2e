from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.ai.base import CaseGenerationContext, CaseGenerationError
from app.services.ai.codex_bridge import CodexBridgeCaseProvider
from app.services.ai_case_generator import GeneratedCase
from app.services.repo_reader import RepoSummary


BridgeGenerationError = CaseGenerationError


class CodexBridgeCaseGenerator:
    """面向新可插拔 AI 供应商的向后兼容适配器。

    应用现在使用 `app.services.ai` 作为抽象 AI 网关。该适配器保留旧导入可用，
    同时委托给内置桥接供应商，而不再通过 shell 调用外部桥接脚本。
    """

    def __init__(
        self,
        script: Path | None = None,
        model: str | None = None,
        wire_api: str = "responses",
        reasoning_effort: str = "xhigh",
        timeout_seconds: int = 180,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.script = script
        self.provider = CodexBridgeCaseProvider(
            model=model or "gpt-5.5",
            wire_api=wire_api,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            api_key=api_key,
            base_url=base_url,
        )

    def generate(
        self,
        prompt: str,
        frontend: RepoSummary,
        backend: RepoSummary,
        priority: str | None = None,
        agent: dict[str, Any] | None = None,
        skills: list[dict[str, Any]] | None = None,
        canvas_dsl: dict[str, Any] | None = None,
        execution_mode: str = "fullstack",
    ) -> GeneratedCase:
        return self.provider.generate(
            CaseGenerationContext(
                prompt=prompt,
                frontend=frontend,
                backend=backend,
                priority=priority,
                agent=agent,
                skills=skills,
                canvas_dsl=canvas_dsl,
                execution_mode=execution_mode,
            )
        )
