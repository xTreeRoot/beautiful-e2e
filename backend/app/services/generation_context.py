from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentProfile, SkillProfile
from app.services.generation_prompts import (
    BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
    API_FLOW_RELATIONSHIP_PROMPT,
    API_FACT_FEEDBACK_PROMPT,
    BACKEND_API_ROUTE_GROUNDING_PROMPT,
)


@dataclass(frozen=True)
class GenerationContext:
    agent: dict[str, Any] | None
    skills: list[dict[str, Any]]


def build_generation_context(
    project_id: str,
    execution_mode: str,
    agent_id: str | None,
    skill_ids: list[str],
    db: Session | None,
) -> GenerationContext:
    """解析项目选择的智能体、技能，以及执行模式相关的默认配置。

    请求结构已经支持显式档案 id，便于后续前端控件接入。在控件完善前，
    backend_api 模式仍会注入内置接口智能体、路由约束和参数推测技能，
    保证供应商提示词可审阅、可继续细化。
    """
    agent = _selected_agent(project_id, agent_id, db)
    skills = _selected_skills(project_id, skill_ids, db)

    if execution_mode == "backend_api":
        agent = agent or _builtin_backend_api_agent()
        if not any(skill.get("id") == "backend-api-entrypoint-first" for skill in skills):
            skills.insert(0, _builtin_entrypoint_first_skill())
        if not any(skill.get("id") == "backend-api-route-grounding" for skill in skills):
            skills.insert(1, _builtin_route_grounding_skill())
        if not any(skill.get("id") == "backend-api-parameter-inference" for skill in skills):
            skills.append(_builtin_parameter_inference_skill())

    return GenerationContext(agent=agent, skills=skills)


def _selected_agent(project_id: str, agent_id: str | None, db: Session) -> dict[str, Any] | None:
    if not agent_id or db is None:
        return None
    agent = db.scalar(
        select(AgentProfile).where(AgentProfile.project_id == project_id, AgentProfile.id == agent_id)
    )
    return _agent_to_dict(agent, source="project") if agent else None


def _selected_skills(
    project_id: str,
    skill_ids: list[str],
    db: Session | None,
) -> list[dict[str, Any]]:
    if not skill_ids or db is None:
        return []
    rows = db.scalars(
        select(SkillProfile).where(
            SkillProfile.project_id == project_id,
            SkillProfile.id.in_(skill_ids),
            SkillProfile.enabled.is_(True),
        )
    ).all()
    by_id = {row.id: row for row in rows}
    return [_skill_to_dict(by_id[skill_id], source="project") for skill_id in skill_ids if skill_id in by_id]


def _builtin_backend_api_agent() -> dict[str, Any]:
    return {
        "id": "backend-api-flow-inference-agent",
        "name": "接口逻辑与参数推测测试架构师",
        "role": "backend_api_flow_inference_architect",
        "description": "根据路由证据、引用文档和前置响应关系生成纯后端接口回归流程。",
        "instructions": (
            "生成纯接口测试步骤。先把用户的业务流程映射到真实路由，"
            "如果用户明确指定“从某入口开始”，第一个可执行接口必须实现该入口，"
            "不要跳到后续详情、活动页或提交接口；"
            "接口链路表、前置认证和测试数据说明只能写入步骤 data，不能伪装成缺 URL 的接口步骤。"
            "再分析接口之间的前置关系、响应提取点、请求参数来源和缺失的上游生产者接口。"
            "对于需要传递的凭证、id、token、业务编号等参数，"
            "必须使用 step.data.extract 与 {{变量}} 占位符建立可执行的数据链路；"
            "如果项目环境已经配置认证请求头，登录态由环境注入，不要再生成同名 token 占位符；"
            "如果某个关键 ID 在当前步骤前没有来源，必须先倒推搜索、列表、详情、首页、预检或创建接口，"
            "让上游响应产生该 ID，再进入消费接口；无法确定时写入 unresolved_parameters 和 "
            "missing_upstream_steps，方便用户用运行反馈继续修正。"
            "当用户要求从分页、列表、搜索或查询真实找到业务实体时，文档固定 ID 只能用于候选过滤或断言，"
            "不能直接替代前置响应 extract；下游路径和请求参数必须消费 {{变量}}。"
            "看到 404、未知处理器或变量推导失败等反馈时，必须把失败 DSL 当作反例，"
            "重新从项目路径内扫描到的路由、参数和请求体契约选择接口。"
        ),
        "tools": {
            "route_catalog": "backend_repository_summary.routes（包含代码路由与 Swagger/OpenAPI 契约）",
            "reference_documents": "reference_documents",
            "response_variables": "step.data.extract + {{变量}}",
        },
        "source": "builtin",
    }


def _builtin_entrypoint_first_skill() -> dict[str, Any]:
    return {
        "id": "backend-api-entrypoint-first",
        "name": "后端接口入口优先",
        "category": "backend_api",
        "description": "要求接口生成尊重用户指定的流程起点，并禁止把分析说明生成成无 URL 步骤。",
        "prompt": BACKEND_API_ENTRYPOINT_FIRST_PROMPT,
        "enabled": True,
        "source": "builtin",
    }


def _builtin_route_grounding_skill() -> dict[str, Any]:
    return {
        "id": "backend-api-route-grounding",
        "name": "后端接口路由约束",
        "category": "backend_api",
        "description": "要求接口生成使用已发现的后端路由并记录证据。",
        "prompt": BACKEND_API_ROUTE_GROUNDING_PROMPT,
        "enabled": True,
        "source": "builtin",
    }


def _builtin_parameter_inference_skill() -> dict[str, Any]:
    return {
        "id": "backend-api-parameter-inference",
        "name": "接口逻辑关系与参数推测",
        "category": "backend_api",
        "description": "要求接口生成分析前置响应、请求体参数来源和缺口反馈。",
        "prompt": f"{API_FLOW_RELATIONSHIP_PROMPT}\n\n{API_FACT_FEEDBACK_PROMPT}",
        "enabled": True,
        "source": "builtin",
    }


def _agent_to_dict(agent: AgentProfile, source: str) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "description": agent.description,
        "instructions": agent.instructions,
        "tools": agent.tools or {},
        "source": source,
    }


def _skill_to_dict(skill: SkillProfile, source: str) -> dict[str, Any]:
    return {
        "id": skill.id,
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "prompt": skill.prompt,
        "enabled": skill.enabled,
        "source": source,
    }
