from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.services.ai.base import CaseGenerationError
from app.services.ai_settings import ai_usage_options
from app.services.dom_preview_compiler import (
    DomPreviewCompilationError,
    compile_dom_module_preview,
    module_compile_source,
    static_compile_dom_module_preview,
)
from app.services.repo_reader import RepoReader


def test_repo_reader_extracts_only_config_pages_with_page_source(tmp_path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "pages.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "path": "pages/home/index",
                        "style": {"navigationBarTitleText": "首页"},
                    },
                    {
                        "path": "pages/entity/detail",
                        "style": {"navigationBarTitleText": "详情页"},
                    },
                ],
                "subPackages": [
                    {
                        "root": "sub",
                        "pages": [
                            {
                                "path": "pages/record/list",
                                "style": {"navigationBarTitleText": "记录页"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    page_file = frontend / "pages/home/index.vue"
    page_file.parent.mkdir(parents=True)
    page_file.write_text(
        '<template><button data-testid="primary-action" aria-label="确认">确认</button></template>',
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(frontend))

    page_modules = [module for module in summary.dom_modules if module["kind"] == "page"]
    routes = [module["route"] for module in page_modules]
    assert routes == ["/pages/home/index"]
    assert "/pages/entity/detail" not in routes
    assert "/sub/pages/record/list" not in routes
    home_module = page_modules[0]
    assert home_module["name"] == "首页"
    assert home_module["source_file"] == "pages/home/index.vue"
    assert home_module["config_source_file"] == "pages.json"
    assert home_module["preview"]["ai_usage_key"] == "dom_compilation"
    assert "首页" in home_module["preview"]["html"]
    assert "primary-action" in home_module["preview"]["html"]


def test_repo_reader_merges_src_page_config_with_page_body(tmp_path) -> None:
    frontend = tmp_path / "frontend"
    source_root = frontend / "src"
    source_root.mkdir(parents=True)
    (source_root / "pages.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "path": "pages/question/index",
                        "style": {"navigationBarTitleText": "常见问题"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    page_file = source_root / "pages/question/index.vue"
    page_file.parent.mkdir(parents=True)
    page_file.write_text(
        '<template><view><button data-testid="question-submit">提交</button></view></template>',
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(frontend))

    page_modules = [
        module
        for module in summary.dom_modules
        if module["kind"] == "page" and module["route"] == "/pages/question/index"
    ]
    assert len(page_modules) == 1
    assert page_modules[0]["source_file"] == "src/pages/question/index.vue"
    assert page_modules[0]["config_source_file"] == "src/pages.json"
    assert "question-submit" in page_modules[0]["preview"]["html"]


def test_dom_compile_source_resolves_page_config_to_page_body(tmp_path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "pages.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "path": "pages/question/index",
                        "style": {"navigationBarTitleText": "常见问题"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    page_file = source_root / "pages/question/index.vue"
    page_file.parent.mkdir(parents=True)
    page_file.write_text(
        '<template><view><button data-testid="question-submit">提交</button></view></template>',
        encoding="utf-8",
    )
    module = {
        "kind": "page",
        "name": "常见问题",
        "route": "/pages/question/index",
        "source": "src/pages.json:1",
        "source_file": "src/pages.json",
    }

    source = module_compile_source(tmp_path, module)
    preview = static_compile_dom_module_preview(module, source_text=source.source_text)

    assert source.source_file == "src/pages/question/index.vue"
    assert source.source_files == ["src/pages.json", "src/pages/question/index.vue"]
    assert "question-submit" in preview["html"]


def test_dom_compile_source_keeps_page_config_context_for_resolved_module(tmp_path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "pages.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "path": "pages/question/index",
                        "style": {"navigationBarTitleText": "常见问题"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    page_file = source_root / "pages/question/index.vue"
    page_file.parent.mkdir(parents=True)
    page_file.write_text("<template><view>页面内容</view></template>", encoding="utf-8")
    module = {
        "kind": "page",
        "name": "常见问题",
        "route": "/pages/question/index",
        "source": "src/pages/question/index.vue:1",
        "source_file": "src/pages/question/index.vue",
        "config_source_file": "src/pages.json",
    }

    source = module_compile_source(tmp_path, module)

    assert source.source_file == "src/pages/question/index.vue"
    assert source.source_files == ["src/pages.json", "src/pages/question/index.vue"]
    assert "页面源码：src/pages/question/index.vue" in source.source_text
    assert "页面路由配置：src/pages.json" in source.source_text


def test_dom_compile_disables_codex_exec_case_schema(monkeypatch) -> None:
    captured = {}

    class FakeClient:
        def complete(self, system: str, prompt: str) -> str:
            return json.dumps({"html": "<main>预览</main>", "warnings": []}, ensure_ascii=False)

    class FakeProvider:
        client = FakeClient()

    def fake_build_provider(settings):
        captured["output_schema_enabled"] = settings.codex_exec_output_schema_enabled
        captured["provider_config"] = settings.ai_provider_config
        return FakeProvider()

    monkeypatch.setattr(
        "app.services.dom_preview_compiler.build_case_generation_provider",
        fake_build_provider,
    )
    settings = get_settings().model_copy(
        update={
            "ai_provider": "codex_exec",
            "codex_exec_output_schema_enabled": True,
            "ai_provider_config": {"output_schema_enabled": True},
        }
    )

    preview = compile_dom_module_preview(
        {"kind": "page", "name": "页面", "route": "/pages/demo/index"},
        source_text="<template><view>内容</view></template>",
        settings=settings,
    )

    assert preview["html"].startswith("<!doctype html>")
    assert captured["output_schema_enabled"] is False
    assert captured["provider_config"]["output_schema_enabled"] is False


def test_dom_compile_provider_error_is_sanitized() -> None:
    class FailingClient:
        def complete(self, system: str, prompt: str) -> str:
            raise CaseGenerationError(
                "Invalid schema for response_format 'codex_output_schema': "
                "源码片段 <template>不应透传</template>"
            )

    with pytest.raises(DomPreviewCompilationError) as exc_info:
        compile_dom_module_preview(
            {"kind": "page", "name": "页面", "route": "/pages/demo/index"},
            source_text="<template>不应透传</template>",
            settings=get_settings(),
            client=FailingClient(),
        )

    message = str(exc_info.value)
    assert "结构化输出配置冲突" in message
    assert "<template>" not in message


def test_ai_usage_options_include_dom_compilation() -> None:
    assert any(option["key"] == "dom_compilation" for option in ai_usage_options())
