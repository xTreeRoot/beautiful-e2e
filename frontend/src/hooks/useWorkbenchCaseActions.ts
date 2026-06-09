import { useState, type Dispatch, type SetStateAction } from 'react';

import {
  api,
  type CaseRunRequestPayload,
  type CaseRunStepOverridePayload,
  type CaseRunStreamEvent,
  type GenerateCaseStreamEvent,
  type Group,
  type TestCase
} from '../api';
import {
  makeDemoCase,
  nodesWithEnvironmentRelativeApiTargets,
  stepsFromNodes
} from '../lib/canvas';
import { applyNodeDebugDraft, withNodeDebugDraft } from '../lib/nodeDebug';
import { environmentSettingsPatch, type ProjectEnvironment } from '../lib/projectEnvironments';
import type {
  CanvasEdge,
  CanvasNode,
  CaseRunProgressState,
  ExecutionMode,
  NodeDebugDraft
} from '../types/workbench';
import { numberEventValue } from './useCaseRunProgress';

type ToastType = 'success' | 'info' | 'warning' | 'error';

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

type UseWorkbenchCaseActionsOptions = {
  projectId?: string;
  groups: Group[];
  cases: TestCase[];
  selectedCase?: TestCase;
  activeGroupId: string;
  executionMode: ExecutionMode;
  frontendPath: string;
  backendPath: string;
  offlineMode: boolean;
  canvasDsl: Record<string, unknown>;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  environments: ProjectEnvironment[];
  baseUrl: string;
  apiBaseUrl: string;
  activeFrontendEnvironmentKey: string;
  activeApiEnvironmentKey: string;
  promptRef: { current: string };
  caseRunProgress: CaseRunProgressState;
  setCases: Dispatch<SetStateAction<TestCase[]>>;
  setSelectedCaseId: Dispatch<SetStateAction<string | null>>;
  applyCaseToCanvas: (testCase: TestCase | undefined) => void;
  setStatus: (status: string) => void;
  showToast: (type: ToastType, content: string) => void;
  setIsGenerating: Dispatch<SetStateAction<boolean>>;
  startGenerateProgress: (options: {
    runId: number;
    prompt: string;
    executionMode: ExecutionMode;
    initialLine?: string;
  }) => void;
  appendGenerateProgressLine: (runId: number, message: string) => void;
  appendGenerateProgressDelta: (runId: number, event: GenerateCaseStreamEvent) => void;
  finishGenerateProgress: (runId: number, phase: 'complete' | 'error', detail: string) => void;
  setIsRunningCase: Dispatch<SetStateAction<boolean>>;
  startCaseRunProgress: (options: StartCaseRunProgressOptions) => void;
  applyCaseRunEvent: (runId: number, event: CaseRunStreamEvent) => void;
  finishCaseRunWithError: (runId: number, detail: string) => void;
};

/**
 * 管理当前用例的生成、保存和运行。
 * 这些动作跨越 API、画布 DSL 和进度面板，放在独立 hook 中让 controller 只负责把状态源组装起来。
 */
export function useWorkbenchCaseActions({
  projectId,
  groups,
  cases,
  selectedCase,
  activeGroupId,
  executionMode,
  frontendPath,
  backendPath,
  offlineMode,
  canvasDsl,
  nodes,
  edges,
  environments,
  baseUrl,
  apiBaseUrl,
  activeFrontendEnvironmentKey,
  activeApiEnvironmentKey,
  promptRef,
  caseRunProgress,
  setCases,
  setSelectedCaseId,
  applyCaseToCanvas,
  setStatus,
  showToast,
  setIsGenerating,
  startGenerateProgress,
  appendGenerateProgressLine,
  appendGenerateProgressDelta,
  finishGenerateProgress,
  setIsRunningCase,
  startCaseRunProgress,
  applyCaseRunEvent,
  finishCaseRunWithError
}: UseWorkbenchCaseActionsOptions) {
  const [isSaving, setIsSaving] = useState(false);

  function applyGeneratedCase(generated: TestCase, targetCase: TestCase | undefined) {
    setCases((current) =>
      targetCase ? current.map((item) => (item.id === generated.id ? generated : item)) : [generated, ...current]
    );
    setSelectedCaseId(generated.id);
    applyCaseToCanvas(generated);
  }

  async function generateCase() {
    const currentPrompt = promptRef.current;
    if (!projectId || !currentPrompt.trim()) return;
    const targetCase = selectedCase;
    const isRegenerating = Boolean(targetCase);
    const fallbackGroupId = activeGroupId === 'all' ? groups[0]?.id ?? null : activeGroupId;
    const targetGroupId = targetCase ? targetCase.group_id : fallbackGroupId;
    const runId = Date.now();
    startGenerateProgress({ runId, prompt: currentPrompt, executionMode });
    setStatus(
      isRegenerating
        ? '正在重新生成当前用例'
        : executionMode === 'backend_api'
          ? '正在生成后端接口用例'
          : '正在生成前后端配合用例'
    );

    if (offlineMode) {
      appendGenerateProgressLine(runId, '演示模式跳过后端流式生成，在本地创建用例。');
      const demoGenerated = makeDemoCase(currentPrompt, targetGroupId ?? undefined);
      const generated = targetCase
        ? {
            ...demoGenerated,
            id: targetCase.id,
            title: targetCase.title,
            description: targetCase.description,
            priority: targetCase.priority,
            status: targetCase.status,
            group_id: targetCase.group_id,
            created_at: targetCase.created_at
          }
        : demoGenerated;
      applyGeneratedCase(generated, targetCase);
      setIsGenerating(false);
      setStatus(isRegenerating ? '演示用例已在本地重新生成' : '演示用例已在本地生成');
      finishGenerateProgress(
        runId,
        'complete',
        isRegenerating ? '演示模式已重新生成当前用例，结果已同步到画布。' : '演示模式已在本地生成用例，结果已同步到画布。'
      );
      showToast('success', isRegenerating ? '已在演示模式重新生成当前用例' : '已在演示模式生成用例');
      return;
    }

    try {
      const generated = await api.generateCaseStream(
        projectId,
        {
          description: currentPrompt,
          target_case_id: targetCase?.id,
          title: targetCase?.title,
          case_description: targetCase?.description,
          execution_mode: executionMode,
          group_id: targetGroupId,
          frontend_repo_path: frontendPath || undefined,
          backend_repo_path: backendPath || undefined,
          created_by: 'developer',
          priority: targetCase?.priority,
          canvas_dsl: canvasDsl
        },
        (event) => {
          if (event.type === 'provider_delta') {
            appendGenerateProgressDelta(runId, event);
            return;
          }
          if (event.message) {
            appendGenerateProgressLine(runId, event.message);
            if (event.type === 'progress') setStatus(event.message);
          }
        }
      );
      applyGeneratedCase(generated, targetCase);
      setStatus(isRegenerating ? '用例已重新生成' : '用例已生成');
      finishGenerateProgress(
        runId,
        'complete',
        isRegenerating ? '当前用例已重新生成，节点图和 DSL 预览已更新。' : '用例已生成，节点图和 DSL 预览已更新。'
      );
      showToast('success', isRegenerating ? '用例已重新生成' : '用例已生成');
    } catch (error) {
      const message = error instanceof Error ? error.message : '生成失败';
      setStatus(message);
      finishGenerateProgress(runId, 'error', message);
      showToast('error', message);
    } finally {
      setIsGenerating(false);
    }
  }

  async function saveCanvas(): Promise<boolean> {
    if (!selectedCase || offlineMode) {
      const message = '后端未连接，暂时不能持久化画布';
      setStatus(message);
      showToast('warning', message);
      return false;
    }
    setIsSaving(true);
    setStatus('正在保存画布 DSL');
    try {
      const graphNodes = nodesWithEnvironmentRelativeApiTargets(nodes);
      const saved = await api.updateCaseGraph(selectedCase.id, {
        graph: { nodes: graphNodes, edges },
        steps: stepsFromNodes(graphNodes),
        execution_mode: executionMode,
        source_prompt: promptRef.current,
        actor: 'developer'
      });
      setCases((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setStatus('画布和 DSL 已保存');
      showToast('success', '画布和 DSL 已保存');
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存失败';
      setStatus(message);
      showToast('error', message);
      return false;
    } finally {
      setIsSaving(false);
    }
  }

  async function runCase(targetCase: TestCase | undefined = selectedCase) {
    if (!targetCase || offlineMode) {
      const message = '后端未连接，暂时不能运行用例';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setSelectedCaseId(targetCase.id);
    const runPayload = buildRuntimeCaseRunPayload();
    if (!runPayload) return;
    if (executionMode === 'backend_api') {
      const runId = Date.now();
      setStatus('正在执行后端接口请求');
      startCaseRunProgress({
        runId,
        caseId: targetCase.id,
        caseTitle: targetCase.title,
        apiBaseUrl,
        environment: activeApiEnvironmentKey,
        executionMode: 'backend_api',
        detail: '正在连接后端运行器',
        total: targetCase.steps.filter((step) => step.action === 'api_request').length
      });
      try {
        let failedCount = 0;
        await api.runBackendApiCaseStream(
          targetCase.id,
          (event) => {
            applyCaseRunEvent(runId, event);
            if (event.type === 'done') failedCount = numberEventValue(event.failed) ?? 0;
          },
          runPayload
        );
        if (failedCount > 0) {
          setStatus(`接口运行完成：${failedCount} 个请求失败`);
          showToast('warning', `接口运行完成：${failedCount} 个请求失败`);
        } else {
          setStatus('后端接口运行完成');
          showToast('success', '后端接口运行完成');
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : '接口运行失败';
        finishCaseRunWithError(runId, message);
        setStatus(message);
        showToast('error', message);
      } finally {
        setIsRunningCase(false);
      }
      return;
    }

    const runId = Date.now();
    setStatus('正在执行浏览器流程');
    startCaseRunProgress({
      runId,
      caseId: targetCase.id,
      caseTitle: targetCase.title,
      apiBaseUrl: baseUrl,
      environment: activeFrontendEnvironmentKey,
      executionMode: 'fullstack',
      detail: '正在启动浏览器运行器',
      total: targetCase.steps.filter((step) =>
        ['goto', 'fill', 'click', 'expect_visible', 'expect_not_visible', 'expect_text'].includes(
          String(step.action)
        )
      ).length
    });
    try {
      let failedCount = 0;
      await api.runFullstackCaseStream(
        targetCase.id,
        (event) => {
          applyCaseRunEvent(runId, event);
          if (event.type === 'done') failedCount = numberEventValue(event.failed) ?? 0;
        },
        { ...runPayload, fail_fast: true }
      );
      if (failedCount > 0) {
        setStatus(`浏览器流程运行完成：${failedCount} 个步骤失败`);
        showToast('warning', `浏览器流程运行完成：${failedCount} 个步骤失败`);
      } else {
        setStatus('浏览器流程运行完成');
        showToast('success', '浏览器流程运行完成');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '浏览器流程运行失败';
      finishCaseRunWithError(runId, message);
      setStatus(message);
      showToast('error', message);
    } finally {
      setIsRunningCase(false);
    }
  }

  async function runCaseNode(
    targetNode: CanvasNode | null | undefined,
    debugDraft?: NodeDebugDraft
  ) {
    if (!targetNode || !selectedCase || offlineMode) {
      const message = '后端未连接，暂时不能调试节点';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    if (executionMode !== 'backend_api') {
      const message = '单节点调试仅支持接口模式';
      setStatus(message);
      showToast('warning', message);
      return;
    }

    const nodesWithDebugDraft = debugDraft
      ? nodes.map((node) => (node.id === targetNode.id ? withNodeDebugDraft(node, debugDraft) : node))
      : nodes;
    const graphNodes = nodesWithEnvironmentRelativeApiTargets(nodesWithDebugDraft);
    const stepOverride = stepOverrideFromNode(graphNodes, targetNode.id, debugDraft);
    if (!stepOverride || stepOverride.action !== 'api_request') {
      const message = '当前节点不是可调试的接口请求';
      setStatus(message);
      showToast('warning', message);
      return;
    }

    const runId = Date.now();
    const runPayload = buildRuntimeCaseRunPayload({
      fail_fast: true,
      step_id: targetNode.id,
      step_override: stepOverride
    });
    if (!runPayload) return;
    setSelectedCaseId(selectedCase.id);
    setStatus(`正在保存单节点调试参数：${stepOverride.label}`);
    startCaseRunProgress({
      runId,
      caseId: selectedCase.id,
      caseTitle: selectedCase.title,
      apiBaseUrl,
      environment: activeApiEnvironmentKey,
      executionMode: 'backend_api',
      detail: `正在保存单节点调试参数：${stepOverride.label}`,
      total: 1,
      open: false,
      debugNodeId: targetNode.id
    });
    try {
      // 单节点调试的手工参数是 DSL 契约的一部分，先写回数据库再执行，
      // 这样刷新页面或下次打开节点时仍能继续使用上次参数。
      await api.updateCaseGraph(selectedCase.id, {
        graph: { nodes: graphNodes, edges },
        steps: stepsFromNodes(graphNodes),
        execution_mode: executionMode,
        source_prompt: promptRef.current,
        actor: 'developer'
      });
      setStatus(`调试参数已保存，正在调试节点：${stepOverride.label}`);
      let failedCount = 0;
      let failedDetail = '';
      await api.runBackendApiCaseStream(
        selectedCase.id,
        (event) => {
          applyCaseRunEvent(runId, event);
          if (event.type === 'result' && event.ok === false) {
            failedDetail = debugFailureDetailFromEvent(event);
          }
          if (event.type === 'done') failedCount = numberEventValue(event.failed) ?? 0;
        },
        runPayload
      );
      if (failedCount > 0) {
        const detail = failedDetail || '响应未达到期望';
        setStatus(`单节点调试未通过：${detail}`);
        showToast('warning', `单节点调试未通过：${detail}`);
      } else {
        setStatus(`单节点调试通过：${stepOverride.label}`);
        showToast('success', `单节点调试通过：${stepOverride.label}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '单节点调试失败';
      finishCaseRunWithError(runId, message);
      setStatus(message);
      showToast('error', message);
    } finally {
      setIsRunningCase(false);
    }
  }

  function rerunCaseFromProgress() {
    const targetCase =
      cases.find((item) => item.id === caseRunProgress.caseId) ??
      selectedCase;
    void runCase(targetCase);
  }

  function buildRuntimeCaseRunPayload(
    patch: CaseRunRequestPayload = {}
  ): CaseRunRequestPayload | null {
    try {
      return {
        ...patch,
        environment_settings: environmentSettingsPatch(
          environments,
          activeFrontendEnvironmentKey,
          activeApiEnvironmentKey
        )
      };
    } catch (error) {
      const message =
        error instanceof Error ? `请检查接口环境配置：${error.message}` : '请检查接口环境配置';
      setStatus(message);
      showToast('warning', message);
      return null;
    }
  }

  return {
    isSaving,
    generateCase,
    saveCanvas,
    runCase,
    runCaseNode,
    rerunCaseFromProgress
  };
}

function stepOverrideFromNode(
  nodes: CanvasNode[],
  nodeId: string,
  debugDraft?: NodeDebugDraft
): CaseRunStepOverridePayload | null {
  const step = stepsFromNodes(nodes).find((item) => item.id === nodeId);
  if (!step) return null;
  return applyNodeDebugDraft({
    id: step.id,
    order_index: step.order_index,
    kind: step.kind,
    label: step.label,
    action: step.action,
    selector: step.selector,
    target_url: step.target_url,
    value: step.value,
    expected: step.expected,
    data: step.data
  }, debugDraft);
}

function debugFailureDetailFromEvent(event: CaseRunStreamEvent): string {
  const expectedStatus = numberEventValue(event.expected_status);
  const statusCode = numberEventValue(event.status_code);
  const parts = [
    event.error || null,
    expectedStatus !== null || statusCode !== null
      ? `期望 ${expectedStatus ?? '-'}，实际 ${statusCode ?? '-'}`
      : null
  ].filter(Boolean);
  return parts.join('；');
}
