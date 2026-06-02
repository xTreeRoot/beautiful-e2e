from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.services.ai_case_generator import GeneratedCase
from app.services.repo_reader import RepoSummary


@dataclass(frozen=True)
class CaseGenerationContext:
    """与供应商无关的 AI 用例生成输入契约。

    路由处理函数只构建一次该上下文，然后透传给 AI 网关。供应商实现可以
    按需使用字段子集，但必须返回共享的 `GeneratedCase` 契约。
    """

    prompt: str
    frontend: RepoSummary
    backend: RepoSummary
    priority: str | None = None
    agent: dict[str, Any] | None = None
    skills: list[dict[str, Any]] | None = None
    canvas_dsl: dict[str, Any] | None = None
    execution_mode: str = "fullstack"
    reference_documents: list[dict[str, Any]] | None = None
    project_context: dict[str, Any] | None = None
    auth_context: dict[str, Any] | None = None


class CaseGenerationError(RuntimeError):
    """供应商在返回有效 `GeneratedCase` 前失败时抛出。"""


class CaseGenerationProvider(ABC):
    """抽象 AI 入口。

    新供应商只需要实现该类，并通过
    `AI_PROVIDER_ENTRYPOINT=package.module:factory` 暴露工厂函数。
    """

    name: str

    @abstractmethod
    def generate(self, context: CaseGenerationContext) -> GeneratedCase:
        """生成一个结构化端到端测试用例。"""
