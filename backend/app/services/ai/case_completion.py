from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Protocol

from app.services.ai.base import CaseGenerationContext, CaseGenerationError, CaseGenerationProvider
from app.services.ai_case_generator import CaseGenerator, GeneratedCase, GeneratedStep
from app.services.generation_prompts import (
    BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
    API_FLOW_RELATIONSHIP_PROMPT,
    API_FACT_FEEDBACK_PROMPT,
    BACKEND_API_ROUTE_GROUNDING_PROMPT,
)
from app.services.flow_entrypoint import flow_entrypoint_from_prompt
from app.services.reference_fixtures import compact_reference_fixtures, extract_reference_fixtures


class CaseCompletionClient(Protocol):
    """文本补全客户端契约。

    具体供应商只负责把 system/prompt 送到模型并返回文本，业务载荷和返回 JSON
    的约束统一留在本模块，避免桥接实现携带用例生成语义。
    """

    def complete(self, system: str, prompt: str) -> str:
        """调用模型并返回最终文本。"""


class CompletionCaseProvider(CaseGenerationProvider):
    """基于通用文本补全能力的用例生成供应商。

    HTTP 桥接、`codex exec` 或自定义 OpenAI 兼容协议都可以复用该类；它只依赖
    `CaseCompletionClient`，因此具体通道不会感知端到端用例业务规则。
    """

    def __init__(
        self,
        *,
        name: str,
        mode: str,
        client: CaseCompletionClient,
        model: str | None = None,
        wire_api: str | None = None,
    ) -> None:
        self.name = name
        self.mode = mode
        self.client = client
        self.model = model
        self.wire_api = wire_api

    def generate(self, context: CaseGenerationContext) -> GeneratedCase:
        system = build_case_generation_system_prompt()
        payload = self._build_prompt_payload(context)

        client = self._client_for_context(context)
        try:
            raw = client.complete(system=system, prompt=json.dumps(payload, ensure_ascii=False))
        except CaseGenerationError:
            raise
        except Exception as exc:
            raise CaseGenerationError(str(exc)) from exc

        return self._case_from_raw(context, raw)

    def stream_generate(self, context: CaseGenerationContext) -> Iterator[dict[str, Any]]:
        system = build_case_generation_system_prompt()
        payload = self._build_prompt_payload(context)
        client = self._client_for_context(context)
        stream_complete = getattr(client, "stream_complete", None)

        if not callable(stream_complete):
            yield {
                "type": "progress",
                "message": f"{self.name} 不支持供应商 SSE 明细，等待最终生成结果。",
                "stage": "provider_stream_unavailable",
                "provider": self.name,
            }
            yield {"type": "generated_case", "case": self.generate(context)}
            return

        content_chunks: list[str] = []
        final_text = ""
        try:
            for event in stream_complete(system=system, prompt=json.dumps(payload, ensure_ascii=False)):
                event_type = str(event.get("type") or "")
                if event_type == "provider_delta":
                    delta = event.get("delta")
                    channel = str(event.get("channel") or "content")
                    if (
                        isinstance(delta, str)
                        and channel == "content"
                        and event.get("collect") is not False
                    ):
                        content_chunks.append(delta)
                    yield {**event, "provider": self.name, "stage": "provider_stream"}
                    continue
                if event_type == "provider_final":
                    text = event.get("text")
                    if isinstance(text, str):
                        final_text = text
                    continue
                yield {**event, "provider": self.name, "stage": "provider_stream"}
        except CaseGenerationError:
            raise
        except Exception as exc:
            raise CaseGenerationError(str(exc)) from exc

        raw = final_text or "".join(content_chunks)
        if not raw.strip():
            raise CaseGenerationError(f"{self.name} SSE 未返回可解析的最终内容")

        yield {
            "type": "progress",
            "message": "供应商 SSE 已结束，开始解析结构化用例。",
            "stage": "provider_parse",
            "provider": self.name,
        }
        yield {"type": "generated_case", "case": self._case_from_raw(context, raw)}

    def _client_for_context(self, context: CaseGenerationContext) -> CaseCompletionClient:
        """按上下文选择补全客户端。

        默认供应商不需要区分上下文；`codex exec` 会用它按项目仓库动态选择工作目录，
        让非交互式 Codex 尽量在最接近代码的位置读取资料。
        """
        return self.client

    def _build_prompt_payload(self, context: CaseGenerationContext) -> dict[str, Any]:
        """构建供应商输入载荷。

        默认供应商使用完整上下文；有输入长度硬限制的通道可以覆盖该方法做
        供应商侧压缩，同时保持路由层和解析逻辑不感知具体供应商差异。
        """
        return build_case_generation_payload(context)

    def _case_from_raw(self, context: CaseGenerationContext, raw: str) -> GeneratedCase:
        obj = parse_case_generation_json(raw, self.name)
        steps = [coerce_generated_step(item) for item in obj.get("steps", []) if isinstance(item, dict)]
        if not steps:
            raise CaseGenerationError(f"{self.name} 未返回有效步骤")
        if context.execution_mode == "backend_api" and any(step.action != "api_request" for step in steps):
            raise CaseGenerationError(f"{self.name} 在 backend_api 模式下返回了非接口步骤")
        if context.execution_mode == "backend_api":
            _validate_backend_api_steps(steps, self.name)

        title = str(obj.get("title") or CaseGenerator()._title_from_prompt(context.prompt))
        description = str(obj.get("description") or context.prompt)
        generated_priority = str(obj.get("priority") or context.priority or "P1").upper()
        if generated_priority not in {"P0", "P1", "P2"}:
            generated_priority = context.priority or "P1"

        return GeneratedCase(
            title=title[:180],
            description=description,
            priority=generated_priority,
            steps=steps,
            graph=CaseGenerator()._graph_for_steps(
                steps,
                context.frontend,
                context.backend,
                execution_mode=context.execution_mode,
            ),
            code_context={
                "frontend": context.frontend.as_dict(),
                "backend": context.backend.as_dict(),
                "generation_mode": self.name,
                "execution_mode": context.execution_mode,
                "backend_api_route_grounding_prompt": BACKEND_API_ROUTE_GROUNDING_PROMPT,
                "backend_api_entrypoint_first_prompt": BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
                "api_flow_relationship_prompt": API_FLOW_RELATIONSHIP_PROMPT,
                "api_fact_feedback_prompt": API_FACT_FEEDBACK_PROMPT,
                "ai_provider": {
                    "name": self.name,
                    "mode": self.mode,
                    "model": self.model,
                    "wire_api": self.wire_api,
                },
                "agent": context.agent,
                "skills": context.skills or [],
                "canvas_dsl": context.canvas_dsl,
                "project_context": context.project_context,
                "reference_documents": reference_indexes(context.reference_documents or []),
                "reference_fixtures": compact_reference_fixtures(
                    extract_reference_fixtures(context.reference_documents or [])
                ),
                "auth_context": _auth_context_from_generation_context(context),
            },
        )


def build_case_generation_system_prompt() -> str:
    """构建所有模型供应商共用的系统提示词。"""
    return (
        "你是端到端测试架构师。只返回有效 JSON，不要返回 Markdown。"
        "根据自然语言和仓库上下文生成适合 Playwright 落地的测试用例。"
        "如果提供 reference_documents，请把它们作为请求流程的主要来源材料。"
        "先从 reference_documents 提取固定 ID、活动/商品名称和页面标题，"
        "不要把地名、范围词或短关键词直接当成完整业务实体。"
        "如果提供 project_context，它是所有 LLM 共享的项目级事实来源，必须优先遵守。"
        "不要把本地文件系统路径直接变成测试步骤；应读取引用文档内容，并推断用户可见旅程。"
        "在 backend_api 模式下，客户端、用户端或小程序流程指客户端消费的真实 HTTP 接口链路，"
        "必须输出 api_request，不要输出 goto/fill/click 等页面动作。"
        "在 fullstack 模式下，客户端、前端或前后端配合请求才生成浏览器可见步骤，覆盖端到端用户流程，"
        "并在步骤 data 中引用文档证据。"
        "允许的动作：goto、fill、click、expect_visible、expect_not_visible、expect_text。"
        "对于 backend_api 模式，只生成 api_request 步骤，并在 data 中使用 method、expected_status、body；"
        "每个 api_request 都必须有非空 target_url 和 data.method。"
        "可用时优先使用 data-testid 选择器；不确定时保持选择器可编辑。"
        + "\n\n"
        + BACKEND_API_ROUTE_GROUNDING_PROMPT
        + "\n\n"
        + BACKEND_API_ENTRYPOINT_FIRST_PROMPT
        + "\n\n"
        + API_FLOW_RELATIONSHIP_PROMPT
        + "\n\n"
        + API_FACT_FEEDBACK_PROMPT
    )


def build_case_generation_payload(context: CaseGenerationContext) -> dict[str, Any]:
    """构建模型输入载荷。

    该载荷是前端画布 DSL、仓库摘要和 Playwright 步骤结构之间的跨层契约，
    字段名需要保持稳定，便于 HTTP 和 `codex exec` 两种通道复用。
    """
    reference_fixtures = compact_reference_fixtures(
        extract_reference_fixtures(context.reference_documents or [])
    )
    flow_entrypoint = flow_entrypoint_from_prompt(context.prompt)
    return {
        "natural_language": context.prompt,
        "execution_mode": context.execution_mode,
        "execution_mode_rules": {
            "backend_api": (
                "生成纯后端接口回归步骤。不要使用浏览器或页面动作。"
                "先从 reference_documents 的执行单、接口目录、接口地图、推荐调用顺序中梳理客户端真实接口链路，"
                "再使用 backend_repository_summary.routes 校验 HTTP 方法、路径、处理函数和 Swagger/OpenAPI 参数契约，"
                "并保留路由证据。若 flow_entrypoint.explicit=true，第一个可执行步骤必须实现该入口。"
            ),
            "fullstack": (
                "在有帮助时结合后端上下文生成前端浏览器动作。"
                "当 reference_documents 包含执行单、需求、页面清单、用户故事或自测记录时，"
                "请从这些文档推导客户端旅程。"
            ),
        },
        "reference_document_rules": [
            "把 reference_documents 当作证据，不要把它们逐字当成 UI 断言文本。",
            "在 backend_api 模式下，用户可见/客户端流程指客户端接口请求链。",
            "先从文档推导业务接口流程，再使用仓库摘要补充路由证据。",
            "每个从文档推导出的步骤都要在 data 中写入 reference_source 和 reference_excerpt。",
            "先使用 reference_fixtures.fixed_ids 和 reference_fixtures.entity_names；"
            "文档已声明 goodsId/campaignId/displayTitle/campaign_name 时，不要退化成只用地名、范围词或短关键词。",
            "如果 backend_repository_summary.routes 含有 Swagger/OpenAPI 或项目分析 Java DTO 的 parameters、request_body、responses，"
            "必须用它们推导请求参数、请求体和响应 extract。",
            "如果 project_context.repositories[].route_contract_examples 含有请求体字段，"
            "必须优先使用这些字段名，不要把项目 DTO 字段改写成其他分页框架的 current/size/keyword。",
            "对需要从前置响应传递的参数，在生产方写 data.extract，消费方使用 {{变量}}。",
            "无法推断来源的 body/path/header 参数写入 data.unresolved_parameters。",
            "如果下游接口需要业务实体 ID，必须先查找能生产该 ID 的上游搜索、列表、详情、首页、预检或创建接口。",
            "不要把长数字、1、fallback 或环境变量当作业务 ID 推导结果，除非文档明确声明它是固定测试夹具。",
            "如果 natural_language 要求真实找到、查出来、从分页/列表/搜索/查询开始再用 ID，"
            "reference_fixtures.fixed_ids 只能作为候选过滤或断言，不能直接满足下游 required 参数。",
        ],
        "flow_entrypoint": flow_entrypoint,
        "flow_entrypoint_rules": [
            "flow_entrypoint.explicit=true 表示用户已经指定流程起点；第一个可执行 api_request 必须匹配 raw_text。",
            "不要把 flow_entrypoint.raw_text 改写成后续页面或活动目标；先生成入口发现接口，再进入详情、确认或业务活动。",
            "如果入口是列表、分页、搜索或查询，优先选择同领域 page/list/search/query 路由并 extract 下游需要的业务 ID。",
            "分析性链路表、认证说明、测试数据说明和断言策略不能单独成为 api_request 步骤。",
            "找不到入口真实路由时，不要输出缺少 URL 的步骤；应把缺口写入 data.missing_upstream_steps。",
            "flow_entrypoint.requires_dynamic_discovery=true 时，下游业务 ID 必须来自入口或前置步骤 data.extract，"
            "不要把 reference_fixtures.fixed_ids 或接口文档示例 URL 中的长数字写进 target_url。",
        ],
        "project_context": context.project_context or _default_project_context(),
        "auth_context": _auth_context_from_generation_context(context),
        "auth_context_rules": [
            "project_context 是所有 LLM 共享的项目级事实来源，后续新增 LLM 也必须复用它。",
            "auth_context 只暴露环境请求头名称、分析结论和候选接口，不包含真实 token 或 cookie 值。",
            "如果 auth_context.effective_mode 是 environment_headers，说明登录态由项目环境请求头注入；"
            "不要为 likely_auth_header_keys 里的 header 生成 {{token}}、{{customer_token}} 等占位符，"
            "也不要强行插入登录接口来生产这些 header。",
            "如果 auth_context.effective_mode 是 configured_headers，configured_header_keys 会由运行环境自动注入；"
            "不要在 step.data.headers 重复覆盖这些 header，除非用户明确要求当前步骤使用不同值。",
            "如果 auth_context.effective_mode 是 login_flow，优先使用 login_route_candidates 建立登录步骤和 token extract。",
            "如果 auth_context.effective_mode 是 external_or_environment_headers，优先提示用户配置环境认证请求头，不要臆造登录接口。",
            "如果 auth_context.effective_mode 是 unknown，只有在真实路由和文档都证明存在可执行登录接口时，"
            "才把登录建模成前置 api_request 并通过 data.extract 传递 token；否则写入 unresolved_parameters。",
            "业务实体 ID、订单号、活动 ID 等业务变量仍必须走前置响应 extract，不能因为存在环境认证头就跳过生产者步骤。",
        ],
        "backend_api_route_grounding_prompt": BACKEND_API_ROUTE_GROUNDING_PROMPT,
        "api_flow_relationship_prompt": API_FLOW_RELATIONSHIP_PROMPT,
        "backend_api_entrypoint_first_prompt": BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
        "api_fact_feedback_prompt": API_FACT_FEEDBACK_PROMPT,
        "api_flow_contract": {
            "extract": "step.data.extract 使用 {变量名: JSONPath} 从当前响应提取值。",
            "placeholder": "后续步骤在 target_url、data.headers 或 data.body 中使用 {{变量名}}。",
            "depends_on": "step.data.depends_on 或 parameter_links 记录变量来源和绑定位置。",
            "unresolved_parameters": "无法可靠推断来源时必须写出缺口，不要静默置空。",
            "missing_upstream_steps": "发现关键参数没有生产者时，写出应该补入的上游接口候选和原因。",
            "hardcoded_id": "长数字或 1 只能在 explicit_fixture=true 时出现，否则应由前置接口 extract。",
        },
        "upstream_discovery_rules": [
            "如果用户指定了流程入口，先为入口生成生产者接口，再生成下游消费者接口。",
            "对 target_url 中的 {xxxId} 或 {{xxx_id}}，先检查前置步骤是否 extract 了对应变量。",
            "没有生产者时，在 backend_repository_summary.routes 中查找同领域 page/list/search/options/detail/home/preview/create 路由。",
            "把找到的生产者步骤插入到消费者之前，并从响应中 extract 下游变量。",
            "如果生产者本身也需要 ID，继续递归倒推，直到到达搜索/列表/登录/公开入口或显式测试夹具。",
            "required=true 的依赖不能靠 parameter_links.fallback 通过；fallback 只写入诊断说明。",
            "如果用户要求从入口查询真实发现实体，固定夹具 ID 不能作为 required=true 的生产者；"
            "入口步骤必须 extract，下游必须用 {{变量名}}。",
        ],
        "fact_feedback_rules": [
            "看到 404、未知处理器或 0 个正确接口时，把失败 URL 当作反例，重新从项目路由目录选择真实接口。",
            "看到未能推导变量时，把它当作缺少上游生产者接口，先补搜索/列表/详情/首页/预检/创建等生产者步骤。",
            "下一轮输出必须把 route_source、route_parameters、route_request_body、extract、depends_on 和 parameter_links 写清楚。",
            "如果项目事实不足，不要硬写 URL；把缺口写入 missing_upstream_steps 和 unresolved_parameters。",
            "如果第一步跳过用户指定的查询/分页/搜索入口，反馈为入口顺序错误，下一轮先补入口发现接口。",
            "如果动态发现链路仍消费固定 ID，反馈为参数来源错误，下一轮把固定 ID 降级为候选/断言。",
        ],
        "requested_priority": context.priority,
        "selected_agent": context.agent,
        "enabled_skills": context.skills or [],
        "current_canvas_dsl": context.canvas_dsl,
        "reference_fixtures": reference_fixtures,
        "reference_documents": context.reference_documents or [],
        "frontend_repository_summary": context.frontend.as_dict(),
        "backend_repository_summary": context.backend.as_dict(),
        "json_schema": {
            "title": "string",
            "description": "string",
            "priority": "P0|P1|P2",
            "steps": [
                {
                    "kind": "setup|action|assertion|api",
                    "label": "string",
                    "action": "goto|fill|click|expect_visible|expect_not_visible|expect_text|api_request",
                    "selector": "string|null",
                    "target_url": "string|null",
                    "value": "string|null",
                    "expected": "string|null",
                    "data": {
                        "method": "GET|POST|PUT|PATCH|DELETE|null",
                        "expected_status": "number|null",
                        "body": "object|string|null",
                        "headers": "object|null",
                        "extract": {"变量名": "$.data.path"},
                        "depends_on": "array|null",
                        "parameter_links": "array|null",
                        "unresolved_parameters": "array|null",
                        "missing_upstream_steps": "array|null",
                        "route_source": "string|null",
                        "route_summary": "string|null",
                        "route_parameters": "array|null",
                        "route_request_body": "object|null",
                        "route_responses": "array|null",
                        "reference_source": "string|null",
                        "reference_excerpt": "string|null",
                        "flow_reason": "string|null",
                    },
                }
            ],
        },
    }


def _auth_context_from_generation_context(context: CaseGenerationContext) -> dict[str, Any]:
    if isinstance(context.auth_context, dict):
        return context.auth_context
    project_auth = (context.project_context or {}).get("auth")
    if isinstance(project_auth, dict):
        return project_auth
    return _default_project_context()["auth"]


def _default_project_context() -> dict[str, Any]:
    return {
        "version": "project_llm_context.v1",
        "auth": {
            "effective_mode": "unknown",
            "configured_header_keys": [],
            "likely_auth_header_keys": [],
            "login_route_candidates": [],
            "redacted": True,
            "reason": "未提供项目级上下文。",
        },
        "repositories": [],
        "rules": [
            "如果生成输入提供 reference_fixtures，所有 LLM 都必须优先使用其中的固定 ID 和实体名称。",
        ],
    }


def reference_indexes(reference_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留引用文档索引，避免把完整内容重复写进用例上下文。"""
    return [
        {
            "path": item.get("path"),
            "title": item.get("title"),
            "chars": item.get("chars"),
            "truncated": item.get("truncated"),
        }
        for item in reference_documents
    ]


def parse_case_generation_json(raw: str, provider_name: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象。

    有些模型会错误包裹 Markdown fence，这里只做窄范围容错；如果没有完整对象，
    仍然抛出明确错误，避免把半截文本当作步骤保存。
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise CaseGenerationError(f"{provider_name} 未返回 JSON")
        obj = json.loads(text[start : end + 1])

    if not isinstance(obj, dict):
        raise CaseGenerationError(f"{provider_name} 返回的 JSON 必须是对象")
    return obj


def _validate_backend_api_steps(steps: list[GeneratedStep], provider_name: str) -> None:
    """拒绝保存不可执行的接口 DSL，避免运行阶段才暴露缺 URL 问题。"""

    for index, step in enumerate(steps, start=1):
        target_url = str(step.target_url or "").strip()
        if not target_url:
            raise CaseGenerationError(
                f"{provider_name} 在 backend_api 模式下返回了不可执行接口步骤："
                f"第 {index} 步「{step.label}」缺少 target_url。"
                "分析性链路表请写入 data.flow_reason 或 route_decision，不要作为步骤返回。"
            )
        data = step.data if isinstance(step.data, dict) else {}
        method = str(data.get("method") or "").strip().upper()
        if not method:
            raise CaseGenerationError(
                f"{provider_name} 在 backend_api 模式下返回了不可执行接口步骤："
                f"第 {index} 步「{step.label}」缺少 data.method。"
            )


def coerce_generated_step(item: dict[str, Any]) -> GeneratedStep:
    """把模型 JSON 规整为内部步骤契约。"""

    def string_or_none(key: str) -> str | None:
        value = item.get(key)
        if value is None:
            return None
        return str(value)

    action = string_or_none("action")
    if action not in {
        "goto",
        "fill",
        "click",
        "expect_visible",
        "expect_not_visible",
        "expect_text",
        "api_request",
        None,
    }:
        action = None

    data = item.get("data")
    return GeneratedStep(
        kind=string_or_none("kind") or "action",
        label=string_or_none("label") or "生成步骤",
        action=action,
        selector=string_or_none("selector"),
        target_url=string_or_none("target_url"),
        value=string_or_none("value"),
        expected=string_or_none("expected"),
        data=data if isinstance(data, dict) else None,
    )
