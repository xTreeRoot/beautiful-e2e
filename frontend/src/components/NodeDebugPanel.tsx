import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button as AntButton,
  Flex,
  Input as AntInput,
  Select as AntSelect,
  Space,
  Tag,
  Typography
} from 'antd';
import {
  AlertCircle,
  Braces,
  CheckCircle2,
  Clock3,
  Loader2,
  PlayCircle,
  Plus,
  Trash2,
  XCircle
} from 'lucide-react';

import type { TestCase } from '../api';
import {
  buildDebugTargetUrl,
  createNodeDebugDraft,
  defaultPathParams,
  pathParamNames
} from '../lib/nodeDebug';
import { formatJsonText, formatResponsePreview } from '../lib/responsePreview';
import type {
  CanvasNode,
  CaseRunProgressState,
  CaseRunStepState,
  ExecutionMode,
  NodeDebugDraft
} from '../types/workbench';

const { Paragraph, Text } = Typography;
const httpMethodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].map(
  (method) => ({ label: method, value: method })
);
const emptyParamRow = () => ({ id: `${Date.now()}-${Math.random()}`, key: '', value: '' });

type DebugParamRow = ReturnType<typeof emptyParamRow>;

type NodeDebugPanelProps = {
  node: CanvasNode;
  selectedCase?: TestCase;
  executionMode: ExecutionMode;
  progress: CaseRunProgressState;
  isRunning: boolean;
  onDebug: (draft: NodeDebugDraft) => void;
};

export function NodeDebugPanel({
  node,
  selectedCase,
  executionMode,
  progress,
  isRunning,
  onDebug
}: NodeDebugPanelProps) {
  const initialDraft = useMemo(() => createNodeDebugDraft(node), [node]);
  const [method, setMethod] = useState(initialDraft.method);
  const [requestPath, setRequestPath] = useState(initialDraft.path);
  const [expected, setExpected] = useState(initialDraft.expected);
  const [bodyDraft, setBodyDraft] = useState(initialDraft.body);
  const [bodyFormatError, setBodyFormatError] = useState<string | null>(null);
  const [pathParamRows, setPathParamRows] = useState<DebugParamRow[]>(() =>
    rowsFromRecord(initialDraft.pathParams)
  );
  const [queryParamRows, setQueryParamRows] = useState<DebugParamRow[]>(() =>
    rowsFromRecord(initialDraft.queryParams)
  );

  useEffect(() => {
    const nextDraft = createNodeDebugDraft(node);
    setMethod(nextDraft.method);
    setRequestPath(nextDraft.path);
    setExpected(nextDraft.expected);
    setBodyDraft(nextDraft.body);
    setBodyFormatError(null);
    setPathParamRows(rowsFromRecord(nextDraft.pathParams));
    setQueryParamRows(rowsFromRecord(nextDraft.queryParams));
  }, [
    node,
    node.data.expected,
    node.data.metadata,
    node.data.method,
    node.data.target_url,
    node.data.value
  ]);

  const isApiRequest = node.data.action === 'api_request' || node.data.kind === 'api';
  const debugDraft = useMemo<NodeDebugDraft>(
    () => ({
      method,
      path: requestPath,
      pathParams: recordFromRows(pathParamRows),
      queryParams: recordFromRows(queryParamRows),
      body: bodyDraft,
      expected
    }),
    [method, requestPath, pathParamRows, queryParamRows, bodyDraft, expected]
  );
  const previewUrl = useMemo(() => buildDebugTargetUrl(debugDraft), [debugDraft]);
  const isDebugRunForNode =
    progress.debugNodeId === node.id &&
    progress.caseId === selectedCase?.id &&
    progress.executionMode === 'backend_api';
  const stepResult =
    progress.steps.find((step) => step.stepId === node.id) ??
    (isDebugRunForNode && progress.total === 1 ? progress.steps[0] : undefined);
  const isCurrentRun =
    isDebugRunForNode &&
    (progress.total === 1 || Boolean(stepResult));
  const isDebugging = isRunning && isCurrentRun;
  const disabledReason = debugDisabledReason({
    isApiRequest,
    selectedCase,
    executionMode,
    requestPath
  });

  function handleRequestPathChange(value: string) {
    setRequestPath(value);
    setPathParamRows((current) => mergePathParamRows(current, value));
  }

  function handleBodyChange(value: string) {
    setBodyDraft(value);
    if (bodyFormatError) setBodyFormatError(null);
  }

  function handleFormatBody() {
    const formatted = formatJsonText(bodyDraft);
    if (formatted === null) {
      setBodyFormatError('Body 不是合法 JSON，无法格式化');
      return;
    }
    setBodyDraft(formatted);
    setBodyFormatError(null);
  }

  return (
    <div className="node-debug-panel">
      <section className="node-debug-form">
        <div className="control-field">
          <Text className="field-label">请求方法</Text>
          <AntSelect value={method} options={httpMethodOptions} onChange={setMethod} />
        </div>
        <div className="control-field">
          <Text className="field-label">期望状态</Text>
          <AntInput value={expected} onChange={(event) => setExpected(event.target.value)} />
        </div>
        <div className="control-field node-debug-path-control">
          <Text className="field-label">请求 Path</Text>
          <AntInput
            value={requestPath}
            onChange={(event) => handleRequestPathChange(event.target.value)}
            placeholder="/api/entities/{entityId}"
          />
        </div>
        <DebugParamsEditor
          label="Path 参数"
          rows={pathParamRows}
          keyPlaceholder="参数名"
          valuePlaceholder="参数值"
          onChange={setPathParamRows}
        />
        <DebugParamsEditor
          label="Query 参数"
          rows={queryParamRows}
          keyPlaceholder="参数名"
          valuePlaceholder="参数值"
          onChange={setQueryParamRows}
        />
        <div className="control-field node-debug-body-control">
          <div className="node-debug-field-header">
            <Text className="field-label">Body</Text>
            <AntButton
              className="secondary-button node-debug-format-button"
              icon={<Braces size={15} />}
              disabled={!bodyDraft.trim()}
              onClick={handleFormatBody}
            >
              格式化 JSON
            </AntButton>
          </div>
          <AntInput.TextArea
            className="node-debug-body-editor"
            value={bodyDraft}
            status={bodyFormatError ? 'error' : undefined}
            autoSize={{ minRows: 8, maxRows: 18 }}
            onChange={(event) => handleBodyChange(event.target.value)}
          />
          {bodyFormatError ? (
            <Text className="node-debug-field-error" type="danger">
              {bodyFormatError}
            </Text>
          ) : null}
        </div>
      </section>

      <aside className="node-debug-run-panel">
        <section className="node-debug-toolbar">
          <div className="node-debug-target">
            <Space size={8} wrap>
              <Tag className={`case-run-method ${method.toLowerCase()}`}>
                {method.toUpperCase()}
              </Tag>
              <Tag>期望 {expected || '200'}</Tag>
            </Space>
            <Paragraph className="node-debug-url" copyable={{ text: previewUrl }}>
              {previewUrl || '未设置接口地址'}
            </Paragraph>
          </div>
          <AntButton
            type="primary"
            icon={<PlayCircle size={16} />}
            loading={isDebugging}
            disabled={Boolean(disabledReason)}
            onClick={() => onDebug(debugDraft)}
          >
            调试当前节点
          </AntButton>
        </section>

        {disabledReason ? <Alert type="warning" showIcon message={disabledReason} /> : null}
        {renderDebugResult({ progress, stepResult, isCurrentRun, isDebugging })}
      </aside>
    </div>
  );
}

function debugDisabledReason({
  isApiRequest,
  selectedCase,
  executionMode,
  requestPath
}: {
  isApiRequest: boolean;
  selectedCase?: TestCase;
  executionMode: ExecutionMode;
  requestPath: string;
}): string | null {
  if (!selectedCase) return '请先选择一个用例';
  if (executionMode !== 'backend_api') return '单节点调试仅支持接口模式';
  if (!isApiRequest) return '当前节点不是接口请求';
  if (!requestPath.trim()) return '请填写请求 Path';
  return null;
}

function DebugParamsEditor({
  label,
  rows,
  keyPlaceholder,
  valuePlaceholder,
  onChange
}: {
  label: string;
  rows: DebugParamRow[];
  keyPlaceholder: string;
  valuePlaceholder: string;
  onChange: (rows: DebugParamRow[]) => void;
}) {
  function updateRow(index: number, patch: Partial<DebugParamRow>) {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function removeRow(index: number) {
    const nextRows = rows.filter((_, rowIndex) => rowIndex !== index);
    onChange(nextRows.length ? nextRows : [emptyParamRow()]);
  }

  return (
    <div className="control-field node-debug-param-editor">
      <Text className="field-label">{label}</Text>
      <div className="node-debug-param-list">
        {rows.map((row, index) => (
          <div className="node-debug-param-row" key={row.id}>
            <AntInput
              value={row.key}
              onChange={(event) => updateRow(index, { key: event.target.value })}
              placeholder={keyPlaceholder}
            />
            <AntInput
              value={row.value}
              onChange={(event) => updateRow(index, { value: event.target.value })}
              placeholder={valuePlaceholder}
            />
            <AntButton
              aria-label={`删除${label}`}
              className="secondary-button node-debug-param-remove"
              icon={<Trash2 size={15} />}
              onClick={() => removeRow(index)}
            />
          </div>
        ))}
      </div>
      <AntButton
        className="secondary-button node-debug-param-add"
        icon={<Plus size={15} />}
        onClick={() => onChange([...rows, emptyParamRow()])}
      >
        添加{label}
      </AntButton>
    </div>
  );
}

function rowsFromRecord(record: Record<string, string>): DebugParamRow[] {
  const rows = Object.entries(record).map(([key, value]) => ({ ...emptyParamRow(), key, value }));
  return rows.length ? rows : [emptyParamRow()];
}

function recordFromRows(rows: DebugParamRow[]): Record<string, string> {
  return Object.fromEntries(
    rows
      .map((row) => [row.key.trim(), row.value] as const)
      .filter(([key]) => Boolean(key))
  );
}

function mergePathParamRows(rows: DebugParamRow[], path: string): DebugParamRow[] {
  const current = new Map(rows.map((row) => [row.key, row]));
  const merged = [...rows];
  for (const [key, value] of Object.entries(defaultPathParams(path))) {
    if (!key || current.has(key)) continue;
    merged.push({ ...emptyParamRow(), key, value });
  }
  const validKeys = new Set(pathParamNames(path));
  const filtered = merged.filter((row) => !row.key || validKeys.size === 0 || validKeys.has(row.key));
  return filtered.length ? filtered : [emptyParamRow()];
}

function renderDebugResult({
  progress,
  stepResult,
  isCurrentRun,
  isDebugging
}: {
  progress: CaseRunProgressState;
  stepResult?: CaseRunStepState;
  isCurrentRun: boolean;
  isDebugging: boolean;
}) {
  if (isCurrentRun && progress.phase === 'error' && !stepResult) {
    return (
      <Alert
        className="node-debug-alert"
        type="error"
        showIcon
        message="单节点调试失败"
        description={progress.detail || '未收到后端运行结果'}
      />
    );
  }

  if (isCurrentRun && progress.summary?.failed && !stepResult) {
    return (
      <Alert
        className="node-debug-alert"
        type="warning"
        showIcon
        message="单节点调试未通过"
        description={progress.detail || '后端未返回当前节点的步骤结果，请检查运行日志。'}
      />
    );
  }

  if (!stepResult) {
    if (isDebugging) {
      return (
        <section className="node-debug-result running">
          <Flex align="center" gap={10}>
            <Loader2 className="node-debug-spin" size={18} aria-hidden="true" />
            <Text strong>正在连接节点调试器</Text>
          </Flex>
        </section>
      );
    }
    return (
      <div className="node-debug-placeholder">
        <Text type="secondary">调试结果会显示在这里</Text>
      </div>
    );
  }

  const formattedResponse = formatResponsePreview(stepResult.responsePreview);

  return (
    <section className={`node-debug-result ${stepResult.status}`}>
      <Flex align="center" justify="space-between" gap={12} wrap>
        <Flex align="center" gap={10}>
          {debugStatusIcon(stepResult.status)}
          <Text strong>{debugStatusText(stepResult)}</Text>
        </Flex>
        <Space size={8} wrap>
          <Tag>状态码 {stepResult.statusCode ?? '-'}</Tag>
          <Tag>{stepResult.durationMs ?? '-'} ms</Tag>
        </Space>
      </Flex>

      {stepResult.status === 'failed' ? (
        <Alert
          className="node-debug-alert"
          type="error"
          showIcon
          message="未通过原因"
          description={failureReasonText(stepResult)}
        />
      ) : null}
      {stepResult.runtimeInferences?.length ? (
        <div className="node-debug-inferences">
          {stepResult.runtimeInferences.map((inference) => (
            <div key={inference.variable} className={`case-run-inference ${inference.status}`}>
              {inference.status === 'failed' ? (
                <AlertCircle size={16} aria-hidden="true" />
              ) : inference.status === 'resolved' ? (
                <CheckCircle2 size={16} aria-hidden="true" />
              ) : (
                <Loader2 size={16} aria-hidden="true" />
              )}
              <div className="case-run-inference-copy">
                <Text strong>{inference.variable}</Text>
                <Text>{inference.message || inference.reason || inference.sourceJsonPath || '变量推导中'}</Text>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {formattedResponse ? (
        <div className="node-debug-response-block">
          <Flex
            className="node-debug-response-header"
            align="center"
            justify="space-between"
            gap={8}
            wrap
          >
            <Text strong>响应内容</Text>
            <Space size={6} wrap>
              {stepResult.responseContentType ? <Tag>{stepResult.responseContentType}</Tag> : null}
              <Tag>{formattedResponse.isJson ? 'JSON 已格式化' : '原始文本'}</Tag>
            </Space>
          </Flex>
          <pre className="node-debug-response">
            <code>{formattedResponse.text}</code>
          </pre>
        </div>
      ) : null}
    </section>
  );
}

function debugStatusIcon(status: CaseRunStepState['status']) {
  if (status === 'passed') return <CheckCircle2 className="node-debug-icon passed" size={18} />;
  if (status === 'failed') return <XCircle className="node-debug-icon failed" size={18} />;
  if (status === 'running') return <Loader2 className="node-debug-icon running" size={18} />;
  return <Clock3 className="node-debug-icon" size={18} />;
}

function debugStatusText(step: CaseRunStepState): string {
  if (step.status === 'passed') return '请求通过';
  if (step.status === 'failed') return '请求未通过';
  if (step.status === 'running') return '请求中';
  return '等待运行';
}

function failureReasonText(step: CaseRunStepState): string {
  const statusText =
    step.statusCode === null
      ? `期望 ${step.expectedStatus}，实际无响应`
      : `期望 ${step.expectedStatus}，实际 ${step.statusCode}`;
  return [step.error, statusText].filter(Boolean).join('；');
}
