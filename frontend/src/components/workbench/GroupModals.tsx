import { Button, Input, Modal, Typography } from 'antd';
import { Plus, Save } from 'lucide-react';

const { Text } = Typography;

type GroupFormModalProps = {
  open: boolean;
  title: string;
  name: string;
  description: string;
  loading: boolean;
  submitLabel: string;
  submitIcon: 'plus' | 'save';
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function GroupFormModal({
  open,
  title,
  name,
  description,
  loading,
  submitLabel,
  submitIcon,
  onNameChange,
  onDescriptionChange,
  onCancel,
  onSubmit
}: GroupFormModalProps) {
  const Icon = submitIcon === 'plus' ? Plus : Save;
  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      width={520}
      footer={[
        <Button key="cancel" className="secondary-button" onClick={onCancel}>
          取消
        </Button>,
        <Button key="submit" type="primary" className="primary-button" icon={<Icon size={16} />} loading={loading} onClick={onSubmit}>
          {submitLabel}
        </Button>
      ]}
    >
      <div className="modal-form-grid">
        <div className="control-field">
          <Text className="field-label">分组名称</Text>
          <Input value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="例如：核心链路组" />
        </div>
        <div className="control-field">
          <Text className="field-label">说明</Text>
          <Input value={description} onChange={(event) => onDescriptionChange(event.target.value)} placeholder="可选" />
        </div>
      </div>
    </Modal>
  );
}
