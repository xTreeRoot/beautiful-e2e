from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.schemas import CaseRunRequest


def project_settings_for_case_run(
    project_settings: Mapping[str, Any],
    payload: CaseRunRequest,
) -> dict[str, Any]:
    """合并本次运行携带的项目环境快照。

    前端允许用户先在侧栏切换环境或编辑地址、请求头，再直接运行用例。
    这份快照只覆盖本次执行读取的环境配置，不持久化到项目，也不写入节点，
    避免接口 DSL 绑定某个历史 host 或认证值。
    """

    settings = dict(project_settings)
    if payload.environment_settings is None:
        return settings

    runtime_settings = payload.environment_settings.model_dump(exclude_none=True)
    if not runtime_settings:
        return settings
    return {**settings, **runtime_settings}
