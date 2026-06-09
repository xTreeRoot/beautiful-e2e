from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Repository
from app.services.project_llm_context import analyze_repository_auth_profile
from app.services.project_route_analysis import build_project_route_analysis
from app.services.repo_reader import RepoReader, RepoSummary

REPOSITORY_KIND_LABELS = {
    "workspace": "工作区",
    "frontend": "前端",
    "backend": "后端",
}


class ProjectAnalyzer:
    """构建并持久化可复用的项目知识，供后续用例生成使用。"""

    def __init__(self, reader: RepoReader | None = None) -> None:
        self.reader = reader or RepoReader()

    def analyze(
        self,
        project_id: str,
        settings: dict[str, Any],
        db: Session,
        actor: str | None = "developer",
    ) -> list[Repository]:
        repositories: list[Repository] = []
        for event in self.analyze_events(project_id, settings, db, actor):
            event_repositories = event.get("_repositories")
            if isinstance(event_repositories, list):
                repositories = event_repositories
        return repositories

    def analyze_events(
        self,
        project_id: str,
        settings: dict[str, Any],
        db: Session,
        actor: str | None = "developer",
    ) -> Iterator[dict[str, Any]]:
        """逐步分析项目仓库并产出可被 SSE 透传的进度事件。"""
        repo_paths = self._repo_paths(settings)
        repositories: list[Repository] = []

        configured_paths = {kind: path for kind, path in repo_paths.items() if path}
        yield {
            "message": f"已解析项目仓库配置，共 {len(configured_paths)} 个路径需要分析。",
            "stage": "repo_paths",
            "repository_count": len(configured_paths),
        }

        for kind, raw_path in repo_paths.items():
            if not raw_path:
                yield {
                    "message": f"{self._kind_label(kind)}仓库未配置路径，跳过扫描。",
                    "stage": "repo_skipped",
                    "repository_kind": kind,
                }
                continue
            yield {
                "message": f"开始扫描{self._kind_label(kind)}仓库：{Path(raw_path).expanduser().name or raw_path}。",
                "stage": "repo_scan_start",
                "repository_kind": kind,
                "path": raw_path,
            }
            summary = self.reader.summarize(raw_path)
            yield {
                "message": (
                    f"{self._kind_label(kind)}仓库扫描完成："
                    f"{len(summary.files)} 个文件、{len(summary.routes)} 条接口、"
                    f"{len(summary.dom_targets)} 个 DOM 目标。"
                ),
                "stage": "repo_scan_done",
                "repository_kind": kind,
                "exists": summary.exists,
                "file_count": len(summary.files),
                "route_count": len(summary.routes),
                "dom_target_count": len(summary.dom_targets),
            }
            auth_profile = analyze_repository_auth_profile(kind, summary)
            yield {
                "message": (
                    f"{self._kind_label(kind)}仓库认证画像："
                    f"{auth_profile.get('mode_hint') or 'unknown'}。"
                ),
                "stage": "auth_profile",
                "repository_kind": kind,
                "auth_mode": auth_profile.get("mode_hint"),
            }
            route_analysis = build_project_route_analysis(kind, summary)
            yield {
                "message": (
                    f"{self._kind_label(kind)}仓库模块归纳完成："
                    f"{len(route_analysis.get('modules') or [])} 个模块、"
                    f"{len(route_analysis.get('relationships') or [])} 条接口关系。"
                ),
                "stage": "route_analysis",
                "repository_kind": kind,
                "module_count": len(route_analysis.get("modules") or []),
                "relationship_count": len(route_analysis.get("relationships") or []),
            }
            summary = replace(summary, auth_profile=auth_profile, analysis=route_analysis)
            repo = self._upsert_repository(project_id, kind, raw_path, summary, db)
            repositories.append(repo)
            yield {
                "message": f"{self._kind_label(kind)}仓库分析结果已写入数据库会话。",
                "stage": "repo_persisted",
                "repository_kind": kind,
                "repository_id": repo.id,
            }

        db.add(
            AuditEvent(
                project_id=project_id,
                actor=actor,
                action="project.analyzed",
                entity_type="project",
                entity_id=project_id,
                payload={
                    "repositories": [
                        {
                            "kind": repo.kind,
                            "path": repo.path,
                            "routes": len((repo.index_summary or {}).get("routes", [])),
                            "dom_targets": len((repo.index_summary or {}).get("dom_targets", [])),
                            "modules": len(
                                ((repo.index_summary or {}).get("analysis") or {}).get(
                                    "modules", []
                                )
                            ),
                            "auth_mode": (repo.index_summary or {})
                            .get("auth_profile", {})
                            .get("mode_hint"),
                        }
                        for repo in repositories
                    ]
                },
            )
        )
        yield {
            "message": f"项目分析完成，已记录 {len(repositories)} 个仓库摘要。",
            "stage": "complete",
            "repository_count": len(repositories),
            "_repositories": repositories,
        }

    def _kind_label(self, kind: str) -> str:
        return REPOSITORY_KIND_LABELS.get(kind, kind)

    def _repo_paths(self, settings: dict[str, Any]) -> dict[str, str]:
        workspace_path = str(settings.get("workspace_path") or "").strip()
        frontend_path = str(settings.get("frontend_repo_path") or "").strip()
        backend_path = str(settings.get("backend_repo_path") or "").strip()

        if workspace_path:
            root = Path(workspace_path).expanduser()
            if not frontend_path:
                frontend_path = self._infer_frontend_path(root)
            if not backend_path:
                backend_path = self._infer_backend_path(root)

        return {
            "workspace": workspace_path,
            "frontend": frontend_path,
            "backend": backend_path,
        }

    def _infer_frontend_path(self, root: Path) -> str:
        if self._looks_like_frontend(root):
            return str(root)
        for child in self._iter_children(root):
            if self._looks_like_frontend(child):
                return str(child)
        return ""

    def _infer_backend_path(self, root: Path) -> str:
        if self._looks_like_backend(root):
            return str(root)
        for child in self._iter_children(root):
            if self._looks_like_backend(child):
                return str(child)
        return ""

    def _iter_children(self, root: Path):
        if not root.exists() or not root.is_dir():
            return []
        return [child for child in root.iterdir() if child.is_dir() and not child.name.startswith(".")]

    def _looks_like_frontend(self, path: Path) -> bool:
        return (path / "package.json").exists() and (
            (path / "src").exists() or (path / "pages").exists() or (path / "app").exists()
        )

    def _looks_like_backend(self, path: Path) -> bool:
        return any(
            candidate.exists()
            for candidate in [
                path / "pom.xml",
                path / "build.gradle",
                path / "build.gradle.kts",
                path / "pyproject.toml",
                path / "src/main/java",
            ]
        )

    def _upsert_repository(
        self,
        project_id: str,
        kind: str,
        raw_path: str,
        summary: RepoSummary,
        db: Session,
    ) -> Repository:
        repo = db.scalar(
            select(Repository).where(Repository.project_id == project_id, Repository.kind == kind)
        )
        clean_path = raw_path.strip()
        analysis = dict(summary.analysis or {})
        analysis.update(
            {
                "kind": kind,
                "analyzed_at": datetime.now(UTC).isoformat(),
                "route_count": len(summary.routes),
                "route_request_body_count": len(
                    [route for route in summary.routes if isinstance(route.get("request_body"), dict)]
                ),
                "route_parameter_count": len(
                    [route for route in summary.routes if isinstance(route.get("parameters"), list)]
                ),
                "dom_target_count": len(summary.dom_targets),
            }
        )
        index_summary = {
            **summary.as_dict(),
            "analysis": analysis,
        }
        if repo is None:
            repo = Repository(
                project_id=project_id,
                name=Path(clean_path).name or kind,
                kind=kind,
                path=clean_path,
                index_summary=index_summary,
            )
            db.add(repo)
        else:
            repo.name = Path(clean_path).name or kind
            repo.path = clean_path
            repo.index_summary = index_summary
        return repo
