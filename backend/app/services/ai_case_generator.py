from __future__ import annotations

from typing import Any

from app.services.api_case_steps import ApiCaseStepBuilder
from app.services.case_generation_types import GeneratedCase, GeneratedStep
from app.services.case_graph_builder import build_case_graph
from app.services.document_case_steps import DocumentCaseStepBuilder, reference_indexes
from app.services.dsl_auth_context import build_dsl_auth_context, build_dsl_project_context
from app.services.generation_prompts import (
    API_FLOW_RELATIONSHIP_PROMPT,
    API_FACT_FEEDBACK_PROMPT,
    BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
    BACKEND_API_ROUTE_GROUNDING_PROMPT,
)
from app.services.reference_fixtures import compact_reference_fixtures, extract_reference_fixtures
from app.services.repo_reader import RepoSummary

__all__ = ["CaseGenerator", "GeneratedCase", "GeneratedStep"]


class CaseGenerator:
    """规则兜底生成器的编排门面。

    这里只负责选择浏览器步骤或接口步骤的生成路径，并组装 `GeneratedCase`
    契约；文档解析、API 路由匹配和图结构构建都放在独立模块中，避免该门面
    再次膨胀成几千行的业务混合体。
    """

    def __init__(
        self,
        *,
        api_step_builder: ApiCaseStepBuilder | None = None,
        document_step_builder: DocumentCaseStepBuilder | None = None,
    ) -> None:
        self._api_step_builder = api_step_builder or ApiCaseStepBuilder()
        self._document_step_builder = document_step_builder or DocumentCaseStepBuilder()

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
        reference_documents: list[dict[str, Any]] | None = None,
        project_context: dict[str, Any] | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> GeneratedCase:
        normalized = prompt.strip()
        lower = normalized.lower()
        title = self._title_from_prompt(normalized)
        references = reference_documents or []

        if execution_mode == "backend_api":
            steps = self._api_step_builder._api_steps(normalized, lower, backend, references)
            return GeneratedCase(
                title=title,
                description=normalized,
                priority=priority or self._priority_for_prompt(normalized),
                steps=steps,
                graph=self._graph_for_steps(steps, frontend, backend, execution_mode=execution_mode),
                code_context=self._code_context(
                    frontend=frontend,
                    backend=backend,
                    execution_mode=execution_mode,
                    agent=agent,
                    skills=skills,
                    canvas_dsl=canvas_dsl,
                    project_context=project_context,
                    auth_context=auth_context,
                    reference_documents=references,
                ),
            )

        steps = [
            GeneratedStep(
                kind="setup",
                label="打开应用",
                action="goto",
                target_url="/",
                expected="应用外壳可见",
            )
        ]

        document_steps = self._document_step_builder._document_grounded_client_steps(
            normalized,
            references,
        )
        if document_steps:
            steps.extend(document_steps)

        if any(token in normalized for token in ["搜索", "查询"]) or "search" in lower:
            steps.extend(
                [
                    GeneratedStep(
                        kind="action",
                        label="搜索目标记录",
                        action="fill",
                        selector="[data-testid='search-input']",
                        value="回归关键词",
                    ),
                    GeneratedStep(
                        kind="assertion",
                        label="确认搜索结果已渲染",
                        action="expect_visible",
                        selector="[data-testid='search-results']",
                        expected="至少一个结果可见",
                    ),
                ]
            )

        if self._asks_for_submit_flow(normalized, lower):
            steps.extend(self._submit_steps())

        if any(token in normalized for token in ["浏览", "列表", "详情"]) or any(
            token in lower for token in ["browse", "detail", "list"]
        ):
            steps.extend(self._browse_steps())

        if len(steps) == 1:
            steps.extend(
                [
                    GeneratedStep(
                        kind="action",
                        label="执行提示词中的业务操作",
                        action="click",
                        selector="[data-testid='primary-action']",
                        expected=normalized,
                    ),
                    GeneratedStep(
                        kind="assertion",
                        label="验证请求结果",
                        action="expect_text",
                        selector="body",
                        expected="业务结果符合自然语言要求",
                    ),
                ]
            )

        steps.append(
            GeneratedStep(
                kind="assertion",
                label="确认没有关键错误",
                action="expect_not_visible",
                selector="[data-testid='global-error'], text=/500|Error|Exception/",
                expected="没有出现阻断错误",
            )
        )

        return GeneratedCase(
            title=title,
            description=normalized,
            priority=priority or self._priority_for_prompt(normalized),
            steps=steps,
            graph=self._graph_for_steps(steps, frontend, backend, execution_mode=execution_mode),
            code_context=self._code_context(
                frontend=frontend,
                backend=backend,
                execution_mode=execution_mode,
                agent=agent,
                skills=skills,
                canvas_dsl=canvas_dsl,
                project_context=project_context,
                auth_context=auth_context,
                reference_documents=references,
            ),
        )

    def _code_context(
        self,
        *,
        frontend: RepoSummary,
        backend: RepoSummary,
        execution_mode: str,
        agent: dict[str, Any] | None,
        skills: list[dict[str, Any]] | None,
        canvas_dsl: dict[str, Any] | None,
        project_context: dict[str, Any] | None,
        auth_context: dict[str, Any] | None,
        reference_documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """组装生成结果追踪上下文，保持供应商和规则兜底返回结构一致。"""
        return {
            "frontend": frontend.as_dict(),
            "backend": backend.as_dict(),
            "generation_mode": "rule_based_scaffold",
            "execution_mode": execution_mode,
            "backend_api_route_grounding_prompt": BACKEND_API_ROUTE_GROUNDING_PROMPT,
            "backend_api_entrypoint_first_prompt": BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
            "api_flow_relationship_prompt": API_FLOW_RELATIONSHIP_PROMPT,
            "api_fact_feedback_prompt": API_FACT_FEEDBACK_PROMPT,
            "agent": agent,
            "skills": skills or [],
            "canvas_dsl": canvas_dsl,
            "project_context": build_dsl_project_context(project_context, auth_context),
            "auth_context": build_dsl_auth_context(project_context, auth_context),
            "reference_documents": reference_indexes(reference_documents),
            "reference_fixtures": compact_reference_fixtures(
                extract_reference_fixtures(reference_documents)
            ),
        }

    def _title_from_prompt(self, prompt: str) -> str:
        compact = " ".join(prompt.split())
        if len(compact) <= 42:
            return compact
        return compact[:42].rstrip() + "..."

    def _priority_for_prompt(self, prompt: str) -> str:
        if any(token in prompt for token in ["核心", "登录", "发布", "提交", "删除"]):
            return "P0"
        return "P1"

    def _asks_for_submit_flow(self, prompt: str, lower: str) -> bool:
        return any(token in prompt for token in ["提交", "保存", "创建", "新增", "确认", "发起"]) or any(
            token in lower for token in ["submit", "save", "create", "confirm", "apply"]
        )

    def _submit_steps(self) -> list[GeneratedStep]:
        return [
            GeneratedStep(
                kind="action",
                label="打开主要业务入口",
                action="click",
                selector="[data-testid='primary-action'], [data-testid='start-flow']",
            ),
            GeneratedStep(
                kind="action",
                label="提交业务操作",
                action="click",
                selector="[data-testid='submit-action'], button[type='submit']",
            ),
            GeneratedStep(
                kind="assertion",
                label="确认业务结果成功",
                action="expect_text",
                selector="[data-testid='success-state'], [data-testid='result-status']",
                expected="成功",
            ),
        ]

    def _browse_steps(self) -> list[GeneratedStep]:
        return [
            GeneratedStep(
                kind="action",
                label="打开浏览列表",
                action="goto",
                target_url="/browse",
            ),
            GeneratedStep(
                kind="assertion",
                label="确认列表内容可见",
                action="expect_visible",
                selector="[data-testid='browse-list'], [data-testid='table']",
            ),
            GeneratedStep(
                kind="action",
                label="打开第一条详情",
                action="click",
                selector="[data-testid='detail-link']",
            ),
            GeneratedStep(
                kind="assertion",
                label="确认详情页已渲染",
                action="expect_visible",
                selector="[data-testid='detail-page']",
            ),
        ]

    def _graph_for_steps(
        self,
        steps: list[GeneratedStep],
        frontend: RepoSummary,
        backend: RepoSummary,
        execution_mode: str = "fullstack",
    ) -> dict[str, Any]:
        return build_case_graph(steps, frontend, backend, execution_mode=execution_mode)

    def __getattr__(self, name: str) -> Any:
        """兼容历史测试或供应商仍临时访问的私有辅助方法。

        新代码应直接依赖拆分后的模块；这里仅作为迁移缓冲，避免一次性修改所有
        调用方造成更大的行为风险。
        """
        if name.startswith("_"):
            for helper in (self._api_step_builder, self._document_step_builder):
                try:
                    return getattr(helper, name)
                except AttributeError:
                    continue
        raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")
