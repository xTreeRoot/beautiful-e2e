import { Button, Flex, Input, List, Modal, Popconfirm, Segmented, Select, Space, Switch, Tag, Typography } from 'antd';
import { Pencil, Plus, RefreshCw, Save, Trash2 } from 'lucide-react';

import type { Project } from '../../api';
import { formatExecutionMode, formatProjectMeta, getProjectExecutionMode } from '../../lib/project';
import { environmentOptions, type ProjectEnvironment } from '../../lib/projectEnvironments';
import type { ExecutionMode } from '../../types/workbench';
import { RequestHeadersEditor } from './RequestHeadersEditor';

const { Text } = Typography;

export function ProjectManagerModal({
  open,
  projects,
  currentProject,
  actionId,
  onClose,
  onOpenCreate,
  onRefresh,
  onSelect,
  onStartEdit,
  onDelete
}: {
  open: boolean;
  projects: Project[];
  currentProject?: Project;
  actionId: string | null;
  onClose: () => void;
  onOpenCreate: () => void;
  onRefresh: () => void;
  onSelect: (projectId: string) => void;
  onStartEdit: (project: Project) => void;
  onDelete: (projectId: string) => void;
}) {
  return (
    <Modal title="项目管理" open={open} footer={null} onCancel={onClose} width={760}>
      <div className="project-manager">
        <Flex align="center" justify="space-between" className="project-manager-heading">
          <Text strong>已保存项目</Text>
          <Space size={8}>
            <Button type="primary" className="primary-button" icon={<Plus size={16} />} onClick={onOpenCreate}>
              新建项目
            </Button>
            <Button className="secondary-button" icon={<RefreshCw size={16} />} loading={actionId === '__refresh'} onClick={onRefresh}>
              刷新
            </Button>
          </Space>
        </Flex>

        <List
          className="project-manager-list"
          dataSource={projects}
          split={false}
          renderItem={(item) => {
            const isCurrent = item.is_current || item.id === currentProject?.id;
            return (
              <List.Item className={isCurrent ? 'project-manager-item active' : 'project-manager-item'}>
                <div className="project-manager-row">
                  <div className="project-manager-copy">
                    <Flex align="center" gap={8}>
                      <Text strong>{item.name}</Text>
                      {isCurrent ? <Tag className="row-count">当前</Tag> : null}
                      <Tag className="row-count">{formatExecutionMode(getProjectExecutionMode(item))}</Tag>
                    </Flex>
                    <Text type="secondary">{item.description || '暂无说明'}</Text>
                    <Text type="secondary">{formatProjectMeta(item)}</Text>
                  </div>

                  <Space className="project-manager-actions" size={8} wrap>
                    <Button className="secondary-button" disabled={isCurrent} onClick={() => onSelect(item.id)}>
                      {isCurrent ? '当前项目' : '选择'}
                    </Button>
                    <Button className="secondary-button" icon={<Pencil size={16} />} onClick={() => onStartEdit(item)}>
                      编辑
                    </Button>
                    <Popconfirm
                      title="删除项目"
                      description="会删除该项目下的分组、用例、步骤和运行记录。"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      disabled={projects.length <= 1}
                      onConfirm={() => onDelete(item.id)}
                    >
                      <Button
                        danger
                        className="secondary-button"
                        icon={<Trash2 size={16} />}
                        loading={actionId === item.id}
                        disabled={projects.length <= 1}
                      >
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                </div>
              </List.Item>
            );
          }}
        />
      </div>
    </Modal>
  );
}

export function ProjectCreateModal({
  open,
  name,
  description,
  executionMode,
  environments,
  frontendEnvironmentKey,
  apiEnvironmentKey,
  baseUrl,
  apiBaseUrl,
  requestHeadersJson,
  analyzeOnCreate,
  loading,
  onNameChange,
  onDescriptionChange,
  onExecutionModeChange,
  onFrontendEnvironmentChange,
  onApiEnvironmentChange,
  onBaseUrlChange,
  onApiBaseUrlChange,
  onRequestHeadersJsonChange,
  onAnalyzeOnCreateChange,
  onCancel,
  onCreate
}: {
  open: boolean;
  name: string;
  description: string;
  executionMode: ExecutionMode;
  environments: ProjectEnvironment[];
  frontendEnvironmentKey: string;
  apiEnvironmentKey: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
  analyzeOnCreate: boolean;
  loading: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onExecutionModeChange: (mode: ExecutionMode) => void;
  onFrontendEnvironmentChange: (environmentKey: string) => void;
  onApiEnvironmentChange: (environmentKey: string) => void;
  onBaseUrlChange: (value: string) => void;
  onApiBaseUrlChange: (value: string) => void;
  onRequestHeadersJsonChange: (value: string) => void;
  onAnalyzeOnCreateChange: (enabled: boolean) => void;
  onCancel: () => void;
  onCreate: () => void;
}) {
  return (
    <Modal
      title="新建项目"
      open={open}
      onCancel={onCancel}
      width={760}
      footer={[
        <Button key="cancel" className="secondary-button" onClick={onCancel}>
          取消
        </Button>,
        <Button key="create" type="primary" className="primary-button" icon={<Plus size={16} />} loading={loading} onClick={onCreate}>
          新建
        </Button>
      ]}
    >
      <div className="modal-form-grid">
        <div className="control-field">
          <Text className="field-label">项目名称</Text>
          <Input value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="例如：票务平台回归测试" />
        </div>
        <div className="control-field">
          <Text className="field-label">项目说明</Text>
          <Input value={description} onChange={(event) => onDescriptionChange(event.target.value)} placeholder="可选" />
        </div>
        <div className="control-field">
          <Text className="field-label">执行模式</Text>
          <Segmented
            block
            className="mode-switch compact"
            value={executionMode}
            onChange={(value) => onExecutionModeChange(value as ExecutionMode)}
            options={[
              { value: 'fullstack', label: '前后端配合' },
              { value: 'backend_api', label: '纯后端接口' }
            ]}
          />
        </div>
        <ProjectBaseUrlFields
          executionMode={executionMode}
          environments={environments}
          frontendEnvironmentKey={frontendEnvironmentKey}
          apiEnvironmentKey={apiEnvironmentKey}
          baseUrl={baseUrl}
          apiBaseUrl={apiBaseUrl}
          requestHeadersJson={requestHeadersJson}
          onFrontendEnvironmentChange={onFrontendEnvironmentChange}
          onApiEnvironmentChange={onApiEnvironmentChange}
          onBaseUrlChange={onBaseUrlChange}
          onApiBaseUrlChange={onApiBaseUrlChange}
          onRequestHeadersJsonChange={onRequestHeadersJsonChange}
        />
        <Flex align="center" justify="space-between" gap={12}>
          <Text className="field-label">创建后立即分析</Text>
          <Switch checked={analyzeOnCreate} onChange={onAnalyzeOnCreateChange} />
        </Flex>
      </div>
    </Modal>
  );
}

export function ProjectEditModal({
  open,
  name,
  description,
  executionMode,
  environments,
  frontendEnvironmentKey,
  apiEnvironmentKey,
  baseUrl,
  apiBaseUrl,
  requestHeadersJson,
  loading,
  onNameChange,
  onDescriptionChange,
  onExecutionModeChange,
  onFrontendEnvironmentChange,
  onApiEnvironmentChange,
  onBaseUrlChange,
  onApiBaseUrlChange,
  onRequestHeadersJsonChange,
  onCancel,
  onSave
}: {
  open: boolean;
  name: string;
  description: string;
  executionMode: ExecutionMode;
  environments: ProjectEnvironment[];
  frontendEnvironmentKey: string;
  apiEnvironmentKey: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
  loading: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onExecutionModeChange: (mode: ExecutionMode) => void;
  onFrontendEnvironmentChange: (environmentKey: string) => void;
  onApiEnvironmentChange: (environmentKey: string) => void;
  onBaseUrlChange: (value: string) => void;
  onApiBaseUrlChange: (value: string) => void;
  onRequestHeadersJsonChange: (value: string) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  return (
    <Modal
      title="编辑项目"
      open={open}
      onCancel={onCancel}
      width={760}
      footer={[
        <Button key="cancel" className="secondary-button" onClick={onCancel}>
          取消
        </Button>,
        <Button key="save" type="primary" className="primary-button" icon={<Save size={16} />} loading={loading} onClick={onSave}>
          保存
        </Button>
      ]}
    >
      <div className="modal-form-grid">
        <div className="control-field">
          <Text className="field-label">项目名称</Text>
          <Input value={name} onChange={(event) => onNameChange(event.target.value)} />
        </div>
        <div className="control-field">
          <Text className="field-label">项目说明</Text>
          <Input value={description} onChange={(event) => onDescriptionChange(event.target.value)} placeholder="可选" />
        </div>
        <div className="control-field">
          <Text className="field-label">执行模式</Text>
          <Segmented
            block
            className="mode-switch compact"
            value={executionMode}
            onChange={(value) => onExecutionModeChange(value as ExecutionMode)}
            options={[
              { value: 'fullstack', label: '前后端配合' },
              { value: 'backend_api', label: '纯后端接口' }
            ]}
          />
        </div>
        <ProjectBaseUrlFields
          executionMode={executionMode}
          environments={environments}
          frontendEnvironmentKey={frontendEnvironmentKey}
          apiEnvironmentKey={apiEnvironmentKey}
          baseUrl={baseUrl}
          apiBaseUrl={apiBaseUrl}
          requestHeadersJson={requestHeadersJson}
          onFrontendEnvironmentChange={onFrontendEnvironmentChange}
          onApiEnvironmentChange={onApiEnvironmentChange}
          onBaseUrlChange={onBaseUrlChange}
          onApiBaseUrlChange={onApiBaseUrlChange}
          onRequestHeadersJsonChange={onRequestHeadersJsonChange}
        />
      </div>
    </Modal>
  );
}

function ProjectBaseUrlFields({
  executionMode,
  environments,
  frontendEnvironmentKey,
  apiEnvironmentKey,
  baseUrl,
  apiBaseUrl,
  requestHeadersJson,
  onFrontendEnvironmentChange,
  onApiEnvironmentChange,
  onBaseUrlChange,
  onApiBaseUrlChange,
  onRequestHeadersJsonChange
}: {
  executionMode: ExecutionMode;
  environments: ProjectEnvironment[];
  frontendEnvironmentKey: string;
  apiEnvironmentKey: string;
  baseUrl: string;
  apiBaseUrl: string;
  requestHeadersJson: string;
  onFrontendEnvironmentChange: (environmentKey: string) => void;
  onApiEnvironmentChange: (environmentKey: string) => void;
  onBaseUrlChange: (value: string) => void;
  onApiBaseUrlChange: (value: string) => void;
  onRequestHeadersJsonChange: (value: string) => void;
}) {
  return (
    <>
      {executionMode === 'fullstack' ? (
        <div className="control-field">
          <Text className="field-label">前端基础地址</Text>
          <BaseUrlEnvironmentControl
            value={baseUrl}
            environmentKey={frontendEnvironmentKey}
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
          environmentKey={apiEnvironmentKey}
          environments={environments}
          onValueChange={onApiBaseUrlChange}
          onEnvironmentChange={onApiEnvironmentChange}
        />
      </div>
      <div className="control-field">
        <Text className="field-label">请求头</Text>
        <RequestHeadersEditor value={requestHeadersJson} onChange={onRequestHeadersJsonChange} />
      </div>
    </>
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
