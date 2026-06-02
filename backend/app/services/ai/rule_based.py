from __future__ import annotations

from app.services.ai.base import CaseGenerationContext, CaseGenerationProvider
from app.services.ai_case_generator import CaseGenerator, GeneratedCase


class RuleBasedCaseProvider(CaseGenerationProvider):
    name = "rule_based"

    def __init__(self, generator: CaseGenerator | None = None) -> None:
        self.generator = generator or CaseGenerator()

    def generate(self, context: CaseGenerationContext) -> GeneratedCase:
        return self.generator.generate(
            context.prompt,
            frontend=context.frontend,
            backend=context.backend,
            priority=context.priority,
            agent=context.agent,
            skills=context.skills,
            canvas_dsl=context.canvas_dsl,
            execution_mode=context.execution_mode,
            reference_documents=context.reference_documents,
            project_context=context.project_context,
            auth_context=context.auth_context,
        )
