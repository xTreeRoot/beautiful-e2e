from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app import models
from app.api.common import project_out
from app.api.groups import delete_group
from app.api.projects import create_project, router, select_project_workspace
from app.db import get_db
from app.schemas import ProjectCreate


def test_deleted_default_groups_are_not_seeded_again_when_project_is_selected(
    mysql_engine: Engine,
) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = create_project(ProjectCreate(name="group-delete-project"), db)
        group_ids = list(
            db.scalars(
                select(models.TestGroup.id)
                .where(models.TestGroup.project_id == project.id)
                .order_by(models.TestGroup.sort_order)
            ).all()
        )

        for group_id in group_ids:
            delete_group(group_id, db)

        workspace = select_project_workspace(project.id, db)

    assert workspace.groups == []


def test_project_out_orders_repositories_after_loading(mysql_engine: Engine) -> None:
    engine = mysql_engine

    with Session(engine) as db:
        project = models.Project(name="repository-order-project")
        db.add(project)
        db.flush()
        db.add_all(
            [
                models.Repository(
                    project_id=project.id,
                    name="workspace",
                    kind="workspace",
                    path="/tmp/workspace",
                    index_summary={"files": [], "routes": []},
                ),
                models.Repository(
                    project_id=project.id,
                    name="backend",
                    kind="backend",
                    path="/tmp/backend",
                    index_summary={"files": [], "routes": [], "padding": "x" * 1000},
                ),
                models.Repository(
                    project_id=project.id,
                    name="frontend",
                    kind="frontend",
                    path="/tmp/frontend",
                    index_summary={"files": [], "routes": []},
                ),
            ]
        )
        db.commit()
        db.refresh(project)

        output = project_out(project, db)

    assert [repo.kind for repo in output.repositories] == ["backend", "frontend", "workspace"]
    assert output.repositories[0].index_summary["padding"] == "x" * 1000


def test_project_analysis_stream_emits_progress_and_project(
    tmp_path,
    mysql_engine: Engine,
) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text("[project]\nname = \"demo\"\n", encoding="utf-8")
    (backend / "routes.py").write_text(
        """
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/demo")
def demo():
    return {"ok": True}
""",
        encoding="utf-8",
    )
    engine = mysql_engine

    with Session(engine) as db:
        project = create_project(
            ProjectCreate(
                name="analysis-stream-project",
                settings={"backend_repo_path": str(backend)},
            ),
            db,
        )
        project_id = project.id

    def override_db():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        with client.stream("POST", f"/projects/{project_id}/analyze/stream") as response:
            body = response.read().decode("utf-8")

    events = _sse_events(body)
    event_names = [name for name, _payload in events]
    project_payload = next(payload for name, payload in events if name == "project")["project"]

    assert response.status_code == 200
    assert event_names[0] == "start"
    assert "progress" in event_names
    assert event_names[-1] == "done"
    assert project_payload["id"] == project_id
    assert project_payload["repositories"][0]["kind"] == "backend"
    assert project_payload["repositories"][0]["index_summary"]["routes"][0]["path"] == "/api/demo"


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events
