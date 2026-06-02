import { Input, Typography } from 'antd';

const { Text } = Typography;

type EditorFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  full?: boolean;
  multiline?: boolean;
  rows?: number;
  maxRows?: number;
  monospace?: boolean;
};

export function EditorField({
  label,
  value,
  onChange,
  full,
  multiline,
  rows,
  maxRows,
  monospace
}: EditorFieldProps) {
  const className = [
    'control-field',
    full ? 'editor-field-full' : '',
    multiline ? 'editor-field-multiline' : '',
    monospace ? 'editor-field-monospace' : ''
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={className}>
      <Text className="field-label">{label}</Text>
      {multiline ? (
        <Input.TextArea
          value={value}
          autoSize={{ minRows: rows ?? 4, maxRows: maxRows ?? 10 }}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <Input value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </div>
  );
}
