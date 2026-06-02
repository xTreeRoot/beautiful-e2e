import { Button, Typography } from 'antd';

import type { NodeTemplate } from '../types/workbench';

const { Text } = Typography;

type NodeToolboxProps = {
  templates: NodeTemplate[];
  onSelect: (template: NodeTemplate) => void;
};

export function NodeToolbox({ templates, onSelect }: NodeToolboxProps) {
  return (
    <>
      <Text className="node-toolbox-title" strong>
        节点工具箱
      </Text>
      <div className="node-toolbox-grid">
        {templates.map((template) => {
          const Icon = template.icon;
          return (
            <Button
              key={template.kind}
              className="node-toolbox-button"
              icon={<Icon size={16} aria-hidden="true" />}
              onClick={() => onSelect(template)}
            >
              {template.label}
            </Button>
          );
        })}
      </div>
    </>
  );
}
