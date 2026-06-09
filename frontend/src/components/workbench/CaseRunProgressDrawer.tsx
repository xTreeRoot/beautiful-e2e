import { Button, Drawer, Empty, Flex, Image, Progress, Segmented, Space, Tag, Typography } from 'antd';
import {
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Clock3,
  LoaderCircle,
  RefreshCw,
  Send,
  XCircle
} from 'lucide-react';
import { memo, useEffect, useMemo, useState } from 'react';

import { formatResponsePreview } from '../../lib/responsePreview';
import type { CaseRunProgressState, CaseRunStepState } from '../../types/workbench';

const { Paragraph, Text, Title } = Typography;

type CaseRunStepFilter = 'all' | 'passed' | 'failed';

type CaseRunProgressDrawerProps = {
  progress: CaseRunProgressState;
  isRerunning?: boolean;
  onRerun?: () => void;
  onClose: () => void;
};

export function CaseRunProgressDrawer({
  progress,
  isRerunning = false,
  onRerun,
  onClose
}: CaseRunProgressDrawerProps) {
  const [stepFilter, setStepFilter] = useState<CaseRunStepFilter>('all');
  const completed = progress.steps.filter((step) => step.status === 'passed' || step.status === 'failed').length;
  const percent = progress.total > 0 ? Math.round((completed / progress.total) * 100) : 0;
  const failed = progress.summary?.failed ?? progress.steps.filter((step) => step.status === 'failed').length;
  const passed = progress.summary?.passed ?? progress.steps.filter((step) => step.status === 'passed').length;
  const passedSteps = progress.steps.filter((step) => step.status === 'passed').length;
  const failedSteps = progress.steps.filter((step) => step.status === 'failed').length;
  const isBackendApi = progress.executionMode === 'backend_api';
  const filteredSteps = useMemo(() => {
    if (stepFilter === 'passed') return progress.steps.filter((step) => step.status === 'passed');
    if (stepFilter === 'failed') return progress.steps.filter((step) => step.status === 'failed');
    return progress.steps;
  }, [progress.steps, stepFilter]);

  useEffect(() => {
    setStepFilter('all');
  }, [progress.runId]);

  return (
    <Drawer
      className="case-run-drawer"
      title={
        <Flex align="center" gap={10}>
          <Send size={18} aria-hidden="true" />
          <span>{isBackendApi ? '接口运行过程' : '浏览器运行过程'}</span>
        </Flex>
      }
      open={progress.open}
      size="large"
      mask={false}
      onClose={onClose}
      extra={
        <Space size={8}>
          <Button
            className="secondary-button"
            icon={<RefreshCw size={15} />}
            loading={isRerunning}
            disabled={!onRerun || progress.phase === 'running'}
            onClick={onRerun}
          >
            重新运行
          </Button>
          <Button onClick={onClose}>收起</Button>
        </Space>
      }
    >
      <div className="case-run-shell">
        <section className="case-run-overview">
          <Flex align="flex-start" justify="space-between" gap={16}>
            <div className="case-run-title-block">
              <Text className="case-run-kicker">当前用例</Text>
              <Title level={3}>{progress.caseTitle || '未命名接口用例'}</Title>
              <Text type={progress.phase === 'error' ? 'danger' : 'secondary'}>{progress.detail}</Text>
            </div>
            <Tag color={phaseColor(progress.phase)}>{phaseText(progress.phase)}</Tag>
          </Flex>

          <Progress
            percent={percent}
            status={progressStatus(progress.phase, failed)}
            showInfo={false}
          />

          <div className="case-run-metrics">
            <Metric label={isBackendApi ? '接口环境' : '前端环境'} value={progress.environment || '-'} />
            <Metric label="基础地址" value={progress.apiBaseUrl || '-'} />
            <Metric label="通过" value={String(passed)} tone="success" />
            <Metric label="失败" value={String(failed)} tone={failed > 0 ? 'danger' : undefined} />
          </div>
        </section>

        <div className="case-run-controls">
          <Segmented
            className="case-run-filter"
            value={stepFilter}
            onChange={(value) => setStepFilter(value as CaseRunStepFilter)}
            options={[
              { value: 'all', label: <FilterLabel text="全部" count={progress.steps.length} /> },
              {
                value: 'passed',
                label: <FilterLabel text={isBackendApi ? '正确接口' : '正确步骤'} count={passedSteps} />
              },
              {
                value: 'failed',
                label: <FilterLabel text={isBackendApi ? '错误接口' : '错误步骤'} count={failedSteps} />
              }
            ]}
          />
        </div>

        <div className="case-run-results">
          {progress.steps.length === 0 ? (
            <Empty className="case-run-empty" description="等待后端返回第一条请求" />
          ) : filteredSteps.length === 0 ? (
            <Empty className="case-run-empty" description={emptyFilterText(stepFilter, isBackendApi)} />
          ) : (
            <div className="case-run-step-list">
              {filteredSteps.map((step) => (
                <CaseRunStepItem key={step.stepId} step={step} isBackendApi={isBackendApi} />
              ))}
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
}

function FilterLabel({ text, count }: { text: string; count: number }) {
  return (
    <span className="case-run-filter-label">
      <span>{text}</span>
      <span className="case-run-filter-count">{count}</span>
    </span>
  );
}

function emptyFilterText(filter: CaseRunStepFilter, isBackendApi: boolean) {
  if (filter === 'passed') return isBackendApi ? '暂无正确接口' : '暂无正确步骤';
  if (filter === 'failed') return isBackendApi ? '暂无错误接口' : '暂无错误步骤';
  return '暂无运行结果';
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'success' | 'danger' }) {
  return (
    <div className={`case-run-metric ${tone ?? ''}`}>
      <Text type="secondary">{label}</Text>
      <Text strong title={value}>
        {value}
      </Text>
    </div>
  );
}

const CaseRunStepItem = memo(function CaseRunStepItem({
  step,
  isBackendApi
}: {
  step: CaseRunStepState;
  isBackendApi: boolean;
}) {
  const actionLabel = isBackendApi ? step.method : browserActionText(step.action);
  const formattedResponse = formatResponsePreview(step.responsePreview);
  return (
    <section className={`case-run-step ${step.status}`}>
      <Flex align="flex-start" justify="space-between" gap={12}>
        <Space align="start" size={10}>
          <span className={`case-run-step-icon ${step.status}`}>{statusIcon(step.status)}</span>
          <div className="case-run-step-copy">
            <Flex align="center" gap={8} wrap>
              <Tag className={`case-run-method ${actionLabel.toLowerCase()}`}>{actionLabel}</Tag>
              <Text strong>{step.label}</Text>
            </Flex>
            {step.url ? (
              <Paragraph className="case-run-url" copyable={{ text: step.url }}>
                {step.url}
              </Paragraph>
            ) : null}
            {!isBackendApi && step.selector ? <Text className="case-run-selector">{step.selector}</Text> : null}
            {isBackendApi && step.runtimeInferences?.length ? (
              <div className="case-run-inference-list">
                {step.runtimeInferences.map((inference) => (
                  <div
                    className={`case-run-inference ${inference.status}`}
                    key={`${step.stepId}-${inference.variable}`}
                  >
                    <BrainCircuit size={14} aria-hidden="true" />
                    <div className="case-run-inference-copy">
                      <Text strong>{inferenceTitle(inference)}</Text>
                      <Text type="secondary">{inferenceDetail(inference)}</Text>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Space>
        <Space className="case-run-step-meta" size={8} wrap>
          <Tag color={step.status === 'failed' ? 'red' : step.status === 'passed' ? 'green' : 'blue'}>
            {statusText(step)}
          </Tag>
          {isBackendApi ? <Tag>期望 {step.expectedStatus}</Tag> : null}
          {step.durationMs !== null ? (
            <Tag icon={<Clock3 size={12} aria-hidden="true" />}>{formatDuration(step.durationMs)}</Tag>
          ) : null}
        </Space>
      </Flex>

      {step.error ? <Text type="danger">{step.error}</Text> : null}
      {!isBackendApi && step.pageUrl ? (
        <Paragraph className="case-run-url" copyable={{ text: step.pageUrl }}>
          当前页面：{step.pageUrl}
        </Paragraph>
      ) : null}
      {!isBackendApi && step.screenshotDataUrl ? (
        <Image
          className="case-run-screenshot"
          src={step.screenshotDataUrl}
          alt={`${step.label} 截图`}
          preview={false}
        />
      ) : null}
      {formattedResponse ? (
        <pre className="case-run-response">
          {step.responseContentType ? `# ${step.responseContentType}\n` : ''}
          {formattedResponse.text}
        </pre>
      ) : null}
    </section>
  );
});

function statusIcon(status: CaseRunStepState['status']) {
  if (status === 'passed') return <CheckCircle2 size={18} aria-hidden="true" />;
  if (status === 'failed') return <XCircle size={18} aria-hidden="true" />;
  if (status === 'running') return <LoaderCircle size={18} aria-hidden="true" />;
  return <CircleAlert size={18} aria-hidden="true" />;
}

function statusText(step: CaseRunStepState) {
  if (step.status === 'running') return '请求中';
  if (step.status === 'passed') return `通过 ${step.statusCode ?? ''}`.trim();
  if (step.status === 'failed') return step.statusCode ? `失败 ${step.statusCode}` : '失败';
  return '待执行';
}

function inferenceTitle(inference: NonNullable<CaseRunStepState['runtimeInferences']>[number]) {
  if (inference.status === 'running') return `AI 正在推导 ${inference.variable}`;
  if (inference.status === 'failed') return `AI 未能推导 ${inference.variable}`;
  const confidence = inference.confidence !== null ? ` · ${Math.round(inference.confidence * 100)}%` : '';
  return `AI 已推导 ${inference.variable}${confidence}`;
}

function inferenceDetail(inference: NonNullable<CaseRunStepState['runtimeInferences']>[number]) {
  if (inference.status === 'running') return inference.message || '正在读取前序响应和当前步骤契约';
  const source = inference.sourceStepLabel ? `来源：${inference.sourceStepLabel}` : '来源：前序响应';
  const path = inference.sourceJsonPath ? `；路径：${inference.sourceJsonPath}` : '';
  const reason = inference.reason ? `；${inference.reason}` : '';
  return `${source}${path}${reason}`;
}

function browserActionText(action: string | null) {
  const labels: Record<string, string> = {
    goto: '打开',
    fill: '填写',
    click: '点击',
    expect_visible: '可见',
    expect_not_visible: '隐藏',
    expect_text: '文本'
  };
  return labels[action ?? ''] ?? '动作';
}

function phaseText(phase: CaseRunProgressState['phase']) {
  if (phase === 'running') return '运行中';
  if (phase === 'complete') return '已完成';
  if (phase === 'error') return '异常';
  return '未运行';
}

function phaseColor(phase: CaseRunProgressState['phase']) {
  if (phase === 'running') return 'processing';
  if (phase === 'complete') return 'success';
  if (phase === 'error') return 'error';
  return 'default';
}

function progressStatus(phase: CaseRunProgressState['phase'], failed: number) {
  if (phase === 'error' || failed > 0) return 'exception';
  if (phase === 'complete') return 'success';
  return 'normal';
}

function formatDuration(value: number) {
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}
