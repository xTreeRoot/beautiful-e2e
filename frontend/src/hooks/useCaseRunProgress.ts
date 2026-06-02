import { useState } from 'react';

import type { CaseRunStreamEvent } from '../api';
import type {
  CaseRunInferenceStatus,
  CaseRunProgressState,
  CaseRunStepState,
  ExecutionMode
} from '../types/workbench';

type StartCaseRunProgressOptions = {
  runId: number;
  caseId: string;
  caseTitle: string;
  apiBaseUrl: string;
  environment: string;
  executionMode: ExecutionMode;
  detail: string;
  total: number;
  open?: boolean;
  debugNodeId?: string | null;
};

const INITIAL_CASE_RUN_PROGRESS: CaseRunProgressState = {
  open: false,
  phase: 'idle',
  runId: 0,
  debugNodeId: null,
  executionMode: 'fullstack',
  caseId: '',
  caseTitle: '',
  apiBaseUrl: '',
  environment: '',
  detail: '',
  total: 0,
  steps: [],
  summary: null
};

/**
 * 管理用例运行抽屉的流式状态。
 * 运行 SSE 同时覆盖浏览器步骤、接口请求和运行期变量推导，集中在这里合并事件可避免总控制器继续承担 UI 状态机细节。
 */
export function useCaseRunProgress() {
  const [isRunningCase, setIsRunningCase] = useState(false);
  const [caseRunProgress, setCaseRunProgress] = useState<CaseRunProgressState>(
    INITIAL_CASE_RUN_PROGRESS
  );

  function startCaseRunProgress(options: StartCaseRunProgressOptions) {
    setCaseRunProgress({
      open: options.open ?? true,
      phase: 'running',
      runId: options.runId,
      debugNodeId: options.debugNodeId ?? null,
      caseId: options.caseId,
      caseTitle: options.caseTitle,
      apiBaseUrl: options.apiBaseUrl,
      environment: options.environment,
      executionMode: options.executionMode,
      detail: options.detail,
      total: options.total,
      steps: [],
      summary: null
    });
    setIsRunningCase(true);
  }

  function closeCaseRunProgress() {
    setCaseRunProgress((current) => ({ ...current, open: false }));
  }

  function applyCaseRunEvent(runId: number, event: CaseRunStreamEvent) {
    setCaseRunProgress((current) => {
      if (current.runId !== runId) return current;
      if (event.type === 'start') {
        return {
          ...current,
          open: current.open,
          phase: 'running',
          executionMode: event.api_base_url ? 'backend_api' : 'fullstack',
          caseId: stringEventValue(event.case_id, current.caseId),
          detail:
            event.message || (event.api_base_url ? '开始执行后端接口用例' : '开始执行浏览器流程'),
          caseTitle: stringEventValue(event.case_title, current.caseTitle),
          apiBaseUrl: stringEventValue(event.api_base_url ?? event.base_url, current.apiBaseUrl),
          environment: stringEventValue(event.environment, current.environment),
          total: numberEventValue(event.total) ?? current.total,
          summary: null
        };
      }
      if (event.type === 'request' || event.type === 'action') {
        const step = caseRunStepFromEvent(event, 'running');
        return {
          ...current,
          detail:
            event.message ||
            (current.executionMode === 'backend_api'
              ? `正在请求 ${step.method} ${step.url}`
              : `正在执行：${step.label}`),
          steps: upsertCaseRunStep(current.steps, step)
        };
      }
      if (event.type === 'inference') {
        const previous = current.steps.find((step) => step.stepId === stringEventValue(event.step_id));
        const step = caseRunStepFromEvent(event, 'running', previous);
        return {
          ...current,
          detail: event.message || `正在推导接口变量：${stringEventValue(event.variable)}`,
          steps: upsertCaseRunStep(current.steps, step)
        };
      }
      if (event.type === 'result') {
        const previous = current.steps.find((step) => step.stepId === stringEventValue(event.step_id));
        const step = caseRunStepFromEvent(event, event.ok ? 'passed' : 'failed', previous);
        return {
          ...current,
          detail: event.message || (step.status === 'passed' ? '请求通过' : step.error || '请求未通过'),
          steps: upsertCaseRunStep(current.steps, step)
        };
      }
      if (event.type === 'done') {
        const failed = numberEventValue(event.failed) ?? 0;
        const passed = numberEventValue(event.passed) ?? 0;
        const total = numberEventValue(event.total) ?? passed + failed;
        return {
          ...current,
          phase: 'complete',
          detail:
            event.message || (current.executionMode === 'backend_api' ? '接口运行完成' : '浏览器流程运行完成'),
          total,
          summary: {
            total,
            passed,
            failed,
            status: failed === 0 ? 'passed' : 'failed'
          }
        };
      }
      if (event.type === 'error') {
        return {
          ...current,
          phase: 'error',
          detail: event.message || '接口运行失败'
        };
      }
      return current;
    });
  }

  function finishCaseRunWithError(runId: number, detail: string) {
    setCaseRunProgress((current) => {
      if (current.runId !== runId) return current;
      return { ...current, open: current.open, phase: 'error', detail };
    });
  }

  return {
    isRunningCase,
    setIsRunningCase,
    caseRunProgress,
    startCaseRunProgress,
    closeCaseRunProgress,
    applyCaseRunEvent,
    finishCaseRunWithError
  };
}

function caseRunStepFromEvent(
  event: CaseRunStreamEvent,
  status: CaseRunStepState['status'],
  previous?: CaseRunStepState
): CaseRunStepState {
  return {
    stepId: stringEventValue(event.step_id, previous?.stepId),
    orderIndex: numberEventValue(event.order_index) ?? previous?.orderIndex ?? 0,
    label: stringEventValue(event.label, previous?.label || '运行步骤'),
    action: nullableStringEventValue(event.action, previous?.action),
    method: stringEventValue(event.method, previous?.method || 'GET'),
    url: stringEventValue(event.url ?? event.target_url ?? event.page_url, previous?.url),
    selector: event.selector ?? previous?.selector ?? null,
    expectedStatus: numberEventValue(event.expected_status) ?? previous?.expectedStatus ?? 200,
    statusCode:
      event.status_code === null ? null : numberEventValue(event.status_code) ?? previous?.statusCode ?? null,
    durationMs: numberEventValue(event.duration_ms) ?? previous?.durationMs ?? null,
    status,
    error: event.error ?? previous?.error ?? null,
    pageUrl: stringEventValue(event.page_url, previous?.pageUrl),
    screenshotDataUrl: stringEventValue(event.screenshot_data_url, previous?.screenshotDataUrl),
    responsePreview: stringEventValue(event.response_preview, previous?.responsePreview),
    responseContentType: event.response_content_type ?? previous?.responseContentType ?? null,
    runtimeInferences: mergeCaseRunInferences(
      previous?.runtimeInferences,
      caseRunInferencesFromEvent(event)
    )
  };
}

function caseRunInferencesFromEvent(event: CaseRunStreamEvent): CaseRunStepState['runtimeInferences'] {
  if (event.type === 'inference') {
    const inference = plainRecord(event.runtime_inference);
    return [
      {
        variable: stringEventValue(event.variable ?? inference?.variable),
        status: caseRunInferenceStatus(event.inference_status),
        confidence: numberEventValue(inference?.confidence) ?? null,
        source: nullableStringEventValue(inference?.source),
        sourceStepLabel: nullableStringEventValue(inference?.source_step_label),
        sourceJsonPath: nullableStringEventValue(inference?.source_json_path),
        reason: nullableStringEventValue(inference?.reason),
        message: nullableStringEventValue(event.message)
      }
    ].filter((item) => item.variable);
  }

  if (Array.isArray(event.runtime_inferences)) {
    return event.runtime_inferences
      .map((item) => plainRecord(item))
      .filter((item): item is Record<string, unknown> => Boolean(item))
      .map((item) => ({
        variable: stringEventValue(item.variable),
        status: 'resolved' as const,
        confidence: numberEventValue(item.confidence) ?? null,
        source: nullableStringEventValue(item.source),
        sourceStepLabel: nullableStringEventValue(item.source_step_label),
        sourceJsonPath: nullableStringEventValue(item.source_json_path),
        reason: nullableStringEventValue(item.reason),
        message: '运行期 agent 已推导变量'
      }))
      .filter((item) => item.variable);
  }

  return undefined;
}

function mergeCaseRunInferences(
  current: CaseRunStepState['runtimeInferences'],
  incoming: CaseRunStepState['runtimeInferences']
): CaseRunStepState['runtimeInferences'] {
  if (!incoming?.length) return current;
  const byVariable = new Map((current ?? []).map((item) => [item.variable, item]));
  incoming.forEach((item) => {
    byVariable.set(item.variable, { ...byVariable.get(item.variable), ...item });
  });
  return Array.from(byVariable.values());
}

function caseRunInferenceStatus(value: unknown): CaseRunInferenceStatus {
  if (value === 'resolved' || value === 'failed') return value;
  return 'running';
}

function plainRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function upsertCaseRunStep(steps: CaseRunStepState[], nextStep: CaseRunStepState) {
  const index = steps.findIndex((step) => step.stepId === nextStep.stepId);
  if (index < 0) {
    return [...steps, nextStep].sort((left, right) => left.orderIndex - right.orderIndex);
  }
  return steps.map((step, stepIndex) => (stepIndex === index ? { ...step, ...nextStep } : step));
}

function stringEventValue(value: unknown, fallback?: string): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback ?? '';
}

function nullableStringEventValue(value: unknown, fallback?: string | null): string | null {
  if (value === null) return null;
  const normalized = stringEventValue(value, fallback ?? undefined);
  return normalized || fallback || null;
}

export function numberEventValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
