import type { ProjectSettings } from '../api';

export type ProjectEnvironment = {
  key: string;
  name: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
};

export type ProjectEnvironmentState = {
  environments: ProjectEnvironment[];
  activeFrontendEnvironmentKey: string;
  activeApiEnvironmentKey: string;
  activeFrontendEnvironment: ProjectEnvironment;
  activeApiEnvironment: ProjectEnvironment;
};

export const DEFAULT_FRONTEND_BASE_URL = 'http://localhost:5173';
export const DEFAULT_API_BASE_URL = 'http://localhost:8000';
export const DEFAULT_ENVIRONMENT_KEY = 'local';

export const COMMON_REQUEST_HEADER_OPTIONS = [
  { value: 'Authorization', label: 'Authorization' },
  { value: 'Content-Type', label: 'Content-Type' },
  { value: 'Accept', label: 'Accept' },
  { value: 'Accept-Language', label: 'Accept-Language' },
  { value: 'Cookie', label: 'Cookie' },
  { value: 'User-Agent', label: 'User-Agent' },
  { value: 'X-Request-Id', label: 'X-Request-Id' },
  { value: 'X-Trace-Id', label: 'X-Trace-Id' },
  { value: 'X-Tenant-Id', label: 'X-Tenant-Id' },
  { value: 'X-User-Id', label: 'X-User-Id' },
  { value: 'X-CSRF-Token', label: 'X-CSRF-Token' },
  { value: 'X-API-Key', label: 'X-API-Key' }
];

export const DEFAULT_PROJECT_ENVIRONMENTS: ProjectEnvironment[] = [
  {
    key: DEFAULT_ENVIRONMENT_KEY,
    name: '本地',
    baseUrl: DEFAULT_FRONTEND_BASE_URL,
    apiBaseUrl: DEFAULT_API_BASE_URL,
    requestHeadersJson: '{}'
  },
  { key: 'dev', name: '开发', baseUrl: '', apiBaseUrl: '', requestHeadersJson: '{}' },
  { key: 'test', name: '测试', baseUrl: '', apiBaseUrl: '', requestHeadersJson: '{}' },
  { key: 'staging', name: '预发', baseUrl: '', apiBaseUrl: '', requestHeadersJson: '{}' },
  { key: 'prod', name: '生产', baseUrl: '', apiBaseUrl: '', requestHeadersJson: '{}' }
];

export function normalizeProjectEnvironments(
  settings: ProjectSettings | null | undefined
): ProjectEnvironmentState {
  const configuredEnvironments = Array.isArray(settings?.environments) ? settings.environments : [];
  const hasConfiguredEnvironments = configuredEnvironments.length > 0;
  const environmentsByKey = new Map<string, ProjectEnvironment>(
    DEFAULT_PROJECT_ENVIRONMENTS.map((environment) => [environment.key, { ...environment }])
  );

  if (!hasConfiguredEnvironments) {
    environmentsByKey.set(DEFAULT_ENVIRONMENT_KEY, {
      ...DEFAULT_PROJECT_ENVIRONMENTS[0],
      baseUrl: stringValue(settings?.base_url) ?? DEFAULT_FRONTEND_BASE_URL,
      apiBaseUrl: stringValue(settings?.api_base_url) ?? DEFAULT_API_BASE_URL
    });
  }

  configuredEnvironments.forEach((rawEnvironment, index) => {
    const environment = normalizeEnvironment(rawEnvironment, index);
    if (!environment) return;
    environmentsByKey.set(environment.key, environment);
  });

  const environments = Array.from(environmentsByKey.values());
  const legacyActiveKey =
    stringValue(settings?.active_environment) ??
    stringValue(settings?.environment) ??
    DEFAULT_ENVIRONMENT_KEY;
  const activeFrontendEnvironmentKey = resolveEnvironmentKey(
    environments,
    stringValue(settings?.active_frontend_environment) ?? legacyActiveKey
  );
  const activeApiEnvironmentKey = resolveEnvironmentKey(
    environments,
    stringValue(settings?.active_api_environment) ??
      stringValue(settings?.active_backend_environment) ??
      legacyActiveKey
  );
  const activeFrontendEnvironment =
    environments.find((environment) => environment.key === activeFrontendEnvironmentKey) ??
    DEFAULT_PROJECT_ENVIRONMENTS[0];
  const activeApiEnvironment =
    environments.find((environment) => environment.key === activeApiEnvironmentKey) ??
    DEFAULT_PROJECT_ENVIRONMENTS[0];

  return {
    environments,
    activeFrontendEnvironmentKey,
    activeApiEnvironmentKey,
    activeFrontendEnvironment,
    activeApiEnvironment
  };
}

export function updateEnvironmentUrls(
  environments: ProjectEnvironment[],
  activeEnvironmentKey: string,
  patch: Partial<Pick<ProjectEnvironment, 'baseUrl' | 'apiBaseUrl' | 'requestHeadersJson'>>
): ProjectEnvironment[] {
  let updated = false;
  const next = environments.map((environment) => {
    if (environment.key !== activeEnvironmentKey) return environment;
    updated = true;
    return { ...environment, ...patch };
  });

  if (updated) return next;
  return [
    ...next,
    {
      key: activeEnvironmentKey,
      name: activeEnvironmentKey,
      baseUrl: patch.baseUrl ?? '',
      apiBaseUrl: patch.apiBaseUrl ?? '',
      requestHeadersJson: patch.requestHeadersJson ?? '{}'
    }
  ];
}

export function environmentSettingsPatch(
  environments: ProjectEnvironment[],
  activeFrontendEnvironmentKey: string,
  activeApiEnvironmentKey: string
): ProjectSettings {
  const normalized = environments.length ? environments : DEFAULT_PROJECT_ENVIRONMENTS;
  const activeFrontendEnvironment =
    normalized.find((environment) => environment.key === activeFrontendEnvironmentKey) ?? normalized[0];
  const activeApiEnvironment =
    normalized.find((environment) => environment.key === activeApiEnvironmentKey) ?? normalized[0];

  return {
    active_environment:
      activeFrontendEnvironment.key === activeApiEnvironment.key
        ? activeFrontendEnvironment.key
        : `${activeFrontendEnvironment.key}/${activeApiEnvironment.key}`,
    active_frontend_environment: activeFrontendEnvironment.key,
    active_api_environment: activeApiEnvironment.key,
    base_url: activeFrontendEnvironment.baseUrl.trim(),
    api_base_url: activeApiEnvironment.apiBaseUrl.trim(),
    environments: normalized.map((environment) => ({
      key: environment.key,
      name: environment.name,
      base_url: environment.baseUrl.trim(),
      api_base_url: environment.apiBaseUrl.trim(),
      request_headers: parseJsonObjectText(environment.requestHeadersJson)
    }))
  };
}

/**
 * 校验每个接口环境绑定的 JSON 字段。
 * 请求头必须保持对象结构，因为 Playwright 会在每次请求前按键合并。
 */
export function firstEnvironmentJsonError(environments: ProjectEnvironment[]): string | null {
  for (const environment of environments) {
    const headersError = jsonObjectTextError(environment.requestHeadersJson);
    if (headersError) return `${environment.name} 请求头 ${headersError}`;
  }
  return null;
}

export function jsonObjectTextError(value: string): string | null {
  try {
    parseJsonObjectText(value);
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : '格式有误';
  }
}

export function parseJsonObjectText(value: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value.trim() || '{}');
  } catch {
    throw new Error('格式有误');
  }
  if (!isPlainObject(parsed)) {
    throw new Error('必须是 JSON 对象');
  }
  return parsed;
}

export function requestHeaderKeysFromJson(value: string): string[] {
  try {
    return Object.keys(parseJsonObjectText(value));
  } catch {
    return [];
  }
}

export function updateRequestHeaderKeysJson(value: string, keys: string[]): string {
  const currentHeaders = parseJsonObjectText(value);
  const nextHeaders = Object.fromEntries(
    uniqueHeaderKeys(keys).map((key) => [
      key,
      Object.prototype.hasOwnProperty.call(currentHeaders, key)
        ? currentHeaders[key]
        : defaultRequestHeaderValue(key)
    ])
  );
  return JSON.stringify(nextHeaders, null, 2);
}

export type RequestHeaderRow = {
  key: string;
  value: string;
};

export function requestHeaderRowsFromJson(value: string): RequestHeaderRow[] {
  try {
    return Object.entries(parseJsonObjectText(value)).map(([key, headerValue]) => ({
      key,
      value: requestHeaderValueText(headerValue)
    }));
  } catch {
    return [];
  }
}

export function requestHeadersJsonFromRows(rows: RequestHeaderRow[]): string {
  const headers: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    headers[key] = row.value;
  }
  return JSON.stringify(headers, null, 2);
}

export function environmentOptions(environments: ProjectEnvironment[]) {
  return (environments.length ? environments : DEFAULT_PROJECT_ENVIRONMENTS).map((environment) => ({
    value: environment.key,
    label: environment.name
  }));
}

function normalizeEnvironment(rawEnvironment: unknown, index: number): ProjectEnvironment | null {
  if (!rawEnvironment || typeof rawEnvironment !== 'object' || Array.isArray(rawEnvironment)) {
    return null;
  }
  const record = rawEnvironment as Record<string, unknown>;
  const key =
    stringValue(record.key) ??
    stringValue(record.id) ??
    stringValue(record.name) ??
    `environment-${index + 1}`;
  const defaultEnvironment = DEFAULT_PROJECT_ENVIRONMENTS.find(
    (environment) => environment.key === key
  );

  return {
    key,
    name: stringValue(record.name) ?? stringValue(record.label) ?? defaultEnvironment?.name ?? key,
    baseUrl:
      stringValue(record.base_url) ??
      stringValue(record.baseUrl) ??
      defaultEnvironment?.baseUrl ??
      '',
    apiBaseUrl:
      stringValue(record.api_base_url) ??
      stringValue(record.apiBaseUrl) ??
      defaultEnvironment?.apiBaseUrl ??
      '',
    requestHeadersJson: jsonTextFromUnknown(
      record.request_headers ?? record.headers ?? defaultEnvironment?.requestHeadersJson
    )
  };
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function resolveEnvironmentKey(environments: ProjectEnvironment[], requestedKey: string): string {
  if (environments.some((environment) => environment.key === requestedKey)) return requestedKey;
  return environments[0]?.key ?? DEFAULT_ENVIRONMENT_KEY;
}

function jsonTextFromUnknown(value: unknown): string {
  if (typeof value === 'string') return value.trim() || '{}';
  if (value === undefined || value === null) return '{}';
  return JSON.stringify(value, null, 2);
}

function uniqueHeaderKeys(keys: string[]): string[] {
  const seen = new Set<string>();
  return keys
    .map((key) => key.trim())
    .filter((key) => {
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

export function defaultRequestHeaderValue(key: string): string {
  const defaults: Record<string, string> = {
    Authorization: '',
    'Content-Type': 'application/json',
    Accept: 'application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    Cookie: '',
    'User-Agent': 'Beautiful-E2E',
    'X-Request-Id': '',
    'X-Trace-Id': '',
    'X-Tenant-Id': '',
    'X-User-Id': '',
    'X-CSRF-Token': '',
    'X-API-Key': ''
  };
  return defaults[key] ?? '';
}

function requestHeaderValueText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === undefined || value === null) return '';
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
