from __future__ import annotations

import re
from typing import Any

from app.services.case_generation_types import GeneratedStep


def reference_indexes(reference_documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """持久化引用文档追踪元数据时省略全文，保持用例记录紧凑。"""
    indexes: list[dict[str, Any]] = []
    for item in reference_documents:
        indexes.append(
            {
                "path": item.get("path"),
                "title": item.get("title"),
                "chars": item.get("chars"),
                "truncated": item.get("truncated"),
            }
        )
    return indexes


def clean_document_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"^[-*+]\s+", "", cleaned)
    cleaned = re.sub(r"^\d+[.)、]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" |")


class DocumentCaseStepBuilder:
    """根据引用文档构建浏览器侧确定性兜底步骤。

    这里不理解具体业务领域，只识别文档中的用户旅程表达；真实领域语义来自
    reference_documents，避免规则生成器逐步变成硬编码业务知识库。
    """

    def _reference_indexes(
        self, reference_documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return reference_indexes(reference_documents)

    def _document_grounded_client_steps(
        self,
        prompt: str,
        reference_documents: list[dict[str, Any]],
    ) -> list[GeneratedStep]:
        """根据引用的产品文档构建可编辑的浏览器步骤。

        这是供应商不可用时的确定性兜底逻辑。它只使用通用文档结构和客户端意图词，
        领域表达继续来自引用文档，避免把具体功能硬编码进生成器。
        """
        if not reference_documents or not self._asks_for_client_flow(prompt):
            return []

        candidates = self._document_flow_candidates(reference_documents)
        if not candidates:
            candidates = [("按引用文档执行客户端旅程", self._first_reference_title(reference_documents))]

        steps: list[GeneratedStep] = []
        for index, (label, source) in enumerate(candidates[:8], start=1):
            action = "goto" if index == 1 else "click"
            steps.append(
                GeneratedStep(
                    kind="action",
                    label=label,
                    action=action,
                    selector=None if action == "goto" else "[data-testid='documented-client-action']",
                    target_url="/" if action == "goto" else None,
                    expected="客户端页面或状态符合引用文档",
                    data={
                        "reference_source": source,
                        "reference_excerpt": label,
                        "document_grounded": True,
                    },
                )
            )

        steps.append(
            GeneratedStep(
                kind="assertion",
                label="验证文档描述的客户端最终状态",
                action="expect_visible",
                selector="[data-testid='documented-success-state'], body",
                expected="引用文档描述的用户可见结果已出现",
                data={"reference_documents": reference_indexes(reference_documents)},
            )
        )
        return steps

    def _asks_for_client_flow(self, prompt: str) -> bool:
        return any(token in prompt for token in ["客户端", "用户端", "前端", "页面", "小程序", "浏览器"])

    def _document_flow_candidates(
        self,
        reference_documents: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        candidates: list[tuple[int, str, str]] = []
        for document in reference_documents:
            source = str(document.get("title") or document.get("path") or "参考文档")
            content = str(document.get("content") or "")
            for line in content.splitlines():
                cleaned = self._clean_document_line(line)
                if len(cleaned) < 4:
                    continue
                score = self._client_flow_line_score(cleaned)
                if score <= 0:
                    continue
                candidates.append((score, cleaned[:120], source))

        deduped: dict[str, tuple[int, str]] = {}
        for score, label, source in sorted(candidates, key=lambda item: item[0], reverse=True):
            if label in deduped:
                continue
            deduped[label] = (score, source)
            if len(deduped) >= 12:
                break

        return [(label, source) for label, (_score, source) in deduped.items()]

    def _clean_document_line(self, line: str) -> str:
        return clean_document_line(line)

    def _client_flow_line_score(self, line: str) -> int:
        score = 0
        if any(token in line for token in ["客户端", "用户端", "前端", "页面", "小程序", "用户"]):
            score += 4
        if any(token in line for token in ["进入", "打开", "查看", "点击", "选择", "提交", "确认", "展示"]):
            score += 3
        if any(token in line for token in ["流程", "链路", "验收", "校验", "规则", "状态", "结果"]):
            score += 2
        if any(token in line.lower() for token in ["todo", "后台", "管理端", "后端", "接口"]):
            score -= 3
        return score

    def _first_reference_title(self, reference_documents: list[dict[str, Any]]) -> str:
        first = reference_documents[0] if reference_documents else {}
        return str(first.get("title") or first.get("path") or "参考文档")
