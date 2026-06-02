import { Button, Input, Modal, Segmented, Select, Space, Typography } from 'antd';
import { FilePlus2, Sparkles } from 'lucide-react';

import type { Group } from '../../api';
import type { CaseCreateMode } from '../../types/workbench';

const { Text } = Typography;

type CaseCreateModalProps = {
  open: boolean;
  mode: CaseCreateMode;
  groups: Group[];
  title: string;
  description: string;
  groupId: string | null;
  priority: string;
  loading: boolean;
  onModeChange: (mode: CaseCreateMode) => void;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onGroupIdChange: (value: string | null) => void;
  onPriorityChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function CaseCreateModal({
  open,
  mode,
  groups,
  title,
  description,
  groupId,
  priority,
  loading,
  onModeChange,
  onTitleChange,
  onDescriptionChange,
  onGroupIdChange,
  onPriorityChange,
  onCancel,
  onSubmit
}: CaseCreateModalProps) {
  const isAiMode = mode === 'ai';
  const SubmitIcon = isAiMode ? Sparkles : FilePlus2;

  return (
    <Modal
      title="新建用例"
      open={open}
      onCancel={onCancel}
      width={640}
      className="case-create-modal"
      footer={[
        <Button key="cancel" className="secondary-button" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          className="primary-button"
          icon={<SubmitIcon size={16} />}
          loading={loading}
          onClick={onSubmit}
        >
          {isAiMode ? 'AI 生成用例' : '创建空白用例'}
        </Button>
      ]}
    >
      <div className="modal-form-grid">
        <Segmented
          block
          className="mode-switch case-create-mode"
          value={mode}
          onChange={(value) => onModeChange(value as CaseCreateMode)}
          options={[
            {
              value: 'blank',
              label: (
                <Space size={6}>
                  <FilePlus2 size={16} aria-hidden="true" />
                  <span>空白新建</span>
                </Space>
              )
            },
            {
              value: 'ai',
              label: (
                <Space size={6}>
                  <Sparkles size={16} aria-hidden="true" />
                  <span>AI 生成</span>
                </Space>
              )
            }
          ]}
        />
        <div className="control-field">
          <Text className="field-label">用例名称</Text>
          <Input
            aria-label="用例名称"
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">说明</Text>
          <Input.TextArea
            aria-label="说明"
            value={description}
            autoSize={{ minRows: isAiMode ? 4 : 2, maxRows: 7 }}
            onChange={(event) => onDescriptionChange(event.target.value)}
          />
        </div>
        <div className="modal-form-row">
          <div className="control-field">
            <Text className="field-label">分组</Text>
            <Select
              aria-label="分组"
              value={groupId ?? 'ungrouped'}
              onChange={(value) => onGroupIdChange(value === 'ungrouped' ? null : value)}
              options={[
                { value: 'ungrouped', label: '未分组' },
                ...groups.map((group) => ({ value: group.id, label: group.name }))
              ]}
            />
          </div>
          <div className="control-field">
            <Text className="field-label">优先级</Text>
            <Select
              aria-label="优先级"
              value={priority}
              onChange={onPriorityChange}
              options={['P0', 'P1', 'P2', 'P3'].map((value) => ({ value, label: value }))}
            />
          </div>
        </div>
      </div>
    </Modal>
  );
}
