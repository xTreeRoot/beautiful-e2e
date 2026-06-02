from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import models
from app.api.projects import create_project, update_project
from app.schemas import ProjectCreate, ProjectUpdate
from app.services.environment_auth import build_generation_auth_context
from app.services.project_environments import active_environment_settings


def test_project_environment_configs_persist_headers(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = create_project(
            ProjectCreate(
                name="env-bound-project",
                settings={
                    "active_frontend_environment": "local",
                    "active_api_environment": "test",
                    "environments": [
                        {
                            "key": "local",
                            "name": "本地",
                            "base_url": "http://localhost:5173",
                            "api_base_url": "http://localhost:8000",
                            "request_headers": {"Authorization": "Bearer local-token"},
                        },
                        {
                            "key": "test",
                            "name": "测试",
                            "base_url": "https://web.test",
                            "api_base_url": "https://api.test",
                            "request_headers": {"x-env": "test"},
                        },
                    ],
                },
            ),
            db,
        )
        rows = db.scalars(
            select(models.ProjectEnvironmentConfig)
            .where(models.ProjectEnvironmentConfig.project_id == project.id)
            .order_by(models.ProjectEnvironmentConfig.env_key)
        ).all()

    assert len(rows) == 2
    assert project.settings["active_api_environment"] == "test"
    assert project.settings["api_base_url"] == "https://api.test"
    assert rows[1].request_headers == {"x-env": "test"}
    assert rows[1].request_variables == {}


def test_project_environment_update_drives_playwright_defaults(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = create_project(ProjectCreate(name="env-update-project"), db)
        saved = update_project(
            project.id,
            ProjectUpdate(
                settings={
                    "active_frontend_environment": "dev",
                    "active_api_environment": "dev",
                    "environments": [
                        {
                            "key": "dev",
                            "name": "开发",
                            "base_url": "https://web.dev",
                            "api_base_url": "https://api.dev",
                            "request_headers": {"Authorization": "Bearer dev-token"},
                        }
                    ],
                }
            ),
            db,
        )

    settings = active_environment_settings(saved.settings)
    assert settings["environment"] == "dev"
    assert settings["base_url"] == "https://web.dev"
    assert settings["api_base_url"] == "https://api.dev"
    assert settings["request_headers"] == {"Authorization": "Bearer dev-token"}
    assert "request_variables" not in settings


def test_generation_auth_context_redacts_configured_header_values(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = create_project(
            ProjectCreate(
                name="env-auth-context-project",
                settings={
                    "active_api_environment": "test",
                    "environments": [
                        {
                            "key": "test",
                            "name": "测试",
                            "api_base_url": "https://api.test",
                            "request_headers": {
                                "X-Customer-Token": "secret-token",
                                "Accept": "application/json",
                            },
                        }
                    ],
                },
            ),
            db,
        )

    auth_context = build_generation_auth_context(project.settings)

    assert auth_context["mode"] == "environment_headers"
    assert auth_context["configured_header_keys"] == ["Accept", "X-Customer-Token"]
    assert auth_context["likely_auth_header_keys"] == ["X-Customer-Token"]
    assert auth_context["redacted"] is True
    assert "secret-token" not in json_safe_text(auth_context)


def test_project_environment_rejects_non_object_headers(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            create_project(
                ProjectCreate(
                    name="invalid-env-project",
                    settings={
                        "environments": [
                            {
                                "key": "local",
                                "name": "本地",
                                "request_headers": ["Authorization"],
                            }
                        ]
                    },
                ),
                db,
            )

    assert error.value.status_code == 400
    assert "request_headers" in str(error.value.detail)


def json_safe_text(value: object) -> str:
    return str(value)
