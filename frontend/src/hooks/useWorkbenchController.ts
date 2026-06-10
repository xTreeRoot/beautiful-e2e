import { useEffect, useMemo, useRef, useState } from 'react';
import { message as AntMessage } from 'antd';

import {
  api,
  demoBootstrap,
  demoCases,
  type Bootstrap,
  type Project,
  type TestCase
} from '../api';
import { buildDsl } from '../lib/canvas';
import { backendNodeTemplates, fullstackNodeTemplates } from '../lib/workbenchConstants';
import type { SidebarMenuKey } from '../types/workbench';
import { useAiProviderConfig } from './useAiProviderConfig';
import { useCaseRunProgress } from './useCaseRunProgress';
import { useGenerateProgress } from './useGenerateProgress';
import { useProjectAnalysisProgress } from './useProjectAnalysisProgress';
import { useWorkbenchCanvas } from './useWorkbenchCanvas';
import { useWorkbenchCaseActions } from './useWorkbenchCaseActions';
import { useWorkbenchCollections } from './useWorkbenchCollections';
import { useWorkbenchProjectActions } from './useWorkbenchProjectActions';
import { useWorkbenchProjectSettings } from './useWorkbenchProjectSettings';

export function useWorkbenchController() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const groups = bootstrap?.groups ?? [];
  const project = bootstrap?.project;
  const projects = bootstrap?.projects?.length ? bootstrap.projects : project ? [project] : [];
  const [activeSidebarMenu, setActiveSidebarMenu] = useState<SidebarMenuKey>('project');
  const [prompt, setPrompt] = useState('');
  const promptRef = useRef('');
  const [status, setStatus] = useState('正在连接后端');
  const [offlineMode, setOfflineMode] = useState(false);
  const {
    executionMode,
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
    projectDirectoryPickTarget,
    newProjectName,
    setNewProjectName,
    newProjectDescription,
    setNewProjectDescription,
    newProjectExecutionMode,
    setNewProjectExecutionMode,
    newProjectAnalyzeOnCreate,
    setNewProjectAnalyzeOnCreate,
    newProjectFrontendPath,
    setNewProjectFrontendPath,
    pickNewProjectFrontendPath,
    newProjectBackendPath,
    setNewProjectBackendPath,
    pickNewProjectBackendPath,
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
    editingProjectFrontendPath,
    setEditingProjectFrontendPath,
    pickEditingProjectFrontendPath,
    editingProjectBackendPath,
    setEditingProjectBackendPath,
    pickEditingProjectBackendPath,
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
  } = useWorkbenchProjectSettings({
    project,
    offlineMode,
    setBootstrap,
    setStatus,
    showToast
  });
  const {
    isGenerating,
    setIsGenerating,
    generateProgress,
    startGenerateProgress,
    closeGenerateProgress,
    appendGenerateProgressLine,
    appendGenerateProgressDelta,
    finishGenerateProgress
  } = useGenerateProgress();
  const {
    projectAnalysisProgress,
    startProjectAnalysisProgress,
    closeProjectAnalysisProgress,
    applyProjectAnalysisProgressEvent,
    finishProjectAnalysisProgress
  } = useProjectAnalysisProgress();
  const {
    isRunningCase,
    setIsRunningCase,
    caseRunProgress,
    startCaseRunProgress,
    openCaseRunProgress,
    closeCaseRunProgress,
    applyCaseRunEvent,
    finishCaseRunWithError
  } = useCaseRunProgress();
  const [isNodeEditorOpen, setIsNodeEditorOpen] = useState(false);
  const {
    cases,
    setCases,
    filteredCases,
    selectedCase,
    activeGroup,
    activeGroupId,
    setActiveGroupId,
    handleActiveGroupChange,
    setSelectedCaseId,
    isGroupCreateOpen,
    newGroupName,
    setNewGroupName,
    newGroupDescription,
    setNewGroupDescription,
    editingGroupId,
    editingGroupName,
    setEditingGroupName,
    editingGroupDescription,
    setEditingGroupDescription,
    groupActionId,
    isCaseCreateOpen,
    newCaseMode,
    setNewCaseMode,
    newCaseTitle,
    setNewCaseTitle,
    newCaseDescription,
    setNewCaseDescription,
    newCaseGroupId,
    setNewCaseGroupId,
    newCasePriority,
    setNewCasePriority,
    editingCaseId,
    editingCaseTitle,
    setEditingCaseTitle,
    editingCaseDescription,
    setEditingCaseDescription,
    editingCaseGroupId,
    setEditingCaseGroupId,
    editingCasePriority,
    setEditingCasePriority,
    editingCaseStatus,
    setEditingCaseStatus,
    caseActionId,
    openGroupCreateModal,
    cancelGroupCreate,
    createManagedGroup,
    startGroupEdit,
    cancelGroupEdit,
    updateManagedGroup,
    deleteManagedGroup,
    openCaseCreateModal,
    cancelCaseCreate,
    createManagedCase,
    startCaseEdit,
    cancelCaseEdit,
    updateManagedCase,
    deleteManagedCase
  } = useWorkbenchCollections({
    project,
    groups,
    executionMode,
    frontendPath,
    backendPath,
    offlineMode,
    setBootstrap,
    setStatus,
    setActiveSidebarMenu,
    showToast
  });
  const {
    projectActionId,
    isCreatingProject,
    isAnalyzingProject,
    refreshProjectList,
    createManagedProject,
    updateManagedProject,
    deleteManagedProject,
    loadProjectWorkspace,
    analyzeCurrentProject
  } = useWorkbenchProjectActions({
    project,
    projects,
    offlineMode,
    newProjectName,
    newProjectDescription,
    newProjectExecutionMode,
    newProjectAnalyzeOnCreate,
    newProjectFrontendPath,
    newProjectBackendPath,
    newProjectEnvironments,
    newProjectFrontendEnvironmentKey,
    newProjectApiEnvironmentKey,
    editingProjectName,
    editingProjectDescription,
    editingProjectExecutionMode,
    editingProjectFrontendPath,
    editingProjectBackendPath,
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
  });
  const {
    flowWrapperRef,
    fitView,
    zoomIn,
    zoomOut,
    nodes,
    edges,
    selectedNode,
    setSelectedNodeId,
    contextToolbox,
    setContextToolbox,
    applyCaseToCanvas,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onPaneContextMenu,
    addNodeFromTemplate,
    updateSelectedNode,
    deleteSelectedNode
  } = useWorkbenchCanvas({ executionMode, updatePrompt, setIsNodeEditorOpen });

  function applyWorkspaceData(data: Bootstrap) {
    setBootstrap(data);
    setActiveGroupId(data.groups[0]?.id ?? 'all');
    applyProjectSettings(data.project);
  }

  function applyUpdatedProject(nextProject: Project) {
    setBootstrap((current) =>
      current
        ? {
            ...current,
            project: current.project.id === nextProject.id ? nextProject : current.project,
            projects: current.projects.map((item) => (item.id === nextProject.id ? nextProject : item))
          }
        : current
    );
    if (project?.id === nextProject.id) applyProjectSettings(nextProject);
  }

  function updatePrompt(value: string) {
    promptRef.current = value;
    setPrompt(value);
  }

  useEffect(() => {
    let ignore = false;

    api
      .bootstrap()
      .then(async (data) => {
        if (ignore) return;
        applyWorkspaceData(data);
        setOfflineMode(false);
        let loadedCases: TestCase[] = [];
        try {
          loadedCases = await api.listCases(data.project.id);
        } catch (error) {
          if (ignore) return;
          const message = error instanceof Error ? error.message : '用例列表加载失败';
          setCases([]);
          setSelectedCaseId(null);
          setStatus(`后端已连接：${data.project.name}；用例列表加载失败：${message}`);
          return;
        }
        if (ignore) return;
        setCases(loadedCases);
        setSelectedCaseId(loadedCases[0]?.id ?? null);
        setStatus(`后端已连接：${data.project.name}`);
      })
      .catch(() => {
        if (ignore) return;
        applyWorkspaceData(demoBootstrap);
        setCases(demoCases);
        setSelectedCaseId(demoCases[0]?.id ?? null);
        setOfflineMode(true);
        setStatus('演示模式：后端不可用');
      });

    return () => {
      ignore = true;
    };
  }, []);

  // 重新生成会保留用例 id，但步骤和图结构会替换，所以这里必须监听用例对象本身。
  useEffect(() => {
    applyCaseToCanvas(selectedCase);
  }, [selectedCase]);

  const availableNodeTemplates = executionMode === 'backend_api' ? backendNodeTemplates : fullstackNodeTemplates;
  const canvasDsl = useMemo(
    () =>
      buildDsl({
        prompt,
        selectedCase,
        group: activeGroup,
        nodes,
        edges,
        baseUrl,
        apiBaseUrl,
        frontendEnvironment: activeFrontendEnvironmentKey,
        apiEnvironment: activeApiEnvironmentKey,
        executionMode
      }),
    [
      prompt,
      selectedCase,
      activeGroup,
      nodes,
      edges,
      baseUrl,
      apiBaseUrl,
      activeFrontendEnvironmentKey,
      activeApiEnvironmentKey,
      executionMode
    ]
  );
  const { isSaving, generateCase, saveCanvas, runCase, runCaseNode, rerunCaseFromProgress } = useWorkbenchCaseActions({
    projectId: project?.id,
    groups,
    cases,
    selectedCase,
    activeGroupId,
    executionMode,
    frontendPath,
    backendPath,
    offlineMode,
    canvasDsl,
    nodes,
    edges,
    environments,
    baseUrl,
    apiBaseUrl,
    activeFrontendEnvironmentKey,
    activeApiEnvironmentKey,
    promptRef,
    caseRunProgress,
    setCases,
    setSelectedCaseId,
    applyCaseToCanvas,
    setStatus,
    showToast,
    setIsGenerating,
    startGenerateProgress,
    appendGenerateProgressLine,
    appendGenerateProgressDelta,
    finishGenerateProgress,
    setIsRunningCase,
    startCaseRunProgress,
    applyCaseRunEvent,
    finishCaseRunWithError
  });

  function showToast(type: 'success' | 'info' | 'warning' | 'error', content: string) {
    void AntMessage[type](content);
  }

  const aiProviderConfig = useAiProviderConfig(showToast);

  return {
    flowWrapperRef,
    fitView,
    zoomIn,
    zoomOut,
    projects,
    project,
    groups,
    cases,
    filteredCases,
    selectedCase,
    selectedNode,
    activeGroup,
    activeGroupId,
    setActiveGroupId,
    handleActiveGroupChange,
    activeSidebarMenu,
    setActiveSidebarMenu,
    setSelectedCaseId,
    prompt,
    setPrompt: updatePrompt,
    executionMode,
    environments,
    activeFrontendEnvironmentKey,
    activeApiEnvironmentKey,
    baseUrl,
    changeBaseUrl,
    apiBaseUrl,
    changeApiBaseUrl,
    requestHeadersJson,
    changeRequestHeadersJson,
    status,
    offlineMode,
    ...aiProviderConfig,
    isGenerating,
    generateProgress,
    closeGenerateProgress,
    projectAnalysisProgress,
    closeProjectAnalysisProgress,
    isSaving,
    isSavingProjectHeaders,
    isRunningCase,
    caseRunProgress,
    openCaseRunProgress,
    closeCaseRunProgress,
    isCreatingProject,
    isAnalyzingProject,
    isNodeEditorOpen,
    setIsNodeEditorOpen,
    isProjectManagerOpen,
    setIsProjectManagerOpen,
    isProjectCreateOpen,
    isProjectAnalysisOpen,
    setIsProjectAnalysisOpen,
    projectDirectoryPickTarget,
    newProjectName,
    setNewProjectName,
    newProjectDescription,
    setNewProjectDescription,
    newProjectExecutionMode,
    setNewProjectExecutionMode,
    newProjectAnalyzeOnCreate,
    setNewProjectAnalyzeOnCreate,
    newProjectFrontendPath,
    setNewProjectFrontendPath,
    pickNewProjectFrontendPath,
    newProjectBackendPath,
    setNewProjectBackendPath,
    pickNewProjectBackendPath,
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
    editingProjectFrontendPath,
    setEditingProjectFrontendPath,
    pickEditingProjectFrontendPath,
    editingProjectBackendPath,
    setEditingProjectBackendPath,
    pickEditingProjectBackendPath,
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
    projectActionId,
    isGroupCreateOpen,
    newGroupName,
    setNewGroupName,
    newGroupDescription,
    setNewGroupDescription,
    editingGroupId,
    editingGroupName,
    setEditingGroupName,
    editingGroupDescription,
    setEditingGroupDescription,
    groupActionId,
    isCaseCreateOpen,
    newCaseMode,
    setNewCaseMode,
    newCaseTitle,
    setNewCaseTitle,
    newCaseDescription,
    setNewCaseDescription,
    newCaseGroupId,
    setNewCaseGroupId,
    newCasePriority,
    setNewCasePriority,
    editingCaseId,
    editingCaseTitle,
    setEditingCaseTitle,
    editingCaseDescription,
    setEditingCaseDescription,
    editingCaseGroupId,
    setEditingCaseGroupId,
    editingCasePriority,
    setEditingCasePriority,
    editingCaseStatus,
    setEditingCaseStatus,
    caseActionId,
    nodes,
    edges,
    contextToolbox,
    setContextToolbox,
    setSelectedNodeId,
    canvasDsl,
    availableNodeTemplates,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onPaneContextMenu,
    changeProjectFrontendEnvironment,
    changeProjectApiEnvironment,
    saveProjectRequestHeaders,
    changeProjectExecutionMode,
    openProjectManager,
    refreshProjectList,
    openProjectCreateModal,
    cancelProjectCreate,
    createManagedProject,
    startProjectEdit,
    cancelProjectEdit,
    updateManagedProject,
    deleteManagedProject,
    openGroupCreateModal,
    cancelGroupCreate,
    createManagedGroup,
    startGroupEdit,
    cancelGroupEdit,
    updateManagedGroup,
    deleteManagedGroup,
    openCaseCreateModal,
    cancelCaseCreate,
    createManagedCase,
    startCaseEdit,
    cancelCaseEdit,
    updateManagedCase,
    deleteManagedCase,
    generateCase,
    saveCanvas,
    runCase,
    runCaseNode,
    rerunCaseFromProgress,
    loadProjectWorkspace,
    analyzeCurrentProject,
    applyUpdatedProject,
    addNodeFromTemplate,
    updateSelectedNode,
    deleteSelectedNode,
    showToast
  };
}

export type WorkbenchController = ReturnType<typeof useWorkbenchController>;
