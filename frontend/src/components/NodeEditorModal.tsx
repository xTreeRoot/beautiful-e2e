import { useEffect, useMemo, useState } from 'react';
import {
  Button as AntButton,
  Flex,
  Input as AntInput,
  Modal,
  Select as AntSelect,
  Tabs,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import { Braces, Link2, PlugZap, Save, Trash2, Workflow } from 'lucide-react';

import { EditorField } from './EditorField';
import { NodeDebugPanel } from './NodeDebugPanel';
import type { TestCase } from '../api';
import { withNodeDebugDraft } from '../lib/nodeDebug';
import type {
  CanvasNode,
  CanvasNodeData,
  CaseRunProgressState,
  ExecutionMode,
  NodeDebugDraft
} from '../types/workbench';

const { Text } = Typography;

const httpMethodOptions = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'].map(
  (method) => ({ label: method, value: method })
);

type NodeEditorModalProps = {
  open: boolean;
  node: CanvasNode | null;
  selectedCase?: TestCase;
  executionMode: ExecutionMode;
  caseRunProgress: CaseRunProgressState;
  isRunning: boolean;
  isSaving: boolean;
  onClose: () => void;
  onSave: () => boolean | void | Promise<boolean | void>;
  onUpdate: (patch: Partial<CanvasNodeData>) => void;
  onDelete: () => void;
  onDebug: (node: CanvasNode, draft: NodeDebugDraft) => void;
};

export function NodeEditorModal({
  open,
  node,
  selectedCase,
  executionMode,
  caseRunProgress,
  isRunning,
  isSaving,
  onClose,
  onSave,
  onUpdate,
  onDelete,
  onDebug
}: NodeEditorModalProps) {
  const [metadataDraft, setMetadataDraft] = useState('{}');
  const [metadataError, setMetadataError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !node) {
      setMetadataDraft('{}');
      setMetadataError(null);
      return;
    }
    setMetadataDraft(JSON.stringify(node.data.metadata ?? {}, null, 2));
    setMetadataError(null);
  }, [node?.id, open]);

  const isApiRequest = node?.data.action === 'api_request' || node?.data.kind === 'api';
  const usesUrl = isApiRequest || node?.data.action === 'goto';

  const title = useMemo(() => {
    if (!node) return '节点属性';
    return (
      <Flex className="node-editor-modal-title" align="center" gap={8}>
        <Workflow size={17} aria-hidden="true" />
        <span>节点属性</span>
        <Tag>{node.data.kind}</Tag>
      </Flex>
    );
  }, [node]);

  if (!node) return null;
  const activeNode = node;

  function handleTargetChange(value: string) {
    if (usesUrl) {
      onUpdate({ target_url: value });
      return;
    }
    onUpdate({ selector: value });
  }

  function handleMetadataChange(value: string) {
    setMetadataDraft(value);
    const trimmed = value.trim();
    if (!trimmed) {
      setMetadataError(null);
      onUpdate({ metadata: null });
      return;
    }
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setMetadataError('扩展数据必须是 JSON 对象');
        return;
      }
      setMetadataError(null);
      onUpdate({ metadata: parsed as Record<string, unknown> });
    } catch {
      setMetadataError('JSON 格式不正确');
    }
  }

  function handleDebug(draft: NodeDebugDraft) {
    onUpdate({ metadata: withNodeDebugDraft(activeNode, draft).data.metadata });
    onDebug(activeNode, draft);
  }

  async function handleSaveAndClose() {
    if (metadataError) return;
    const saved = await onSave();
    if (saved !== false) {
      onClose();
    }
  }

  const editorPanel = (
    <div className="node-editor-modal">
      <section className="node-editor-modal-section">
        <Flex className="section-title" align="center" gap={8}>
          <Workflow size={17} aria-hidden="true" />
          <Text strong>基础信息</Text>
        </Flex>
        <div className="node-editor-modal-grid">
          <EditorField
            label="类型"
            value={node.data.kind}
            onChange={(value) => onUpdate({ kind: value })}
          />
          <EditorField
            label="名称"
            value={node.data.label}
            onChange={(value) => onUpdate({ label: value })}
          />
          <EditorField
            label="动作"
            value={node.data.action ?? ''}
            onChange={(value) => onUpdate({ action: value })}
          />
          <EditorField
            label={isApiRequest ? '期望状态' : '期望'}
            value={node.data.expected ?? ''}
            onChange={(value) => onUpdate({ expected: value })}
          />
          <EditorField
            label="说明"
            value={node.data.description ?? ''}
            onChange={(value) => onUpdate({ description: value })}
            full
            multiline
            rows={2}
            maxRows={6}
          />
        </div>
      </section>

      <section className="node-editor-modal-section">
        <Flex className="section-title" align="center" gap={8}>
          {isApiRequest ? <PlugZap size={17} aria-hidden="true" /> : <Link2 size={17} aria-hidden="true" />}
          <Text strong>{isApiRequest ? '接口请求' : '前端动作'}</Text>
        </Flex>
        <div className="node-editor-modal-grid">
          {isApiRequest ? (
            <div className="control-field">
              <Text className="field-label">请求方法</Text>
              <AntSelect
                value={(node.data.method || 'GET').toUpperCase()}
                options={httpMethodOptions}
                onChange={(method) => onUpdate({ method })}
              />
            </div>
          ) : null}
          <EditorField
            label={usesUrl ? '地址 URL' : '选择器'}
            value={(usesUrl ? node.data.target_url : node.data.selector) ?? ''}
            onChange={handleTargetChange}
            full={!isApiRequest}
          />
          <EditorField
            label={isApiRequest ? '请求体 JSON / 文本' : '输入值'}
            value={node.data.value ?? ''}
            onChange={(value) => onUpdate({ value })}
            full
            multiline={isApiRequest}
            rows={isApiRequest ? 7 : 3}
            maxRows={18}
            monospace={isApiRequest}
          />
        </div>
      </section>

      <section className="node-editor-modal-section">
        <Flex className="section-title" align="center" gap={8}>
          <Braces size={17} aria-hidden="true" />
          <Text strong>扩展数据</Text>
          {metadataError ? <Text type="danger">{metadataError}</Text> : null}
        </Flex>
        <AntInput.TextArea
          className="node-metadata-editor"
          value={metadataDraft}
          status={metadataError ? 'error' : undefined}
          autoSize={{ minRows: 7, maxRows: 18 }}
          onChange={(event) => handleMetadataChange(event.target.value)}
        />
      </section>
    </div>
  );

  return (
    <Modal
      className="node-editor-modal-shell"
      rootClassName="node-editor-modal-root"
      title={title}
      open={open}
      onCancel={onClose}
      centered
      width="min(1680px, calc(100vw - 48px))"
      footer={
        <Flex align="center" justify="space-between" gap={12}>
          <Tooltip title="删除选中节点">
            <AntButton danger icon={<Trash2 size={16} />} onClick={onDelete}>
              删除节点
            </AntButton>
          </Tooltip>
          <AntButton
            type="primary"
            icon={<Save size={16} />}
            loading={isSaving}
            disabled={Boolean(metadataError)}
            onClick={() => void handleSaveAndClose()}
          >
            保存并关闭
          </AntButton>
        </Flex>
      }
    >
      <Tabs
        className="node-editor-tabs"
        items={[
          { key: 'editor', label: '节点配置', children: editorPanel },
          {
            key: 'debug',
            label: '单节点调试',
            children: (
              <NodeDebugPanel
                node={node}
                selectedCase={selectedCase}
                executionMode={executionMode}
                progress={caseRunProgress}
                isRunning={isRunning}
                onDebug={handleDebug}
              />
            )
          }
        ]}
      />
    </Modal>
  );
}
