from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    settings: dict[str, Any] | None = None
    analyze_on_create: bool = False


class ProjectFromDirectoryRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = None
    analyze_on_create: bool = False


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    execution_mode: str | None = None
    frontend_repo_path: str | None = None
    backend_repo_path: str | None = None
    workspace_path: str | None = None
    active_environment: str | None = None
    active_frontend_environment: str | None = None
    active_api_environment: str | None = None
    base_url: str | None = None
    api_base_url: str | None = None
    settings: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    is_current: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    repositories: list["RepositoryOut"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    kind: str
    path: str
    index_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ProjectKnowledgeGraphOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    review_status: str
    review_notes: str | None
    graph: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProjectKnowledgeGraphUpdate(BaseModel):
    graph: dict[str, Any] = Field(default_factory=dict)
    review_status: str | None = None
    review_notes: str | None = None
    actor: str | None = "developer"


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    sort_order: int | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    description: str | None
    sort_order: int


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_index: int
    kind: str
    label: str
    action: str | None
    selector: str | None
    target_url: str | None
    value: str | None
    expected: str | None
    data: dict[str, Any] | None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    group_id: str | None
    title: str
    description: str
    priority: str
    status: str
    source_prompt: str
    created_by: str | None
    code_context: dict[str, Any] | None
    graph: dict[str, Any] | None
    playwright_spec_path: str | None
    steps: list[StepOut] = []
    created_at: datetime
    updated_at: datetime


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    group_id: str | None = None
    priority: str | None = None
    status: str | None = None


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    group_id: str | None = None
    priority: str = "P1"
    status: str = "draft"
    created_by: str | None = "developer"


class BootstrapOut(BaseModel):
    project: ProjectOut
    projects: list[ProjectOut] = Field(default_factory=list)
    groups: list[GroupOut]


class GenerateCaseRequest(BaseModel):
    description: str = Field(min_length=3)
    target_case_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=180)
    case_description: str | None = None
    execution_mode: str = "fullstack"
    group_id: str | None = None
    agent_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    frontend_repo_path: str | None = None
    backend_repo_path: str | None = None
    created_by: str | None = "developer"
    priority: str | None = None
    canvas_dsl: dict[str, Any] | None = None


class DirectoryPickRequest(BaseModel):
    title: str = "选择目录"
    initial_path: str | None = None


class DirectoryPickOut(BaseModel):
    path: str | None
    canceled: bool = False


class AiProviderUpdate(BaseModel):
    provider: str | None = None
    provider_entrypoint: str | None = None
    usage_plan: dict[str, str] | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    wire_api: str | None = None
    reasoning_effort: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=10, le=1800)
    codex_exec_command: str | None = None
    codex_exec_model: str | None = None
    codex_exec_profile: str | None = None
    codex_exec_profile_v2: str | None = None
    codex_exec_cwd: str | None = None
    codex_exec_sandbox: str | None = None
    codex_exec_ephemeral: bool | None = None
    codex_exec_skip_git_repo_check: bool | None = None
    codex_exec_ignore_user_config: bool | None = None
    codex_exec_ignore_rules: bool | None = None
    codex_exec_strict_config: bool | None = None
    codex_exec_output_schema_enabled: bool | None = None
    codex_exec_oss: bool | None = None
    codex_exec_local_provider: str | None = None
    codex_exec_image_paths: list[str] | None = None
    codex_exec_add_dirs: list[str] | None = None
    codex_exec_config_overrides: list[str] | None = None
    codex_exec_enabled_features: list[str] | None = None
    codex_exec_disabled_features: list[str] | None = None
    codex_exec_dangerously_bypass_approvals_and_sandbox: bool | None = None
    codex_exec_dangerously_bypass_hook_trust: bool | None = None


class PlaywrightExportOut(BaseModel):
    case_id: str
    spec_path: str
    content: str


class CaseRunStepOverride(BaseModel):
    id: str | None = None
    order_index: int | None = Field(default=None, ge=1)
    kind: str | None = None
    label: str | None = None
    action: str | None = None
    selector: str | None = None
    target_url: str | None = None
    value: str | None = None
    expected: str | None = None
    data: dict[str, Any] | None = None


class CaseRunRequest(BaseModel):
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    fail_fast: bool = False
    step_id: str | None = None
    step_override: CaseRunStepOverride | None = None


class GraphOut(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class CaseGraphUpdate(BaseModel):
    graph: dict[str, Any]
    steps: list[dict[str, Any]] = []
    execution_mode: str | None = None
    source_prompt: str | None = None
    actor: str | None = "developer"
