import { Alert, Button, Empty, Flex, Input, Modal, Select, Skeleton, Space, Switch, Tabs, Tag, Typography } from 'antd';
import { Bot, CheckCircle2, Cloud, KeyRound, RefreshCw, Save, Terminal, Wrench } from 'lucide-react';

import type { AiProviderInfo, AiProviderStatus } from '../../api';
import type { AiProviderFormState } from '../../types/workbench';

const { Text } = Typography;

type AiConfigModalProps = {
  open: boolean;
  status: AiProviderStatus | null;
  form: AiProviderFormState;
  loading: boolean;
  saving: boolean;
  error: string;
  onClose: () => void;
  onRefresh: () => void;
  onSave: () => void;
  onFormChange: (patch: Partial<AiProviderFormState>) => void;
};

export function AiConfigModal({
  open,
  status,
  form,
  loading,
  saving,
  error,
  onClose,
  onRefresh,
  onSave,
  onFormChange
}: AiConfigModalProps) {
  const selectedProvider = status?.providers.find((provider) => provider.name === form.provider);

  return (
    <Modal
      className="ai-config-modal-shell"
      centered
      title="AI 配置"
      open={open}
      onCancel={onClose}
      width="min(1180px, calc(100vw - 48px))"
      footer={[
        <Button key="refresh" className="secondary-button" icon={<RefreshCw size={16} />} loading={loading} onClick={onRefresh}>
          刷新
        </Button>,
        <Button key="cancel" className="secondary-button" onClick={onClose}>
          取消
        </Button>,
        <Button key="save" type="primary" className="primary-button" icon={<Save size={16} />} loading={saving} onClick={onSave}>
          保存
        </Button>
      ]}
    >
      <div className="ai-config-modal">
        {error ? <Alert type="error" showIcon message={error} /> : null}
        {loading && !status ? <Skeleton active paragraph={{ rows: 8 }} /> : null}
        {!loading && !status ? <Empty description="暂无 AI 配置数据" /> : null}
        {status ? (
          <Tabs
            className="ai-config-tabs"
            items={[
              {
                key: 'provider',
                label: 'AI 配置',
                children: renderProviderConfigTab(status, form, selectedProvider, onFormChange)
              },
              {
                key: 'usage',
                label: '功能节点配置',
                children: renderUsagePlanner(status, form, onFormChange)
              }
            ]}
          />
        ) : null}
      </div>
    </Modal>
  );
}

function renderProviderConfigTab(
  status: AiProviderStatus,
  form: AiProviderFormState,
  selectedProvider: AiProviderInfo | undefined,
  onFormChange: (patch: Partial<AiProviderFormState>) => void
) {
  return (
    <div className="ai-config-layout">
      <div className="ai-provider-list" aria-label="AI 供应商">
        {status.providers.map((provider) => (
          <button
            key={provider.name}
            type="button"
            className={provider.name === form.provider ? 'ai-provider-option active' : 'ai-provider-option'}
            onClick={() => onFormChange({ provider: provider.name })}
          >
            <span className="ai-provider-icon">{providerIcon(provider.name)}</span>
            <span className="ai-provider-copy">
              <Flex align="center" gap={6} wrap>
                <Text strong>{provider.label}</Text>
                {provider.active ? <Tag className="row-count">当前</Tag> : null}
              </Flex>
              <Text type="secondary">{provider.description}</Text>
              <Flex gap={6} wrap>
                <ProviderStatusTag provider={provider} />
                <Tag className="row-count">{formatProtocol(provider.protocol)}</Tag>
              </Flex>
            </span>
          </button>
        ))}
      </div>

      <div className="ai-config-panel">
        <Flex align="center" justify="space-between" gap={12} wrap>
          <div>
            <Text className="field-label">当前编辑</Text>
            <Text strong className="ai-config-current">
              {selectedProvider?.label ?? form.provider}
            </Text>
          </div>
          <Space size={6} wrap>
            {status.fallback_rule_based ? <Tag className="row-count">失败回退规则生成</Tag> : null}
            {status.api_key_configured ? <Tag color="green">密钥已配置</Tag> : null}
            {status.base_url_configured ? <Tag color="green">地址已配置</Tag> : null}
          </Space>
        </Flex>

        {renderProviderFields(form, onFormChange)}

        {selectedProvider ? (
          <div className="ai-env-list">
            <Text className="field-label">环境变量</Text>
            <Flex gap={6} wrap>
              {selectedProvider.env_vars.map((item) => (
                <Tag key={item} className="ai-env-tag">
                  {item}
                </Tag>
              ))}
            </Flex>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function renderUsagePlanner(
  status: AiProviderStatus,
  form: AiProviderFormState,
  onFormChange: (patch: Partial<AiProviderFormState>) => void
) {
  const usageOptions = status.usage_options ?? [];
  const providerOptions = status.providers.map((provider) => ({
    value: provider.name,
    label: provider.label
  }));

  if (usageOptions.length === 0) return null;

  return (
    <div className="ai-usage-planner">
      <Flex align="center" justify="space-between" gap={12} wrap>
        <div>
          <Text className="field-label">功能节点配置</Text>
          <Text strong className="ai-config-current">
            用途分配
          </Text>
        </div>
        <Tag className="row-count">保存后生效</Tag>
      </Flex>
      <div className="ai-usage-grid">
        {usageOptions.map((usage) => (
          <div key={usage.key} className="ai-usage-row">
            <span className="ai-usage-icon">
              <Bot size={16} aria-hidden="true" />
            </span>
            <span className="ai-usage-copy">
              <Flex align="center" gap={8} wrap>
                <Text strong>{usage.label}</Text>
                <Tag className="ai-usage-key">{usage.key}</Tag>
              </Flex>
              <Text type="secondary">{usage.description}</Text>
            </span>
            <Select
              className="ai-usage-select"
              value={form.usagePlan[usage.key] || form.provider}
              options={providerOptions}
              onChange={(value) => onFormChange({ usagePlan: { [usage.key]: value } })}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function renderProviderFields(
  form: AiProviderFormState,
  onFormChange: (patch: Partial<AiProviderFormState>) => void
) {
  if (form.provider === 'codex_exec') {
    return (
      <div className="modal-form-grid ai-config-fields">
        <div className="control-field">
          <Text className="field-label">命令</Text>
          <Input
            prefix={<Terminal size={15} />}
            value={form.codexExecCommand}
            onChange={(event) => onFormChange({ codexExecCommand: event.target.value })}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">模型</Text>
          <Input value={form.codexExecModel} placeholder="留空使用 Codex 本地配置" onChange={(event) => onFormChange({ codexExecModel: event.target.value })} />
        </div>
        <div className="control-field">
          <Text className="field-label">Profile</Text>
          <Input value={form.codexExecProfile} onChange={(event) => onFormChange({ codexExecProfile: event.target.value })} />
        </div>
        <div className="control-field">
          <Text className="field-label">Profile V2</Text>
          <Input value={form.codexExecProfileV2} onChange={(event) => onFormChange({ codexExecProfileV2: event.target.value })} />
        </div>
        <div className="control-field">
          <Text className="field-label">沙盒</Text>
          <Select
            value={form.codexExecSandbox || 'inherit'}
            onChange={(value) => onFormChange({ codexExecSandbox: value === 'inherit' ? '' : value })}
            options={[
              { value: 'inherit', label: '跟随 Codex 配置' },
              { value: 'read-only', label: 'read-only' },
              { value: 'workspace-write', label: 'workspace-write' },
              { value: 'danger-full-access', label: 'danger-full-access' }
            ]}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">本地供应商</Text>
          <Select
            value={form.codexExecLocalProvider || 'inherit'}
            onChange={(value) => onFormChange({ codexExecLocalProvider: value === 'inherit' ? '' : value })}
            options={[
              { value: 'inherit', label: '跟随 Codex 配置' },
              { value: 'lmstudio', label: 'lmstudio' },
              { value: 'ollama', label: 'ollama' }
            ]}
          />
        </div>
        <div className="control-field modal-form-wide">
          <Text className="field-label">工作目录</Text>
          <Input value={form.codexExecCwd} placeholder="留空使用后端启动目录" onChange={(event) => onFormChange({ codexExecCwd: event.target.value })} />
        </div>
        <div className="control-field modal-form-wide">
          <Text className="field-label">额外目录</Text>
          <Input.TextArea
            className="json-config-field"
            autoSize={{ minRows: 2, maxRows: 4 }}
            value={form.codexExecAddDirs}
            placeholder="每行一个 --add-dir"
            onChange={(event) => onFormChange({ codexExecAddDirs: event.target.value })}
          />
        </div>
        <div className="control-field modal-form-wide">
          <Text className="field-label">图片附件</Text>
          <Input.TextArea
            className="json-config-field"
            autoSize={{ minRows: 2, maxRows: 4 }}
            value={form.codexExecImagePaths}
            placeholder="每行一个 --image 路径"
            onChange={(event) => onFormChange({ codexExecImagePaths: event.target.value })}
          />
        </div>
        <div className="control-field modal-form-wide">
          <Text className="field-label">Config 覆盖</Text>
          <Input.TextArea
            className="json-config-field"
            autoSize={{ minRows: 2, maxRows: 4 }}
            value={form.codexExecConfigOverrides}
            placeholder={'每行一个 -c，例如 model_reasoning_effort="high"'}
            onChange={(event) => onFormChange({ codexExecConfigOverrides: event.target.value })}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">启用 Feature</Text>
          <Input.TextArea
            className="json-config-field"
            autoSize={{ minRows: 2, maxRows: 3 }}
            value={form.codexExecEnabledFeatures}
            onChange={(event) => onFormChange({ codexExecEnabledFeatures: event.target.value })}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">禁用 Feature</Text>
          <Input.TextArea
            className="json-config-field"
            autoSize={{ minRows: 2, maxRows: 3 }}
            value={form.codexExecDisabledFeatures}
            onChange={(event) => onFormChange({ codexExecDisabledFeatures: event.target.value })}
          />
        </div>
        <div className="codex-exec-switch-grid modal-form-wide">
          {renderSwitchField('输出 Schema', form.codexExecOutputSchemaEnabled, (checked) =>
            onFormChange({ codexExecOutputSchemaEnabled: checked })
          )}
          {renderSwitchField('临时会话', form.codexExecEphemeral, (checked) =>
            onFormChange({ codexExecEphemeral: checked })
          )}
          {renderSwitchField('跳过 Git 检查', form.codexExecSkipGitRepoCheck, (checked) =>
            onFormChange({ codexExecSkipGitRepoCheck: checked })
          )}
          {renderSwitchField('忽略用户配置', form.codexExecIgnoreUserConfig, (checked) =>
            onFormChange({ codexExecIgnoreUserConfig: checked })
          )}
          {renderSwitchField('忽略规则', form.codexExecIgnoreRules, (checked) =>
            onFormChange({ codexExecIgnoreRules: checked })
          )}
          {renderSwitchField('严格配置', form.codexExecStrictConfig, (checked) =>
            onFormChange({ codexExecStrictConfig: checked })
          )}
          {renderSwitchField('OSS', form.codexExecOss, (checked) =>
            onFormChange({ codexExecOss: checked })
          )}
          {renderSwitchField(
            '绕过审批和沙盒',
            form.codexExecDangerouslyBypassApprovalsAndSandbox,
            (checked) => onFormChange({ codexExecDangerouslyBypassApprovalsAndSandbox: checked })
          )}
          {renderSwitchField('绕过 Hook 信任', form.codexExecDangerouslyBypassHookTrust, (checked) =>
            onFormChange({ codexExecDangerouslyBypassHookTrust: checked })
          )}
        </div>
      </div>
    );
  }

  if (form.provider === 'codex_bridge' || form.provider === 'openai_compatible') {
    return (
      <div className="modal-form-grid ai-config-fields">
        <div className="control-field modal-form-wide">
          <Text className="field-label">基础地址</Text>
          <Input value={form.baseUrl} placeholder="https://api.example.com/v1" onChange={(event) => onFormChange({ baseUrl: event.target.value })} />
        </div>
        <div className="control-field modal-form-wide">
          <Text className="field-label">API 密钥</Text>
          <Input.Password
            prefix={<KeyRound size={15} />}
            value={form.apiKey}
            placeholder="留空保持当前后端配置"
            onChange={(event) => onFormChange({ apiKey: event.target.value })}
          />
        </div>
        <div className="control-field">
          <Text className="field-label">模型</Text>
          <Input value={form.model} onChange={(event) => onFormChange({ model: event.target.value })} />
        </div>
        <div className="control-field">
          <Text className="field-label">协议</Text>
          <Select
            value={form.wireApi}
            onChange={(value) => onFormChange({ wireApi: value })}
            options={[
              { value: 'responses', label: 'Responses' },
              { value: 'chat', label: 'Chat Completions' }
            ]}
          />
        </div>
      </div>
    );
  }

  if (form.provider === 'custom_entrypoint') {
    return (
      <div className="modal-form-grid ai-config-fields">
        <div className="control-field modal-form-wide">
          <Text className="field-label">入口</Text>
          <Input
            value={form.providerEntryPoint}
            placeholder="package.module:create_provider"
            onChange={(event) => onFormChange({ providerEntryPoint: event.target.value })}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="ai-config-static">
      <CheckCircle2 size={18} />
      <Text>本地规则生成器无需额外配置。</Text>
    </div>
  );
}

function renderSwitchField(label: string, checked: boolean, onChange: (checked: boolean) => void) {
  return (
    <label className="codex-exec-switch-field">
      <Switch size="small" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}

function ProviderStatusTag({ provider }: { provider: AiProviderInfo }) {
  if (provider.available === false) return <Tag color="red">不可用</Tag>;
  if (provider.configured) return <Tag color="green">已配置</Tag>;
  if (provider.configurable) return <Tag color="gold">待配置</Tag>;
  return <Tag className="row-count">无需配置</Tag>;
}

function providerIcon(name: string) {
  if (name === 'codex_exec') return <Terminal size={17} aria-hidden="true" />;
  if (name === 'codex_bridge') return <Cloud size={17} aria-hidden="true" />;
  if (name === 'openai_compatible') return <Wrench size={17} aria-hidden="true" />;
  return <Bot size={17} aria-hidden="true" />;
}

function formatProtocol(protocol: string) {
  const map: Record<string, string> = {
    codex_cli: 'Codex CLI',
    deterministic: '本地',
    openai_http: 'HTTP',
    python_entrypoint: 'Python'
  };
  return map[protocol] ?? protocol;
}
