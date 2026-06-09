from __future__ import annotations

from app import models
from app.services.api_flow_runtime_agent import (
    ApiFlowResponseHistory,
    ApiFlowRuntimeAgent,
)


def test_runtime_agent_infers_missing_variable_from_truncated_response_preview() -> None:
    agent = ApiFlowRuntimeAgent()
    step = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="查询资源详情",
        action="api_request",
        target_url="/api/public/resources/{{resourceId}}/detail",
        data={"method": "GET"},
    )

    inference = agent.infer_missing_variable(
        variable="resourceId",
        step=step,
        known_variables={},
        response_history=[
            ApiFlowResponseHistory(
                step_id="step-1",
                order_index=1,
                label="分页查询资源",
                status_code=200,
                response_preview=(
                    '# application/json; charset=UTF-8\n'
                    '{"success":true,"data":{"page":1,"list":[{"resourceId":"resource-123",'
                    '"name":"目标记录"}],"next":'
                ),
                extracted_variables={},
            )
        ],
    )

    assert inference is not None
    assert inference.value == "resource-123"
    assert inference.source == "deterministic_response_alias"
    assert inference.source_json_path == "$..resourceId"


def test_runtime_agent_prefers_enum_key_leaf_when_alias_matches_object() -> None:
    agent = ApiFlowRuntimeAgent()
    step = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="提交动作结果",
        action="api_request",
        target_url="/api/public/actions/complete",
        data={"method": "POST", "body": {"actionType": "{{actionType}}"}},
    )

    inference = agent.infer_missing_variable(
        variable="actionType",
        step=step,
        known_variables={},
        response_history=[
            ApiFlowResponseHistory(
                step_id="step-1",
                order_index=1,
                label="查询可选动作",
                status_code=200,
                response_preview=(
                    '{"success":true,"data":{"items":[{"actionType":{'
                    '"key":"PRIMARY_ACTION","label":"主要动作","value":"primary_action"'
                    "}}]}}"
                ),
                extracted_variables={},
            )
        ],
    )

    assert inference is not None
    assert inference.value == "PRIMARY_ACTION"
    assert inference.source == "deterministic_response_alias"
    assert inference.source_json_path == "$.data.items[0].actionType.key"
