import { Button, Modal, Typography, message as AntMessage } from 'antd';
import { Clipboard, X } from 'lucide-react';
import { useMemo } from 'react';

import type { TestCase } from '../../api';

const { Text } = Typography;

type DslPreviewModalProps = {
  open: boolean;
  selectedCase?: TestCase;
  canvasDsl: unknown;
  onClose: () => void;
};

export function DslPreviewModal({
  open,
  selectedCase,
  canvasDsl,
  onClose
}: DslPreviewModalProps) {
  const dslJson = useMemo(() => JSON.stringify(canvasDsl, null, 2), [canvasDsl]);

  async function handleCopyDsl() {
    try {
      await navigator.clipboard.writeText(dslJson);
      void AntMessage.success('DSL JSON 已复制');
    } catch {
      void AntMessage.error('复制失败，请手动选中 JSON 复制');
    }
  }

  return (
    <Modal
      className="dsl-preview-modal"
      title={
        <div className="dsl-preview-title">
          <Text className="field-label">DSL JSON</Text>
          <Text strong>{selectedCase?.title ?? '未选择用例'}</Text>
        </div>
      }
      open={open}
      width={960}
      onCancel={onClose}
      footer={[
        <Button key="close" className="secondary-button" icon={<X size={16} />} onClick={onClose}>
          关闭
        </Button>,
        <Button
          key="copy"
          type="primary"
          className="primary-button"
          icon={<Clipboard size={16} />}
          onClick={() => void handleCopyDsl()}
        >
          复制 JSON
        </Button>
      ]}
    >
      <pre className="dsl-preview-code">{dslJson}</pre>
    </Modal>
  );
}
