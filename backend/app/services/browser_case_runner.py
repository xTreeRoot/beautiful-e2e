from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from app.models import TestCase, TestStep
from app.services.project_environments import DEFAULT_FRONTEND_BASE_URL

BROWSER_ACTIONS = {
    "goto",
    "fill",
    "click",
    "expect_visible",
    "expect_not_visible",
    "expect_text",
}
LIVE_RUNNER_SCRIPT = r"""
import { chromium, expect } from '@playwright/test';

const input = await readStdin();
const payload = JSON.parse(input);

function emit(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

function stepTarget(step) {
  return step.target_url || step.selector || '';
}

async function screenshot(page) {
  const image = await page.screenshot({ type: 'jpeg', quality: 70, fullPage: false });
  return `data:image/jpeg;base64,${image.toString('base64')}`;
}

async function runStep(page, step, timeoutMs) {
  switch (step.action) {
    case 'goto': {
      const target = step.target_url || '/';
      const url = target.startsWith('http') ? target : new URL(target, payload.base_url).toString();
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
      break;
    }
    case 'fill':
      await page.locator(step.selector || 'body').first().fill(step.value || '', { timeout: timeoutMs });
      break;
    case 'click':
      await page.locator(step.selector || 'body').first().click({ timeout: timeoutMs });
      break;
    case 'expect_visible':
      await expect(page.locator(step.selector || 'body').first()).toBeVisible({ timeout: timeoutMs });
      break;
    case 'expect_not_visible':
      await expect(page.locator(step.selector || 'body').first()).toBeHidden({ timeout: timeoutMs });
      break;
    case 'expect_text':
      await expect(page.locator(step.selector || 'body').first()).toContainText(step.expected || '', {
        timeout: timeoutMs
      });
      break;
    default:
      throw new Error(`不支持的浏览器动作：${step.action || '空动作'}`);
  }
}

async function main() {
  emit({
    type: 'start',
    message: '开始执行浏览器流程。',
    case_id: payload.case_id,
    case_title: payload.case_title,
    base_url: payload.base_url,
    environment: payload.environment,
    total: payload.steps.length
  });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    baseURL: payload.base_url,
    extraHTTPHeaders: payload.request_headers || {},
    viewport: { width: 1280, height: 720 }
  });
  const page = await context.newPage();
  let passed = 0;
  let failed = 0;

  try {
    for (const step of payload.steps) {
      emit({
        type: 'action',
        message: `正在执行：${step.label}`,
        step_id: step.id,
        order_index: step.order_index,
        label: step.label,
        action: step.action,
        selector: step.selector,
        target_url: stepTarget(step),
        page_url: page.url()
      });
      const startedAt = Date.now();
      try {
        await runStep(page, step, payload.timeout_ms);
        passed += 1;
        emit({
          type: 'result',
          message: '步骤通过',
          step_id: step.id,
          order_index: step.order_index,
          label: step.label,
          action: step.action,
          selector: step.selector,
          target_url: stepTarget(step),
          status_code: null,
          duration_ms: Date.now() - startedAt,
          ok: true,
          error: null,
          page_url: page.url(),
          screenshot_data_url: await screenshot(page)
        });
      } catch (error) {
        failed += 1;
        emit({
          type: 'result',
          message: error instanceof Error ? error.message : String(error),
          step_id: step.id,
          order_index: step.order_index,
          label: step.label,
          action: step.action,
          selector: step.selector,
          target_url: stepTarget(step),
          status_code: null,
          duration_ms: Date.now() - startedAt,
          ok: false,
          error: error instanceof Error ? error.message : String(error),
          page_url: page.url(),
          screenshot_data_url: await screenshot(page)
        });
        if (payload.fail_fast) break;
      }
    }
  } finally {
    await context.close();
    await browser.close();
  }

  emit({
    type: 'done',
    message: '浏览器流程运行完成。',
    status: failed === 0 ? 'passed' : 'failed',
    total: passed + failed,
    passed,
    failed
  });
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
      data += chunk;
    });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

try {
  await main();
} catch (error) {
  emit({
    type: 'error',
    message: error instanceof Error ? error.message : String(error)
  });
  process.exitCode = 1;
}
"""


class BrowserCaseRunner:
    """直接执行页面步骤并输出平台可视化事件。

    这里复用 runner 目录中已安装的 Playwright 依赖，但不会生成或写入
    Playwright spec。运行结果只通过 stdout 的 JSON 行返回给 API 层。
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_FRONTEND_BASE_URL,
        environment: str = "local",
        request_headers: Mapping[str, Any] | None = None,
        timeout_seconds: float = 20.0,
        fail_fast: bool = True,
        runner_dir: Path | None = None,
        node_binary: str | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_FRONTEND_BASE_URL).strip()
        self.environment = environment
        self.request_headers = _normalize_headers(request_headers or {})
        self.timeout_seconds = timeout_seconds
        self.fail_fast = fail_fast
        self.runner_dir = runner_dir or Path(__file__).resolve().parents[3] / "runner"
        self.node_binary = node_binary or shutil.which("node") or "node"

    def executable_steps(self, case: TestCase) -> list[TestStep]:
        """返回可由浏览器执行的步骤，接口步骤会留给 backend_api 运行器处理。"""

        return [step for step in case.steps if step.action in BROWSER_ACTIONS]

    def stream(self, case: TestCase) -> Iterator[dict[str, Any]]:
        steps = self.executable_steps(case)
        if not steps:
            raise ValueError("当前用例没有可执行浏览器步骤")

        payload = {
            "case_id": case.id,
            "case_title": case.title,
            "base_url": self.base_url,
            "environment": self.environment,
            "request_headers": self.request_headers,
            "timeout_ms": int(self.timeout_seconds * 1000),
            "fail_fast": self.fail_fast,
            "steps": [self._step_payload(step) for step in steps],
        }
        yield from self._stream_node_runner(payload)

    def _stream_node_runner(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        if not (self.runner_dir / "node_modules" / "@playwright" / "test").exists():
            raise ValueError("浏览器运行器依赖未安装，请先在 runner 目录执行 npm install")

        process = subprocess.Popen(
            [self.node_binary, "--input-type=module", "-e", LIVE_RUNNER_SCRIPT],
            cwd=self.runner_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None

        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False))
            process.stdin.close()
        except BrokenPipeError:
            pass

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                yield {"type": "error", "message": line}
                continue
            if isinstance(event, dict):
                yield event

        return_code = process.wait()
        stderr = process.stderr.read().strip()
        if return_code != 0 and stderr:
            yield {"type": "error", "message": stderr}

    def _step_payload(self, step: TestStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "order_index": step.order_index,
            "label": step.label,
            "action": step.action,
            "selector": step.selector,
            "target_url": step.target_url,
            "value": step.value,
            "expected": step.expected,
        }


def _normalize_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        normalized[key_text] = "" if value is None else str(value)
    return normalized
