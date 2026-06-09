const MAX_NESTED_JSON_DEPTH = 3;

export type FormattedResponsePreview = {
  text: string;
  isJson: boolean;
};

/**
 * 格式化请求或响应中的 JSON 文本。
 * 调试链路里可能收到被上游额外转义的一层 JSON，展示层只解析有限层数，避免误伤普通文本。
 */
export function formatJsonText(value: string): string | null {
  const parsed = parseJsonLikeText(value);
  if (parsed === null) return null;
  return JSON.stringify(parsed, null, 2);
}

/**
 * 把后端返回的响应预览转换为可展示文本。
 * 非 JSON 内容保持原样，确保文本、HTML 或错误页仍能直接排查。
 */
export function formatResponsePreview(value?: string): FormattedResponsePreview | null {
  if (!value) return null;
  const formatted = formatJsonText(value);
  if (formatted === null) return { text: value, isJson: false };
  return { text: formatted, isJson: true };
}

function parseJsonLikeText(value: string, depth = 0): unknown | null {
  const trimmed = value.trim();
  if (!trimmed) return '';

  for (const candidate of jsonTextCandidates(trimmed)) {
    const parsed = tryParseJson(candidate);
    if (!parsed.ok) continue;

    if (typeof parsed.value === 'string' && depth < MAX_NESTED_JSON_DEPTH) {
      const nestedValue = parsed.value.trim();
      if (looksLikeJsonContainer(nestedValue)) {
        const nestedParsed = parseJsonLikeText(nestedValue, depth + 1);
        if (nestedParsed !== null) return nestedParsed;
      }
    }

    return parsed.value;
  }

  return null;
}

function jsonTextCandidates(value: string): string[] {
  const candidates = [value];
  const normalized = normalizeEscapedJsonContainer(value);
  if (normalized && normalized !== value) candidates.push(normalized);
  return candidates;
}

function normalizeEscapedJsonContainer(value: string): string | null {
  if (!looksLikeJsonContainer(value) || !value.includes('\\"')) return null;
  return value.replace(/\\"/g, '"');
}

function looksLikeJsonContainer(value: string): boolean {
  return (
    (value.startsWith('{') && value.endsWith('}')) ||
    (value.startsWith('[') && value.endsWith(']'))
  );
}

function tryParseJson(value: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(value) as unknown };
  } catch {
    return { ok: false };
  }
}
