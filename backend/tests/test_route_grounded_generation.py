from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.cases import _effective_execution_mode
from app.models import Project, ProjectKnowledgeGraph, Repository
from app.services.api_entrypoint_flow import enforce_api_entrypoint_flow
from app.services.api_flow_diagnostics import annotate_api_flow_diagnostics
from app.services.api_generation_feedback import attach_api_generation_feedback
from app.services.api_route_contract_enforcer import enforce_api_route_contracts
from app.services.api_step_sanitizer import has_executable_api_step, sanitize_backend_api_steps
from app.services.ai.base import CaseGenerationContext, CaseGenerationError
from app.services.ai.case_completion import CompletionCaseProvider, build_case_generation_payload
from app.services.ai_case_generator import CaseGenerator, GeneratedCase, GeneratedStep
from app.services.generation_context import build_generation_context
from app.services.prompt_references import PromptReferenceReader
from app.services.project_analyzer import ProjectAnalyzer
from app.services.project_knowledge_graph import with_review_status
from app.services.project_llm_context import build_project_llm_context
from app.services.repo_reader import RepoReader, RepoSummary


def test_repo_reader_extracts_spring_routes_with_source_evidence(tmp_path) -> None:
    controller = tmp_path / "src/main/java/demo/WorkflowController.java"
    controller.parent.mkdir(parents=True)
    controller.write_text(
        """
        package demo;

        public class WorkflowController {
            @Operation(summary = "提交审核")
            @PostMapping("/api/private/reviews/submit")
            @Log("提交审核")
            public void submitReview(@RequestBody ReviewSubmitCmd cmd) {}
        }
        """,
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(tmp_path))

    assert summary.routes == [
        {
            "method": "POST",
            "path": "/api/private/reviews/submit",
            "summary": "提交审核",
            "log": "提交审核",
            "handler": "submitReview",
            "source": "src/main/java/demo/WorkflowController.java:6",
        }
    ]


def test_repo_reader_extracts_multiline_operation_summary(tmp_path) -> None:
    controller = tmp_path / "src/main/java/demo/CustomerSearchController.java"
    controller.parent.mkdir(parents=True)
    controller.write_text(
        '''
        package demo;

        public class CustomerSearchController {
            @Operation(summary = "资源搜索条件分页查询资源列表",
                    description = """
                            传参中如果 onlySpecial 为 true，则只返回特殊条件资源。
                            """)
            @PostMapping("/api/pb/resources/page")
            @Log("资源搜索条件分页查询资源分页")
            public void getResourcePage() {}
        }
        ''',
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(tmp_path))

    assert summary.routes[0]["summary"] == "资源搜索条件分页查询资源列表"
    assert summary.routes[0]["log"] == "资源搜索条件分页查询资源分页"


def test_repo_reader_extracts_java_request_body_dto_contract(tmp_path) -> None:
    controller = tmp_path / "src/main/java/demo/CustomerSearchController.java"
    controller.parent.mkdir(parents=True)
    controller.write_text(
        """
        package demo;

        import demo.dto.ResourceQry;

        public class CustomerSearchController {
            @Operation(summary = "资源搜索条件分页查询资源列表")
            @PostMapping("/api/pb/resources/page")
            public void getResourcePage(@Valid @RequestBody ResourceQry resourceQry) {}
        }
        """,
        encoding="utf-8",
    )
    dto = tmp_path / "src/main/java/demo/dto/ResourceQry.java"
    dto.parent.mkdir(parents=True)
    dto.write_text(
        """
        package demo.dto;

        import demo.page.PageRequest;
        import io.swagger.v3.oas.annotations.media.Schema;
        import lombok.Data;

        @Data
        public class ResourceQry extends PageRequest {
            @Schema(description = "经纬度", example = "113.317323,23.038455", requiredMode =
                    Schema.RequiredMode.REQUIRED)
            private String location;
            @Schema(description = "资源名称（搜索模式-模糊查询）")
            private String resourceName;
            @Schema(hidden = true)
            private String platform;
        }
        """,
        encoding="utf-8",
    )
    page_request = tmp_path / "src/main/java/demo/page/PageRequest.java"
    page_request.parent.mkdir(parents=True)
    page_request.write_text(
        """
        package demo.page;

        public class PageRequest {
            private Long page;
            private Long limit;
        }
        """,
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(tmp_path))
    route = summary.routes[0]
    body = route["request_body"]

    assert route["method"] == "POST"
    assert route["path"] == "/api/pb/resources/page"
    assert body["java_type"] == "ResourceQry"
    assert list(body["schema"]["properties"]) == ["page", "limit", "location", "resourceName"]
    assert "platform" not in body["schema"]["properties"]
    assert body["schema"]["required"] == ["location"]
    assert body["example"] == {
        "page": 1,
        "limit": 10,
        "location": "113.317323,23.038455",
    }


def test_repo_reader_extracts_swagger_routes_with_parameters_and_body(tmp_path) -> None:
    swagger = tmp_path / "openapi.json"
    swagger.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "servers": [{"url": "/client"}],
                "paths": {
                    "/api/public/demo/search": {
                        "get": {
                            "tags": ["客户端业务"],
                            "summary": "查询业务列表",
                            "operationId": "searchDemo",
                            "parameters": [
                                {
                                    "name": "keyword",
                                    "in": "query",
                                    "required": False,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "responses": {
                                "200": {
                                    "description": "成功",
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {"data": {"type": "array"}},
                                            }
                                        }
                                    },
                                }
                            },
                        }
                    },
                    "/api/private/demo/{demoId}/join": {
                        "post": {
                            "summary": "加入业务",
                            "operationId": "joinDemo",
                            "parameters": [
                                {
                                    "name": "demoId",
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                    "example": "1000000000000000001",
                                }
                            ],
                            "requestBody": {
                                "required": True,
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["credential"],
                                            "properties": {"credential": {"type": "string"}},
                                        },
                                        "example": {"credential": "{{businessCredential}}"},
                                    }
                                },
                            },
                            "responses": {"200": {"description": "成功"}},
                        }
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(tmp_path))
    generated = CaseGenerator().generate(
        "查询业务列表再加入业务",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=summary,
        execution_mode="backend_api",
    )

    assert [route["path"] for route in summary.routes] == [
        "/client/api/public/demo/search",
        "/client/api/private/demo/{demoId}/join",
    ]
    assert summary.routes[0]["source_type"] == "openapi"
    assert summary.routes[0]["parameters"][0]["name"] == "keyword"
    assert summary.routes[1]["request_body"]["example"] == {
        "credential": "{{businessCredential}}"
    }
    assert generated.steps[1].target_url == "/client/api/private/demo/1000000000000000001/join"
    assert generated.steps[1].data is not None
    assert generated.steps[1].data["body"] == {"credential": "{{businessCredential}}"}
    assert generated.steps[1].data["route_request_body"]["required"] is True


def test_api_route_contract_enforcer_corrects_body_to_real_dto_fields() -> None:
    generated = GeneratedCase(
        title="资源业务流程链路",
        description="资源业务流程链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="客户端资源分页查询：搜索目标资源",
                action="api_request",
                target_url="/customer/api/pb/resources/page",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "body": {"current": 1, "size": 20, "keyword": "目标关键词"},
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )
    route = {
        "method": "POST",
        "path": "/api/pb/resources/page",
        "summary": "资源搜索条件分页查询资源列表",
        "source": "CustomerSearchController.java:60",
        "request_body": {
            "required": True,
            "java_type": "ResourceQry",
            "schema": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "location": {"type": "string"},
                    "resourceName": {"type": "string"},
                },
                "required": ["location"],
            },
            "example": {"page": 1, "limit": 10, "location": "113.317323,23.038455"},
        },
    }

    enforced = enforce_api_route_contracts(generated, [route])
    data = enforced.steps[0].data or {}

    assert data["method"] == "POST"
    assert data["body"] == {
        "page": 1,
        "limit": 20,
        "resourceName": "目标关键词",
        "location": "113.317323,23.038455",
    }
    assert data["route_request_body"]["java_type"] == "ResourceQry"
    assert data["route_contract_enforced"] is True


def test_api_route_contract_enforcer_uses_reference_fixture_names_for_search_body() -> None:
    generated = GeneratedCase(
        title="资源业务流程链路",
        description="资源业务流程链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="客户端资源分页查询：搜索目标资源",
                action="api_request",
                target_url="/customer/api/pb/resources/page",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "body": {"current": 1, "size": 20, "keyword": "目标关键词"},
                },
            ),
            GeneratedStep(
                kind="api",
                label="流程首页",
                action="api_request",
                target_url="/customer/api/pb/workflows/resources/2057302278429007873/home",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_path_template": "/api/pb/workflows/resources/{resourceId}/home",
                },
            ),
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )
    routes = [
        {
            "method": "POST",
            "path": "/api/pb/resources/page",
            "summary": "资源搜索条件分页查询资源列表",
            "source": "CustomerSearchController.java:60",
            "request_body": {
                "required": True,
                "java_type": "ResourceQry",
                "schema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "location": {"type": "string"},
                        "resourceName": {"type": "string"},
                    },
                    "required": ["location"],
                },
                "example": {"page": 1, "limit": 10, "location": "113.317323,23.038455"},
            },
        },
        {
            "method": "GET",
            "path": "/api/pb/workflows/resources/{resourceId}/home",
            "summary": "流程首页",
            "source": "ResourceWorkflowHomeController.java:39",
        },
    ]
    references = [
        {
            "title": "P0配置项清单.md",
            "path": "/tmp/P0配置项清单.md",
            "content": """
            | 字段 | 类型 | 必填 | 默认值 | 说明 |
            | --- | --- | --- | --- | --- |
            | `workflow_name` | `string` | 是 | 无 | 运营内部名称，例如 `Alpha Demo Workflow`。 |
            | `display_title` | `string` | 是 | 无 | 用户端标题，例如 `Alpha Demo Workflow`。 |

            | 名称 | 值 | 说明 |
            | --- | --- | --- |
            | `resourceId` | `2057302278429007873` | 固定资源 ID；首页按资源查业务流程 |
            """,
            "chars": 520,
            "truncated": False,
        }
    ]

    enforced = enforce_api_route_contracts(generated, routes, references)
    search_data = enforced.steps[0].data or {}
    home_data = enforced.steps[1].data or {}

    assert search_data["method"] == "POST"
    assert search_data["body"] == {
        "page": 1,
        "limit": 20,
        "resourceName": "Alpha Demo Workflow",
        "location": "113.317323,23.038455",
    }
    assert search_data["reference_fixtures"]["fixed_ids"]["resourceId"] == "2057302278429007873"
    assert home_data["parameter_links"][0]["reason"].endswith("explicit_fixture。")


def test_entrypoint_flow_uses_dynamic_resource_id_when_prompt_requires_real_discovery() -> None:
    generated = GeneratedCase(
        title="资源业务流程链路",
        description="资源业务流程链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="流程首页",
                action="api_request",
                target_url="/customer/api/pb/workflows/resources/2057302278429007873/home",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_path_template": "/api/pb/workflows/resources/{resourceId}/home",
                    "parameter_links": [
                        {
                            "variable": "resourceId",
                            "value": "2057302278429007873",
                            "location": "target_url",
                            "reason": "引用文档声明的固定测试夹具 explicit_fixture。",
                        }
                    ],
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )
    routes = [
        {
            "method": "POST",
            "path": "/api/pb/resources/page",
            "summary": "资源搜索条件分页查询资源列表",
            "handler": "getResourcePage",
            "source": "CustomerSearchController.java:60",
            "request_body": {
                "required": True,
                "java_type": "ResourceQry",
                "schema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "location": {"type": "string"},
                        "resourceName": {"type": "string"},
                    },
                    "required": ["location"],
                },
                "example": {"page": 1, "limit": 10, "location": "113.317323,23.038455"},
            },
            "responses": [
                {
                    "status": 200,
                    "fields": ["page", "limit", "total", "list", "resourceId", "resourceName"],
                }
            ],
        },
        {
            "method": "GET",
            "path": "/api/pb/workflows/resources/{resourceId}/home",
            "summary": "用户流程首页状态",
            "source": "ResourceWorkflowHomeController.java:39",
        },
    ]
    references = [
        {
            "title": "接口地图.md",
            "path": "/tmp/接口地图.md",
            "content": """
            | 名称 | 值 | 说明 |
            | --- | --- | --- |
            | `resourceId` | `2057302278429007873` | 固定资源 ID；首页按资源查业务流程 |
            | `display_title` | `string` | 用户端标题，例如 `Alpha Demo Workflow`。 |
            """,
        }
    ]

    enforced = enforce_api_entrypoint_flow(
        generated,
        prompt=(
            "不要直接测目标业务页，要从客户端资源分页查询开始，真实找到目标资源，"
            "再用资源 id 进入资源详情，并串起目标业务完整流程。"
        ),
        routes=routes,
        reference_documents=references,
    )
    producer_data = enforced.steps[0].data or {}
    consumer_data = enforced.steps[1].data or {}

    assert enforced.steps[0].target_url == "/customer/api/pb/resources/page"
    assert producer_data["body"]["resourceName"] == "Alpha Demo Workflow"
    assert producer_data["extract"]["resourceId"] == "$.data.list[0].resourceId"
    assert enforced.steps[1].target_url == "/customer/api/pb/workflows/resources/{{resourceId}}/home"
    assert consumer_data["parameter_links"][0]["source"] == "previous_response"
    assert "value" not in consumer_data["parameter_links"][0]
    assert enforced.code_context["api_entrypoint_flow_enforcement"]["items"][0]["type"] == (
        "entrypoint_inserted"
    )


def test_entrypoint_flow_downgrades_fixture_id_when_dynamic_producer_is_missing() -> None:
    generated = GeneratedCase(
        title="资源业务流程链路",
        description="资源业务流程链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="流程首页",
                action="api_request",
                target_url="/customer/api/pb/workflows/resources/2057302278429007873/home",
                expected="200",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_path_template": "/api/pb/workflows/resources/{resourceId}/home",
                    "parameter_links": [
                        {
                            "variable": "resourceId",
                            "value": "2057302278429007873",
                            "location": "target_url",
                            "reason": "引用文档声明的固定测试夹具 explicit_fixture。",
                        }
                    ],
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )

    enforced = enforce_api_entrypoint_flow(
        generated,
        prompt=(
            "不要直接测目标业务页，要从客户端资源分页查询开始，真实找到目标资源，"
            "再用资源 id 进入详情。"
        ),
        routes=[
            {
                "method": "GET",
                "path": "/api/pb/workflows/resources/{resourceId}/home",
                "summary": "用户流程首页状态",
                "source": "ResourceWorkflowHomeController.java:39",
            }
        ],
        reference_documents=[],
    )
    data = enforced.steps[0].data or {}

    assert enforced.steps[0].target_url == "/customer/api/pb/workflows/resources/{{resourceId}}/home"
    assert "parameter_links" not in data or not data["parameter_links"]
    missing = [
        item
        for item in data["missing_upstream_steps"]
        if isinstance(item, dict) and item.get("variable") == "resourceId"
    ][0]
    unresolved = [
        item
        for item in data["unresolved_parameters"]
        if isinstance(item, dict) and item.get("variable") == "resourceId"
    ][0]
    assert missing["location"] == "target_url"
    assert unresolved["literal_value"] == "2057302278429007873"


def test_rule_based_api_generation_keeps_path_id_placeholder_for_dynamic_discovery() -> None:
    references = [
        {
            "title": "接口地图.md",
            "content": """
            客户端网关前缀：`/customer`
            | 场景 | 方法路径 | 说明 |
            | --- | --- | --- |
            | 资源首页 | GET /api/pb/workflows/resources/{resourceId}/home | resourceId 来自资源分页 |

            | 名称 | 值 | 说明 |
            | --- | --- | --- |
            | `resourceId` | `2057302278429007873` | 固定资源 ID |
            """,
        }
    ]
    backend = RepoSummary(
        path="/repo",
        exists=True,
        files=[],
        signals=[],
        routes=[
            {
                "method": "GET",
                "path": "/api/pb/workflows/resources/{resourceId}/home",
                "summary": "资源首页",
                "source": "ResourceWorkflowHomeController.java:39",
            }
        ],
    )

    generated = CaseGenerator().generate(
        "不要直接测目标业务页，要从客户端资源分页查询开始，真实找到目标资源，再用资源 id 进入详情。",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=backend,
        execution_mode="backend_api",
        reference_documents=references,
    )
    data = generated.steps[0].data or {}

    assert generated.steps[0].target_url == "/customer/api/pb/workflows/resources/{{resourceId}}/home"
    assert "parameter_links" not in data


def test_api_route_contract_enforcer_corrects_near_miss_route_and_query_body_contract() -> None:
    generated = GeneratedCase(
        title="客户端资源查询链路",
        description="客户端资源查询链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="资源分页查询找到目标资源",
                action="api_request",
                target_url="/customer/api/pd/resources/page?page=1&limit=20&keyword=目标查询词",
                expected="200",
                data={"method": "GET", "expected_status": 200},
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )
    routes = [
        {
            "method": "POST",
            "path": "/api/pb/resources/page",
            "summary": "资源搜索条件分页查询资源列表",
            "source": "CustomerResourceController.java:60",
            "request_body": {
                "required": True,
                "java_type": "ResourceQry",
                "schema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "resourceName": {"type": "string"},
                    },
                },
            },
        }
    ]

    enforced = enforce_api_route_contracts(generated, routes)
    step = enforced.steps[0]
    data = step.data or {}

    assert step.target_url == "/customer/api/pb/resources/page"
    assert data["method"] == "POST"
    assert data["body"] == {"page": 1, "limit": 20, "resourceName": "目标查询词"}
    assert data["route_source"] == "CustomerResourceController.java:60"
    assert any(item["field"] == "target_url" for item in data["route_contract_corrections"])


def test_api_generation_feedback_persists_agent_prompt_and_diagnostics() -> None:
    generated = GeneratedCase(
        title="资源概览链路",
        description="资源概览链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="资源概览信息",
                action="api_request",
                target_url="/api/public/resources/{{resource_id}}/overview",
                data={
                    "method": "GET",
                    "missing_upstream_steps": [
                        {
                            "type": "missing_upstream_step",
                            "variable": "resource_id",
                            "candidate_routes": [
                                {"method": "GET", "path": "/api/public/resources/search"}
                            ],
                        }
                    ],
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={
            "execution_mode": "backend_api",
            "api_flow_diagnostics": {
                "items": [
                    {
                        "type": "missing_upstream_step",
                        "variable": "resource_id",
                    }
                ]
            },
        },
    )

    feedback_case = attach_api_generation_feedback(generated)
    feedback = feedback_case.code_context["api_generation_feedback"]

    assert feedback["version"] == "api_generation_feedback.v1"
    assert "404" in feedback["agent_prompt"]
    assert feedback["flow_diagnostics"][0]["variable"] == "resource_id"
    assert feedback["step_feedback"][0]["missing_upstream_steps"][0]["variable"] == "resource_id"


def test_repo_reader_skips_non_openapi_multi_document_yaml(tmp_path) -> None:
    config = tmp_path / "application.yml"
    config.write_text(
        """
        nacos:
          server-addr: 127.0.0.1:8848
        ---
        spring:
          datasource:
            url: jdbc:mysql://127.0.0.1:3306/demo
        """,
        encoding="utf-8",
    )

    summary = RepoReader().summarize(str(tmp_path))

    assert summary.routes == []


def test_backend_api_fallback_uses_route_catalog_instead_of_fabricated_urls() -> None:
    backend = RepoSummary(
        path="/repo",
        exists=True,
        files=[],
        signals=[],
        routes=[
            {
                "method": "GET",
                "path": "/api/public/articles/search",
                "summary": "文章搜索列表",
                "log": "按关键词查询文章列表",
                "handler": "searchArticles",
                "source": "ArticleController.java:60",
            },
            {
                "method": "GET",
                "path": "/api/public/articles/{articleId}/detail",
                "summary": "文章详情",
                "log": "查看文章详情",
                "handler": "getArticleDetail",
                "source": "ArticleController.java:80",
            },
            {
                "method": "POST",
                "path": "/api/private/reviews/submit",
                "summary": "提交审核",
                "log": "提交审核申请",
                "handler": "submitReview",
                "source": "ReviewController.java:52",
            },
            {
                "method": "GET",
                "path": "/api/private/reviews/status/{reviewId}",
                "summary": "查询审核状态",
                "log": "查询审核状态",
                "handler": "getReviewStatus",
                "source": "ReviewController.java:78",
            },
        ],
    )
    frontend = RepoSummary(path=None, exists=False, files=[], signals=[], routes=[])

    generated = CaseGenerator().generate(
        "从文章搜索到文章详情再到提交审核并查询审核状态的全链路测试",
        frontend=frontend,
        backend=backend,
        execution_mode="backend_api",
    )
    urls = [step.target_url for step in generated.steps]

    assert "/api/fallback" not in urls
    assert urls == [
        "/api/public/articles/search",
        "/api/public/articles/1/detail",
        "/api/private/reviews/submit",
        "/api/private/reviews/status/1",
    ]
    assert all(step.data and step.data.get("route_source") for step in generated.steps)


def test_backend_api_mode_injects_builtin_agent_and_route_skill() -> None:
    context = build_generation_context(
        project_id="project-id",
        execution_mode="backend_api",
        agent_id=None,
        skill_ids=[],
        db=None,  # type: ignore[arg-type]
    )

    assert context.agent is not None
    assert context.agent["id"] == "backend-api-flow-inference-agent"
    assert [skill["id"] for skill in context.skills] == [
        "backend-api-entrypoint-first",
        "backend-api-route-grounding",
        "backend-api-parameter-inference",
    ]
    assert "流程入口" in context.skills[0]["prompt"]
    assert "真实依据" in context.skills[1]["prompt"]
    assert "参数来源" in context.skills[2]["prompt"]


def test_prompt_reference_reader_collects_documents_from_prompt_path(tmp_path) -> None:
    (tmp_path / "执行单.md").write_text("# 执行单\n\n## 客户端流程\n- 用户进入业务页面\n", encoding="utf-8")
    (tmp_path / "stories").mkdir()
    (tmp_path / "stories/user-flow.md").write_text(
        "# 用户故事\n\n- 客户端选择目标并提交\n",
        encoding="utf-8",
    )

    documents = PromptReferenceReader(max_documents=4).collect(
        f"根据{tmp_path} 生成客户端全流程测试用例"
    )

    assert [document.title for document in documents][:2] == ["执行单.md", "stories/user-flow.md"]
    assert "用户进入业务页面" in documents[0].content


def test_prompt_reference_reader_prioritizes_interface_docs_for_real_api_prompt(tmp_path) -> None:
    (tmp_path / "执行单.md").write_text("# 执行单\n", encoding="utf-8")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "platform-backend-客户端接口.md").write_text(
        "# 前端接口目录\n\n| 场景 | 方法 | 路径 |\n| --- | --- | --- |\n| 业务首页 | `GET` | `/api/public/demo/{demoId}/home` |\n",
        encoding="utf-8",
    )
    (tmp_path / "stories").mkdir()
    (tmp_path / "stories" / "user-flow.md").write_text("# 用户故事\n", encoding="utf-8")

    documents = PromptReferenceReader(max_documents=4).collect(
        f"根据{tmp_path} 生成客户端全流程测试真实接口"
    )

    assert documents[0].title == "evidence/platform-backend-客户端接口.md"


def test_reference_documents_drive_client_flow_without_feature_specific_rules() -> None:
    references = [
        {
            "path": "/tmp/spec/需求.md",
            "title": "需求.md",
            "content": """
            # 需求
            ## 用户端流程
            - 用户进入业务页面
            - 用户选择目标并提交
            - 页面展示处理结果
            """,
            "chars": 80,
            "truncated": False,
        }
    ]
    generated = CaseGenerator().generate(
        "根据/tmp/spec 生成客户端全流程测试用例",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        execution_mode="fullstack",
        reference_documents=references,
    )

    labels = [step.label for step in generated.steps]
    assert "用户进入业务页面" in labels
    assert "用户选择目标并提交" in labels
    assert generated.code_context["reference_documents"] == [
        {"path": "/tmp/spec/需求.md", "title": "需求.md", "chars": 80, "truncated": False}
    ]


def test_backend_api_uses_referenced_interface_chain_and_route_evidence() -> None:
    references = [
        {
            "path": "/tmp/spec/接口地图.md",
            "title": "接口地图.md",
            "content": """
            # 前端接口地图
            客户端网关前缀：`/client`

            | 名称 | 值 | 说明 |
            | --- | --- | --- |
            | `demoId` | `1000000000000000001` | 固定业务 ID |

            ## 推荐调用顺序
            1. 用户进入业务页：先调「业务首页」。
            2. 用户点击参与：登录后调「加入业务」。

            | 场景 | 方法 | 路径 | 登录 |
            | --- | --- | --- | --- |
            | 业务首页 | `GET` | `/api/public/demo/{demoId}/home` | 可选 |
            | 加入业务 | `POST` | `/api/private/demo/{demoId}/join` | 必须 |
            """,
            "chars": 420,
            "truncated": False,
        }
    ]
    backend = RepoSummary(
        path="/repo",
        exists=True,
        files=[],
        signals=[],
        routes=[
            {
                "method": "GET",
                "path": "/api/public/demo/{demoId}/home",
                "summary": "业务首页",
                "log": "业务首页",
                "handler": "home",
                "source": "DemoController.java:10",
            },
            {
                "method": "POST",
                "path": "/api/private/demo/{demoId}/join",
                "summary": "加入业务",
                "log": "加入业务",
                "handler": "join",
                "source": "DemoController.java:20",
            },
        ],
    )

    generated = CaseGenerator().generate(
        "根据/tmp/spec 生成客户端全流程测试真实接口",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=backend,
        execution_mode="backend_api",
        reference_documents=references,
    )

    assert [step.action for step in generated.steps] == ["api_request", "api_request"]
    assert [step.target_url for step in generated.steps] == [
        "/client/api/public/demo/1000000000000000001/home",
        "/client/api/private/demo/1000000000000000001/join",
    ]
    assert generated.steps[0].data is not None
    assert generated.steps[0].data["route_source"] == "DemoController.java:10"
    assert generated.steps[0].data["reference_source"] == "接口地图.md"
    assert generated.steps[1].data is not None
    assert generated.steps[1].data["body_required"] is True
    assert "api_flow_relationship_prompt" in generated.code_context


def test_reference_docs_can_define_response_extract_and_body_parameter_links() -> None:
    references = [
        {
            "path": "/tmp/spec/接口链路.md",
            "title": "接口链路.md",
            "content": """
            # 前端接口链路

            | 场景 | 方法 | 路径 | 响应提取 | 请求体 |
            | --- | --- | --- | --- | --- |
            | 查询访问凭证 | `GET` | `/api/private/demo/credential` | 返回 `accessCredential` | - |
            | 执行业务动作 | `POST` | `/api/private/demo/execute` | - | {"credential":"{{accessCredential}}"} |
            """,
            "chars": 320,
            "truncated": False,
        }
    ]
    backend = RepoSummary(
        path="/repo",
        exists=True,
        files=[],
        signals=[],
        routes=[
            {
                "method": "GET",
                "path": "/api/private/demo/credential",
                "summary": "查询访问凭证",
                "log": "查询访问凭证",
                "handler": "credential",
                "source": "DemoController.java:10",
            },
            {
                "method": "POST",
                "path": "/api/private/demo/execute",
                "summary": "执行业务动作",
                "log": "执行业务动作",
                "handler": "execute",
                "source": "DemoController.java:20",
            },
        ],
    )

    generated = CaseGenerator().generate(
        "根据/tmp/spec 生成客户端全流程测试真实接口",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=backend,
        execution_mode="backend_api",
        reference_documents=references,
    )

    producer = generated.steps[0].data or {}
    consumer = generated.steps[1].data or {}

    assert producer["extract"]["accessCredential"] == "$.data.accessCredential"
    assert consumer["body"] == {"credential": "{{accessCredential}}"}
    assert consumer["parameter_links"][0]["variable"] == "accessCredential"
    assert consumer["depends_on"][0]["from_step_label"] == "查询访问凭证"


def test_flow_diagnostics_marks_hardcoded_id_as_missing_upstream_step() -> None:
    generated = GeneratedCase(
        title="资源概览链路",
        description="资源概览链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="资源概览信息",
                action="api_request",
                target_url="/api/public/resources/2057302278429007873/overview",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_path_template": "/api/public/resources/{resourceId}/overview",
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )
    annotated = annotate_api_flow_diagnostics(
        generated,
        [
            {
                "method": "POST",
                "path": "/api/public/resources/search",
                "summary": "资源查询列表",
                "handler": "searchResources",
                "source": "ResourceController.java:60",
            }
        ],
    )

    data = annotated.steps[0].data or {}
    missing = data["missing_upstream_steps"][0]

    assert missing["variable"] == "resource_id"
    assert missing["literal_value"] == "2057302278429007873"
    assert missing["candidate_routes"][0]["path"] == "/api/public/resources/search"
    assert annotated.code_context["api_flow_diagnostics"]["missing_upstream_step_count"] == 1


def test_flow_diagnostics_marks_missing_required_query_parameter() -> None:
    generated = GeneratedCase(
        title="资源预检链路",
        description="资源预检链路",
        priority="P1",
        steps=[
            GeneratedStep(
                kind="api",
                label="资源查询",
                action="api_request",
                target_url="/api/public/resources/search",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "extract": {"resourceId": "$.data.list[0].resourceId"},
                },
            ),
            GeneratedStep(
                kind="api",
                label="资源预检",
                action="api_request",
                target_url="/api/public/resources/{{resourceId}}/preview",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_path_template": "/api/public/resources/{resourceId}/preview",
                    "extract": {"resourceId": "$.data.resourceId"},
                    "route_parameters": [
                        {"name": "resourceId", "in": "path", "required": True},
                        {"name": "targetUserId", "in": "query", "required": True},
                    ],
                },
            )
        ],
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
    )

    annotated = annotate_api_flow_diagnostics(generated, [])
    data = annotated.steps[1].data or {}

    missing = [
        item
        for item in data["missing_upstream_steps"]
        if isinstance(item, dict) and item.get("variable") == "targetUserId"
    ][0]
    assert missing["location"] == "query"


def test_case_generation_payload_requires_upstream_discovery_rules() -> None:
    project_context = {
        "version": "project_llm_context.v1",
        "auth": {
            "effective_mode": "login_flow",
            "configured_header_keys": ["X-Customer-Token"],
            "likely_auth_header_keys": ["X-Customer-Token"],
            "login_route_candidates": [
                {"method": "POST", "path": "/customer/api/pb/user/login"}
            ],
            "redacted": True,
        },
        "repositories": [
            {
                "kind": "backend",
                "auth_profile": {
                    "mode_hint": "login_flow",
                    "login_route_candidates": [
                        {"method": "POST", "path": "/customer/api/pb/user/login"}
                    ],
                    "header_candidates": ["X-Customer-Token"],
                },
            }
        ],
        "rules": [
            "登录态可以来自环境请求头或可执行登录接口；业务实体 ID 仍必须来自前置响应或显式测试夹具。",
            "如果生成输入提供 reference_fixtures，必须先使用固定 ID。",
        ],
    }
    context = CaseGenerationContext(
        prompt="生成客户端真实接口链路",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path="/repo", exists=True, files=[], signals=[], routes=[]),
        execution_mode="backend_api",
        project_context=project_context,
        auth_context=project_context["auth"],
        reference_documents=[
            {
                "title": "接口地图.md",
                "content": """
                | 名称 | 值 | 说明 |
                | --- | --- | --- |
                | `resourceId` | `2057302278429007873` | 固定资源 ID |
                | 页面主标题 | `Alpha Demo Workflow` | 用户端展示 |
                """,
            }
        ],
    )
    payload = build_case_generation_payload(context)

    assert "upstream_discovery_rules" in payload
    assert any("搜索" in rule or "列表" in rule for rule in payload["upstream_discovery_rules"])
    assert "missing_upstream_steps" in payload["api_flow_contract"]
    assert payload["project_context"]["version"] == "project_llm_context.v1"
    assert payload["project_context"]["auth"]["effective_mode"] == "project_request_headers"
    assert "login_route_candidates" not in payload["project_context"]["auth"]
    repository_auth = payload["project_context"]["repositories"][0]["auth_profile"]
    assert repository_auth["mode_hint"] == "project_request_headers"
    assert "login_route_candidates" not in repository_auth
    assert payload["auth_context"]["effective_mode"] == "project_request_headers"
    assert payload["auth_context"]["likely_auth_header_keys"] == ["X-Customer-Token"]
    assert "login_route_candidates" not in payload["auth_context"]
    assert payload["reference_fixtures"]["fixed_ids"]["resourceId"] == "2057302278429007873"
    assert payload["reference_fixtures"]["entity_names"][0]["value"] == "Alpha Demo Workflow"
    assert any("项目请求头" in rule for rule in payload["auth_context_rules"])
    assert not any("login_flow" in rule for rule in payload["auth_context_rules"])
    assert any("reference_fixtures" in rule for rule in payload["reference_document_rules"])


def test_rule_based_generation_does_not_inject_login_steps_from_prompt() -> None:
    generated = CaseGenerator().generate(
        "登录后进入记录列表并校验状态",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        execution_mode="fullstack",
    )

    labels = [step.label for step in generated.steps]

    assert "进入登录页" not in labels
    assert "提交登录" not in labels
    assert all(step.target_url != "/login" for step in generated.steps)
    assert generated.code_context["auth_context"]["effective_mode"] == "project_request_headers"


def test_backend_api_sanitizer_drops_auth_guidance_pseudo_step() -> None:
    generated = GeneratedCase(
        title="客户端接口链路",
        description="客户端接口链路",
        priority="P1",
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
        steps=[
            GeneratedStep(
                kind="api",
                label="匿名可调，如果本地已有登录态，也可以带 Authorization",
                action="api_request",
                target_url="/api/pb/",
                data={
                    "method": "GET",
                    "expected_status": 200,
                    "route_source": "evidence/client-api-map.md",
                    "route_summary": "匿名可调，如果本地已有登录态，也可以带 Authorization，部分接口会返回用户相关状态。",
                    "route_path_template": "/api/pb/",
                },
            ),
            GeneratedStep(
                kind="api",
                label="查询资源列表",
                action="api_request",
                target_url="/api/pb/resources/page",
                data={"method": "POST", "expected_status": 200},
            ),
        ],
    )

    sanitized = sanitize_backend_api_steps(
        generated,
        [{"method": "POST", "path": "/api/pb/resources/page", "summary": "资源分页"}],
    )

    assert [step.label for step in sanitized.steps] == ["查询资源列表"]
    assert has_executable_api_step(sanitized) is True
    dropped = sanitized.code_context["dropped_non_executable_api_steps"]["items"][0]
    assert dropped["target_url"] == "/api/pb/"
    assert "认证" in dropped["reason"] or "前缀" in dropped["reason"]


def test_backend_api_sanitizer_marks_all_auth_guidance_steps_non_executable() -> None:
    generated = GeneratedCase(
        title="认证说明",
        description="认证说明",
        priority="P1",
        graph={"nodes": [], "edges": []},
        code_context={"execution_mode": "backend_api"},
        steps=[
            GeneratedStep(
                kind="api",
                label="本地已有登录态时带 Authorization",
                action="api_request",
                target_url="/api/pb/",
                data={
                    "method": "GET",
                    "route_summary": "登录态说明，不是业务接口。",
                    "route_path_template": "/api/pb/",
                },
            )
        ],
    )

    sanitized = sanitize_backend_api_steps(generated, [])

    assert sanitized.steps == []
    assert has_executable_api_step(sanitized) is False


def test_case_generation_payload_extracts_explicit_flow_entrypoint() -> None:
    context = CaseGenerationContext(
        prompt="不要直接测目标业务页，要从客户端资源分页查询开始，再进入详情和目标业务完整流程",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path="/repo", exists=True, files=[], signals=[], routes=[]),
        execution_mode="backend_api",
    )

    payload = build_case_generation_payload(context)

    assert payload["flow_entrypoint"]["explicit"] is True
    assert payload["flow_entrypoint"]["raw_text"] == "资源分页查询"
    assert payload["flow_entrypoint"]["must_be_first_executable_step"] is True
    assert payload["flow_entrypoint"]["requires_dynamic_discovery"] is True
    assert any("第一个可执行 api_request" in rule for rule in payload["flow_entrypoint_rules"])
    assert any("fixed_ids" in rule for rule in payload["flow_entrypoint_rules"])


def test_completion_provider_rejects_backend_api_step_without_url() -> None:
    class StaticClient:
        def complete(self, system: str, prompt: str) -> str:
            return json.dumps(
                {
                    "title": "接口链路",
                    "description": "接口链路",
                    "priority": "P1",
                    "steps": [
                        {
                            "kind": "api",
                            "label": "接口链路表：先查询列表再进入详情",
                            "action": "api_request",
                            "selector": None,
                            "target_url": None,
                            "value": None,
                            "expected": "200",
                            "data": {"method": "GET"},
                        }
                    ],
                },
                ensure_ascii=False,
            )

    provider = CompletionCaseProvider(
        name="fake_provider",
        mode="test",
        client=StaticClient(),
    )
    context = CaseGenerationContext(
        prompt="从业务分页查询开始生成真实接口链路",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path="/repo", exists=True, files=[], signals=[], routes=[]),
        execution_mode="backend_api",
    )

    with pytest.raises(CaseGenerationError, match="缺少 target_url"):
        provider.generate(context)


def test_project_llm_context_exposes_route_contract_examples(mysql_engine: Engine) -> None:
    backend = RepoSummary(
        path="/repo",
        exists=True,
        files=[],
        signals=[],
        routes=[
            {
                "method": "POST",
                "path": "/api/pb/resources/page",
                "summary": "资源搜索条件分页查询资源列表",
                "source": "CustomerSearchController.java:60",
                "request_body": {
                    "required": True,
                    "java_type": "ResourceQry",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer"},
                            "limit": {"type": "integer"},
                            "resourceName": {"type": "string"},
                        },
                        "required": [],
                    },
                },
            }
        ],
    )
    with Session(mysql_engine) as db:
        project = Project(name="project-context-route-contract-test")
        db.add(project)
        db.flush()
        context = build_project_llm_context(
            project.id,
            {},
            db,
            repository_summaries={"backend": backend},
        )

    backend_context = context["repositories"][0]

    assert backend_context["route_contract_profile"]["request_body_route_count"] == 1
    assert backend_context["route_contract_examples"][0]["request_body"]["fields"] == [
        "page",
        "limit",
        "resourceName",
    ]
    assert any("真实 DTO 字段" in rule for rule in context["rules"])


def test_backend_toggle_keeps_project_selected_execution_mode() -> None:
    assert _effective_execution_mode("backend_api", "根据/any/path 生成客户端全流程测试用例") == "backend_api"
    assert _effective_execution_mode("backend_api", "根据页面清单生成后端接口测试用例") == "backend_api"
    assert _effective_execution_mode("backend_api", "根据接口变更记录生成后端接口测试用例") == "backend_api"


def test_project_analyzer_persists_repository_index_summary(tmp_path, mysql_engine: Engine) -> None:
    backend = tmp_path / "backend"
    frontend = tmp_path / "frontend"
    backend.mkdir()
    frontend.mkdir()
    (backend / "pom.xml").write_text("<project />", encoding="utf-8")
    controller = backend / "ResourceController.java"
    controller.write_text(
        """
        public class ResourceController {
            @GetMapping("/api/public/resources/{id}/detail")
            @Operation(summary = "资源详情")
            public void detail() {}
        }
        """,
        encoding="utf-8",
    )
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (frontend / "src").mkdir()
    (frontend / "src/App.tsx").write_text(
        "<button data-testid=\"submit-form\" aria-label=\"提交表单\" />",
        encoding="utf-8",
    )

    engine = mysql_engine
    with Session(engine) as db:
        project = Project(name="analysis-test")
        db.add(project)
        db.flush()
        ProjectAnalyzer().analyze(
            project.id,
            {
                "workspace_path": str(tmp_path),
                "frontend_repo_path": "",
                "backend_repo_path": "",
            },
            db,
        )
        db.commit()

        repositories = {
            repo.kind: repo
            for repo in db.scalars(select(Repository).where(Repository.project_id == project.id))
        }

    assert repositories["backend"].index_summary["routes"][0]["path"] == "/api/public/resources/{id}/detail"
    assert repositories["frontend"].index_summary["dom_targets"][0]["value"] == "submit-form"


def test_project_analyzer_groups_routes_and_relationships_with_code_evidence(
    tmp_path,
    mysql_engine: Engine,
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("<project />", encoding="utf-8")
    (backend / "CustomerSearchController.java").write_text(
        '''
        public class CustomerSearchController {
            @Operation(summary = "资源搜索条件分页查询资源列表",
                    description = """
                            传参中如果 onlySpecial 为 true，则只返回特殊条件资源。
                            """)
            @PostMapping("/api/pb/resources/page")
            @Log("资源搜索条件分页查询资源分页")
            public void getResourcePage() {}

            @Operation(summary = "特殊子域资源分页")
            @PostMapping("/api/pb/resources/special/page")
            @Log("资源搜索条件分页查询资源列表")
            public void getResourcePageInSpecialScope() {}

            @Operation(summary = "资源详情")
            @GetMapping("/api/pb/resources/detail/{id}")
            public void detail() {}

            @Operation(summary = "用户流程首页状态")
            @GetMapping("/api/pb/workflows/resources/{resourceId}/home")
            public void home() {}
        }
        ''',
        encoding="utf-8",
    )

    with Session(mysql_engine) as db:
        project = Project(name="analysis-route-module-test")
        db.add(project)
        db.flush()
        ProjectAnalyzer().analyze(
            project.id,
            {
                "workspace_path": str(tmp_path),
                "frontend_repo_path": "",
                "backend_repo_path": "",
            },
            db,
        )
        db.commit()

        repository = db.scalar(
            select(Repository).where(
                Repository.project_id == project.id,
                Repository.kind == "backend",
            )
        )
        knowledge_graph = db.scalar(
            select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project.id)
        )
        project_context = build_project_llm_context(project.id, {}, db)

    assert repository is not None
    assert knowledge_graph is not None
    analysis = repository.index_summary["analysis"]
    graph = knowledge_graph.graph
    modules = {module["id"]: module for module in analysis["modules"]}
    graph_modules = {module["source_module_id"]: module for module in graph["modules"]}
    resource_routes = {
        route["path"]: route
        for route in modules["module_resources"]["routes"]
    }
    special_scope_routes = {
        route["path"]: route
        for route in modules["module_resources_special"]["routes"]
    }
    resource_relationship = next(
        relationship
        for relationship in analysis["relationships"]
        if relationship["variable"] == "resourceId"
        and relationship["from_route"]["path"] == "/api/pb/resources/page"
        and relationship["to_route"]["path"]
        == "/api/pb/workflows/resources/{resourceId}/home"
    )

    assert resource_routes["/api/pb/resources/page"]["role"] == "discovery"
    assert resource_routes["/api/pb/resources/page"]["produces"] == ["resourceId"]
    assert "/api/pb/resources/special/page" in special_scope_routes
    assert "只有提示词、文档或人工审核命中这些子域词" in modules["module_resources_special"]["scope_boundary"]
    assert resource_relationship["from_module"] == "module_resources"
    assert resource_relationship["to_module"] == "module_workflows_resources"
    assert resource_relationship["confirmed"] is False
    assert "source=" in resource_relationship["evidence"][0]
    assert knowledge_graph.review_status == "draft"
    assert graph["review"]["fact_strength"] == "candidate"
    assert graph_modules["module_resources_special"]["routes"][0]["excluded_scenarios"]
    assert project_context["repositories"][0]["analysis"]["modules"]
    assert project_context["knowledge_graph"] is None


def test_reviewed_project_knowledge_graph_is_promoted_to_generation_context(
    tmp_path,
    mysql_engine: Engine,
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("<project />", encoding="utf-8")
    (backend / "RecordController.java").write_text(
        """
        public class RecordController {
            @Operation(summary = "记录分页查询")
            @PostMapping("/api/public/records/page")
            public void page() {}

            @Operation(summary = "流程首页")
            @GetMapping("/api/public/process/records/{recordId}/home")
            public void home() {}
        }
        """,
        encoding="utf-8",
    )

    with Session(mysql_engine) as db:
        project = Project(name="reviewed-knowledge-graph-test")
        db.add(project)
        db.flush()
        ProjectAnalyzer().analyze(
            project.id,
            {
                "workspace_path": str(tmp_path),
                "frontend_repo_path": "",
                "backend_repo_path": "",
            },
            db,
        )
        graph_row = db.scalar(
            select(ProjectKnowledgeGraph).where(ProjectKnowledgeGraph.project_id == project.id)
        )
        assert graph_row is not None
        graph_row.review_status = "reviewed"
        graph_row.graph = with_review_status(graph_row.graph, "reviewed")
        reviewed_graph = graph_row.graph
        db.commit()

        project_context = build_project_llm_context(project.id, {}, db)

    graph_modules = reviewed_graph["modules"]
    graph_relationships = reviewed_graph["relationships"]
    assert graph_modules
    assert graph_modules[0]["review_status"] == "reviewed"
    assert graph_modules[0]["routes"][0]["review_status"] == "reviewed"
    assert graph_relationships
    assert graph_relationships[0]["review_status"] == "reviewed"
    assert graph_relationships[0]["confirmed"] is True

    context = CaseGenerationContext(
        prompt="从记录分页查询开始，再进入流程首页",
        frontend=RepoSummary(path=None, exists=False, files=[], signals=[]),
        backend=RepoSummary(path=str(backend), exists=True, files=[], signals=[], routes=[]),
        execution_mode="backend_api",
        project_context=project_context,
        auth_context=project_context["auth"],
    )
    payload = build_case_generation_payload(context)

    assert payload["project_context"]["knowledge_graph"]["review"]["status"] == "reviewed"
    assert payload["project_context"]["knowledge_graph"]["review"]["fact_strength"] == "strong"
    assert payload["project_context"]["knowledge_graph_review"]["strong_fact_available"] is True
    assert any("knowledge_graph" in rule for rule in payload["reference_document_rules"])


def test_reviewed_project_knowledge_graph_keeps_rejected_relationships() -> None:
    graph = {
        "modules": [
            {
                "id": "module_records",
                "review_status": "draft",
                "routes": [{"id": "route_records_page", "review_status": "draft"}],
            }
        ],
        "relationships": [
            {
                "id": "rel_allowed",
                "review_status": "draft",
                "confirmed": False,
            },
            {
                "id": "rel_rejected",
                "review_status": "rejected",
                "confirmed": True,
            },
        ],
    }

    reviewed_graph = with_review_status(graph, "reviewed")

    assert reviewed_graph["modules"][0]["review_status"] == "reviewed"
    assert reviewed_graph["modules"][0]["routes"][0]["review_status"] == "reviewed"
    assert reviewed_graph["relationships"][0]["review_status"] == "reviewed"
    assert reviewed_graph["relationships"][0]["confirmed"] is True
    assert reviewed_graph["relationships"][1]["review_status"] == "rejected"
    assert reviewed_graph["relationships"][1]["confirmed"] is False


def test_project_analyzer_persists_auth_profile_for_shared_llm_context(
    tmp_path,
    mysql_engine: Engine,
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("<project />", encoding="utf-8")
    (backend / "CustomerLoginController.java").write_text(
        """
        public class CustomerLoginController {
            @PostMapping("/customer/api/pb/user/login")
            @Operation(summary = "小程序用户登录")
            public void login() {}
        }
        """,
        encoding="utf-8",
    )

    engine = mysql_engine
    with Session(engine) as db:
        project = Project(name="analysis-auth-profile-test")
        db.add(project)
        db.flush()
        settings = {
            "workspace_path": str(tmp_path),
            "frontend_repo_path": "",
            "backend_repo_path": "",
        }
        ProjectAnalyzer().analyze(project.id, settings, db)
        db.commit()

        repository = db.scalar(
            select(Repository).where(
                Repository.project_id == project.id,
                Repository.kind == "backend",
            )
        )
        project_context = build_project_llm_context(project.id, settings, db)
        environment_project_context = build_project_llm_context(
            project.id,
            {
                **settings,
                "active_api_environment": "test",
                "environments": [
                    {
                        "key": "test",
                        "name": "测试",
                        "request_headers": {"X-Customer-Token": "manual-token"},
                    }
                ],
            },
            db,
        )

    assert repository is not None
    auth_profile = repository.index_summary["auth_profile"]
    assert auth_profile["mode_hint"] == "external_or_environment_headers"
    assert auth_profile["login_route_candidates"][0]["path"] == "/customer/api/pb/user/login"
    assert project_context["auth"]["effective_mode"] == "external_or_environment_headers"
    assert environment_project_context["auth"]["effective_mode"] == "environment_headers"


def test_project_analyzer_persists_swagger_route_contracts(
    tmp_path,
    mysql_engine: Engine,
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pom.xml").write_text("<project />", encoding="utf-8")
    (backend / "swagger.json").write_text(
        json.dumps(
            {
                "swagger": "2.0",
                "basePath": "/api",
                "paths": {
                    "/private/records/create": {
                        "post": {
                            "summary": "创建记录",
                            "operationId": "createRecord",
                            "parameters": [
                                {
                                    "name": "body",
                                    "in": "body",
                                    "required": True,
                                    "schema": {
                                        "type": "object",
                                        "required": ["resourceId"],
                                        "properties": {"resourceId": {"type": "string"}},
                                    },
                                }
                            ],
                            "responses": {"200": {"description": "成功"}},
                        }
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    engine = mysql_engine
    with Session(engine) as db:
        project = Project(name="swagger-analysis-test")
        db.add(project)
        db.flush()
        ProjectAnalyzer().analyze(
            project.id,
            {
                "workspace_path": str(tmp_path),
                "frontend_repo_path": "",
                "backend_repo_path": "",
            },
            db,
        )
        db.commit()

        repository = db.scalar(
            select(Repository).where(
                Repository.project_id == project.id,
                Repository.kind == "backend",
            )
        )

    assert repository is not None
    route = repository.index_summary["routes"][0]
    assert route["path"] == "/api/private/records/create"
    assert route["source_type"] == "swagger"
    assert route["request_body"]["schema"]["required"] == ["resourceId"]
