import { useCallback, useState } from 'react';

import { api, type AiProviderStatus, type AiProviderUpdatePayload } from '../api';
import type { AiProviderFormState } from '../types/workbench';

type ToastKind = 'success' | 'info' | 'warning' | 'error';

const DEFAULT_FORM: AiProviderFormState = {
  provider: 'codex_exec',
  providerEntryPoint: '',
  usagePlan: {
    project_analysis: 'codex_exec',
    dsl_generation: 'codex_exec',
    api_runtime: 'codex_exec',
    dom_compilation: 'codex_exec'
  },
  apiKey: '',
  baseUrl: '',
  model: '',
  wireApi: 'responses',
  codexExecCommand: 'codex',
  codexExecModel: '',
  codexExecProfile: '',
  codexExecProfileV2: '',
  codexExecCwd: '',
  codexExecSandbox: '',
  codexExecEphemeral: false,
  codexExecSkipGitRepoCheck: false,
  codexExecIgnoreUserConfig: false,
  codexExecIgnoreRules: false,
  codexExecStrictConfig: false,
  codexExecOutputSchemaEnabled: true,
  codexExecOss: false,
  codexExecLocalProvider: '',
  codexExecImagePaths: '',
  codexExecAddDirs: '',
  codexExecConfigOverrides: '',
  codexExecEnabledFeatures: '',
  codexExecDisabledFeatures: '',
  codexExecDangerouslyBypassApprovalsAndSandbox: false,
  codexExecDangerouslyBypassHookTrust: false
};

export function useAiProviderConfig(showToast: (type: ToastKind, content: string) => void) {
  const [aiProviderStatus, setAiProviderStatus] = useState<AiProviderStatus | null>(null);
  const [aiProviderForm, setAiProviderForm] = useState<AiProviderFormState>(DEFAULT_FORM);
  const [isAiConfigOpen, setIsAiConfigOpen] = useState(false);
  const [isLoadingAiProvider, setIsLoadingAiProvider] = useState(false);
  const [isSavingAiProvider, setIsSavingAiProvider] = useState(false);
  const [aiProviderError, setAiProviderError] = useState('');

  const loadAiProviderStatus = useCallback(async () => {
    setIsLoadingAiProvider(true);
    setAiProviderError('');
    try {
      const status = await api.getAiProvider();
      setAiProviderStatus(status);
      setAiProviderForm(statusToForm(status));
      return status;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'AI 配置加载失败';
      setAiProviderError(message);
      showToast('error', message);
      return null;
    } finally {
      setIsLoadingAiProvider(false);
    }
  }, [showToast]);

  const openAiConfig = useCallback(() => {
    setIsAiConfigOpen(true);
    void loadAiProviderStatus();
  }, [loadAiProviderStatus]);

  const closeAiConfig = useCallback(() => {
    setIsAiConfigOpen(false);
    setAiProviderError('');
  }, []);

  const updateAiProviderForm = useCallback((patch: Partial<AiProviderFormState>) => {
    setAiProviderForm((current) => {
      const usagePlan = patch.usagePlan
        ? { ...current.usagePlan, ...patch.usagePlan }
        : usagePlanForProviderSwitch(current, patch.provider);
      return {
        ...current,
        ...patch,
        usagePlan
      };
    });
  }, []);

  const saveAiProviderConfig = useCallback(async () => {
    setIsSavingAiProvider(true);
    setAiProviderError('');
    try {
      const status = await api.updateAiProvider(formToPayload(aiProviderForm));
      setAiProviderStatus(status);
      setAiProviderForm(statusToForm(status));
      showToast('success', `AI 配置已保存：${formatActiveProvider(status)}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'AI 配置保存失败';
      setAiProviderError(message);
      showToast('error', message);
    } finally {
      setIsSavingAiProvider(false);
    }
  }, [aiProviderForm, showToast]);

  return {
    aiProviderStatus,
    aiProviderForm,
    isAiConfigOpen,
    isLoadingAiProvider,
    isSavingAiProvider,
    aiProviderError,
    openAiConfig,
    closeAiConfig,
    loadAiProviderStatus,
    updateAiProviderForm,
    saveAiProviderConfig
  };
}

function statusToForm(status: AiProviderStatus): AiProviderFormState {
  return {
    provider: status.active_provider || status.provider || DEFAULT_FORM.provider,
    providerEntryPoint: status.provider_entrypoint ?? '',
    usagePlan: normalizeUsagePlan(status),
    apiKey: '',
    baseUrl: '',
    model: status.model ?? '',
    wireApi: status.wire_api ?? DEFAULT_FORM.wireApi,
    codexExecCommand: status.codex_exec_command || DEFAULT_FORM.codexExecCommand,
    codexExecModel: status.codex_exec_model ?? '',
    codexExecProfile: status.codex_exec_profile ?? '',
    codexExecProfileV2: status.codex_exec_profile_v2 ?? '',
    codexExecCwd: status.codex_exec_cwd ?? '',
    codexExecSandbox: status.codex_exec_sandbox ?? '',
    codexExecEphemeral: status.codex_exec_ephemeral ?? DEFAULT_FORM.codexExecEphemeral,
    codexExecSkipGitRepoCheck:
      status.codex_exec_skip_git_repo_check ?? DEFAULT_FORM.codexExecSkipGitRepoCheck,
    codexExecIgnoreUserConfig:
      status.codex_exec_ignore_user_config ?? DEFAULT_FORM.codexExecIgnoreUserConfig,
    codexExecIgnoreRules: status.codex_exec_ignore_rules ?? DEFAULT_FORM.codexExecIgnoreRules,
    codexExecStrictConfig: status.codex_exec_strict_config ?? DEFAULT_FORM.codexExecStrictConfig,
    codexExecOutputSchemaEnabled:
      status.codex_exec_output_schema_enabled ?? DEFAULT_FORM.codexExecOutputSchemaEnabled,
    codexExecOss: status.codex_exec_oss ?? DEFAULT_FORM.codexExecOss,
    codexExecLocalProvider: status.codex_exec_local_provider ?? '',
    codexExecImagePaths: joinLines(status.codex_exec_image_paths),
    codexExecAddDirs: joinLines(status.codex_exec_add_dirs),
    codexExecConfigOverrides: joinLines(status.codex_exec_config_overrides),
    codexExecEnabledFeatures: joinLines(status.codex_exec_enabled_features),
    codexExecDisabledFeatures: joinLines(status.codex_exec_disabled_features),
    codexExecDangerouslyBypassApprovalsAndSandbox:
      status.codex_exec_dangerously_bypass_approvals_and_sandbox ??
      DEFAULT_FORM.codexExecDangerouslyBypassApprovalsAndSandbox,
    codexExecDangerouslyBypassHookTrust:
      status.codex_exec_dangerously_bypass_hook_trust ??
      DEFAULT_FORM.codexExecDangerouslyBypassHookTrust
  };
}

function formToPayload(form: AiProviderFormState): AiProviderUpdatePayload {
  const isCustomEntryPoint = form.provider === 'custom_entrypoint';
  const payload: AiProviderUpdatePayload = {
    provider: isCustomEntryPoint ? undefined : form.provider,
    provider_entrypoint: isCustomEntryPoint ? form.providerEntryPoint.trim() : '',
    usage_plan: form.usagePlan
  };
  assignIfPresent(payload, 'api_key', form.apiKey);
  assignIfPresent(payload, 'base_url', form.baseUrl);
  assignIfPresent(payload, 'model', form.model);
  assignIfPresent(payload, 'wire_api', form.wireApi);
  assignIfPresent(payload, 'codex_exec_command', form.codexExecCommand);
  assignIfPresent(payload, 'codex_exec_model', form.codexExecModel);
  assignIfPresent(payload, 'codex_exec_profile', form.codexExecProfile);
  assignIfPresent(payload, 'codex_exec_profile_v2', form.codexExecProfileV2);
  assignIfPresent(payload, 'codex_exec_cwd', form.codexExecCwd);
  assignIfPresent(payload, 'codex_exec_sandbox', form.codexExecSandbox);
  payload.codex_exec_ephemeral = form.codexExecEphemeral;
  payload.codex_exec_skip_git_repo_check = form.codexExecSkipGitRepoCheck;
  payload.codex_exec_ignore_user_config = form.codexExecIgnoreUserConfig;
  payload.codex_exec_ignore_rules = form.codexExecIgnoreRules;
  payload.codex_exec_strict_config = form.codexExecStrictConfig;
  payload.codex_exec_output_schema_enabled = form.codexExecOutputSchemaEnabled;
  payload.codex_exec_oss = form.codexExecOss;
  assignIfPresent(payload, 'codex_exec_local_provider', form.codexExecLocalProvider);
  payload.codex_exec_image_paths = splitLines(form.codexExecImagePaths);
  payload.codex_exec_add_dirs = splitLines(form.codexExecAddDirs);
  payload.codex_exec_config_overrides = splitLines(form.codexExecConfigOverrides);
  payload.codex_exec_enabled_features = splitLines(form.codexExecEnabledFeatures);
  payload.codex_exec_disabled_features = splitLines(form.codexExecDisabledFeatures);
  payload.codex_exec_dangerously_bypass_approvals_and_sandbox =
    form.codexExecDangerouslyBypassApprovalsAndSandbox;
  payload.codex_exec_dangerously_bypass_hook_trust = form.codexExecDangerouslyBypassHookTrust;
  return payload;
}

function assignIfPresent<Key extends keyof AiProviderUpdatePayload>(
  payload: AiProviderUpdatePayload,
  key: Key,
  value: string
) {
  const normalized = value.trim();
  if (normalized) {
    payload[key] = normalized as AiProviderUpdatePayload[Key];
  }
}

function normalizeUsagePlan(status: AiProviderStatus): Record<string, string> {
  const fallback = status.active_provider || status.provider || DEFAULT_FORM.provider;
  const nextPlan: Record<string, string> = { ...DEFAULT_FORM.usagePlan, ...(status.usage_plan ?? {}) };
  for (const option of status.usage_options ?? []) {
    nextPlan[option.key] = nextPlan[option.key] || fallback;
  }
  return nextPlan;
}

function usagePlanForProviderSwitch(
  current: AiProviderFormState,
  nextProvider: string | undefined
): Record<string, string> {
  if (!nextProvider || nextProvider === current.provider) return current.usagePlan;

  const nextPlan: Record<string, string> = {};
  for (const [usageKey, provider] of Object.entries(current.usagePlan)) {
    nextPlan[usageKey] = provider === current.provider ? nextProvider : provider;
  }
  return nextPlan;
}

function splitLines(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinLines(value: string[] | undefined): string {
  return (value ?? []).join('\n');
}

function formatActiveProvider(status: AiProviderStatus): string {
  const provider = status.providers.find((item) => item.name === status.active_provider);
  return provider?.label ?? status.active_provider;
}
