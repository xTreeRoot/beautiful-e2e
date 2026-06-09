from __future__ import annotations

from app import models
from app.services.api_flow_runtime_agent import (
    ApiFlowFailureAttempt,
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


def test_runtime_agent_repairs_failed_enum_object_body_to_scalar_leaf() -> None:
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

    repair = agent.repair_failed_request(
        step=step,
        known_variables={},
        response_history=[],
        failed_attempts=[
            ApiFlowFailureAttempt(
                attempt=1,
                status_code=500,
                expected_status=200,
                error="响应状态码不符合期望",
                response_preview='{"success":false,"msg":"动作标识不能为空"}',
                response_content_type="application/json",
                request={
                    "method": "POST",
                    "url": "http://localhost:8000/api/public/actions/complete",
                    "expected_status": 200,
                    "body": {
                        "actionType": {
                            "key": "PRIMARY_ACTION",
                            "label": "主要动作",
                            "value": "primary_action",
                        }
                    },
                },
            )
        ],
    )

    assert repair is not None
    assert repair.source == "deterministic_enum_body_leaf"
    assert repair.body == {"actionType": "PRIMARY_ACTION"}


def test_runtime_agent_request_repair_prompt_receives_failed_attempt_context() -> None:
    class CaptureClient:
        prompt = ""

        def complete(self, system: str, prompt: str) -> str:
            self.prompt = prompt
            return (
                '{"confidence":0.91,"variables":{"actionType":"PRIMARY_ACTION"},'
                '"body_patch":{"actionType":"PRIMARY_ACTION"},"reason":"根据第一次失败响应修复"}'
            )

    client = CaptureClient()
    agent = ApiFlowRuntimeAgent(ai_client=client)
    step = models.TestStep(
        id="step-2",
        order_index=2,
        kind="api",
        label="提交动作结果",
        action="api_request",
        target_url="/api/public/actions/complete",
        data={"method": "POST", "body": {"actionType": "{{actionType}}"}},
    )

    repair = agent.repair_failed_request(
        step=step,
        known_variables={},
        response_history=[],
        failed_attempts=[
            ApiFlowFailureAttempt(
                attempt=1,
                status_code=500,
                expected_status=200,
                error="响应状态码不符合期望",
                response_preview='{"success":false,"msg":"动作标识不能为空"}',
                response_content_type="application/json",
                request={
                    "method": "POST",
                    "url": "http://localhost:8000/api/public/actions/complete",
                    "expected_status": 200,
                    "body": {"actionType": ""},
                },
            )
        ],
    )

    assert repair is not None
    assert repair.variable_updates == {"actionType": "PRIMARY_ACTION"}
    assert repair.body_patch == {"actionType": "PRIMARY_ACTION"}
    assert '"failed_attempts"' in client.prompt
    assert "动作标识不能为空" in client.prompt
