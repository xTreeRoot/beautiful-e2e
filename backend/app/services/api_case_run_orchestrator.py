from __future__ import annotations

from collections.abc import Generator, Iterable
from dataclasses import replace
from typing import Any

from app.models import TestCase, TestStep
from app.services.api_flow_runtime_agent import (
    ApiFlowFailureAttempt,
    ApiFlowResponseHistory,
    ApiFlowRuntimeAgent,
    RuntimeRequestRepair,
    RuntimeVariableInference,
)
from app.services.api_flow_variables import MissingApiFlowVariableError
from app.services.case_runner import ApiCaseRunner, ApiRequestSpec, ApiStepRunResult

API_STEP_MAX_ATTEMPTS = 3
_BODY_NOT_SET = object()

StreamEvent = tuple[str, dict[str, Any]]


class BackendApiCaseRunOrchestrator:
    """编排后端接口步骤运行、变量推导和失败重试。

    API 层只负责加载用例和返回 SSE；运行中的变量表、失败上下文和三次尝试
    策略都集中在这里，避免路由函数继续膨胀。
    """

    def __init__(
        self,
        *,
        runner: ApiCaseRunner,
        runtime_agent: ApiFlowRuntimeAgent | None,
        fail_fast: bool,
        is_single_step_debug: bool,
        max_attempts: int = API_STEP_MAX_ATTEMPTS,
    ) -> None:
        self.runner = runner
        self.runtime_agent = runtime_agent
        self.fail_fast = fail_fast
        self.is_single_step_debug = is_single_step_debug
        self.max_attempts = max(1, max_attempts)

    def stream(
        self,
        *,
        case: TestCase,
        api_steps: Iterable[TestStep],
        api_base_url: str,
        environment: str,
    ) -> Generator[StreamEvent, None, None]:
        passed = 0
        failed = 0
        flow_variables: dict[str, Any] = {}
        response_history: list[ApiFlowResponseHistory] = []
        steps = list(api_steps)

        yield (
            "start",
            {
                "message": (
                    "开始调试单个接口节点。"
                    if self.is_single_step_debug
                    else "开始执行后端接口用例。"
                ),
                "stage": "start",
                "case_id": case.id,
                "case_title": case.title,
                "api_base_url": api_base_url,
                "environment": environment,
                "total": len(steps),
            },
        )

        for step in steps:
            ok = yield from self._stream_step(step, flow_variables, response_history)
            if ok:
                passed += 1
            else:
                failed += 1
                if self.fail_fast:
                    break

        yield (
            "done",
            {
                "message": "单节点调试完成。" if self.is_single_step_debug else "接口运行完成。",
                "stage": "done",
                "status": "passed" if failed == 0 else "failed",
                "total": passed + failed,
                "passed": passed,
                "failed": failed,
            },
        )

    def _stream_step(
        self,
        step: TestStep,
        flow_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
    ) -> Generator[StreamEvent, None, bool]:
        runtime_inferences: list[RuntimeVariableInference] = []
        runtime_repairs: list[RuntimeRequestRepair] = []
        failed_attempts: list[ApiFlowFailureAttempt] = []
        body_override: Any = _BODY_NOT_SET
        body_patch: dict[str, Any] = {}
        attempt = 1

        while attempt <= self.max_attempts:
            request_spec = yield from self._build_request(
                step,
                flow_variables,
                response_history,
                runtime_inferences,
            )
            if request_spec is None:
                return False
            request_spec = _request_with_body_repair(request_spec, body_override, body_patch)

            yield (
                "request",
                {
                    "message": (
                        f"正在请求 {request_spec.method} {request_spec.url}"
                        if attempt == 1
                        else f"正在第 {attempt} 次尝试 {request_spec.method} {request_spec.url}"
                    ),
                    "stage": "request",
                    **request_spec.event_payload(),
                    "attempt": attempt,
                    "max_attempts": self.max_attempts,
                    "runtime_inferences": [
                        inference.event_payload() for inference in runtime_inferences
                    ],
                    "runtime_repairs": [repair.event_payload() for repair in runtime_repairs],
                },
            )

            result = self.runner.run_request(request_spec)
            response_history.append(_response_history_from_result(result))
            if result.ok:
                flow_variables.update(result.extracted_variables or {})
                yield (
                    "result",
                    {
                        "message": "请求通过",
                        "stage": "result",
                        **result.event_payload(),
                        "attempt": attempt,
                        "max_attempts": self.max_attempts,
                        "retry_pending": False,
                    },
                )
                return True

            failed_attempt = _failure_attempt_from_result(attempt, request_spec, result)
            failed_attempts.append(failed_attempt)
            can_retry = attempt < self.max_attempts and self.runtime_agent is not None
            yield (
                "result",
                {
                    "message": result.error or "请求未通过",
                    "stage": "result",
                    **result.event_payload(),
                    "attempt": attempt,
                    "max_attempts": self.max_attempts,
                    "retry_pending": can_retry,
                },
            )
            if not can_retry:
                return False

            yield _repair_event_payload(step, attempt, self.max_attempts, "running")
            repair = self.runtime_agent.repair_failed_request(
                step=step,
                known_variables=flow_variables,
                response_history=response_history,
                failed_attempts=failed_attempts,
            )
            if repair is None:
                yield _repair_event_payload(step, attempt, self.max_attempts, "failed")
                return False

            flow_variables.update(repair.variable_updates)
            if repair.body is not None:
                body_override = repair.body
            body_patch.update(repair.body_patch)
            runtime_repairs.append(repair)
            yield _repair_event_payload(step, attempt, self.max_attempts, "resolved", repair)
            attempt += 1

        return False

    def _build_request(
        self,
        step: TestStep,
        flow_variables: dict[str, Any],
        response_history: list[ApiFlowResponseHistory],
        runtime_inferences: list[RuntimeVariableInference],
    ) -> Generator[StreamEvent, None, ApiRequestSpec | None]:
        attempted_variables: set[str] = set()
        while True:
            try:
                return self.runner.build_request(step, flow_variables)
            except MissingApiFlowVariableError as exc:
                if self.is_single_step_debug:
                    error = (
                        f"单节点调试未填写变量：{exc.variable_name}，"
                        "请在 Path、Query 或 Body 中手动填入实际值。"
                    )
                    result = self.runner.build_step_error_result(step, error)
                    yield ("result", result.event_payload())
                    return None
                if exc.variable_name in attempted_variables:
                    result = self.runner.build_step_error_result(step, str(exc))
                    yield ("result", result.event_payload())
                    return None
                attempted_variables.add(exc.variable_name)
                yield (
                    "inference",
                    _runtime_inference_event_payload(
                        step,
                        variable=exc.variable_name,
                        status="running",
                        message=f"正在使用运行期 agent 推导变量：{exc.variable_name}",
                    ),
                )
                if self.runtime_agent is None:
                    result = self.runner.build_step_error_result(step, str(exc))
                    yield ("result", result.event_payload())
                    return None
                inference = self.runtime_agent.infer_missing_variable(
                    variable=exc.variable_name,
                    step=step,
                    known_variables=flow_variables,
                    response_history=response_history,
                )
                if inference is None:
                    error = f"运行期 agent 无法从前序响应推导变量：{exc.variable_name}"
                    yield (
                        "inference",
                        _runtime_inference_event_payload(
                            step,
                            variable=exc.variable_name,
                            status="failed",
                            message=error,
                        ),
                    )
                    result = self.runner.build_step_error_result(step, error)
                    yield ("result", result.event_payload())
                    return None
                flow_variables[exc.variable_name] = inference.value
                runtime_inferences.append(inference)
                yield (
                    "inference",
                    _runtime_inference_event_payload(
                        step,
                        variable=exc.variable_name,
                        status="resolved",
                        message=f"运行期 agent 已推导变量：{exc.variable_name}",
                        inference=inference,
                    ),
                )
            except ValueError as exc:
                result = self.runner.build_step_error_result(step, str(exc))
                yield ("result", result.event_payload())
                return None


def _request_with_body_repair(
    request_spec: ApiRequestSpec,
    body_override: Any,
    body_patch: dict[str, Any],
) -> ApiRequestSpec:
    if body_override is _BODY_NOT_SET and not body_patch:
        return request_spec

    body = request_spec.body if body_override is _BODY_NOT_SET else body_override
    if body_patch:
        body = {**body, **body_patch} if isinstance(body, dict) else dict(body_patch)
    return replace(request_spec, body=body)


def _response_history_from_result(result: ApiStepRunResult) -> ApiFlowResponseHistory:
    return ApiFlowResponseHistory(
        step_id=result.step_id,
        order_index=result.order_index,
        label=result.label,
        status_code=result.status_code,
        response_preview=result.response_preview,
        extracted_variables=result.extracted_variables or {},
    )


def _failure_attempt_from_result(
    attempt: int,
    request_spec: ApiRequestSpec,
    result: ApiStepRunResult,
) -> ApiFlowFailureAttempt:
    return ApiFlowFailureAttempt(
        attempt=attempt,
        status_code=result.status_code,
        expected_status=result.expected_status,
        error=result.error,
        response_preview=result.response_preview,
        response_content_type=result.response_content_type,
        request={
            "method": request_spec.method,
            "url": request_spec.url,
            "expected_status": request_spec.expected_status,
            "body": request_spec.body,
        },
    )


def _runtime_inference_event_payload(
    step: TestStep,
    *,
    variable: str,
    status: str,
    message: str,
    inference: RuntimeVariableInference | None = None,
) -> dict[str, Any]:
    data = step.data or {}
    payload: dict[str, Any] = {
        "message": message,
        "stage": "runtime_inference",
        "inference_status": status,
        "variable": variable,
        "step_id": step.id,
        "order_index": step.order_index,
        "label": step.label,
        "action": step.action,
        "method": str(data.get("method") or "GET").upper(),
        "target_url": step.target_url,
        "expected_status": data.get("expected_status") or step.expected or 200,
    }
    if inference is not None:
        payload["runtime_inference"] = inference.event_payload()
    return payload


def _repair_event_payload(
    step: TestStep,
    attempt: int,
    max_attempts: int,
    status: str,
    repair: RuntimeRequestRepair | None = None,
) -> StreamEvent:
    data = step.data or {}
    messages = {
        "running": f"第 {attempt} 次请求失败，运行期 agent 正在准备下一次尝试数据。",
        "resolved": f"运行期 agent 已准备第 {attempt + 1} 次尝试数据。",
        "failed": "运行期 agent 无法根据失败响应准备下一次尝试数据。",
    }
    payload: dict[str, Any] = {
        "message": messages.get(status, "运行期 agent 正在处理失败响应。"),
        "stage": "runtime_repair",
        "repair_status": status,
        "step_id": step.id,
        "order_index": step.order_index,
        "label": step.label,
        "action": step.action,
        "method": str(data.get("method") or "GET").upper(),
        "target_url": step.target_url,
        "expected_status": data.get("expected_status") or step.expected or 200,
        "attempt": attempt,
        "next_attempt": min(attempt + 1, max_attempts),
        "max_attempts": max_attempts,
    }
    if repair is not None:
        payload["runtime_repair"] = repair.event_payload()
    return "repair", payload
