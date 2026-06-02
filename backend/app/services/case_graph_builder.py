from __future__ import annotations

from typing import Any

from app.services.case_generation_types import GeneratedStep
from app.services.repo_reader import RepoSummary


def build_case_graph(
    steps: list[GeneratedStep],
    frontend: RepoSummary,
    backend: RepoSummary,
    execution_mode: str = "fullstack",
) -> dict[str, Any]:
    """把生成步骤转换为 React Flow 消费的稳定图结构。

    当前图布局是确定性兜底逻辑，节点 id 与步骤顺序绑定，便于前端保存选中状态
    和后续人工编辑；仓库摘要参数保留在签名里，避免供应商和规则生成器契约分叉。
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    start_x = 160
    start_y = 80
    col_width = 220
    row_height = 130
    columns = 4
    for index, step in enumerate(steps, start=1):
        node_id = f"step-{index}"
        col = (index - 1) % columns
        row = (index - 1) // columns
        nodes.append(
            {
                "id": node_id,
                "data": {"label": f"{index}. {step.label}"},
                "position": {"x": start_x + col * col_width, "y": start_y + row * row_height},
            }
        )
        if index > 1:
            source = f"step-{index - 1}"
            edges.append({"id": f"{source}-{node_id}", "source": source, "target": node_id})

    return {"nodes": nodes, "edges": edges}
