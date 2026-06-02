import { AutoComplete, Button, Input, Typography } from 'antd';
import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  COMMON_REQUEST_HEADER_OPTIONS,
  defaultRequestHeaderValue,
  jsonObjectTextError,
  requestHeaderRowsFromJson,
  requestHeadersJsonFromRows,
  type RequestHeaderRow
} from '../../lib/projectEnvironments';

const { Text } = Typography;

const emptyHeaderRow: RequestHeaderRow = { key: '', value: '' };

export function RequestHeadersEditor({
  value,
  onChange
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const error = jsonObjectTextError(value);
  const parsedRows = useMemo(() => requestHeaderRowsFromJson(value), [value]);
  const [draftRows, setDraftRows] = useState<RequestHeaderRow[]>([
    { ...emptyHeaderRow }
  ]);

  useEffect(() => {
    if (error) return;
    setDraftRows(parsedRows.length ? parsedRows : [{ ...emptyHeaderRow }]);
  }, [error, parsedRows]);

  const headerOptions = useMemo(() => {
    const optionMap = new Map(COMMON_REQUEST_HEADER_OPTIONS.map((item) => [item.value, item]));
    for (const row of draftRows) {
      const key = row.key.trim();
      if (key && !optionMap.has(key)) {
        optionMap.set(key, { value: key, label: key });
      }
    }
    return Array.from(optionMap.values());
  }, [draftRows]);

  function commitRows(nextRows: RequestHeaderRow[]) {
    setDraftRows(nextRows.length ? nextRows : [{ ...emptyHeaderRow }]);
    onChange(requestHeadersJsonFromRows(nextRows));
  }

  function updateRow(index: number, patch: Partial<RequestHeaderRow>) {
    const nextRows = draftRows.map((row, rowIndex) => {
      if (rowIndex !== index) return row;
      const nextRow = { ...row, ...patch };
      if (patch.key && !row.value) {
        nextRow.value = defaultRequestHeaderValue(patch.key);
      }
      return nextRow;
    });
    commitRows(nextRows);
  }

  function addRow() {
    setDraftRows((current) => [...current, { ...emptyHeaderRow }]);
  }

  function removeRow(index: number) {
    commitRows(draftRows.filter((_, rowIndex) => rowIndex !== index));
  }

  if (error) {
    return (
      <div className="request-headers-editor">
        <Text type="danger" className="json-field-error">
          请求头 {error}
        </Text>
        <Button className="secondary-button request-header-add" onClick={() => onChange('{}')}>
          重置请求头
        </Button>
      </div>
    );
  }

  return (
    <div className="request-headers-editor">
      {draftRows.map((row, index) => (
        <div className="request-header-row" key={`${row.key}-${index}`}>
          <AutoComplete
            className="request-header-key"
            value={row.key}
            options={headerOptions}
            onChange={(nextKey) => updateRow(index, { key: nextKey })}
            filterOption={(input, option) =>
              String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            }
            placeholder="请求头名称"
          />
          <Input
            value={row.value}
            onChange={(event) => updateRow(index, { value: event.target.value })}
            placeholder="请求头值"
          />
          <Button
            aria-label="删除请求头"
            className="secondary-button request-header-remove"
            icon={<Trash2 size={15} />}
            onClick={() => removeRow(index)}
          />
        </div>
      ))}
      <Button
        className="secondary-button request-header-add"
        icon={<Plus size={15} />}
        onClick={addRow}
      >
        添加请求头
      </Button>
    </div>
  );
}
