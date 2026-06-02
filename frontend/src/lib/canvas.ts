import { demoCases, type CaseGraph, type Group, type Step, type TestCase } from '../api';
import { executableKinds } from './workbenchConstants';
import type {
  CanvasEdge,
  CanvasNode,
  CanvasNodeData,
  ExecutionMode,
  NodeTemplate
} from '../types/workbench';

const RESERVED_STEP_DATA_KEYS = new Set(['method', 'body', 'expected_status', 'node_id', 'position']);
const CONTEXT_NODE_IDS = new Set(['prompt', 'frontend', 'backend']);

export function makeNodeData(
  template: NodeTemplate,
  executionMode: ExecutionMode
): CanvasNodeData {
  if (template.kind === 'api') {
    return {
      kind: 'api',
      label: defaultNodeLabel('api'),
      action: 'api_request',
      target_url: '/api/health',
      method: 'GET',
      value: null,
      expected: '200'
    };
  }
  return {
    kind: template.kind,
    label: defaultNodeLabel(template.kind),
    action: executionMode === 'backend_api' && template.kind === 'assertion' ? 'api_request' : template.action ?? null,
    selector: defaultSelector(template.kind),
    target_url: template.kind === 'page' ? '/' : null,
    value: template.kind === 'input' ? '测试数据' : null,
    expected: executionMode === 'backend_api' ? '200' : template.kind === 'assertion' ? 'visible' : null,
    method: executionMode === 'backend_api' ? 'GET' : null
  };
}

/**
 * 把后端持久化的图结构载荷转换为 React Flow 节点。
 * 旧版生成图包含 prompt/frontend/backend 上下文节点；这里隐藏它们，
 * 让旧用例按新的纯业务步骤图方式渲染。
 */
export function toCanvasNodes(testCase: TestCase): CanvasNode[] {
  const graphNodes = testCase.graph?.nodes ?? [];
  if (graphNodes.length === 0) {
    return testCase.steps.map((step, index) => stepToNode(step, index));
  }

  return graphNodes
    .filter((raw) => !CONTEXT_NODE_IDS.has(String((raw as Partial<CanvasNode>).id ?? '')))
    .map((raw, index) => {
      const node = raw as Partial<CanvasNode>;
      const nodeId = String(node.id ?? `node-${index}`);
      const step = matchStep(testCase.steps, nodeId, index);
      const stepData = recordFromUnknown(step?.data);
      const rawData = (node.data ?? {}) as Partial<CanvasNodeData>;
      return {
        id: nodeId,
        type: node.type ?? 'default',
        position: node.position ?? { x: 120 + index * 180, y: 120 },
        data: {
          ...rawData,
          kind: step ? kindFromStep(step) : String(rawData.kind ?? 'context'),
          label: String(rawData.label ?? step?.label ?? `节点 ${index + 1}`),
          action: step?.action ?? rawData.action ?? null,
          selector: step?.selector ?? rawData.selector ?? null,
          target_url: step?.target_url ?? rawData.target_url ?? null,
          value: step?.value ?? bodyToEditorValue(stepData?.body) ?? rawData.value ?? null,
          expected: step?.expected ?? stringFromUnknown(stepData?.expected_status) ?? rawData.expected ?? null,
          method: String(stepData?.method ?? rawData.method ?? ''),
          description: rawData.description ?? null,
          metadata: mergeMetadata(rawData.metadata, metadataFromStepData(step?.data))
        }
      };
    });
}

export function toCanvasEdges(graph: CaseGraph | null): CanvasEdge[] {
  return (graph?.edges ?? [])
    .filter((edge) => !CONTEXT_NODE_IDS.has(String(edge.source)) && !CONTEXT_NODE_IDS.has(String(edge.target)))
    .map((edge, index) => ({
      id: String(edge.id ?? `edge-${index}`),
      source: String(edge.source),
      target: String(edge.target),
      type: String(edge.type ?? 'smoothstep')
    }));
}

export function stepsFromNodes(currentNodes: CanvasNode[]) {
  return currentNodes
    .filter((node) => executableKinds.has(node.data.kind))
    .map((node, index) => ({
      id: node.id,
      order_index: index + 1,
      kind: node.data.kind === 'page' ? 'setup' : node.data.kind,
      label: node.data.label,
      action: node.data.action,
      selector: node.data.selector,
      target_url: node.data.target_url,
      value: node.data.value,
      expected: node.data.expected,
      data: buildStepData(node),
    }));
}

export function buildDsl({
  prompt,
  selectedCase,
  group,
  nodes,
  edges,
  baseUrl,
  apiBaseUrl,
  frontendEnvironment,
  apiEnvironment,
  executionMode
}: {
  prompt: string;
  selectedCase: TestCase | undefined;
  group: Group | undefined;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  baseUrl: string;
  apiBaseUrl: string;
  frontendEnvironment: string;
  apiEnvironment: string;
  executionMode: ExecutionMode;
}) {
  return {
    name: selectedCase?.title ?? '未命名用例',
    group: group?.name ?? '未分组',
    priority: selectedCase?.priority ?? 'P1',
    tags: ['ai-generated', 'regression'],
    executionMode,
    environment: frontendEnvironment === apiEnvironment ? frontendEnvironment : `${frontendEnvironment}/${apiEnvironment}`,
    frontendEnvironment,
    apiEnvironment,
    sourcePrompt: prompt,
    baseUrl,
    apiBaseUrl,
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      label: node.data.label,
      action: node.data.action,
      selector: node.data.selector,
      url: node.data.target_url,
      value: node.data.value,
      expected: node.data.expected,
      method: node.data.method,
      metadata: node.data.metadata
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target
    })),
    steps: stepsFromNodes(nodes).map((step) => ({
      id: step.id,
      type: step.action,
      label: step.label,
      selector: step.selector,
      url: step.target_url,
      value: step.value,
      expected: step.expected,
      data: step.data
    }))
  };
}

export function findCaseGroup(
  selectedCase: TestCase | undefined,
  groups: Group[],
  activeGroupId: string
): Group | undefined {
  return (
    groups.find((group) => group.id === selectedCase?.group_id) ??
    groups.find((group) => group.id === activeGroupId) ??
    groups[0]
  );
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function makeDemoCase(prompt: string, groupId?: string): TestCase {
  const now = new Date().toISOString();
  return {
    ...demoCases[0],
    id: `demo-${Date.now()}`,
    title: prompt.length > 32 ? `${prompt.slice(0, 32)}...` : prompt,
    description: prompt,
    source_prompt: prompt,
    group_id: groupId ?? 'core',
    created_at: now,
    updated_at: now
  };
}

export function makeBlankCase({
  title,
  description,
  groupId,
  priority
}: {
  title: string;
  description?: string;
  groupId?: string | null;
  priority: string;
}): TestCase {
  const now = new Date().toISOString();
  return {
    ...demoCases[0],
    id: `blank-${Date.now()}`,
    title,
    description: description?.trim() || title,
    source_prompt: description?.trim() || title,
    group_id: groupId ?? null,
    priority,
    status: 'draft',
    code_context: { generation_mode: 'manual' },
    graph: { nodes: [], edges: [] },
    steps: [],
    playwright_spec_path: null,
    created_at: now,
    updated_at: now
  };
}

function stepToNode(step: Step, index: number): CanvasNode {
  const stepData = recordFromUnknown(step.data);
  return {
    id: step.id,
    type: 'default',
    position: { x: 180 + (index % 4) * 220, y: 120 + Math.floor(index / 4) * 130 },
    data: {
      kind: kindFromStep(step),
      label: step.label,
      action: step.action,
      selector: step.selector,
      target_url: step.target_url,
      value: step.value ?? bodyToEditorValue(stepData?.body),
      expected: step.expected ?? stringFromUnknown(stepData?.expected_status),
      method: String(stepData?.method ?? ''),
      metadata: metadataFromStepData(step.data)
    }
  };
}

function matchStep(steps: Step[], nodeId: string, index: number): Step | undefined {
  const match = nodeId.match(/^step-(\d+)$/);
  if (match) return steps.find((step) => step.order_index === Number(match[1]));
  return steps.find((step) => step.id === nodeId);
}

function kindFromStep(step: Step): string {
  if (step.action === 'api_request') return 'api';
  if (step.action === 'goto') return 'page';
  if (step.action === 'fill') return 'input';
  if (step.action === 'click') return 'click';
  if (step.kind === 'assertion' || step.action?.startsWith('expect')) return 'assertion';
  return step.kind || 'action';
}

function defaultNodeLabel(kind: string): string {
  const labels: Record<string, string> = {
    page: '打开业务页面',
    click: '点击操作',
    input: '填写输入',
    assertion: '确认结果',
    api: '调用接口',
    subflow: '复用子流程'
  };
  return labels[kind] ?? '新节点';
}

function defaultSelector(kind: string): string | null {
  const selectors: Record<string, string | null> = {
    click: "[data-testid='primary-action']",
    input: "[data-testid='input']",
    assertion: "[data-testid='result']",
    api: null
  };
  return selectors[kind] ?? null;
}

function parseJsonOrText(value: unknown): unknown {
  if (typeof value !== 'string' || !value.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function buildStepData(node: CanvasNode): Record<string, unknown> {
  const metadata = recordFromUnknown(node.data.metadata) ?? {};
  const baseData: Record<string, unknown> = {
    ...metadata,
    node_id: node.id,
    position: node.position
  };

  // 请求体通过可见的 body 字段编辑。它不能放进 metadata，否则清空请求体时
  // 无法从导出的 Playwright 请求里同步移除。
  if (node.data.kind === 'api' || node.data.action === 'api_request') {
    const body = parseJsonOrText(node.data.value);
    baseData.method = node.data.method || 'GET';
    baseData.expected_status = expectedStatusFromNode(node, metadata);
    if (body !== undefined) baseData.body = body;
  }

  return baseData;
}

function metadataFromStepData(value: unknown): Record<string, unknown> | null {
  const record = recordFromUnknown(value);
  if (!record) return null;
  const metadata = Object.fromEntries(
    Object.entries(record).filter(([key]) => !RESERVED_STEP_DATA_KEYS.has(key))
  );
  return Object.keys(metadata).length ? metadata : null;
}

function mergeMetadata(
  rawMetadata: unknown,
  stepMetadata: Record<string, unknown> | null
): Record<string, unknown> | null {
  const rawRecord = recordFromUnknown(rawMetadata);
  const merged = { ...(rawRecord ?? {}), ...(stepMetadata ?? {}) };
  return Object.keys(merged).length ? merged : null;
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function bodyToEditorValue(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function stringFromUnknown(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  return String(value);
}

function expectedStatusFromNode(node: CanvasNode, metadata: Record<string, unknown>): number {
  return statusCodeFromUnknown(node.data.expected) ?? statusCodeFromUnknown(metadata.expected_status) ?? 200;
}

function statusCodeFromUnknown(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const exactValue = Number(value.trim());
  if (Number.isFinite(exactValue)) return exactValue;
  const statusMatch = value.match(/\b[1-5]\d{2}\b/);
  return statusMatch ? Number(statusMatch[0]) : null;
}
