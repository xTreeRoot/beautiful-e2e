import { Button, Flex, Layout, Space, Tooltip, Typography } from 'antd';
import { Bot, Braces, CirclePlay, History, RefreshCw, Save, Sparkles } from 'lucide-react';

import type { Group, TestCase } from '../../api';
import type { ExecutionMode } from '../../types/workbench';

const { Header } = Layout;
const { Text, Title } = Typography;

type WorkspaceTopbarProps = {
  executionMode: ExecutionMode;
  activeGroup?: Group;
  selectedCase?: TestCase;
  status: string;
  offlineMode: boolean;
  isGenerating: boolean;
  isSaving: boolean;
  isRunningCase: boolean;
  hasCaseRunSnapshot: boolean;
  onGenerate: () => void;
  onOpenAiConfig: () => void;
  onSaveCanvas: () => void;
  onRunCase: () => void;
  onOpenCaseRunSnapshot: () => void;
  onOpenDsl: () => void;
};

export function WorkspaceTopbar({
  executionMode,
  activeGroup,
  selectedCase,
  status,
  offlineMode,
  isGenerating,
  isSaving,
  isRunningCase,
  hasCaseRunSnapshot,
  onGenerate,
  onOpenAiConfig,
  onSaveCanvas,
  onRunCase,
  onOpenCaseRunSnapshot,
  onOpenDsl
}: WorkspaceTopbarProps) {
  const normalizedStatus = status.trim();
  const isInitialBackendStatus = /^后端已连接：[^；]+$/.test(normalizedStatus);
  const shouldShowStatus = normalizedStatus.length > 0 && !isInitialBackendStatus;
  const generateLabel = selectedCase ? '重新生成' : '生成';

  return (
    <Header className="topbar">
      <Flex align="center" justify="space-between" gap={16} className="topbar-inner">
        <div className="topbar-copy">
          <Text className="topbar-meta">
            {executionMode === 'backend_api' ? '纯后端接口模式' : '前后端配合模式'} ·{' '}
            {activeGroup?.name ?? '测试分组'}
          </Text>
          <Title level={1}>{selectedCase?.title ?? '自然语言生成 E2E 回归用例'}</Title>
          {shouldShowStatus ? (
            <Text className="topbar-status" type={offlineMode ? 'warning' : 'secondary'}>
              {normalizedStatus}
            </Text>
          ) : null}
        </div>
        <Space className="topbar-actions" size={10} wrap>
          <Tooltip title="刷新用例">
            <Button className="icon-button" aria-label="刷新用例" icon={<RefreshCw size={18} />} />
          </Tooltip>
          <Button
            type="primary"
            className="primary-button"
            icon={<Sparkles size={18} />}
            loading={isGenerating}
            onClick={onGenerate}
          >
            {generateLabel}
          </Button>
          <Button className="secondary-button" icon={<Bot size={18} />} onClick={onOpenAiConfig}>
            AI 配置
          </Button>
          <Button className="secondary-button" icon={<Save size={18} />} loading={isSaving} onClick={onSaveCanvas}>
            保存
          </Button>
          <Button
            className="run-button"
            icon={<CirclePlay size={18} />}
            loading={isRunningCase}
            onClick={onRunCase}
          >
            {executionMode === 'backend_api' ? '运行接口' : '运行流程'}
          </Button>
          <Tooltip title={hasCaseRunSnapshot ? '打开上次运行历史（快照）' : '暂无运行历史'}>
            <Button
              className="secondary-button"
              icon={<History size={18} />}
              disabled={!hasCaseRunSnapshot}
              onClick={onOpenCaseRunSnapshot}
            >
              上次快照
            </Button>
          </Tooltip>
          <Button className="secondary-button" icon={<Braces size={18} />} onClick={onOpenDsl}>
            打开 DSL
          </Button>
        </Space>
      </Flex>
    </Header>
  );
}
