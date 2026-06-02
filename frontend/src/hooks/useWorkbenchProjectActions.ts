import { useState, type Dispatch, type SetStateAction } from 'react';

import { api, type Bootstrap, type Project, type ProjectAnalysisStreamEvent, type TestCase } from '../api';
import { environmentSettingsPatch, type ProjectEnvironment } from '../lib/projectEnvironments';
import type { ExecutionMode, ProjectAnalysisProgressState } from '../types/workbench';

type ToastType = 'success' | 'info' | 'warning' | 'error';

type UseWorkbenchProjectActionsOptions = {
  project?: Project;
  projects: Project[];
  offlineMode: boolean;
  workspacePath: string | undefined;
  newProjectName: string;
  newProjectDescription: string;
  newProjectExecutionMode: ExecutionMode;
  newProjectAnalyzeOnCreate: boolean;
  newProjectEnvironments: ProjectEnvironment[];
  newProjectFrontendEnvironmentKey: string;
  newProjectApiEnvironmentKey: string;
  editingProjectName: string;
  editingProjectDescription: string;
  editingProjectExecutionMode: ExecutionMode;
  editingProjectEnvironments: ProjectEnvironment[];
  editingProjectFrontendEnvironmentKey: string;
  editingProjectApiEnvironmentKey: string;
  setBootstrap: Dispatch<SetStateAction<Bootstrap | null>>;
  setCases: Dispatch<SetStateAction<TestCase[]>>;
  setSelectedCaseId: Dispatch<SetStateAction<string | null>>;
  setActiveGroupId: Dispatch<SetStateAction<string>>;
  setStatus: (status: string) => void;
  applyProjectSettings: (project: Project) => void;
  ensureEnvironmentJsonReady: (environments: ProjectEnvironment[]) => boolean;
  cancelProjectCreate: () => void;
  cancelProjectEdit: () => void;
  startProjectAnalysisProgress: (options: {
    runId: number;
    projectName: string;
    initialLine?: string;
  }) => void;
  applyProjectAnalysisProgressEvent: (
    runId: number,
    event: ProjectAnalysisStreamEvent
  ) => void;
  finishProjectAnalysisProgress: (
    runId: number,
    phase: Extract<ProjectAnalysisProgressState['phase'], 'complete' | 'error'>,
    detail: string
  ) => void;
  showToast: (type: ToastType, content: string) => void;
};

/**
 * 管理项目级异步动作。
 * 项目刷新、切换、创建和分析会同时改 bootstrap 与用例集合，集中在这里可以让 controller 不再承载项目事务细节。
 */
export function useWorkbenchProjectActions({
  project,
  projects,
  offlineMode,
  workspacePath,
  newProjectName,
  newProjectDescription,
  newProjectExecutionMode,
  newProjectAnalyzeOnCreate,
  newProjectEnvironments,
  newProjectFrontendEnvironmentKey,
  newProjectApiEnvironmentKey,
  editingProjectName,
  editingProjectDescription,
  editingProjectExecutionMode,
  editingProjectEnvironments,
  editingProjectFrontendEnvironmentKey,
  editingProjectApiEnvironmentKey,
  setBootstrap,
  setCases,
  setSelectedCaseId,
  setActiveGroupId,
  setStatus,
  applyProjectSettings,
  ensureEnvironmentJsonReady,
  cancelProjectCreate,
  cancelProjectEdit,
  startProjectAnalysisProgress,
  applyProjectAnalysisProgressEvent,
  finishProjectAnalysisProgress,
  showToast
}: UseWorkbenchProjectActionsOptions) {
  const [projectActionId, setProjectActionId] = useState<string | null>(null);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [isAnalyzingProject, setIsAnalyzingProject] = useState(false);

  async function refreshProjectList() {
    if (offlineMode) {
      const message = '后端未连接，暂时不能刷新项目列表';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setProjectActionId('__refresh');
    try {
      const refreshed = await api.listProjects();
      const refreshedProject = refreshed.find((item) => item.id === project?.id);
      setBootstrap((current) =>
        current
          ? {
              ...current,
              project: refreshed.find((item) => item.id === current.project.id) ?? current.project,
              projects: refreshed
            }
          : current
      );
      if (refreshedProject) applyProjectSettings(refreshedProject);
      setStatus('项目列表已刷新');
      showToast('success', '项目列表已刷新');
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目刷新失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setProjectActionId(null);
    }
  }

  async function createManagedProject() {
    const name = newProjectName.trim();
    if (!name) {
      showToast('warning', '请输入项目名称');
      return;
    }
    if (offlineMode) {
      const message = '后端未连接，暂时不能新建项目';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setProjectActionId('__create');
    try {
      if (!ensureEnvironmentJsonReady(newProjectEnvironments)) return;
      const settingsPatch = environmentSettingsPatch(
        newProjectEnvironments,
        newProjectFrontendEnvironmentKey,
        newProjectApiEnvironmentKey
      );
      const created = await api.createProject({
        name,
        description: newProjectDescription.trim() || undefined,
        settings: {
          execution_mode: newProjectExecutionMode,
          frontend_repo_path: '',
          backend_repo_path: '',
          workspace_path: '',
          ...settingsPatch
        },
        analyze_on_create: newProjectAnalyzeOnCreate
      });
      cancelProjectCreate();
      await loadProjectWorkspace(created.id);
      setStatus(`项目已创建：${created.name}`);
      showToast('success', `项目已创建：${created.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目创建失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setProjectActionId(null);
    }
  }

  async function updateManagedProject(projectId: string) {
    const name = editingProjectName.trim();
    if (!name) {
      showToast('warning', '请输入项目名称');
      return;
    }
    setProjectActionId(projectId);
    try {
      if (!ensureEnvironmentJsonReady(editingProjectEnvironments)) return;
      const settingsPatch = environmentSettingsPatch(
        editingProjectEnvironments,
        editingProjectFrontendEnvironmentKey,
        editingProjectApiEnvironmentKey
      );
      const saved = await api.updateProject(projectId, {
        name,
        description: editingProjectDescription.trim() || null,
        execution_mode: editingProjectExecutionMode,
        base_url: settingsPatch.base_url,
        api_base_url: settingsPatch.api_base_url,
        settings: settingsPatch
      });
      setBootstrap((current) =>
        current
          ? {
              ...current,
              project: current.project.id === saved.id ? saved : current.project,
              projects: current.projects.map((item) => (item.id === saved.id ? saved : item))
            }
          : current
      );
      if (project?.id === saved.id) applyProjectSettings(saved);
      cancelProjectEdit();
      setStatus(`项目已更新：${saved.name}`);
      showToast('success', `项目已更新：${saved.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目更新失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setProjectActionId(null);
    }
  }

  async function deleteManagedProject(projectId: string) {
    if (projects.length <= 1) {
      showToast('warning', '至少保留一个项目');
      return;
    }
    const deletingCurrent = project?.id === projectId;
    const fallback = projects.find((item) => item.id !== projectId);
    setProjectActionId(projectId);
    try {
      await api.deleteProject(projectId);
      cancelProjectEdit();
      if (deletingCurrent && fallback) {
        await loadProjectWorkspace(fallback.id);
      } else {
        setBootstrap((current) =>
          current
            ? {
                ...current,
                projects: current.projects.filter((item) => item.id !== projectId)
              }
            : current
        );
      }
      setStatus('项目已删除');
      showToast('success', '项目已删除');
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目删除失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setProjectActionId(null);
    }
  }

  async function loadProjectWorkspace(projectId: string) {
    if (offlineMode) {
      const message = '后端未连接，暂时不能切换项目';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setStatus('正在加载项目工作区');
    try {
      const data = await api.loadProjectWorkspace(projectId);
      setBootstrap(data);
      setActiveGroupId(data.groups[0]?.id ?? 'all');
      applyProjectSettings(data.project);
      const loadedCases = await api.listCases(data.project.id);
      setCases(loadedCases);
      setSelectedCaseId(loadedCases[0]?.id ?? null);
      setStatus(`已选择项目：${data.project.name}`);
      showToast('success', `已选择项目：${data.project.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目加载失败';
      setStatus(message);
      showToast('error', message);
    }
  }

  async function createProjectFromLocalDirectory() {
    if (offlineMode) {
      const message = '后端未连接，暂时不能从本地新建项目';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    setIsCreatingProject(true);
    setStatus('请选择本地项目目录');
    try {
      const picked = await api.pickDirectory({
        title: '选择本地项目目录',
        initial_path: workspacePath || undefined
      });
      if (!picked.path) {
        setStatus('项目创建已取消');
        showToast('info', '已取消新建项目');
        return;
      }
      const created = await api.createProjectFromDirectory({
        path: picked.path,
        analyze_on_create: newProjectAnalyzeOnCreate
      });
      await loadProjectWorkspace(created.id);
      setStatus(`项目已创建：${created.name}`);
      showToast('success', `已新建项目：${created.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '项目创建失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setIsCreatingProject(false);
    }
  }

  async function analyzeCurrentProject() {
    if (!project || offlineMode) {
      const message = '后端未连接，暂时不能更新项目分析';
      setStatus(message);
      showToast('warning', message);
      return;
    }
    const runId = Date.now();
    startProjectAnalysisProgress({
      runId,
      projectName: project.name,
      initialLine: `准备重新分析项目：${project.name}`
    });
    setIsAnalyzingProject(true);
    setProjectActionId('__analyze');
    setStatus('正在分析项目仓库');
    try {
      const analyzed = await api.analyzeProjectStream(project.id, (event) => {
        applyProjectAnalysisProgressEvent(runId, event);
      });
      setBootstrap((current) =>
        current
          ? {
              ...current,
              project: analyzed,
              projects: current.projects.map((item) => (item.id === analyzed.id ? analyzed : item))
            }
          : current
      );
      applyProjectSettings(analyzed);
      setStatus(`项目分析已更新：${analyzed.name}`);
      finishProjectAnalysisProgress(runId, 'complete', `项目分析已更新：${analyzed.name}`);
      showToast('success', '项目分析已更新');
    } catch (error) {
      const rawMessage = error instanceof Error ? error.message : '项目分析失败';
      const message = rawMessage.includes('Not Found') ? '分析接口未加载，请重启后端服务后再试' : rawMessage;
      setStatus(message);
      finishProjectAnalysisProgress(runId, 'error', message);
      showToast('error', message);
    } finally {
      setIsAnalyzingProject(false);
      setProjectActionId(null);
    }
  }

  return {
    projectActionId,
    isCreatingProject,
    isAnalyzingProject,
    refreshProjectList,
    createManagedProject,
    updateManagedProject,
    deleteManagedProject,
    loadProjectWorkspace,
    createProjectFromLocalDirectory,
    analyzeCurrentProject
  };
}
