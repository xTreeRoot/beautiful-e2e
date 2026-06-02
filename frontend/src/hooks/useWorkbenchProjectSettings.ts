import { useState, type Dispatch, type SetStateAction } from 'react';

import { api, type Bootstrap, type Project } from '../api';
import { formatExecutionMode, getProjectExecutionMode, withProjectSettings } from '../lib/project';
import {
  DEFAULT_API_BASE_URL,
  DEFAULT_ENVIRONMENT_KEY,
  DEFAULT_FRONTEND_BASE_URL,
  environmentSettingsPatch,
  firstEnvironmentJsonError,
  normalizeProjectEnvironments,
  updateEnvironmentUrls,
  type ProjectEnvironment
} from '../lib/projectEnvironments';
import type { ExecutionMode } from '../types/workbench';

type ToastType = 'success' | 'info' | 'warning' | 'error';

type UseWorkbenchProjectSettingsOptions = {
  project?: Project;
  offlineMode: boolean;
  setBootstrap: Dispatch<SetStateAction<Bootstrap | null>>;
  setStatus: (status: string) => void;
  showToast: (type: ToastType, content: string) => void;
};

/**
 * 管理当前项目设置、环境配置和项目表单状态。
 * 项目设置会影响生成、运行和 DSL 构建，抽成 hook 后总控制器只读取最终状态并触发项目级动作。
 */
export function useWorkbenchProjectSettings({
  project,
  offlineMode,
  setBootstrap,
  setStatus,
  showToast
}: UseWorkbenchProjectSettingsOptions) {
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('fullstack');
  const [frontendPath, setFrontendPath] = useState('');
  const [backendPath, setBackendPath] = useState('');
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>([]);
  const [activeFrontendEnvironmentKey, setActiveFrontendEnvironmentKey] = useState(DEFAULT_ENVIRONMENT_KEY);
  const [activeApiEnvironmentKey, setActiveApiEnvironmentKey] = useState(DEFAULT_ENVIRONMENT_KEY);
  const [baseUrl, setBaseUrl] = useState(DEFAULT_FRONTEND_BASE_URL);
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [requestHeadersJson, setRequestHeadersJson] = useState('{}');
  const [isSavingProjectHeaders, setIsSavingProjectHeaders] = useState(false);
  const [isProjectManagerOpen, setIsProjectManagerOpen] = useState(false);
  const [isProjectCreateOpen, setIsProjectCreateOpen] = useState(false);
  const [isProjectAnalysisOpen, setIsProjectAnalysisOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [newProjectExecutionMode, setNewProjectExecutionMode] = useState<ExecutionMode>('fullstack');
  const [newProjectAnalyzeOnCreate, setNewProjectAnalyzeOnCreate] = useState(true);
  const [newProjectEnvironments, setNewProjectEnvironments] = useState<ProjectEnvironment[]>([]);
  const [newProjectFrontendEnvironmentKey, setNewProjectFrontendEnvironmentKey] = useState(DEFAULT_ENVIRONMENT_KEY);
  const [newProjectApiEnvironmentKey, setNewProjectApiEnvironmentKey] = useState(DEFAULT_ENVIRONMENT_KEY);
  const [newProjectBaseUrl, setNewProjectBaseUrl] = useState(DEFAULT_FRONTEND_BASE_URL);
  const [newProjectApiBaseUrl, setNewProjectApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [newProjectRequestHeadersJson, setNewProjectRequestHeadersJson] = useState('{}');
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectName, setEditingProjectName] = useState('');
  const [editingProjectDescription, setEditingProjectDescription] = useState('');
  const [editingProjectExecutionMode, setEditingProjectExecutionMode] = useState<ExecutionMode>('fullstack');
  const [editingProjectEnvironments, setEditingProjectEnvironments] = useState<ProjectEnvironment[]>([]);
  const [editingProjectFrontendEnvironmentKey, setEditingProjectFrontendEnvironmentKey] =
    useState(DEFAULT_ENVIRONMENT_KEY);
  const [editingProjectApiEnvironmentKey, setEditingProjectApiEnvironmentKey] =
    useState(DEFAULT_ENVIRONMENT_KEY);
  const [editingProjectBaseUrl, setEditingProjectBaseUrl] = useState(DEFAULT_FRONTEND_BASE_URL);
  const [editingProjectApiBaseUrl, setEditingProjectApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [editingProjectRequestHeadersJson, setEditingProjectRequestHeadersJson] = useState('{}');

  function applyProjectSettings(nextProject: Project) {
    const settings = nextProject.settings ?? {};
    const environmentState = normalizeProjectEnvironments(settings);
    setExecutionMode(getProjectExecutionMode(nextProject));
    setFrontendPath(String(settings.frontend_repo_path ?? ''));
    setBackendPath(String(settings.backend_repo_path ?? ''));
    setEnvironments(environmentState.environments);
    setActiveFrontendEnvironmentKey(environmentState.activeFrontendEnvironmentKey);
    setActiveApiEnvironmentKey(environmentState.activeApiEnvironmentKey);
    setBaseUrl(environmentState.activeFrontendEnvironment.baseUrl);
    setApiBaseUrl(environmentState.activeApiEnvironment.apiBaseUrl);
    setRequestHeadersJson(environmentState.activeApiEnvironment.requestHeadersJson);
  }

  function ensureEnvironmentJsonReady(nextEnvironments: ProjectEnvironment[]) {
    const error = firstEnvironmentJsonError(nextEnvironments);
    if (!error) return true;
    const message = `请检查接口环境配置：${error}`;
    setStatus(message);
    showToast('warning', message);
    return false;
  }

  function applyEnvironmentSettingsToProject(
    nextEnvironments: ProjectEnvironment[],
    nextFrontendEnvironmentKey: string,
    nextApiEnvironmentKey: string
  ) {
    if (!ensureEnvironmentJsonReady(nextEnvironments)) return null;
    const settingsPatch = environmentSettingsPatch(
      nextEnvironments,
      nextFrontendEnvironmentKey,
      nextApiEnvironmentKey
    );
    setBootstrap((current) =>
      current && project
        ? {
            ...current,
            project: withProjectSettings(current.project, settingsPatch),
            projects: current.projects.map((item) =>
              item.id === project.id ? withProjectSettings(item, settingsPatch) : item
            )
          }
        : current
    );
    return settingsPatch;
  }

  function changeBaseUrl(value: string) {
    setBaseUrl(value);
    setEnvironments((current) =>
      updateEnvironmentUrls(current, activeFrontendEnvironmentKey, { baseUrl: value })
    );
  }

  function changeApiBaseUrl(value: string) {
    setApiBaseUrl(value);
    setEnvironments((current) =>
      updateEnvironmentUrls(current, activeApiEnvironmentKey, { apiBaseUrl: value })
    );
  }

  function changeRequestHeadersJson(value: string) {
    setRequestHeadersJson(value);
    setEnvironments((current) =>
      updateEnvironmentUrls(current, activeApiEnvironmentKey, { requestHeadersJson: value })
    );
  }

  async function saveProjectRequestHeaders() {
    if (!project || offlineMode) {
      const message = '后端未连接，暂时不能更新项目请求头';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    if (!ensureEnvironmentJsonReady(environments)) return;
    const settingsPatch = environmentSettingsPatch(
      environments,
      activeFrontendEnvironmentKey,
      activeApiEnvironmentKey
    );

    setIsSavingProjectHeaders(true);
    setStatus('正在更新项目请求头');
    try {
      const saved = await api.updateProject(project.id, {
        base_url: settingsPatch.base_url,
        api_base_url: settingsPatch.api_base_url,
        settings: settingsPatch
      });
      setBootstrap((current) =>
        current
          ? {
              ...current,
              project: saved,
              projects: current.projects.map((item) => (item.id === saved.id ? saved : item))
            }
          : current
      );
      applyProjectSettings(saved);
      setStatus('项目请求头已更新');
      showToast('success', '项目请求头已更新，后续接口运行会使用最新配置');
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目请求头更新失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setIsSavingProjectHeaders(false);
    }
  }

  function changeProjectFrontendEnvironment(nextEnvironmentKey: string) {
    const nextEnvironment = environments.find((environment) => environment.key === nextEnvironmentKey);
    if (!nextEnvironment) return;
    if (!ensureEnvironmentJsonReady(environments)) return;
    setActiveFrontendEnvironmentKey(nextEnvironmentKey);
    setBaseUrl(nextEnvironment.baseUrl);
    applyEnvironmentSettingsToProject(environments, nextEnvironmentKey, activeApiEnvironmentKey);
    setStatus(`前端环境已切换：${nextEnvironment.name}`);
    showToast('info', `前端环境已切换：${nextEnvironment.name}`);
  }

  function changeProjectApiEnvironment(nextEnvironmentKey: string) {
    const nextEnvironment = environments.find((environment) => environment.key === nextEnvironmentKey);
    if (!nextEnvironment) return;
    if (!ensureEnvironmentJsonReady(environments)) return;
    setActiveApiEnvironmentKey(nextEnvironmentKey);
    setApiBaseUrl(nextEnvironment.apiBaseUrl);
    setRequestHeadersJson(nextEnvironment.requestHeadersJson);
    applyEnvironmentSettingsToProject(environments, activeFrontendEnvironmentKey, nextEnvironmentKey);
    setStatus(`接口环境已切换：${nextEnvironment.name}`);
    showToast('info', `接口环境已切换：${nextEnvironment.name}`);
  }

  async function changeProjectExecutionMode(nextMode: ExecutionMode) {
    const previousMode = executionMode;
    if (!ensureEnvironmentJsonReady(environments)) return;
    const settingsPatch = environmentSettingsPatch(
      environments,
      activeFrontendEnvironmentKey,
      activeApiEnvironmentKey
    );
    setExecutionMode(nextMode);
    setBootstrap((current) =>
      current && project
        ? {
            ...current,
            project: withProjectSettings(current.project, { execution_mode: nextMode }),
            projects: current.projects.map((item) =>
              item.id === project.id ? withProjectSettings(item, { execution_mode: nextMode }) : item
            )
          }
        : current
    );

    if (!project || offlineMode) {
      setStatus(`执行模式已切换：${formatExecutionMode(nextMode)}`);
      showToast('info', `执行模式已切换：${formatExecutionMode(nextMode)}`);
      return;
    }

    setStatus('正在保存项目执行模式');
    try {
      const saved = await api.updateProject(project.id, {
        execution_mode: nextMode,
        frontend_repo_path: frontendPath,
        backend_repo_path: backendPath,
        base_url: settingsPatch.base_url,
        api_base_url: settingsPatch.api_base_url,
        settings: settingsPatch
      });
      setBootstrap((current) =>
        current
          ? {
              ...current,
              project: saved,
              projects: current.projects.map((item) => (item.id === saved.id ? saved : item))
            }
          : current
      );
      setStatus(`项目执行模式已保存：${formatExecutionMode(nextMode)}`);
      showToast('success', `执行模式已保存到项目：${formatExecutionMode(nextMode)}`);
    } catch (error) {
      setExecutionMode(previousMode);
      setBootstrap((current) =>
        current && project
          ? {
              ...current,
              project: withProjectSettings(current.project, { execution_mode: previousMode }),
              projects: current.projects.map((item) =>
                item.id === project.id ? withProjectSettings(item, { execution_mode: previousMode }) : item
              )
            }
          : current
      );
      const message = error instanceof Error ? error.message : '项目执行模式保存失败';
      setStatus(message);
      showToast('error', message);
    }
  }

  function openProjectManager() {
    if (offlineMode) {
      const message = '后端未连接，暂时不能管理项目';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setIsProjectManagerOpen(true);
  }

  function openProjectCreateModal() {
    setNewProjectName('');
    setNewProjectDescription('');
    setNewProjectExecutionMode(executionMode);
    setNewProjectEnvironments(environments);
    setNewProjectFrontendEnvironmentKey(activeFrontendEnvironmentKey);
    setNewProjectApiEnvironmentKey(activeApiEnvironmentKey);
    setNewProjectBaseUrl(baseUrl);
    setNewProjectApiBaseUrl(apiBaseUrl);
    setNewProjectRequestHeadersJson(requestHeadersJson);
    setNewProjectAnalyzeOnCreate(true);
    setIsProjectCreateOpen(true);
  }

  function cancelProjectCreate() {
    setIsProjectCreateOpen(false);
    setNewProjectName('');
    setNewProjectDescription('');
    setNewProjectExecutionMode(executionMode);
    setNewProjectEnvironments([]);
    setNewProjectFrontendEnvironmentKey(DEFAULT_ENVIRONMENT_KEY);
    setNewProjectApiEnvironmentKey(DEFAULT_ENVIRONMENT_KEY);
    setNewProjectBaseUrl(DEFAULT_FRONTEND_BASE_URL);
    setNewProjectApiBaseUrl(DEFAULT_API_BASE_URL);
    setNewProjectRequestHeadersJson('{}');
    setNewProjectAnalyzeOnCreate(true);
  }

  function changeNewProjectBaseUrl(value: string) {
    setNewProjectBaseUrl(value);
    setNewProjectEnvironments((current) =>
      updateEnvironmentUrls(current, newProjectFrontendEnvironmentKey, { baseUrl: value })
    );
  }

  function changeNewProjectApiBaseUrl(value: string) {
    setNewProjectApiBaseUrl(value);
    setNewProjectEnvironments((current) =>
      updateEnvironmentUrls(current, newProjectApiEnvironmentKey, { apiBaseUrl: value })
    );
  }

  function changeNewProjectRequestHeadersJson(value: string) {
    setNewProjectRequestHeadersJson(value);
    setNewProjectEnvironments((current) =>
      updateEnvironmentUrls(current, newProjectApiEnvironmentKey, { requestHeadersJson: value })
    );
  }

  function changeNewProjectFrontendEnvironment(environmentKey: string) {
    const nextEnvironment = newProjectEnvironments.find((environment) => environment.key === environmentKey);
    if (!nextEnvironment) return;
    setNewProjectFrontendEnvironmentKey(environmentKey);
    setNewProjectBaseUrl(nextEnvironment.baseUrl);
  }

  function changeNewProjectApiEnvironment(environmentKey: string) {
    const nextEnvironment = newProjectEnvironments.find((environment) => environment.key === environmentKey);
    if (!nextEnvironment) return;
    setNewProjectApiEnvironmentKey(environmentKey);
    setNewProjectApiBaseUrl(nextEnvironment.apiBaseUrl);
    setNewProjectRequestHeadersJson(nextEnvironment.requestHeadersJson);
  }

  function startProjectEdit(item: Project) {
    setEditingProjectId(item.id);
    setEditingProjectName(item.name);
    setEditingProjectDescription(item.description ?? '');
    setEditingProjectExecutionMode(getProjectExecutionMode(item));
    const environmentState = normalizeProjectEnvironments(item.settings);
    setEditingProjectEnvironments(environmentState.environments);
    setEditingProjectFrontendEnvironmentKey(environmentState.activeFrontendEnvironmentKey);
    setEditingProjectApiEnvironmentKey(environmentState.activeApiEnvironmentKey);
    setEditingProjectBaseUrl(environmentState.activeFrontendEnvironment.baseUrl);
    setEditingProjectApiBaseUrl(environmentState.activeApiEnvironment.apiBaseUrl);
    setEditingProjectRequestHeadersJson(environmentState.activeApiEnvironment.requestHeadersJson);
  }

  function cancelProjectEdit() {
    setEditingProjectId(null);
    setEditingProjectName('');
    setEditingProjectDescription('');
    setEditingProjectExecutionMode('fullstack');
    setEditingProjectEnvironments([]);
    setEditingProjectFrontendEnvironmentKey(DEFAULT_ENVIRONMENT_KEY);
    setEditingProjectApiEnvironmentKey(DEFAULT_ENVIRONMENT_KEY);
    setEditingProjectBaseUrl(DEFAULT_FRONTEND_BASE_URL);
    setEditingProjectApiBaseUrl(DEFAULT_API_BASE_URL);
    setEditingProjectRequestHeadersJson('{}');
  }

  function changeEditingProjectBaseUrl(value: string) {
    setEditingProjectBaseUrl(value);
    setEditingProjectEnvironments((current) =>
      updateEnvironmentUrls(current, editingProjectFrontendEnvironmentKey, { baseUrl: value })
    );
  }

  function changeEditingProjectApiBaseUrl(value: string) {
    setEditingProjectApiBaseUrl(value);
    setEditingProjectEnvironments((current) =>
      updateEnvironmentUrls(current, editingProjectApiEnvironmentKey, { apiBaseUrl: value })
    );
  }

  function changeEditingProjectRequestHeadersJson(value: string) {
    setEditingProjectRequestHeadersJson(value);
    setEditingProjectEnvironments((current) =>
      updateEnvironmentUrls(current, editingProjectApiEnvironmentKey, { requestHeadersJson: value })
    );
  }

  function changeEditingProjectFrontendEnvironment(environmentKey: string) {
    const nextEnvironment = editingProjectEnvironments.find((environment) => environment.key === environmentKey);
    if (!nextEnvironment) return;
    setEditingProjectFrontendEnvironmentKey(environmentKey);
    setEditingProjectBaseUrl(nextEnvironment.baseUrl);
  }

  function changeEditingProjectApiEnvironment(environmentKey: string) {
    const nextEnvironment = editingProjectEnvironments.find((environment) => environment.key === environmentKey);
    if (!nextEnvironment) return;
    setEditingProjectApiEnvironmentKey(environmentKey);
    setEditingProjectApiBaseUrl(nextEnvironment.apiBaseUrl);
    setEditingProjectRequestHeadersJson(nextEnvironment.requestHeadersJson);
  }

  return {
    executionMode,
    setExecutionMode,
    frontendPath,
    backendPath,
    environments,
    activeFrontendEnvironmentKey,
    activeApiEnvironmentKey,
    baseUrl,
    changeBaseUrl,
    apiBaseUrl,
    changeApiBaseUrl,
    requestHeadersJson,
    changeRequestHeadersJson,
    isSavingProjectHeaders,
    isProjectManagerOpen,
    setIsProjectManagerOpen,
    isProjectCreateOpen,
    isProjectAnalysisOpen,
    setIsProjectAnalysisOpen,
    newProjectName,
    setNewProjectName,
    newProjectDescription,
    setNewProjectDescription,
    newProjectExecutionMode,
    setNewProjectExecutionMode,
    newProjectAnalyzeOnCreate,
    setNewProjectAnalyzeOnCreate,
    newProjectEnvironments,
    newProjectFrontendEnvironmentKey,
    changeNewProjectFrontendEnvironment,
    newProjectApiEnvironmentKey,
    changeNewProjectApiEnvironment,
    newProjectBaseUrl,
    changeNewProjectBaseUrl,
    newProjectApiBaseUrl,
    changeNewProjectApiBaseUrl,
    newProjectRequestHeadersJson,
    changeNewProjectRequestHeadersJson,
    editingProjectId,
    editingProjectName,
    setEditingProjectName,
    editingProjectDescription,
    setEditingProjectDescription,
    editingProjectExecutionMode,
    setEditingProjectExecutionMode,
    editingProjectEnvironments,
    editingProjectFrontendEnvironmentKey,
    changeEditingProjectFrontendEnvironment,
    editingProjectApiEnvironmentKey,
    changeEditingProjectApiEnvironment,
    editingProjectBaseUrl,
    changeEditingProjectBaseUrl,
    editingProjectApiBaseUrl,
    changeEditingProjectApiBaseUrl,
    editingProjectRequestHeadersJson,
    changeEditingProjectRequestHeadersJson,
    applyProjectSettings,
    ensureEnvironmentJsonReady,
    changeProjectFrontendEnvironment,
    changeProjectApiEnvironment,
    saveProjectRequestHeaders,
    changeProjectExecutionMode,
    openProjectManager,
    openProjectCreateModal,
    cancelProjectCreate,
    startProjectEdit,
    cancelProjectEdit
  };
}
