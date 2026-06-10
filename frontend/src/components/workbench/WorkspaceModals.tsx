import type { Group, Project, TestCase } from '../../api';
import type { ProjectEnvironment } from '../../lib/projectEnvironments';
import type {
  CanvasNode,
  CanvasNodeData,
  CaseCreateMode,
  CaseRunProgressState,
  ExecutionMode,
  NodeDebugDraft
} from '../../types/workbench';
import { NodeEditorModal } from '../NodeEditorModal';
import { ProjectAnalysisModal } from '../ProjectAnalysisModal';
import { CaseCreateModal } from './CaseCreateModal';
import { CaseEditModal } from './CaseEditModal';
import { GroupFormModal } from './GroupModals';
import {
  ProjectCreateModal,
  ProjectEditModal,
  ProjectManagerModal
} from './ProjectModals';

type WorkspaceModalsProps = {
  projects: Project[];
  project?: Project;
  groups: Group[];
  selectedCase?: TestCase;
  selectedNode: CanvasNode | null;
  executionMode: ExecutionMode;
  caseRunProgress: CaseRunProgressState;
  isRunningCase: boolean;
  isSavingCanvas: boolean;
  isNodeEditorOpen: boolean;
  isProjectAnalysisOpen: boolean;
  isProjectManagerOpen: boolean;
  isProjectCreateOpen: boolean;
  isGroupCreateOpen: boolean;
  isAnalyzingProject: boolean;
  projectActionId: string | null;
  groupActionId: string | null;
  caseActionId: string | null;
  newProjectName: string;
  newProjectDescription: string;
  newProjectExecutionMode: ExecutionMode;
  newProjectAnalyzeOnCreate: boolean;
  projectDirectoryPickTarget: string | null;
  newProjectFrontendPath: string;
  newProjectBackendPath: string;
  newProjectEnvironments: ProjectEnvironment[];
  newProjectFrontendEnvironmentKey: string;
  newProjectApiEnvironmentKey: string;
  newProjectBaseUrl: string;
  newProjectApiBaseUrl: string;
  newProjectRequestHeadersJson: string;
  editingProjectId: string | null;
  editingProjectName: string;
  editingProjectDescription: string;
  editingProjectExecutionMode: ExecutionMode;
  editingProjectFrontendPath: string;
  editingProjectBackendPath: string;
  editingProjectEnvironments: ProjectEnvironment[];
  editingProjectFrontendEnvironmentKey: string;
  editingProjectApiEnvironmentKey: string;
  editingProjectBaseUrl: string;
  editingProjectApiBaseUrl: string;
  editingProjectRequestHeadersJson: string;
  newGroupName: string;
  newGroupDescription: string;
  editingGroupId: string | null;
  editingGroupName: string;
  editingGroupDescription: string;
  isCaseCreateOpen: boolean;
  newCaseMode: CaseCreateMode;
  newCaseTitle: string;
  newCaseDescription: string;
  newCaseGroupId: string | null;
  newCasePriority: string;
  editingCaseId: string | null;
  editingCaseTitle: string;
  editingCaseDescription: string;
  editingCaseGroupId: string | null;
  editingCasePriority: string;
  editingCaseStatus: string;
  onCloseNodeEditor: () => void;
  onSaveNodeEditor: () => boolean | void | Promise<boolean | void>;
  onUpdateSelectedNode: (patch: Partial<CanvasNodeData>) => void;
  onDeleteSelectedNode: () => void;
  onDebugNode: (node: CanvasNode, draft: NodeDebugDraft) => void;
  onSelectProject: (projectId: string) => void;
  onCloseProjectAnalysis: () => void;
  onRunProjectAnalysis: () => void;
  onCloseProjectManager: () => void;
  onOpenProjectCreate: () => void;
  onRefreshProjects: () => void;
  onStartProjectEdit: (project: Project) => void;
  onDeleteProject: (projectId: string) => void;
  onNewProjectNameChange: (value: string) => void;
  onNewProjectDescriptionChange: (value: string) => void;
  onNewProjectExecutionModeChange: (mode: ExecutionMode) => void;
  onNewProjectAnalyzeOnCreateChange: (enabled: boolean) => void;
  onNewProjectFrontendPathChange: (value: string) => void;
  onPickNewProjectFrontendPath: () => void;
  onNewProjectBackendPathChange: (value: string) => void;
  onPickNewProjectBackendPath: () => void;
  onNewProjectFrontendEnvironmentChange: (environmentKey: string) => void;
  onNewProjectApiEnvironmentChange: (environmentKey: string) => void;
  onNewProjectBaseUrlChange: (value: string) => void;
  onNewProjectApiBaseUrlChange: (value: string) => void;
  onNewProjectRequestHeadersJsonChange: (value: string) => void;
  onCancelProjectCreate: () => void;
  onCreateProject: () => void;
  onEditingProjectNameChange: (value: string) => void;
  onEditingProjectDescriptionChange: (value: string) => void;
  onEditingProjectExecutionModeChange: (mode: ExecutionMode) => void;
  onEditingProjectFrontendPathChange: (value: string) => void;
  onPickEditingProjectFrontendPath: () => void;
  onEditingProjectBackendPathChange: (value: string) => void;
  onPickEditingProjectBackendPath: () => void;
  onEditingProjectFrontendEnvironmentChange: (environmentKey: string) => void;
  onEditingProjectApiEnvironmentChange: (environmentKey: string) => void;
  onEditingProjectBaseUrlChange: (value: string) => void;
  onEditingProjectApiBaseUrlChange: (value: string) => void;
  onEditingProjectRequestHeadersJsonChange: (value: string) => void;
  onCancelProjectEdit: () => void;
  onSaveProjectEdit: () => void;
  onNewGroupNameChange: (value: string) => void;
  onNewGroupDescriptionChange: (value: string) => void;
  onCancelGroupCreate: () => void;
  onCreateGroup: () => void;
  onEditingGroupNameChange: (value: string) => void;
  onEditingGroupDescriptionChange: (value: string) => void;
  onCancelGroupEdit: () => void;
  onSaveGroupEdit: () => void;
  onNewCaseModeChange: (mode: CaseCreateMode) => void;
  onNewCaseTitleChange: (value: string) => void;
  onNewCaseDescriptionChange: (value: string) => void;
  onNewCaseGroupIdChange: (groupId: string | null) => void;
  onNewCasePriorityChange: (value: string) => void;
  onCancelCaseCreate: () => void;
  onCreateCase: () => void;
  onEditingCaseTitleChange: (value: string) => void;
  onEditingCaseDescriptionChange: (value: string) => void;
  onEditingCaseGroupIdChange: (groupId: string | null) => void;
  onEditingCasePriorityChange: (value: string) => void;
  onEditingCaseStatusChange: (value: string) => void;
  onCancelCaseEdit: () => void;
  onSaveCaseEdit: () => void;
  showToast: (type: 'success' | 'info' | 'warning' | 'error', content: string) => void;
};

export function WorkspaceModals(props: WorkspaceModalsProps) {
  return (
    <>
      <NodeEditorModal
        open={props.isNodeEditorOpen}
        node={props.selectedNode}
        selectedCase={props.selectedCase}
        executionMode={props.executionMode}
        caseRunProgress={props.caseRunProgress}
        isRunning={props.isRunningCase}
        isSaving={props.isSavingCanvas}
        onClose={props.onCloseNodeEditor}
        onSave={props.onSaveNodeEditor}
        onUpdate={props.onUpdateSelectedNode}
        onDelete={props.onDeleteSelectedNode}
        onDebug={props.onDebugNode}
      />
      <ProjectAnalysisModal
        open={props.isProjectAnalysisOpen}
        project={props.project}
        loading={props.isAnalyzingProject}
        onClose={props.onCloseProjectAnalysis}
        onRunAnalysis={props.onRunProjectAnalysis}
        showToast={props.showToast}
      />
      <ProjectManagerModal
        open={props.isProjectManagerOpen}
        projects={props.projects}
        currentProject={props.project}
        actionId={props.projectActionId}
        onClose={props.onCloseProjectManager}
        onOpenCreate={props.onOpenProjectCreate}
        onRefresh={props.onRefreshProjects}
        onSelect={props.onSelectProject}
        onStartEdit={props.onStartProjectEdit}
        onDelete={props.onDeleteProject}
      />
      <ProjectCreateModal
        open={props.isProjectCreateOpen}
        name={props.newProjectName}
        description={props.newProjectDescription}
        executionMode={props.newProjectExecutionMode}
        frontendPath={props.newProjectFrontendPath}
        backendPath={props.newProjectBackendPath}
        environments={props.newProjectEnvironments}
        frontendEnvironmentKey={props.newProjectFrontendEnvironmentKey}
        apiEnvironmentKey={props.newProjectApiEnvironmentKey}
        baseUrl={props.newProjectBaseUrl}
        apiBaseUrl={props.newProjectApiBaseUrl}
        requestHeadersJson={props.newProjectRequestHeadersJson}
        analyzeOnCreate={props.newProjectAnalyzeOnCreate}
        loading={props.projectActionId === '__create'}
        pickingFrontendPath={props.projectDirectoryPickTarget === 'new-project-frontend'}
        pickingBackendPath={props.projectDirectoryPickTarget === 'new-project-backend'}
        onNameChange={props.onNewProjectNameChange}
        onDescriptionChange={props.onNewProjectDescriptionChange}
        onExecutionModeChange={props.onNewProjectExecutionModeChange}
        onFrontendPathChange={props.onNewProjectFrontendPathChange}
        onBackendPathChange={props.onNewProjectBackendPathChange}
        onPickFrontendPath={props.onPickNewProjectFrontendPath}
        onPickBackendPath={props.onPickNewProjectBackendPath}
        onFrontendEnvironmentChange={props.onNewProjectFrontendEnvironmentChange}
        onApiEnvironmentChange={props.onNewProjectApiEnvironmentChange}
        onBaseUrlChange={props.onNewProjectBaseUrlChange}
        onApiBaseUrlChange={props.onNewProjectApiBaseUrlChange}
        onRequestHeadersJsonChange={props.onNewProjectRequestHeadersJsonChange}
        onAnalyzeOnCreateChange={props.onNewProjectAnalyzeOnCreateChange}
        onCancel={props.onCancelProjectCreate}
        onCreate={props.onCreateProject}
      />
      <ProjectEditModal
        open={Boolean(props.editingProjectId)}
        name={props.editingProjectName}
        description={props.editingProjectDescription}
        executionMode={props.editingProjectExecutionMode}
        frontendPath={props.editingProjectFrontendPath}
        backendPath={props.editingProjectBackendPath}
        environments={props.editingProjectEnvironments}
        frontendEnvironmentKey={props.editingProjectFrontendEnvironmentKey}
        apiEnvironmentKey={props.editingProjectApiEnvironmentKey}
        baseUrl={props.editingProjectBaseUrl}
        apiBaseUrl={props.editingProjectApiBaseUrl}
        requestHeadersJson={props.editingProjectRequestHeadersJson}
        loading={props.editingProjectId ? props.projectActionId === props.editingProjectId : false}
        pickingFrontendPath={props.projectDirectoryPickTarget === 'editing-project-frontend'}
        pickingBackendPath={props.projectDirectoryPickTarget === 'editing-project-backend'}
        onNameChange={props.onEditingProjectNameChange}
        onDescriptionChange={props.onEditingProjectDescriptionChange}
        onExecutionModeChange={props.onEditingProjectExecutionModeChange}
        onFrontendPathChange={props.onEditingProjectFrontendPathChange}
        onBackendPathChange={props.onEditingProjectBackendPathChange}
        onPickFrontendPath={props.onPickEditingProjectFrontendPath}
        onPickBackendPath={props.onPickEditingProjectBackendPath}
        onFrontendEnvironmentChange={props.onEditingProjectFrontendEnvironmentChange}
        onApiEnvironmentChange={props.onEditingProjectApiEnvironmentChange}
        onBaseUrlChange={props.onEditingProjectBaseUrlChange}
        onApiBaseUrlChange={props.onEditingProjectApiBaseUrlChange}
        onRequestHeadersJsonChange={props.onEditingProjectRequestHeadersJsonChange}
        onCancel={props.onCancelProjectEdit}
        onSave={props.onSaveProjectEdit}
      />
      <GroupFormModal
        open={props.isGroupCreateOpen}
        title="新建分组"
        name={props.newGroupName}
        description={props.newGroupDescription}
        loading={props.groupActionId === '__create'}
        submitLabel="新建"
        submitIcon="plus"
        onNameChange={props.onNewGroupNameChange}
        onDescriptionChange={props.onNewGroupDescriptionChange}
        onCancel={props.onCancelGroupCreate}
        onSubmit={props.onCreateGroup}
      />
      <GroupFormModal
        open={Boolean(props.editingGroupId)}
        title="编辑分组"
        name={props.editingGroupName}
        description={props.editingGroupDescription}
        loading={props.editingGroupId ? props.groupActionId === props.editingGroupId : false}
        submitLabel="保存"
        submitIcon="save"
        onNameChange={props.onEditingGroupNameChange}
        onDescriptionChange={props.onEditingGroupDescriptionChange}
        onCancel={props.onCancelGroupEdit}
        onSubmit={props.onSaveGroupEdit}
      />
      <CaseCreateModal
        open={props.isCaseCreateOpen}
        mode={props.newCaseMode}
        groups={props.groups}
        title={props.newCaseTitle}
        description={props.newCaseDescription}
        groupId={props.newCaseGroupId}
        priority={props.newCasePriority}
        loading={props.caseActionId === '__create'}
        onModeChange={props.onNewCaseModeChange}
        onTitleChange={props.onNewCaseTitleChange}
        onDescriptionChange={props.onNewCaseDescriptionChange}
        onGroupIdChange={props.onNewCaseGroupIdChange}
        onPriorityChange={props.onNewCasePriorityChange}
        onCancel={props.onCancelCaseCreate}
        onSubmit={props.onCreateCase}
      />
      <CaseEditModal
        open={Boolean(props.editingCaseId)}
        groups={props.groups}
        title={props.editingCaseTitle}
        description={props.editingCaseDescription}
        groupId={props.editingCaseGroupId}
        priority={props.editingCasePriority}
        status={props.editingCaseStatus}
        loading={props.editingCaseId ? props.caseActionId === props.editingCaseId : false}
        onTitleChange={props.onEditingCaseTitleChange}
        onDescriptionChange={props.onEditingCaseDescriptionChange}
        onGroupIdChange={props.onEditingCaseGroupIdChange}
        onPriorityChange={props.onEditingCasePriorityChange}
        onStatusChange={props.onEditingCaseStatusChange}
        onCancel={props.onCancelCaseEdit}
        onSave={props.onSaveCaseEdit}
      />
    </>
  );
}
