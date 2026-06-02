from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import TestCase, TestStep
from app.services.project_environments import (
    DEFAULT_API_BASE_URL,
    DEFAULT_ENVIRONMENT,
    DEFAULT_FRONTEND_BASE_URL,
)


class PlaywrightEmitter:
    def __init__(
        self,
        output_dir: Path,
        *,
        base_url: str = DEFAULT_FRONTEND_BASE_URL,
        api_base_url: str = DEFAULT_API_BASE_URL,
        environment: str = DEFAULT_ENVIRONMENT,
        request_headers: dict[str, Any] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.base_url = base_url or DEFAULT_FRONTEND_BASE_URL
        self.api_base_url = api_base_url or DEFAULT_API_BASE_URL
        self.environment = environment or DEFAULT_ENVIRONMENT
        self.request_headers = request_headers or {}

    def emit(self, case: TestCase) -> tuple[Path, str]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{self._slug(case.title)}-{case.id[:8]}.spec.ts"
        content = self._render(case)
        path.write_text(content, encoding="utf-8")
        return path, content

    def preview(self, case: TestCase) -> str:
        return self._render(case)

    def _render(self, case: TestCase) -> str:
        uses_api = self._uses_api(case)
        uses_page = self._uses_page(case)
        if uses_api and uses_page:
            fixture = "page, request"
        elif uses_api:
            fixture = "request"
        else:
            fixture = "page"
        lines = [
            "import { test, expect } from '@playwright/test';",
            "",
            f"test.describe('{self._escape(case.group.name if case.group else '未分组')}', () => {{",
            f"  test('{self._escape(case.title)}', async ({{ {fixture} }}) => {{",
            (
                "    test.info().annotations.push({ type: 'environment', "
                f"description: process.env.E2E_ENV ?? '{self._escape(self.environment)}' }});"
            ),
            f"    const baseUrl = process.env.BASE_URL ?? '{self._escape(self.base_url)}';",
            (
                "    const apiBaseUrl = process.env.API_BASE_URL ?? "
                f"process.env.BASE_URL ?? '{self._escape(self.api_base_url)}';"
            ),
            "    function parseJsonEnv(raw, fallback) {",
            "      if (!raw) return fallback;",
            "      try { return JSON.parse(raw); } catch { return fallback; }",
            "    }",
            (
                "    const requestHeaders = parseJsonEnv("
                f"process.env.REQUEST_HEADERS_JSON, {self._json_literal(self.request_headers)});"
            ),
        ]

        if uses_api:
            lines.extend(
                [
                    "    const apiVars = {};",
                    "    function readJsonPath(value, path) {",
                    "      if (!path) return undefined;",
                    "      if (!String(path).startsWith('$')) return findField(value, path);",
                    "      const tokens = String(path).replace(/^\\$\\.?/, '').split('.').filter(Boolean);",
                    "      let current = value;",
                    "      for (const token of tokens) {",
                    "        const match = token.match(/^([A-Za-z_][\\w-]*)(?:\\[(\\d+)\\])?$/);",
                    "        if (!match || current == null) return undefined;",
                    "        current = current[match[1]];",
                    "        if (match[2] !== undefined) current = Array.isArray(current) ? current[Number(match[2])] : undefined;",
                    "      }",
                    "      return current;",
                    "    }",
                    "    function findField(value, field) {",
                    "      if (Array.isArray(value)) {",
                    "        for (const item of value) {",
                    "          const found = findField(item, field);",
                    "          if (found !== undefined && found !== null) return found;",
                    "        }",
                    "      }",
                    "      if (value && typeof value === 'object') {",
                    "        if (Object.prototype.hasOwnProperty.call(value, field)) return value[field];",
                    "        for (const item of Object.values(value)) {",
                    "          const found = findField(item, field);",
                    "          if (found !== undefined && found !== null) return found;",
                    "        }",
                    "      }",
                    "      return undefined;",
                    "    }",
                    "    function resolveValue(value, vars) {",
                    "      if (typeof value === 'string') {",
                    "        const exact = value.trim().match(/^\\{\\{\\s*([A-Za-z_][\\w.-]*)\\s*\\}\\}$/);",
                    "        if (exact) {",
                    "          if (!(exact[1] in vars)) throw new Error(`接口步骤引用的变量未解析：${exact[1]}`);",
                    "          return vars[exact[1]];",
                    "        }",
                    "        return value.replace(/\\{\\{\\s*([A-Za-z_][\\w.-]*)\\s*\\}\\}/g, (_, name) => {",
                    "          if (!(name in vars)) throw new Error(`接口步骤引用的变量未解析：${name}`);",
                    "          return String(vars[name]);",
                    "        });",
                    "      }",
                    "      if (Array.isArray(value)) return value.map((item) => resolveValue(item, vars));",
                    "      if (value && typeof value === 'object') {",
                    "        return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolveValue(item, vars)]));",
                    "      }",
                    "      return value;",
                    "    }",
                    "    function placeholdersInValue(value) {",
                    "      const names = new Set();",
                    "      if (typeof value === 'string') {",
                    "        for (const match of value.matchAll(/\\{\\{\\s*([A-Za-z_][\\w.-]*)\\s*\\}\\}/g)) names.add(match[1]);",
                    "      } else if (Array.isArray(value)) {",
                    "        for (const item of value) for (const name of placeholdersInValue(item)) names.add(name);",
                    "      } else if (value && typeof value === 'object') {",
                    "        for (const item of Object.values(value)) for (const name of placeholdersInValue(item)) names.add(name);",
                    "      }",
                    "      return names;",
                    "    }",
                    "    function hasHeader(headers, requestedKey) {",
                    "      const target = String(requestedKey).toLowerCase();",
                    "      return Object.entries(headers || {}).some(([key, value]) => String(key).toLowerCase() === target && Boolean(String(value ?? '').trim()));",
                    "    }",
                    "    function headersWithoutEnvironmentOverrides(headers, vars, envHeaders) {",
                    "      return Object.fromEntries(Object.entries(headers || {}).filter(([key, value]) => {",
                    "        const missing = [...placeholdersInValue(value)].filter((name) => !(name in vars));",
                    "        return !(missing.length && hasHeader(envHeaders, key));",
                    "      }));",
                    "    }",
                    "    async function applyExtract(response, extractSpec, vars) {",
                    "      if (!extractSpec) return;",
                    "      let payload;",
                    "      try { payload = await response.json(); } catch { return; }",
                    "      const entries = Array.isArray(extractSpec)",
                    "        ? extractSpec.map((item) => [item.name ?? item.variable, item.path ?? item.json_path ?? item.selector])",
                    "        : Object.entries(extractSpec);",
                    "      for (const [name, selector] of entries) {",
                    "        if (!name) continue;",
                    "        const value = readJsonPath(payload, selector || name);",
                    "        if (value !== undefined && value !== null) vars[name] = value;",
                    "      }",
                    "    }",
                ]
            )

        if uses_page:
            lines.append("    await page.setExtraHTTPHeaders(requestHeaders);")

        for step in case.steps:
            lines.extend(self._render_step(step))

        lines.extend(["  });", "});", ""])
        return "\n".join(lines)

    def _render_step(self, step: TestStep) -> list[str]:
        label = self._escape(step.label)
        selector = self._escape(step.selector or "body")
        value = self._escape(step.value or "")
        expected = self._escape(step.expected or "")
        data = step.data or {}

        lines = [f"    await test.step('{label}', async () => {{"]
        match step.action:
            case "api_request":
                method = self._escape(str(data.get("method") or "GET").lower())
                target = self._escape(step.target_url or step.selector or "/")
                status = int(data.get("expected_status") or step.expected or 200)
                response_name = f"response{step.order_index}"
                body = data.get("body")
                step_headers = data.get("headers")
                headers_literal = (
                    self._json_literal(step_headers) if isinstance(step_headers, dict) else "{}"
                )
                options_name = f"requestOptions{step.order_index}"
                target_name = f"targetUrl{step.order_index}"
                headers_name = f"stepHeaders{step.order_index}"
                lines.append(f"      const {target_name} = resolveValue('{target}', apiVars);")
                lines.append(
                    f"      const {headers_name} = headersWithoutEnvironmentOverrides("
                    f"{headers_literal}, apiVars, requestHeaders);"
                )
                lines.append(
                    f"      const {options_name} = {{ headers: {{ ...requestHeaders, "
                    f"...resolveValue({headers_name}, apiVars) }} }};"
                )
                if body is not None:
                    body_name = f"requestBody{step.order_index}"
                    lines.append(
                        f"      const {body_name} = resolveValue({self._json_literal(body)}, apiVars);"
                    )
                    lines.append(f"      {options_name}.data = {body_name};")
                lines.append(
                    f"      const {response_name} = await request.{method}("
                    f"new URL({target_name}, apiBaseUrl).toString(), "
                    f"{options_name});"
                )
                lines.append(f"      expect({response_name}.status()).toBe({status});")
                if data.get("extract"):
                    lines.append(
                        f"      await applyExtract({response_name}, "
                        f"{self._json_literal(data.get('extract'))}, apiVars);"
                    )
            case "goto":
                target = step.target_url or "/"
                if target.startswith("http"):
                    lines.append(f"      await page.goto('{self._escape(target)}');")
                else:
                    lines.append(f"      await page.goto(new URL('{self._escape(target)}', baseUrl).toString());")
            case "fill":
                lines.append(f"      await page.locator('{selector}').first().fill('{value}');")
            case "click":
                lines.append(f"      await page.locator('{selector}').first().click();")
            case "expect_visible":
                lines.append(f"      await expect(page.locator('{selector}').first()).toBeVisible();")
            case "expect_not_visible":
                lines.append(f"      await expect(page.locator('{selector}').first()).toBeHidden();")
            case "expect_text":
                lines.append(f"      await expect(page.locator('{selector}').first()).toContainText('{expected}');")
            case _:
                lines.append("      // TODO: 将该生成步骤映射为具体的 Playwright 动作。")
                lines.append(f"      await expect(page.locator('{selector}').first()).toBeVisible();")

        lines.append("    });")
        return lines

    def _uses_api(self, case: TestCase) -> bool:
        mode = (case.code_context or {}).get("execution_mode")
        return mode == "backend_api" or any(step.action == "api_request" for step in case.steps)

    def _uses_page(self, case: TestCase) -> bool:
        return any(step.action in {"goto", "fill", "click", "expect_visible", "expect_not_visible", "expect_text"} for step in case.steps)

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug[:48] or "generated-case"

    def _escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _json_literal(self, value) -> str:
        import json

        return json.dumps(value, ensure_ascii=False)
