import { Button, Input, Modal, Select, Typography } from 'antd';
import { Save } from 'lucide-react';

import type { Group } from '../../api';

const { Text } = Typography;

const caseStatusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'ready', label: '就绪' },
  { value: 'archived', label: '已归档' }
];

type CaseEditModalProps = {
  open: boolean;
  groups: Group[];
  title: string;
  description: string;
  groupId: string | null;
  priority: string;
  status: string;
  loading: boolean;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onGroupIdChange: (value: string | null) => void;
  onPriorityChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onCancel: () => void;
  onSave: () => void;
};

export function CaseEditModal({
  open,
  groups,
  title,
  description,
  groupId,
  priority,
  status,
  loading,
  onTitleChange,
  onDescriptionChange,
  onGroupIdChange,
  onPriorityChange,
  onStatusChange,
  onCancel,
  onSave
}: CaseEditModalProps) {
  return (
    <Modal
      title="编辑用例"
      open={open}
      onCancel={onCancel}
      width={600}
      footer={[
        <Button key="cancel" className="secondary-button" onClick={onCancel}>
          取消
        </Button>,
        <Button key="save" type="primary" className="primary-button" icon={<Save size={16} />} loading={loading} onClick={onSave}>
          保存
        </Button>
      ]}
    >
      <div className="modal-form-grid">
        <div className="control-field">
          <Text className="field-label">用例名称</Text>
          <Input value={title} onChange={(event) => onTitleChange(event.target.value)} />
        </div>
        <div className="control-field">
          <Text className="field-label">说明</Text>
          <Input.TextArea
            value={description}
            autoSize={{ minRows: 2, maxRows: 5 }}
            onChange={(event) => onDescriptionChange(event.target.value)}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">分组</Text>
          <Select
            value={groupId ?? 'ungrouped'}
            onChange={(value) => onGroupIdChange(value === 'ungrouped' ? null : value)}
            options={[
              { value: 'ungrouped', label: '未分组' },
              ...groups.map((group) => ({ value: group.id, label: group.name }))
            ]}
          />
        </div>
        <div className="modal-form-row">
          <div className="control-field">
            <Text className="field-label">优先级</Text>
            <Select value={priority} onChange={onPriorityChange} options={['P0', 'P1', 'P2', 'P3'].map((value) => ({ value, label: value }))} />
          </div>
          <div className="control-field">
            <Text className="field-label">状态</Text>
            <Select value={status} onChange={onStatusChange} options={caseStatusOptions} />
          </div>
        </div>
      </div>
    </Modal>
  );
}
