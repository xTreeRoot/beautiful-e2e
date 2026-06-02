import {
  Button,
  Card,
  Flex,
  Input,
  Layout,
  List,
  Menu,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Tag,
  Typography
} from 'antd';
import {
  Boxes,
  FileInput,
  FolderOpen,
  GitBranch,
  Globe2,
  Network,
  Pencil,
  PlugZap,
  Plus,
  RefreshCw,
  Save,
  Settings,
  Trash2,
  Workflow
} from 'lucide-react';

import type { Group, Project, TestCase } from '../../api';
import { formatExecutionMode, getProjectExecutionMode } from '../../lib/project';
import { environmentOptions, type ProjectEnvironment } from '../../lib/projectEnvironments';
import type { ExecutionMode, SidebarMenuKey } from '../../types/workbench';
import { SectionTitle } from '../SectionTitle';
import { RequestHeadersEditor } from './RequestHeadersEditor';

const { Sider } = Layout;
const { Text, Title } = Typography;

type WorkspaceSidebarProps = {
  activeMenu: SidebarMenuKey;
  onMenuChange: (key: SidebarMenuKey) => void;
  executionMode: ExecutionMode;
  onExecutionModeChange: (mode: ExecutionMode) => void;
  project?: Project;
  groups: Group[];
  cases: TestCase[];
  filteredCases: TestCase[];
  selectedCase?: TestCase;
  activeGroupId: string;
  environments: ProjectEnvironment[];
  activeFrontendEnvironmentKey: string;
  activeApiEnvironmentKey: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
  isCreatingProject: boolean;
  isAnalyzingProject: boolean;
  isSavingProjectHeaders: boolean;
  groupActionId: string | null;
  caseActionId: string | null;
  onFrontendEnvironmentChange: (environmentKey: string) => void;
  onApiEnvironmentChange: (environmentKey: string) => void;
  onBaseUrlChange: (value: string) => void;
  onApiBaseUrlChange: (value: string) => void;
  onRequestHeadersJsonChange: (value: string) => void;
  onSaveProjectRequestHeaders: () => void;
  onCreateProjectFromDirectory: () => void;
  onOpenProjectManager: () => void;
  onOpenProjectAnalysis: () => void;
  onOpenGroupCreate: () => void;
  onActiveGroupChange: (groupId: string) => void;
  onStartGroupEdit: (group: Group) => void;
  onDeleteGroup: (groupId: string) => void;
  onOpenCaseCreate: () => void;
  onSelectedCaseChange: (caseId: string) => void;
  onStartCaseEdit: (testCase: TestCase) => void;
  onDeleteCase: (caseId: string) => void;
};

export function WorkspaceSidebar({
  activeMenu,
  onMenuChange,
  executionMode,
  onExecutionModeChange,
  project,
  groups,
  cases,
  filteredCases,
  selectedCase,
  activeGroupId,
  environments,
  activeFrontendEnvironmentKey,
  activeApiEnvironmentKey,
  baseUrl,
  apiBaseUrl,
  requestHeadersJson,
  isCreatingProject,
  isAnalyzingProject,
  isSavingProjectHeaders,
  groupActionId,
  caseActionId,
  onFrontendEnvironmentChange,
  onApiEnvironmentChange,
  onBaseUrlChange,
  onApiBaseUrlChange,
  onRequestHeadersJsonChange,
  onSaveProjectRequestHeaders,
  onCreateProjectFromDirectory,
  onOpenProjectManager,
  onOpenProjectAnalysis,
  onOpenGroupCreate,
  onActiveGroupChange,
  onStartGroupEdit,
  onDeleteGroup,
  onOpenCaseCreate,
  onSelectedCaseChange,
  onStartCaseEdit,
  onDeleteCase
}: WorkspaceSidebarProps) {
  return (
    <Sider className="sidebar" width={380} theme="light" aria-label="项目控制">
      <BrandHeader />

      <Menu
        className="workspace-menu"
        mode="inline"
        selectedKeys={[activeMenu]}
        onClick={({ key }) => onMenuChange(key as SidebarMenuKey)}
        items={[
          { key: 'project', icon: <Settings size={16} />, label: '项目' },
          { key: 'groups', icon: <GitBranch size={16} />, label: '测试分组' },
          { key: 'cases', icon: <FileInput size={16} />, label: '用例库' }
        ]}
      />

      {activeMenu === 'project' ? (
        <ProjectSidebarPanel
          executionMode={executionMode}
          project={project}
          environments={environments}
          activeFrontendEnvironmentKey={activeFrontendEnvironmentKey}
          activeApiEnvironmentKey={activeApiEnvironmentKey}
          baseUrl={baseUrl}
          apiBaseUrl={apiBaseUrl}
          requestHeadersJson={requestHeadersJson}
          isCreatingProject={isCreatingProject}
          isAnalyzingProject={isAnalyzingProject}
          isSavingProjectHeaders={isSavingProjectHeaders}
          onExecutionModeChange={onExecutionModeChange}
          onFrontendEnvironmentChange={onFrontendEnvironmentChange}
          onApiEnvironmentChange={onApiEnvironmentChange}
          onBaseUrlChange={onBaseUrlChange}
          onApiBaseUrlChange={onApiBaseUrlChange}
          onRequestHeadersJsonChange={onRequestHeadersJsonChange}
          onSaveProjectRequestHeaders={onSaveProjectRequestHeaders}
          onCreateProjectFromDirectory={onCreateProjectFromDirectory}
          onOpenProjectManager={onOpenProjectManager}
          onOpenProjectAnalysis={onOpenProjectAnalysis}
        />
      ) : null}

      {activeMenu === 'groups' ? (
        <GroupsSidebarPanel
          project={project}
          groups={groups}
          cases={cases}
          activeGroupId={activeGroupId}
          actionId={groupActionId}
          onOpenCreate={onOpenGroupCreate}
          onActiveGroupChange={onActiveGroupChange}
          onStartEdit={onStartGroupEdit}
          onDelete={onDeleteGroup}
        />
      ) : null}

      {activeMenu === 'cases' ? (
        <CasesSidebarPanel
          project={project}
          groups={groups}
          filteredCases={filteredCases}
          selectedCase={selectedCase}
          actionId={caseActionId}
          onOpenCreate={onOpenCaseCreate}
          onSelectedCaseChange={onSelectedCaseChange}
          onStartEdit={onStartCaseEdit}
          onDelete={onDeleteCase}
        />
      ) : null}
    </Sider>
  );
}

function BrandHeader() {
  return (
    <Flex className="brand" align="center" gap={12}>
      <Flex className="brand-mark" align="center" justify="center">
        <Network size={20} aria-hidden="true" />
      </Flex>
      <div>
        <Title level={4}>Beautiful E2E</Title>
        <Text type="secondary">AI 回归测试工作台</Text>
      </div>
    </Flex>
  );
}

function ProjectSidebarPanel({
  executionMode,
  project,
  environments,
  activeFrontendEnvironmentKey,
  activeApiEnvironmentKey,
  baseUrl,
  apiBaseUrl,
  requestHeadersJson,
  isCreatingProject,
  isAnalyzingProject,
  isSavingProjectHeaders,
  onExecutionModeChange,
  onFrontendEnvironmentChange,
  onApiEnvironmentChange,
  onBaseUrlChange,
  onApiBaseUrlChange,
  onRequestHeadersJsonChange,
  onSaveProjectRequestHeaders,
  onCreateProjectFromDirectory,
  onOpenProjectManager,
  onOpenProjectAnalysis
}: {
  executionMode: ExecutionMode;
  project?: Project;
  environments: ProjectEnvironment[];
  activeFrontendEnvironmentKey: string;
  activeApiEnvironmentKey: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
  isCreatingProject: boolean;
  isAnalyzingProject: boolean;
  isSavingProjectHeaders: boolean;
  onExecutionModeChange: (mode: ExecutionMode) => void;
  onFrontendEnvironmentChange: (environmentKey: string) => void;
  onApiEnvironmentChange: (environmentKey: string) => void;
  onBaseUrlChange: (value: string) => void;
  onApiBaseUrlChange: (value: string) => void;
  onRequestHeadersJsonChange: (value: string) => void;
  onSaveProjectRequestHeaders: () => void;
  onCreateProjectFromDirectory: () => void;
  onOpenProjectManager: () => void;
  onOpenProjectAnalysis: () => void;
}) {
  return (
    <>
      <Card className="side-section" size="small">
        <SectionTitle icon={<Workflow size={17} aria-hidden="true" />} title="执行模式" />
        <Segmented
          block
          className="mode-switch"
          value={executionMode}
          onChange={(value) => onExecutionModeChange(value as ExecutionMode)}
          options={[
            {
              value: 'fullstack',
              label: (
                <Space size={6}>
                  <Globe2 size={16} aria-hidden="true" />
                  <span>前后端配合</span>
                </Space>
              )
            },
            {
              value: 'backend_api',
              label: (
                <Space size={6}>
                  <PlugZap size={16} aria-hidden="true" />
                  <span>纯后端接口</span>
                </Space>
              )
            }
          ]}
        />
      </Card>

      <Card className="side-section project-config-section" size="small">
        <SectionTitle icon={<Settings size={17} aria-hidden="true" />} title="项目配置" />
        <div className="project-summary">
          <div className="project-summary-main">
            <Text className="field-label">当前项目</Text>
            <Text strong className="project-current-name">
              {project?.name ?? '未选择项目'}
            </Text>
          </div>
        </div>
        <div className="project-actions" aria-label="项目操作">
          <Button
            className="secondary-button project-action"
            icon={<FolderOpen size={16} />}
            loading={isCreatingProject}
            onClick={onCreateProjectFromDirectory}
          >
            本地新建
          </Button>
          <Button className="secondary-button project-action" icon={<Settings size={16} />} onClick={onOpenProjectManager}>
            项目管理
          </Button>
          <Button
            className="secondary-button project-action"
            icon={<RefreshCw size={16} />}
            loading={isAnalyzingProject}
            onClick={onOpenProjectAnalysis}
          >
            更新分析
          </Button>
        </div>
        {executionMode === 'fullstack' ? (
          <div className="control-field">
            <Text className="field-label">前端基础地址</Text>
            <BaseUrlEnvironmentControl
              value={baseUrl}
              environmentKey={activeFrontendEnvironmentKey}
              environments={environments}
              onValueChange={onBaseUrlChange}
              onEnvironmentChange={onFrontendEnvironmentChange}
            />
          </div>
        ) : null}
        <div className="control-field">
          <Text className="field-label">接口基础地址</Text>
          <BaseUrlEnvironmentControl
            value={apiBaseUrl}
            environmentKey={activeApiEnvironmentKey}
            environments={environments}
            onValueChange={onApiBaseUrlChange}
            onEnvironmentChange={onApiEnvironmentChange}
          />
        </div>
        <RequestHeadersField
          requestHeadersJson={requestHeadersJson}
          onRequestHeadersJsonChange={onRequestHeadersJsonChange}
          isSavingProjectHeaders={isSavingProjectHeaders}
          onSaveProjectRequestHeaders={onSaveProjectRequestHeaders}
        />
      </Card>
    </>
  );
}

function RequestHeadersField({
  requestHeadersJson,
  onRequestHeadersJsonChange,
  isSavingProjectHeaders,
  onSaveProjectRequestHeaders
}: {
  requestHeadersJson: string;
  onRequestHeadersJsonChange: (value: string) => void;
  isSavingProjectHeaders: boolean;
  onSaveProjectRequestHeaders: () => void;
}) {
  return (
    <div className="control-field request-headers-field">
      <Flex className="field-toolbar" align="center" justify="space-between" gap={8}>
        <Text className="field-label">请求头</Text>
        <Button
          size="small"
          className="secondary-button request-header-save"
          icon={<Save size={14} />}
          loading={isSavingProjectHeaders}
          onClick={onSaveProjectRequestHeaders}
        >
          更新请求头
        </Button>
      </Flex>
      <RequestHeadersEditor value={requestHeadersJson} onChange={onRequestHeadersJsonChange} />
    </div>
  );
}

function BaseUrlEnvironmentControl({
  value,
  environmentKey,
  environments,
  onValueChange,
  onEnvironmentChange
}: {
  value: string;
  environmentKey: string;
  environments: ProjectEnvironment[];
  onValueChange: (value: string) => void;
  onEnvironmentChange: (environmentKey: string) => void;
}) {
  return (
    <Space.Compact className="base-url-env-control">
      <Input value={value} onChange={(event) => onValueChange(event.target.value)} />
      <Select value={environmentKey} onChange={onEnvironmentChange} options={environmentOptions(environments)} />
    </Space.Compact>
  );
}

function GroupsSidebarPanel({
  project,
  groups,
  cases,
  activeGroupId,
  actionId,
  onOpenCreate,
  onActiveGroupChange,
  onStartEdit,
  onDelete
}: {
  project?: Project;
  groups: Group[];
  cases: TestCase[];
  activeGroupId: string;
  actionId: string | null;
  onOpenCreate: () => void;
  onActiveGroupChange: (groupId: string) => void;
  onStartEdit: (group: Group) => void;
  onDelete: (groupId: string) => void;
}) {
  return (
    <Card className="side-section" size="small">
      <SectionTitle
        icon={<GitBranch size={17} aria-hidden="true" />}
        title="测试分组"
        extra={
          <Space size={6}>
            <Tag className="section-count">{cases.length}</Tag>
            <Button size="small" className="secondary-button" icon={<Plus size={14} />} onClick={onOpenCreate}>
              新建
            </Button>
          </Space>
        }
      />
      <Text type="secondary" className="project-scope-note">
        归属项目：{project?.name ?? '未选择项目'}
      </Text>
      <Space direction="vertical" className="group-list" size={8}>
        <button
          type="button"
          className={activeGroupId === 'all' ? 'group-row active' : 'group-row'}
          onClick={() => onActiveGroupChange('all')}
        >
          <Boxes size={18} aria-hidden="true" />
          <span className="row-title">全部用例</span>
          <Tag className="row-count">{cases.length}</Tag>
        </button>
        {groups.map((group) => (
          <div key={group.id} className={activeGroupId === group.id ? 'group-row active' : 'group-row'}>
            <button type="button" className="group-row-main" onClick={() => onActiveGroupChange(group.id)}>
              <Boxes size={18} aria-hidden="true" />
              <span className="row-title">{group.name}</span>
              <Tag className="row-count">{cases.filter((item) => item.group_id === group.id).length}</Tag>
            </button>
            <Space className="group-row-actions" size={6}>
              <Button className="icon-button small" icon={<Pencil size={15} />} onClick={() => onStartEdit(group)} />
              <Popconfirm
                title="删除分组"
                description="用例会保留，并变为未分组。"
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => onDelete(group.id)}
              >
                <Button danger className="icon-button small" icon={<Trash2 size={15} />} loading={actionId === group.id} />
              </Popconfirm>
            </Space>
          </div>
        ))}
      </Space>
    </Card>
  );
}

function CasesSidebarPanel({
  project,
  groups,
  filteredCases,
  selectedCase,
  actionId,
  onOpenCreate,
  onSelectedCaseChange,
  onStartEdit,
  onDelete
}: {
  project?: Project;
  groups: Group[];
  filteredCases: TestCase[];
  selectedCase?: TestCase;
  actionId: string | null;
  onOpenCreate: () => void;
  onSelectedCaseChange: (caseId: string) => void;
  onStartEdit: (testCase: TestCase) => void;
  onDelete: (caseId: string) => void;
}) {
  return (
    <Card className="side-section" size="small">
      <SectionTitle
        icon={<FileInput size={17} aria-hidden="true" />}
        title="用例"
        extra={
          <Space size={6}>
            <Tag className="section-count">{filteredCases.length}</Tag>
            <Button size="small" className="secondary-button" icon={<Plus size={14} />} onClick={onOpenCreate}>
              新建
            </Button>
          </Space>
        }
      />
      <Text type="secondary" className="project-scope-note">
        归属项目：{project?.name ?? '未选择项目'}
      </Text>
      <List
        className="case-list"
        dataSource={filteredCases}
        split={false}
        renderItem={(item) => (
          <List.Item>
            <div className={selectedCase?.id === item.id ? 'case-row active' : 'case-row'}>
              <button type="button" className="case-row-main" onClick={() => onSelectedCaseChange(item.id)}>
                <Tag className={`priority ${item.priority.toLowerCase()}`}>{item.priority}</Tag>
                <span className="case-copy">
                  <Text strong className="case-title">{item.title}</Text>
                  <Text type="secondary">
                    {item.steps.length} 步 · {formatCaseStatus(item.status)} · {groups.find((group) => group.id === item.group_id)?.name ?? '未分组'}
                  </Text>
                </span>
              </button>
              <Space className="case-row-actions" size={6}>
                <Button className="icon-button small" icon={<Pencil size={15} />} onClick={() => onStartEdit(item)} />
                <Popconfirm
                  title="删除用例"
                  description="会删除该用例的节点、步骤和运行结果。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => onDelete(item.id)}
                >
                  <Button danger className="icon-button small" icon={<Trash2 size={15} />} loading={actionId === item.id} />
                </Popconfirm>
              </Space>
            </div>
          </List.Item>
        )}
      />
    </Card>
  );
}

function formatCaseStatus(status: string): string {
  const map: Record<string, string> = {
    draft: '草稿',
    ready: '就绪',
    archived: '已归档'
  };
  return map[status] ?? status;
}
