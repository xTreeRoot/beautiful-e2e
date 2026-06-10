import { ConfigProvider, Layout as AntLayout } from 'antd';
import { useState } from 'react';

import type { WorkbenchController } from '../../hooks/useWorkbenchController';
import { AiConfigModal } from './AiConfigModal';
import { CaseRunProgressDrawer } from './CaseRunProgressDrawer';
import { DslPreviewModal } from './DslPreviewModal';
import { GenerateProgressModal } from './GenerateProgressModal';
import { ProjectAnalysisProgressModal } from './ProjectAnalysisProgressModal';
import { WorkspaceMain } from './WorkspaceMain';
import { WorkspaceModals } from './WorkspaceModals';
import { WorkspaceSidebar } from './WorkspaceSidebar';

type WorkbenchAppViewProps = {
  controller: WorkbenchController;
};

export function WorkbenchAppView({ controller }: WorkbenchAppViewProps) {
  const [isDslPreviewOpen, setIsDslPreviewOpen] = useState(false);
  const {
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
    handleActiveGroupChange,
    activeSidebarMenu,
    setActiveSidebarMenu,
    setSelectedCaseId,
    prompt,
    setPrompt,
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
    aiProviderStatus,
    aiProviderForm,
    isAiConfigOpen,
    isLoadingAiProvider,
    isSavingAiProvider,
    aiProviderError,
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
    openAiConfig,
    closeAiConfig,
    loadAiProviderStatus,
    updateAiProviderForm,
    saveAiProviderConfig,
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
  } = controller;
  const hasCaseRunSnapshot = caseRunProgress.runId > 0 && caseRunProgress.phase !== 'idle';

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#1f7a6a',
          borderRadius: 8,
          colorText: '#222833',
          fontFamily:
            'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
        }
      }}
    >
      <AntLayout className="app-shell">
        <WorkspaceSidebar
          activeMenu={activeSidebarMenu}
          onMenuChange={setActiveSidebarMenu}
          executionMode={executionMode}
          onExecutionModeChange={(mode) => void changeProjectExecutionMode(mode)}
          project={project}
          groups={groups}
          cases={cases}
          filteredCases={filteredCases}
          selectedCase={selectedCase}
          activeGroupId={activeGroupId}
          environments={environments}
          activeFrontendEnvironmentKey={activeFrontendEnvironmentKey}
          activeApiEnvironmentKey={activeApiEnvironmentKey}
          baseUrl={baseUrl}
          apiBaseUrl={apiBaseUrl}
          requestHeadersJson={requestHeadersJson}
          isCreatingProject={isCreatingProject}
          isAnalyzingProject={isAnalyzingProject}
          isSavingProjectHeaders={isSavingProjectHeaders}
          groupActionId={groupActionId}
          caseActionId={caseActionId}
          onFrontendEnvironmentChange={changeProjectFrontendEnvironment}
          onApiEnvironmentChange={changeProjectApiEnvironment}
          onBaseUrlChange={changeBaseUrl}
          onApiBaseUrlChange={changeApiBaseUrl}
          onRequestHeadersJsonChange={changeRequestHeadersJson}
          onSaveProjectRequestHeaders={() => void saveProjectRequestHeaders()}
          onOpenProjectCreate={openProjectCreateModal}
          onOpenProjectManager={openProjectManager}
          onOpenProjectAnalysis={() => setIsProjectAnalysisOpen(true)}
          onOpenGroupCreate={openGroupCreateModal}
          onActiveGroupChange={handleActiveGroupChange}
          onStartGroupEdit={startGroupEdit}
          onDeleteGroup={(groupId) => void deleteManagedGroup(groupId)}
          onOpenCaseCreate={openCaseCreateModal}
          onSelectedCaseChange={setSelectedCaseId}
          onStartCaseEdit={startCaseEdit}
          onDeleteCase={(caseId) => void deleteManagedCase(caseId)}
        />

        <WorkspaceMain
          flowWrapperRef={flowWrapperRef}
          executionMode={executionMode}
          activeGroup={activeGroup}
          selectedCase={selectedCase}
          status={status}
          offlineMode={offlineMode}
          isGenerating={isGenerating}
          isSaving={isSaving}
          isRunningCase={isRunningCase}
          hasCaseRunSnapshot={hasCaseRunSnapshot}
          prompt={prompt}
          templates={availableNodeTemplates}
          nodes={nodes}
          edges={edges}
          contextToolbox={contextToolbox}
          onPromptChange={setPrompt}
          onGenerate={() => void generateCase()}
          onOpenAiConfig={openAiConfig}
          onSaveCanvas={() => void saveCanvas()}
          onRunCase={() => void runCase()}
          onOpenCaseRunSnapshot={openCaseRunProgress}
          onOpenDsl={() => setIsDslPreviewOpen(true)}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onPaneContextMenu={onPaneContextMenu}
          onCloseContextToolbox={() => setContextToolbox(null)}
          onSelectedNodeChange={(nodeId) => {
            setContextToolbox(null);
            setSelectedNodeId(nodeId);
            setIsNodeEditorOpen(true);
          }}
          onAddNode={addNodeFromTemplate}
          onZoomIn={() => zoomIn({ duration: 180 })}
          onZoomOut={() => zoomOut({ duration: 180 })}
          onFitView={() => fitView({ padding: 0.18, duration: 180 })}
        />
      </AntLayout>

      <GenerateProgressModal progress={generateProgress} onConfirm={closeGenerateProgress} />
      <ProjectAnalysisProgressModal
        progress={projectAnalysisProgress}
        onConfirm={closeProjectAnalysisProgress}
      />
      <AiConfigModal
        open={isAiConfigOpen}
        status={aiProviderStatus}
        form={aiProviderForm}
        loading={isLoadingAiProvider}
        saving={isSavingAiProvider}
        error={aiProviderError}
        onClose={closeAiConfig}
        onRefresh={() => void loadAiProviderStatus()}
        onSave={() => void saveAiProviderConfig()}
        onFormChange={updateAiProviderForm}
      />
      <DslPreviewModal
        open={isDslPreviewOpen}
        selectedCase={selectedCase}
        canvasDsl={canvasDsl}
        onClose={() => setIsDslPreviewOpen(false)}
      />
      <CaseRunProgressDrawer
        progress={caseRunProgress}
        isRerunning={isRunningCase}
        onRerun={rerunCaseFromProgress}
        onClose={closeCaseRunProgress}
      />

      <WorkspaceModals
        projects={projects}
        project={project}
        groups={groups}
        selectedCase={selectedCase}
        selectedNode={selectedNode}
        executionMode={executionMode}
        caseRunProgress={caseRunProgress}
        isRunningCase={isRunningCase}
        isSavingCanvas={isSaving}
        isNodeEditorOpen={isNodeEditorOpen}
        isProjectAnalysisOpen={isProjectAnalysisOpen}
        isProjectManagerOpen={isProjectManagerOpen}
        isProjectCreateOpen={isProjectCreateOpen}
        isGroupCreateOpen={isGroupCreateOpen}
        isAnalyzingProject={isAnalyzingProject}
        projectActionId={projectActionId}
        groupActionId={groupActionId}
        caseActionId={caseActionId}
        newProjectName={newProjectName}
        newProjectDescription={newProjectDescription}
        newProjectExecutionMode={newProjectExecutionMode}
        newProjectAnalyzeOnCreate={newProjectAnalyzeOnCreate}
        projectDirectoryPickTarget={projectDirectoryPickTarget}
        newProjectFrontendPath={newProjectFrontendPath}
        newProjectBackendPath={newProjectBackendPath}
        newProjectEnvironments={newProjectEnvironments}
        newProjectFrontendEnvironmentKey={newProjectFrontendEnvironmentKey}
        newProjectApiEnvironmentKey={newProjectApiEnvironmentKey}
        newProjectBaseUrl={newProjectBaseUrl}
        newProjectApiBaseUrl={newProjectApiBaseUrl}
        newProjectRequestHeadersJson={newProjectRequestHeadersJson}
        editingProjectId={editingProjectId}
        editingProjectName={editingProjectName}
        editingProjectDescription={editingProjectDescription}
        editingProjectExecutionMode={editingProjectExecutionMode}
        editingProjectFrontendPath={editingProjectFrontendPath}
        editingProjectBackendPath={editingProjectBackendPath}
        editingProjectEnvironments={editingProjectEnvironments}
        editingProjectFrontendEnvironmentKey={editingProjectFrontendEnvironmentKey}
        editingProjectApiEnvironmentKey={editingProjectApiEnvironmentKey}
        editingProjectBaseUrl={editingProjectBaseUrl}
        editingProjectApiBaseUrl={editingProjectApiBaseUrl}
        editingProjectRequestHeadersJson={editingProjectRequestHeadersJson}
        newGroupName={newGroupName}
        newGroupDescription={newGroupDescription}
        editingGroupId={editingGroupId}
        editingGroupName={editingGroupName}
        editingGroupDescription={editingGroupDescription}
        isCaseCreateOpen={isCaseCreateOpen}
        newCaseMode={newCaseMode}
        newCaseTitle={newCaseTitle}
        newCaseDescription={newCaseDescription}
        newCaseGroupId={newCaseGroupId}
        newCasePriority={newCasePriority}
        editingCaseId={editingCaseId}
        editingCaseTitle={editingCaseTitle}
        editingCaseDescription={editingCaseDescription}
        editingCaseGroupId={editingCaseGroupId}
        editingCasePriority={editingCasePriority}
        editingCaseStatus={editingCaseStatus}
        onCloseNodeEditor={() => setIsNodeEditorOpen(false)}
        onSaveNodeEditor={saveCanvas}
        onUpdateSelectedNode={updateSelectedNode}
        onDeleteSelectedNode={deleteSelectedNode}
        onDebugNode={(node, draft) => void runCaseNode(node, draft)}
        onSelectProject={(projectId) => void loadProjectWorkspace(projectId)}
        onCloseProjectAnalysis={() => setIsProjectAnalysisOpen(false)}
        onRunProjectAnalysis={() => void analyzeCurrentProject()}
        onProjectUpdated={applyUpdatedProject}
        onCloseProjectManager={() => {
          setIsProjectManagerOpen(false);
          cancelProjectCreate();
          cancelProjectEdit();
        }}
        onOpenProjectCreate={openProjectCreateModal}
        onRefreshProjects={() => void refreshProjectList()}
        onStartProjectEdit={startProjectEdit}
        onDeleteProject={(projectId) => void deleteManagedProject(projectId)}
        onNewProjectNameChange={setNewProjectName}
        onNewProjectDescriptionChange={setNewProjectDescription}
        onNewProjectExecutionModeChange={setNewProjectExecutionMode}
        onNewProjectAnalyzeOnCreateChange={setNewProjectAnalyzeOnCreate}
        onNewProjectFrontendPathChange={setNewProjectFrontendPath}
        onPickNewProjectFrontendPath={() => void pickNewProjectFrontendPath()}
        onNewProjectBackendPathChange={setNewProjectBackendPath}
        onPickNewProjectBackendPath={() => void pickNewProjectBackendPath()}
        onNewProjectFrontendEnvironmentChange={changeNewProjectFrontendEnvironment}
        onNewProjectApiEnvironmentChange={changeNewProjectApiEnvironment}
        onNewProjectBaseUrlChange={changeNewProjectBaseUrl}
        onNewProjectApiBaseUrlChange={changeNewProjectApiBaseUrl}
        onNewProjectRequestHeadersJsonChange={changeNewProjectRequestHeadersJson}
        onCancelProjectCreate={cancelProjectCreate}
        onCreateProject={() => void createManagedProject()}
        onEditingProjectNameChange={setEditingProjectName}
        onEditingProjectDescriptionChange={setEditingProjectDescription}
        onEditingProjectExecutionModeChange={setEditingProjectExecutionMode}
        onEditingProjectFrontendPathChange={setEditingProjectFrontendPath}
        onPickEditingProjectFrontendPath={() => void pickEditingProjectFrontendPath()}
        onEditingProjectBackendPathChange={setEditingProjectBackendPath}
        onPickEditingProjectBackendPath={() => void pickEditingProjectBackendPath()}
        onEditingProjectFrontendEnvironmentChange={changeEditingProjectFrontendEnvironment}
        onEditingProjectApiEnvironmentChange={changeEditingProjectApiEnvironment}
        onEditingProjectBaseUrlChange={changeEditingProjectBaseUrl}
        onEditingProjectApiBaseUrlChange={changeEditingProjectApiBaseUrl}
        onEditingProjectRequestHeadersJsonChange={changeEditingProjectRequestHeadersJson}
        onCancelProjectEdit={cancelProjectEdit}
        onSaveProjectEdit={() => {
          if (editingProjectId) void updateManagedProject(editingProjectId);
        }}
        onNewGroupNameChange={setNewGroupName}
        onNewGroupDescriptionChange={setNewGroupDescription}
        onCancelGroupCreate={cancelGroupCreate}
        onCreateGroup={() => void createManagedGroup()}
        onEditingGroupNameChange={setEditingGroupName}
        onEditingGroupDescriptionChange={setEditingGroupDescription}
        onCancelGroupEdit={cancelGroupEdit}
        onSaveGroupEdit={() => {
          if (editingGroupId) void updateManagedGroup(editingGroupId);
        }}
        onNewCaseModeChange={setNewCaseMode}
        onNewCaseTitleChange={setNewCaseTitle}
        onNewCaseDescriptionChange={setNewCaseDescription}
        onNewCaseGroupIdChange={setNewCaseGroupId}
        onNewCasePriorityChange={setNewCasePriority}
        onCancelCaseCreate={cancelCaseCreate}
        onCreateCase={() => void createManagedCase()}
        onEditingCaseTitleChange={setEditingCaseTitle}
        onEditingCaseDescriptionChange={setEditingCaseDescription}
        onEditingCaseGroupIdChange={setEditingCaseGroupId}
        onEditingCasePriorityChange={setEditingCasePriority}
        onEditingCaseStatusChange={setEditingCaseStatus}
        onCancelCaseEdit={cancelCaseEdit}
        onSaveCaseEdit={() => {
          if (editingCaseId) void updateManagedCase(editingCaseId);
        }}
        showToast={showToast}
      />
    </ConfigProvider>
  );
}
