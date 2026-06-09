from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


REFERENCE_EXTENSIONS = {
    ".md",
    ".mdx",
    ".txt",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
}

IGNORED_REFERENCE_PARTS = {
    ".git",
    ".next",
    ".nuxt",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}


@dataclass(frozen=True)
class ReferenceDocument:
    path: str
    title: str
    content: str
    chars: int
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "content": self.content,
            "chars": self.chars,
            "truncated": self.truncated,
        }

    def as_index(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "chars": self.chars,
            "truncated": self.truncated,
        }


class PromptReferenceReader:
    """把提示词里提到的本地文档路径解析为模型可用上下文。

    远程 AI 供应商无法自行读取调用方机器上的绝对路径。后端会把显式本地路径展开为
    有长度上限的文本片段，并作为一等生成证据传给模型。
    """

    def __init__(
        self,
        *,
        max_documents: int = 18,
        max_chars_per_document: int = 5000,
        max_total_chars: int = 45000,
        max_candidate_files: int = 240,
    ) -> None:
        self.max_documents = max_documents
        self.max_chars_per_document = max_chars_per_document
        self.max_total_chars = max_total_chars
        self.max_candidate_files = max_candidate_files

    def collect(self, prompt: str) -> list[ReferenceDocument]:
        documents: list[ReferenceDocument] = []
        seen_paths: set[str] = set()
        remaining_chars = self.max_total_chars

        for path in self.extract_paths(prompt):
            for document in self._documents_for_path(path, prompt, remaining_chars):
                if document.path in seen_paths:
                    continue
                documents.append(document)
                seen_paths.add(document.path)
                remaining_chars -= len(document.content)
                if len(documents) >= self.max_documents or remaining_chars <= 0:
                    return documents

        return documents

    def extract_paths(self, prompt: str) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for raw_candidate in self._path_candidates(prompt):
            resolved = self._resolve_existing_path(raw_candidate)
            if not resolved:
                continue
            key = str(resolved)
            if key in seen:
                continue
            paths.append(resolved)
            seen.add(key)
        return paths

    def _path_candidates(self, prompt: str) -> list[str]:
        quoted = re.findall(r"[\"'“”‘’](/[^\"'“”‘’]+)[\"'“”‘’]", prompt)
        unquoted = re.findall(r"/[^\s，。；;,，]+", prompt)
        return [*quoted, *unquoted]

    def _resolve_existing_path(self, raw_candidate: str) -> Path | None:
        candidate = raw_candidate.strip().strip("()[]{}<>「」『』、，。；;,.")
        while candidate:
            path = Path(candidate).expanduser()
            if path.exists() and path != Path("/"):
                return path.resolve()
            candidate = candidate[:-1].rstrip("()[]{}<>「」『』、，。；;,.")
        return None

    def _documents_for_path(
        self,
        path: Path,
        prompt: str,
        remaining_chars: int,
    ) -> list[ReferenceDocument]:
        if path.is_file():
            document = self._read_document(path, path.parent, remaining_chars)
            return [document] if document else []
        if not path.is_dir():
            return []

        files = list(self._iter_reference_files(path))
        files.sort(key=lambda file_path: self._file_sort_key(file_path, prompt, path))

        documents: list[ReferenceDocument] = []
        for file_path in files[: self.max_candidate_files]:
            if len(documents) >= self.max_documents or remaining_chars <= 0:
                break
            document = self._read_document(file_path, path, remaining_chars)
            if not document:
                continue
            documents.append(document)
            remaining_chars -= len(document.content)
        return documents

    def _iter_reference_files(self, root: Path):
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in IGNORED_REFERENCE_PARTS for part in file_path.parts):
                continue
            if file_path.suffix.lower() not in REFERENCE_EXTENSIONS:
                continue
            yield file_path

    def _file_sort_key(self, file_path: Path, prompt: str, root: Path) -> tuple[int, int, str]:
        rel = file_path.relative_to(root).as_posix()
        search_text = f"{rel} {file_path.stem}".lower()
        prompt_text = prompt.lower()
        wants_interface_context = any(token in prompt_text for token in ["接口", "api", "http"])

        score = 0
        primary_document_terms = [
            "执行单",
            "需求",
            "readme",
        ]
        document_role_terms = [
            "页面",
            "ui",
            "原型",
            "用户端",
            "客户端",
            "user",
            "miniapp",
            "小程序",
            "story",
            "stories",
            "流程",
            "验证",
            "清单",
            "接口",
            "api",
            "http",
            "自测",
            "测试",
        ]
        interface_document_terms = [
            "接口",
            "api",
            "http",
            "接口地图",
            "接口目录",
            "接口变更",
            "客户端接口",
        ]
        fixture_document_terms = [
            "配置",
            "配置项",
            "文案",
            "规则",
            "接口变更记录",
            "原始请求响应",
            "测试执行摘要",
        ]
        for term in primary_document_terms:
            if term.lower() in search_text:
                score += 24
            if term.lower() in prompt_text and term.lower() in search_text:
                score += 8
        if wants_interface_context:
            for term in interface_document_terms:
                if term.lower() in search_text:
                    score += 28
        if any(token in prompt_text for token in ["名称", "名字", "标题", "固定", "id"]):
            for term in fixture_document_terms:
                if term.lower() in search_text:
                    score += 18
        for term in document_role_terms:
            if term.lower() in search_text:
                score += 8
            if term.lower() in prompt_text and term.lower() in search_text:
                score += 6

        if (
            not wants_interface_context
            and ("客户端" in prompt or "用户端" in prompt or "前端" in prompt)
            and any(
                term in search_text for term in ["backend", "后端", "admin", "管理端"]
            )
        ):
            score -= 10

        return (-score, len(file_path.relative_to(root).parts), rel)

    def _read_document(
        self,
        file_path: Path,
        root: Path,
        remaining_chars: int,
    ) -> ReferenceDocument | None:
        if remaining_chars <= 0:
            return None
        try:
            raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        if not raw_content.strip():
            return None

        limit = min(self.max_chars_per_document, remaining_chars)
        content = raw_content[:limit]
        truncated = len(raw_content) > len(content)
        title = file_path.relative_to(root).as_posix() if file_path.is_relative_to(root) else file_path.name
        return ReferenceDocument(
            path=str(file_path),
            title=title,
            content=content,
            chars=len(raw_content),
            truncated=truncated,
        )
