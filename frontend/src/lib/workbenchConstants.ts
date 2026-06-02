import {
  Globe2,
  Keyboard,
  MousePointerClick,
  PlugZap,
  ShieldCheck,
  Workflow
} from 'lucide-react';

import type { NodeTemplate } from '../types/workbench';

export const samplePrompt = '根据需求文档生成客户端全流程回归用例，覆盖入口、详情、提交和结果断言';

export const fullstackNodeTemplates: NodeTemplate[] = [
  { kind: 'page', label: '页面', action: 'goto', icon: Globe2 },
  { kind: 'click', label: '点击', action: 'click', icon: MousePointerClick },
  { kind: 'input', label: '输入', action: 'fill', icon: Keyboard },
  { kind: 'assertion', label: '断言', action: 'expect_visible', icon: ShieldCheck },
  { kind: 'api', label: '接口', action: 'api_request', icon: PlugZap },
  { kind: 'subflow', label: '子流程', icon: Workflow }
];

export const backendNodeTemplates: NodeTemplate[] = [
  { kind: 'api', label: '接口', action: 'api_request', icon: PlugZap },
  { kind: 'assertion', label: '断言', action: 'api_request', icon: ShieldCheck },
  { kind: 'subflow', label: '子流程', icon: Workflow }
];

export const executableKinds = new Set(['page', 'click', 'input', 'assertion', 'api']);
