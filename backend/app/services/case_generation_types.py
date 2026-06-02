from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeneratedStep:
    kind: str
    label: str
    action: str | None = None
    selector: str | None = None
    target_url: str | None = None
    value: str | None = None
    expected: str | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class GeneratedCase:
    title: str
    description: str
    priority: str
    steps: list[GeneratedStep]
    graph: dict[str, Any]
    code_context: dict[str, Any]
