import { API_BASE, request } from './api/client';
import type { ProjectKnowledgeGraph, ProjectKnowledgeGraphUpdatePayload } from './types/projectKnowledgeGraph';
import { streamJsonSse } from './api/streams';

export type Group = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  sort_order: number;
};

export type Repository = {
  id: string;
  project_id: string;
  name: string;
  kind: string;
  path: string;
  index_summary: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ProjectSettings = {
  execution_mode?: string;
  frontend_repo_path?: string;
  backend_repo_path?: string;
  workspace_path?: string;
  active_environment?: string;
  active_frontend_environment?: string;
  active_api_environment?: string;
  base_url?: string;
  api_base_url?: string;
  environments?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type Project = {
  id: string;
  name: string;
  description: string | null;
  is_current: boolean;
  settings: ProjectSettings;
  repositories: Repository[];
  created_at: string;
  updated_at: string;
};

export type Step = {
  id: string;
  order_index: number;
  kind: string;
  label: string;
  action: string | null;
  selector: string | null;
  target_url: string | null;
  value: string | null;
  expected: string | null;
  data?: Record<string, unknown> | null;
};

export type CaseGraph = {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
};

export type TestCase = {
  id: string;
  project_id: string;
  group_id: string | null;
  title: string;
  description: string;
  priority: string;
  status: string;
  source_prompt: string;
  created_by: string | null;
  code_context: Record<string, unknown> | null;
  graph: CaseGraph | null;
  steps: Step[];
  playwright_spec_path: string | null;
  created_at: string;
  updated_at: string;
};

export type GenerateCasePayload = {
  description: string;
  target_case_id?: string;
  title?: string;
  case_description?: string;
  execution_mode?: string;
  group_id?: string | null;
  agent_id?: string;
  skill_ids?: string[];
  frontend_repo_path?: string;
  backend_repo_path?: string;
  created_by?: string;
  priority?: string;
  canvas_dsl?: Record<string, unknown>;
};

export type GenerateCaseStreamEvent = {
  type: 'start' | 'progress' | 'provider_delta' | 'case' | 'done' | 'error' | string;
  message?: string;
  stage?: string;
  status_code?: number;
  case?: TestCase;
  channel?: 'reasoning' | 'content' | string;
  delta?: string;
  label?: string;
  provider?: string;
  vendor_event_type?: string;
  [key: string]: unknown;
};

export type ProjectAnalysisStreamEvent = {
  type: 'start' | 'progress' | 'project' | 'done' | 'error' | string;
  message?: string;
  stage?: string;
  status_code?: number;
  project?: Project;
  repository_kind?: string;
  repository_count?: number;
  file_count?: number;
  scanned_file_count?: number;
  route_count?: number;
  discovered_route_count?: number;
  dom_target_count?: number;
  discovered_dom_target_count?: number;
  dom_module_count?: number;
  discovered_dom_module_count?: number;
  scan_group_count?: number;
  scan_truncated?: boolean;
  files_truncated?: boolean;
  routes_truncated?: boolean;
  dom_targets_truncated?: boolean;
  dom_modules_truncated?: boolean;
  auth_mode?: string;
  [key: string]: unknown;
};

export type DomModuleCompileMode = 'static' | 'ai';

export type DomModuleCompileStreamEvent = {
  type: 'start' | 'progress' | 'project' | 'done' | 'error' | string;
  message?: string;
  stage?: string;
  status_code?: number;
  percent?: number;
  mode?: DomModuleCompileMode | string;
  project?: Project;
  [key: string]: unknown;
};

export type CaseRunStreamEvent = {
  type: 'start' | 'inference' | 'repair' | 'request' | 'result' | 'done' | 'error' | string;
  message?: string;
  stage?: string;
  case_id?: string;
  case_title?: string;
  base_url?: string;
  api_base_url?: string;
  environment?: string;
  total?: number;
  passed?: number;
  failed?: number;
  status?: 'passed' | 'failed' | string;
  step_id?: string;
  order_index?: number;
  label?: string;
  action?: string | null;
  method?: string;
  url?: string;
  target_url?: string | null;
  selector?: string | null;
  expected_status?: number;
  status_code?: number | null;
  duration_ms?: number;
  ok?: boolean;
  error?: string | null;
  page_url?: string;
  screenshot_data_url?: string;
  response_preview?: string;
  response_content_type?: string | null;
  inference_status?: 'running' | 'resolved' | 'failed' | string;
  repair_status?: 'running' | 'resolved' | 'failed' | string;
  variable?: string;
  runtime_inference?: Record<string, unknown>;
  runtime_inferences?: Array<Record<string, unknown>>;
  runtime_repair?: Record<string, unknown>;
  runtime_repairs?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type CaseRunStepOverridePayload = {
  id: string;
  order_index: number;
  kind: string;
  label: string;
  action?: string | null;
  selector?: string | null;
  target_url?: string | null;
  value?: string | null;
  expected?: string | null;
  data?: Record<string, unknown> | null;
};

export type CaseRunRequestPayload = {
  timeout_seconds?: number;
  fail_fast?: boolean;
  step_id?: string;
  step_override?: CaseRunStepOverridePayload;
  environment_settings?: ProjectSettings;
};

export type Bootstrap = {
  project: Project;
  projects: Project[];
  groups: Group[];
};

export type DirectoryPickResult = {
  path: string | null;
  canceled: boolean;
};

export type AiProviderInfo = {
  name: string;
  label: string;
  description: string;
  mode: string;
  protocol: string;
  configurable: boolean;
  env_vars: string[];
  active?: boolean;
  available?: boolean;
  configured?: boolean;
  entrypoint?: string;
  usages?: string[];
};

export type AiUsageOption = {
  key: string;
  label: string;
  description: string;
};

export type AiProviderStatus = {
  provider: string;
  active_provider: string;
  provider_entrypoint: string | null;
  available_providers: string[];
  providers: AiProviderInfo[];
  provider_configured: boolean;
  usage_options: AiUsageOption[];
  usage_plan: Record<string, string>;
  model: string | null;
  wire_api: string | null;
  api_key_configured: boolean;
  base_url_configured: boolean;
  codex_exec_command: string;
  codex_exec_available: boolean;
  codex_exec_path?: string | null;
  codex_exec_model: string | null;
  codex_exec_profile: string | null;
  codex_exec_profile_v2: string | null;
  codex_exec_cwd: string | null;
  codex_exec_sandbox: string | null;
  codex_exec_ephemeral: boolean;
  codex_exec_skip_git_repo_check: boolean;
  codex_exec_ignore_user_config: boolean;
  codex_exec_ignore_rules: boolean;
  codex_exec_strict_config: boolean;
  codex_exec_output_schema_enabled: boolean;
  codex_exec_oss: boolean;
  codex_exec_local_provider: string | null;
  codex_exec_image_paths: string[];
  codex_exec_add_dirs: string[];
  codex_exec_config_overrides: string[];
  codex_exec_enabled_features: string[];
  codex_exec_disabled_features: string[];
  codex_exec_dangerously_bypass_approvals_and_sandbox: boolean;
  codex_exec_dangerously_bypass_hook_trust: boolean;
  codex_exec_capabilities?: Record<string, unknown>;
  fallback_rule_based: boolean;
};

export type AiProviderUpdatePayload = {
  provider?: string;
  provider_entrypoint?: string;
  usage_plan?: Record<string, string>;
  api_key?: string;
  base_url?: string;
  model?: string;
  wire_api?: string;
  reasoning_effort?: string;
  timeout_seconds?: number;
  codex_exec_command?: string;
  codex_exec_model?: string;
  codex_exec_profile?: string;
  codex_exec_profile_v2?: string;
  codex_exec_cwd?: string;
  codex_exec_sandbox?: string;
  codex_exec_ephemeral?: boolean;
  codex_exec_skip_git_repo_check?: boolean;
  codex_exec_ignore_user_config?: boolean;
  codex_exec_ignore_rules?: boolean;
  codex_exec_strict_config?: boolean;
  codex_exec_output_schema_enabled?: boolean;
  codex_exec_oss?: boolean;
  codex_exec_local_provider?: string;
  codex_exec_image_paths?: string[];
  codex_exec_add_dirs?: string[];
  codex_exec_config_overrides?: string[];
  codex_exec_enabled_features?: string[];
  codex_exec_disabled_features?: string[];
  codex_exec_dangerously_bypass_approvals_and_sandbox?: boolean;
  codex_exec_dangerously_bypass_hook_trust?: boolean;
};

async function streamGenerateCase(
  path: string,
  payload: GenerateCasePayload,
  onEvent?: (event: GenerateCaseStreamEvent) => void
): Promise<TestCase> {
  let generatedCase: TestCase | null = null;

  await streamJsonSse<GenerateCaseStreamEvent>(
    `${API_BASE}${path}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    },
    {
      unsupportedMessage: '当前浏览器不支持流式生成响应',
      errorMessage: '流式生成失败',
      onEvent: (event) => {
        onEvent?.(event);
        if (event.type === 'case' && event.case) generatedCase = event.case;
      }
    }
  );

  if (!generatedCase) throw new Error('流式生成未返回用例结果');
  return generatedCase;
}

async function streamProjectAnalysis(
  path: string,
  onEvent?: (event: ProjectAnalysisStreamEvent) => void
): Promise<Project> {
  let analyzedProject: Project | null = null;

  await streamJsonSse<ProjectAnalysisStreamEvent>(
    `${API_BASE}${path}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    },
    {
      unsupportedMessage: '当前浏览器不支持流式项目分析响应',
      errorMessage: '项目分析失败',
      onEvent: (event) => {
        onEvent?.(event);
        if (event.type === 'project' && event.project) analyzedProject = event.project;
      }
    }
  );

  if (!analyzedProject) throw new Error('流式项目分析未返回项目结果');
  return analyzedProject;
}

async function streamCaseRun(
  path: string,
  onEvent?: (event: CaseRunStreamEvent) => void,
  payload: CaseRunRequestPayload = {}
): Promise<void> {
  await streamJsonSse<CaseRunStreamEvent>(
    `${API_BASE}${path}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    },
    {
      unsupportedMessage: '当前浏览器不支持流式运行响应',
      errorMessage: '接口运行失败',
      onEvent
    }
  );
}

async function streamDomModuleCompile(
  projectId: string,
  payload: {
    repository_id: string;
    module_id: string;
    mode: DomModuleCompileMode;
  },
  onEvent?: (event: DomModuleCompileStreamEvent) => void
): Promise<Project> {
  let compiledProject: Project | null = null;

  await streamJsonSse<DomModuleCompileStreamEvent>(
    `${API_BASE}/projects/${projectId}/dom-modules/compile/stream`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    },
    {
      unsupportedMessage: '当前浏览器不支持流式 DOM 编译响应',
      errorMessage: 'DOM 模块编译失败',
      onEvent: (event) => {
        onEvent?.(event);
        if (event.type === 'project' && event.project) compiledProject = event.project;
      }
    }
  );

  if (!compiledProject) throw new Error('流式 DOM 编译未返回项目结果');
  return compiledProject;
}

export const api = {
  bootstrap: () => request<Bootstrap>('/bootstrap', { method: 'POST' }),
  loadProjectWorkspace: (projectId: string) =>
    request<Bootstrap>(`/projects/${projectId}/select`, { method: 'POST' }),
  listProjects: () => request<Project[]>('/projects'),
  createProject: (payload: {
    name: string;
    description?: string | null;
    settings?: Record<string, unknown>;
    analyze_on_create?: boolean;
  }) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  createProjectFromDirectory: (payload: { path: string; name?: string; analyze_on_create?: boolean }) =>
    request<Project>('/projects/from-directory', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  analyzeProject: (projectId: string) =>
    request<Project>(`/projects/${projectId}/analyze`, { method: 'POST' }),
  analyzeProjectStream: (
    projectId: string,
    onEvent?: (event: ProjectAnalysisStreamEvent) => void
  ) => streamProjectAnalysis(`/projects/${projectId}/analyze/stream`, onEvent),
  compileDomModuleStream: (
    projectId: string,
    payload: {
      repository_id: string;
      module_id: string;
      mode: DomModuleCompileMode;
    },
    onEvent?: (event: DomModuleCompileStreamEvent) => void
  ) => streamDomModuleCompile(projectId, payload, onEvent),
  getProjectKnowledgeGraph: (projectId: string) =>
    request<ProjectKnowledgeGraph>(`/projects/${projectId}/knowledge-graph`),
  rebuildProjectKnowledgeGraph: (projectId: string) =>
    request<ProjectKnowledgeGraph>(`/projects/${projectId}/knowledge-graph/rebuild`, {
      method: 'POST'
    }),
  updateProjectKnowledgeGraph: (
    projectId: string,
    payload: ProjectKnowledgeGraphUpdatePayload
  ) =>
    request<ProjectKnowledgeGraph>(`/projects/${projectId}/knowledge-graph`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  updateProject: (
    projectId: string,
    payload: {
      name?: string;
      description?: string | null;
      execution_mode?: string;
      frontend_repo_path?: string;
      backend_repo_path?: string;
      workspace_path?: string;
      active_environment?: string;
      active_frontend_environment?: string;
      active_api_environment?: string;
      base_url?: string;
      api_base_url?: string;
      settings?: Record<string, unknown>;
    }
  ) =>
    request<Project>(`/projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  deleteProject: (projectId: string) =>
    request<{ id: string; status: string }>(`/projects/${projectId}`, { method: 'DELETE' }),
  pickDirectory: (payload: { title: string; initial_path?: string }) =>
    request<DirectoryPickResult>('/fs/pick-directory', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  getAiProvider: () => request<AiProviderStatus>('/ai/provider'),
  updateAiProvider: (payload: AiProviderUpdatePayload) =>
    request<AiProviderStatus>('/ai/provider', {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  createGroup: (
    projectId: string,
    payload: { name: string; description?: string | null; sort_order?: number }
  ) =>
    request<Group>(`/projects/${projectId}/groups`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateGroup: (
    groupId: string,
    payload: { name?: string; description?: string | null; sort_order?: number }
  ) =>
    request<Group>(`/groups/${groupId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  deleteGroup: (groupId: string) =>
    request<{ id: string; status: string }>(`/groups/${groupId}`, { method: 'DELETE' }),
  listCases: (projectId: string, groupId?: string) => {
    const query = groupId ? `?group_id=${encodeURIComponent(groupId)}` : '';
    return request<TestCase[]>(`/projects/${projectId}/cases${query}`);
  },
  createCase: (
    projectId: string,
    payload: {
      title: string;
      description?: string | null;
      group_id?: string | null;
      priority?: string;
      status?: string;
      created_by?: string;
    }
  ) =>
    request<TestCase>(`/projects/${projectId}/cases`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  updateCase: (
    caseId: string,
    payload: {
      title?: string;
      description?: string | null;
      group_id?: string | null;
      priority?: string;
      status?: string;
    }
  ) =>
    request<TestCase>(`/cases/${caseId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  deleteCase: (caseId: string) =>
    request<{ id: string; status: string }>(`/cases/${caseId}`, { method: 'DELETE' }),
  generateCase: (projectId: string, payload: GenerateCasePayload) =>
    request<TestCase>(`/projects/${projectId}/cases/generate`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  generateCaseStream: (
    projectId: string,
    payload: GenerateCasePayload,
    onEvent?: (event: GenerateCaseStreamEvent) => void
  ) => streamGenerateCase(`/projects/${projectId}/cases/generate/stream`, payload, onEvent),
  updateCaseGraph: (
    caseId: string,
    payload: {
      graph: CaseGraph;
      steps: Array<Record<string, unknown>>;
      execution_mode?: string;
      source_prompt?: string;
      actor?: string;
    }
  ) =>
    request<TestCase>(`/cases/${caseId}/graph`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  emitPlaywright: (caseId: string) =>
    request<{ case_id: string; spec_path: string; content: string }>(
      `/cases/${caseId}/emit-playwright`,
      { method: 'POST' }
    ),
  runBackendApiCaseStream: (
    caseId: string,
    onEvent?: (event: CaseRunStreamEvent) => void,
    payload?: CaseRunRequestPayload
  ) => streamCaseRun(`/cases/${caseId}/run/backend-api/stream`, onEvent, payload),
  runFullstackCaseStream: (
    caseId: string,
    onEvent?: (event: CaseRunStreamEvent) => void,
    payload?: CaseRunRequestPayload
  ) => streamCaseRun(`/cases/${caseId}/run/fullstack/stream`, onEvent, payload ?? { fail_fast: true })
};

export { demoBootstrap, demoCases } from './demoData';
