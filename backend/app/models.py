from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    groups: Mapped[list[TestGroup]] = relationship(back_populates="project", cascade="all, delete-orphan")
    repositories: Mapped[list[Repository]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    knowledge_graphs: Mapped[list[ProjectKnowledgeGraph]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    environment_configs: Mapped[list[ProjectEnvironmentConfig]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    agents: Mapped[list[AgentProfile]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    skills: Mapped[list[SkillProfile]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(40), default="tester")


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    index_summary: Mapped[dict | None] = mapped_column(JSON)

    project: Mapped[Project] = relationship(back_populates="repositories")


class ProjectKnowledgeGraph(TimestampMixin, Base):
    """项目级链路事实图谱。

    图谱内容是项目分析的候选事实和人工审核后的强事实载体。生成 DSL 时只把
    `review_status=reviewed` 的图谱当作强约束，未审核内容只能作为候选证据。
    """

    __tablename__ = "project_knowledge_graphs"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_knowledge_graph_project"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    review_notes: Mapped[str | None] = mapped_column(Text)
    graph: Mapped[dict | None] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="knowledge_graphs")


class ProjectEnvironmentConfig(TimestampMixin, Base):
    """生成的接口/浏览器测试使用的项目环境配置。

    请求头绑定到接口环境，让同一个项目无需编辑用例即可指向不同网关
    或不同认证令牌。
    """

    __tablename__ = "project_environment_configs"
    __table_args__ = (UniqueConstraint("project_id", "env_key", name="uq_project_environment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    env_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    frontend_base_url: Mapped[str] = mapped_column(Text, default="")
    api_base_url: Mapped[str] = mapped_column(Text, default="")
    request_headers: Mapped[Any] = mapped_column(JSON, default=dict)
    # 保留旧本地数据库可能已经存在的字段，避免启动时破坏兼容性。
    request_variables: Mapped[Any] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="environment_configs")


class AiProviderConfig(TimestampMixin, Base):
    """持久化 AI 供应商配置与用途规划。

    `usage_keys` 表示该供应商负责的业务用途；同一个供应商可以绑定多个用途，
    但每个用途在服务层会被规整为只指向一个供应商。
    """

    __tablename__ = "ai_provider_configs"
    __table_args__ = (UniqueConstraint("provider_key", name="uq_ai_provider_config_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_entrypoint: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict | None] = mapped_column(JSON, default=dict)
    usage_keys: Mapped[list | None] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")


class AgentProfile(TimestampMixin, Base):
    __tablename__ = "agent_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    tools: Mapped[dict | None] = mapped_column(JSON)

    project: Mapped[Project] = relationship(back_populates="agents")


class SkillProfile(TimestampMixin, Base):
    __tablename__ = "skill_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship(back_populates="skills")


class TestGroup(TimestampMixin, Base):
    __tablename__ = "test_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="groups")
    cases: Mapped[list[TestCase]] = relationship(back_populates="group")


class TestCase(TimestampMixin, Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        Index("ix_test_cases_project_created_at", "project_id", "created_at"),
        Index("ix_test_cases_project_group_created_at", "project_id", "group_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("test_groups.id"))
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="P1")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    source_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(120))
    code_context: Mapped[dict | None] = mapped_column(JSON)
    graph: Mapped[dict | None] = mapped_column(JSON)
    playwright_spec_path: Mapped[str | None] = mapped_column(Text)

    group: Mapped[TestGroup | None] = relationship(back_populates="cases")
    steps: Mapped[list[TestStep]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="TestStep.order_index"
    )
    comments: Mapped[list[CaseComment]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class TestStep(TimestampMixin, Base):
    __tablename__ = "test_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    action: Mapped[str | None] = mapped_column(String(80))
    selector: Mapped[str | None] = mapped_column(String(255))
    target_url: Mapped[str | None] = mapped_column(String(255))
    value: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict | None] = mapped_column(JSON)

    case: Mapped[TestCase] = relationship(back_populates="steps")


class TestRun(TimestampMixin, Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("test_groups.id"))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("test_cases.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    trigger: Mapped[str] = mapped_column(String(40), default="manual")
    started_by: Mapped[str | None] = mapped_column(String(120))
    report_path: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class TestRunResult(TimestampMixin, Base):
    __tablename__ = "test_run_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    trace_path: Mapped[str | None] = mapped_column(Text)


class CaseComment(TimestampMixin, Base):
    __tablename__ = "case_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text, nullable=False)

    case: Mapped[TestCase] = relationship(back_populates="comments")


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
