import type { CaseRunStepOverridePayload } from '../api';
import type { CanvasNode, NodeDebugDraft } from '../types/workbench';

const PATH_PARAM_PATTERNS = [
  /\{\{([A-Za-z0-9_.-]+)\}\}/g,
  /\{([A-Za-z0-9_.-]+)\}/g,
  /(^|\/):([A-Za-z_][A-Za-z0-9_]*)/g
];
const NODE_DEBUG_DRAFT_METADATA_KEY = 'node_debug_draft';

/**
 * 从节点配置生成单节点调试草稿。
 * 这里会把 URL 上已有 query 拆成可编辑参数，避免调试表单改动污染节点本身。
 */
export function createNodeDebugDraft(node: CanvasNode): NodeDebugDraft {
  const { path, queryParams } = splitPathAndQuery(String(node.data.target_url ?? ''));
  const fallback = {
    method: String(node.data.method ?? 'GET').toUpperCase(),
    path,
    pathParams: defaultPathParams(path),
    queryParams,
    body: String(node.data.value ?? ''),
    expected: String(node.data.expected ?? '200')
  };
  const metadata = plainRecord(node.data.metadata);
  return normalizeNodeDebugDraft(metadata?.[NODE_DEBUG_DRAFT_METADATA_KEY], fallback);
}

/**
 * 把调试草稿写回节点 metadata。
 * 正式请求字段保持不变，调试参数通过 DSL 的扩展字段持久化，便于下一次打开节点继续调试。
 */
export function withNodeDebugDraft(node: CanvasNode, draft: NodeDebugDraft): CanvasNode {
  const metadata = plainRecord(node.data.metadata) ?? {};
  return {
    ...node,
    data: {
      ...node.data,
      metadata: {
        ...metadata,
        [NODE_DEBUG_DRAFT_METADATA_KEY]: normalizeNodeDebugDraft(draft, draft)
      }
    }
  };
}

/**
 * 把调试草稿覆盖到步骤运行载荷。
 * Body 为空表示本次调试不发送请求体；非 JSON 文本会按纯文本传给后端运行器。
 */
export function applyNodeDebugDraft(
  step: CaseRunStepOverridePayload,
  draft?: NodeDebugDraft
): CaseRunStepOverridePayload {
  if (!draft) return step;

  const data = { ...(step.data ?? {}) };
  const body = parseJsonOrText(draft.body);
  data.method = draft.method || 'GET';
  data.expected_status = statusCodeFromUnknown(draft.expected) ?? statusCodeFromUnknown(data.expected_status) ?? 200;
  if (body === undefined) {
    delete data.body;
  } else {
    data.body = body;
  }

  return {
    ...step,
    target_url: buildDebugTargetUrl(draft),
    value: draft.body.trim() ? draft.body : null,
    expected: draft.expected || step.expected,
    data
  };
}

/**
 * 预览最终调试请求地址。
 * Path 参数会替换 `{{id}}`、`{id}` 和 `/:id` 三类常见路由占位符。
 */
export function buildDebugTargetUrl(draft: NodeDebugDraft): string {
  const substitutedPath = substitutePathParams(draft.path, draft.pathParams);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(draft.queryParams)) {
    const normalizedKey = key.trim();
    if (!normalizedKey) continue;
    query.append(normalizedKey, value);
  }
  const queryText = query.toString();
  if (!queryText) return substitutedPath;
  if (substitutedPath.endsWith('?') || substitutedPath.endsWith('&')) {
    return `${substitutedPath}${queryText}`;
  }
  return `${substitutedPath}${substitutedPath.includes('?') ? '&' : '?'}${queryText}`;
}

export function defaultPathParams(path: string): Record<string, string> {
  return Object.fromEntries(pathParamNames(path).map((name) => [name, '']));
}

export function pathParamNames(path: string): string[] {
  const names = new Set<string>();
  for (const pattern of PATH_PARAM_PATTERNS) {
    for (const match of path.matchAll(pattern)) {
      const name = match[2] ?? match[1];
      if (name) names.add(name);
    }
  }
  return Array.from(names);
}

function normalizeNodeDebugDraft(value: unknown, fallback: NodeDebugDraft): NodeDebugDraft {
  const record = plainRecord(value);
  if (!record) return fallback;

  return {
    method: stringFromUnknown(record.method, fallback.method).toUpperCase() || 'GET',
    path: stringFromUnknown(record.path, fallback.path),
    pathParams: stringRecordFromUnknown(record.pathParams, fallback.pathParams),
    queryParams: stringRecordFromUnknown(record.queryParams, fallback.queryParams),
    body: stringFromUnknown(record.body, fallback.body),
    expected: stringFromUnknown(record.expected, fallback.expected)
  };
}

function splitPathAndQuery(value: string): { path: string; queryParams: Record<string, string> } {
  const hashIndex = value.indexOf('#');
  const target = hashIndex >= 0 ? value.slice(0, hashIndex) : value;
  const queryIndex = target.indexOf('?');
  if (queryIndex < 0) return { path: target, queryParams: {} };

  const path = target.slice(0, queryIndex);
  const queryText = target.slice(queryIndex + 1);
  const queryParams: Record<string, string> = {};
  for (const [key, itemValue] of new URLSearchParams(queryText).entries()) {
    queryParams[key] = itemValue;
  }
  return { path, queryParams };
}

function plainRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringRecordFromUnknown(
  value: unknown,
  fallback: Record<string, string>
): Record<string, string> {
  const record = plainRecord(value);
  if (!record) return fallback;

  return Object.fromEntries(
    Object.entries(record).map(([key, itemValue]) => [key, stringFromUnknown(itemValue, '')])
  );
}

function stringFromUnknown(value: unknown, fallback: string): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function substitutePathParams(path: string, pathParams: Record<string, string>): string {
  let result = path;
  for (const [key, value] of Object.entries(pathParams)) {
    const normalizedKey = key.trim();
    if (!normalizedKey || !value) continue;
    const encoded = encodeURIComponent(value);
    result = result
      .split(`{{${normalizedKey}}}`)
      .join(encoded)
      .split(`{${normalizedKey}}`)
      .join(encoded);
    result = result.replace(new RegExp(`(^|/):${escapeRegExp(normalizedKey)}(?=/|$)`, 'g'), `$1${encoded}`);
  }
  return result;
}

function parseJsonOrText(value: string): unknown {
  if (!value.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function statusCodeFromUnknown(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
