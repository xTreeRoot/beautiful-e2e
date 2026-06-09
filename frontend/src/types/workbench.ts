import type { Edge, Node } from '@xyflow/react';
import type { LucideIcon } from 'lucide-react';

export type CanvasNodeData = {
  label: string;
  kind: string;
  action?: string | null;
  selector?: string | null;
  target_url?: string | null;
  value?: string | null;
  expected?: string | null;
  description?: string | null;
  method?: string | null;
  metadata?: Record<string, unknown> | null;
  [key: string]: unknown;
};

export type CanvasNode = Node<CanvasNodeData>;
export type CanvasEdge = Edge;

export type NodeTemplate = {
  kind: string;
  label: string;
  action?: string;
  icon: LucideIcon;
};

export type ExecutionMode = 'fullstack' | 'backend_api';
export type SidebarMenuKey = 'project' | 'groups' | 'cases';
export type CaseCreateMode = 'blank' | 'ai';
export type FlowPosition = { x: number; y: number };
export type GenerateProgressPhase = 'idle' | 'running' | 'complete' | 'error';
export type CaseRunProgressPhase = 'idle' | 'running' | 'complete' | 'error';
export type CaseRunStepStatus = 'pending' | 'running' | 'passed' | 'failed';
export type CaseRunInferenceStatus = 'running' | 'resolved' | 'failed';

export type NodeDebugDraft = {
  method: string;
  path: string;
  pathParams: Record<string, string>;
  queryParams: Record<string, string>;
  body: string;
  expected: string;
};

export type ContextToolbox = {
  x: number;
  y: number;
  flowPosition: FlowPosition;
};

export type GenerateProgressState = {
  open: boolean;
  runId: number;
  phase: GenerateProgressPhase;
  prompt: string;
  executionMode: ExecutionMode;
  detail: string;
  lines: string[];
  startedAt: number | null;
  finishedAt: number | null;
};

export type ProjectAnalysisProgressState = {
  open: boolean;
  runId: number;
  phase: GenerateProgressPhase;
  projectName: string;
  detail: string;
  lines: string[];
  startedAt: number | null;
  finishedAt: number | null;
};

export type CaseRunStepState = {
  stepId: string;
  orderIndex: number;
  label: string;
  action: string | null;
  method: string;
  url: string;
  selector?: string | null;
  expectedStatus: number;
  statusCode: number | null;
  durationMs: number | null;
  status: CaseRunStepStatus;
  error?: string | null;
  pageUrl?: string;
  screenshotDataUrl?: string;
  responsePreview?: string;
  responseContentType?: string | null;
  runtimeInferences?: CaseRunInferenceState[];
};

export type CaseRunInferenceState = {
  kind?: 'variable' | 'repair';
  variable: string;
  status: CaseRunInferenceStatus;
  confidence: number | null;
  source: string | null;
  sourceStepLabel: string | null;
  sourceJsonPath: string | null;
  reason: string | null;
  message: string | null;
};

export type CaseRunSummary = {
  total: number;
  passed: number;
  failed: number;
  status: 'passed' | 'failed';
};

export type CaseRunProgressState = {
  open: boolean;
  phase: CaseRunProgressPhase;
  runId: number;
  debugNodeId?: string | null;
  executionMode: ExecutionMode;
  caseId: string;
  caseTitle: string;
  apiBaseUrl: string;
  environment: string;
  detail: string;
  total: number;
  steps: CaseRunStepState[];
  summary: CaseRunSummary | null;
};

export type AiProviderFormState = {
  provider: string;
  providerEntryPoint: string;
  usagePlan: Record<string, string>;
  apiKey: string;
  baseUrl: string;
  model: string;
  wireApi: string;
  codexExecCommand: string;
  codexExecModel: string;
  codexExecProfile: string;
  codexExecProfileV2: string;
  codexExecCwd: string;
  codexExecSandbox: string;
  codexExecEphemeral: boolean;
  codexExecSkipGitRepoCheck: boolean;
  codexExecIgnoreUserConfig: boolean;
  codexExecIgnoreRules: boolean;
  codexExecStrictConfig: boolean;
  codexExecOutputSchemaEnabled: boolean;
  codexExecOss: boolean;
  codexExecLocalProvider: string;
  codexExecImagePaths: string;
  codexExecAddDirs: string;
  codexExecConfigOverrides: string;
  codexExecEnabledFeatures: string;
  codexExecDisabledFeatures: string;
  codexExecDangerouslyBypassApprovalsAndSandbox: boolean;
  codexExecDangerouslyBypassHookTrust: boolean;
};
