from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.services.case_generation_types import GeneratedCase
from app.services.generation_prompts import API_FACT_FEEDBACK_PROMPT


API_GENERATION_FEEDBACK_VERSION = "api_generation_feedback.v1"


def attach_api_generation_feedback(generated: GeneratedCase) -> GeneratedCase:
    """把生成后纠偏和参数诊断整理成后续 agent 可复用的反馈。

    这里不推测业务流程，只把已存在的路由契约纠偏、缺上游生产者和未解析参数
    转换为结构化事实。下一轮生成可以把它当作反例提示，重新回到项目路由目录。
    """

    context = dict(generated.code_context or {})
    route_items = _list_items(context.get("api_route_contract_enforcement"))
    diagnostic_items = _list_items(context.get("api_flow_diagnostics"))
    step_items = _step_feedback_items(generated)
    if not route_items and not diagnostic_items and not step_items:
        context.setdefault("api_fact_feedback_prompt", API_FACT_FEEDBACK_PROMPT)
        return replace(generated, code_context=context)

    feedback = {
        "version": API_GENERATION_FEEDBACK_VERSION,
        "agent_prompt": API_FACT_FEEDBACK_PROMPT,
        "next_generation_rules": [
            "把失败 URL 和硬编码参数当作反例，重新从项目路径内的真实路由目录选择接口。",
            "每个 path/query/body/header 参数都必须来自真实契约、前置 extract 或显式测试夹具。",
            "变量未能推导时，先补上游生产者接口；找不到生产者时写 missing_upstream_steps。",
            "404、未知处理器和 Method Not Allowed 优先按路由不真实处理，不要继续沿用原 URL。",
        ],
        "route_contract_corrections": route_items[:40],
        "flow_diagnostics": diagnostic_items[:40],
        "step_feedback": step_items[:40],
    }
    context["api_generation_feedback"] = feedback
    context["api_fact_feedback_prompt"] = API_FACT_FEEDBACK_PROMPT
    return replace(generated, code_context=context)


def _list_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    items = value.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _step_feedback_items(generated: GeneratedCase) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for step in generated.steps:
        data = step.data if isinstance(step.data, dict) else {}
        missing = [item for item in data.get("missing_upstream_steps", []) if isinstance(item, dict)]
        unresolved = [item for item in data.get("unresolved_parameters", []) if isinstance(item, dict)]
        corrections = [
            item for item in data.get("route_contract_corrections", []) if isinstance(item, dict)
        ]
        if not missing and not unresolved and not corrections:
            continue
        items.append(
            {
                "step_label": step.label,
                "target_url": step.target_url,
                "method": data.get("method"),
                "route_source": data.get("route_source"),
                "route_path_template": data.get("route_path_template"),
                "missing_upstream_steps": missing[:8],
                "unresolved_parameters": unresolved[:8],
                "route_contract_corrections": corrections[:8],
            }
        )
    return items
