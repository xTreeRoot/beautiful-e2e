import type { Bootstrap, TestCase } from './api';

const timestamp = new Date().toISOString();

export const demoBootstrap: Bootstrap = {
  project: {
    id: 'demo-project',
    name: 'Beautiful E2E',
    description: 'AI 辅助端到端回归测试平台',
    is_current: true,
    settings: {
      execution_mode: 'fullstack',
      frontend_repo_path: '',
      backend_repo_path: '',
      workspace_path: '',
      active_environment: 'local',
      active_frontend_environment: 'local',
      active_api_environment: 'local',
      base_url: 'http://localhost:5173',
      api_base_url: 'http://localhost:8000',
      environments: [
        {
          key: 'local',
          name: '本地',
          base_url: 'http://localhost:5173',
          api_base_url: 'http://localhost:8000'
        },
        { key: 'dev', name: '开发', base_url: '', api_base_url: '' },
        { key: 'test', name: '测试', base_url: '', api_base_url: '' },
        { key: 'staging', name: '预发', base_url: '', api_base_url: '' },
        { key: 'prod', name: '生产', base_url: '', api_base_url: '' }
      ]
    },
    repositories: [],
    created_at: timestamp,
    updated_at: timestamp
  },
  projects: [],
  groups: [
    {
      id: 'core',
      project_id: 'demo-project',
      name: '核心链路组',
      description: '登录、提交、发布、删除等阻断发布的链路',
      sort_order: 10
    },
    {
      id: 'browse',
      project_id: 'demo-project',
      name: '浏览组',
      description: '列表、详情、搜索、只读页面',
      sort_order: 20
    },
    {
      id: 'smoke',
      project_id: 'demo-project',
      name: '回归冒烟组',
      description: '每次构建都要快速通过的信心检查',
      sort_order: 30
    }
  ]
};

export const demoCases: TestCase[] = [
  {
    id: 'demo-case',
    project_id: 'demo-project',
    group_id: 'core',
    title: '登录后进入工作台并完成核心断言',
    description: '用户输入账号密码，登录成功后进入工作台，页面无关键错误。',
    priority: 'P0',
    status: 'draft',
    source_prompt: '核心链路：登录后进入工作台并看到业务数据',
    created_by: 'developer',
    code_context: { execution_mode: 'fullstack' },
    playwright_spec_path: null,
    created_at: timestamp,
    updated_at: timestamp,
    steps: [
      {
        id: 's1',
        order_index: 1,
        kind: 'setup',
        label: '打开应用',
        action: 'goto',
        selector: null,
        target_url: '/',
        value: null,
        expected: '应用外壳可见'
      },
      {
        id: 's2',
        order_index: 2,
        kind: 'action',
        label: '提交登录',
        action: 'click',
        selector: "[data-testid='login-submit']",
        target_url: null,
        value: null,
        expected: null
      },
      {
        id: 's3',
        order_index: 3,
        kind: 'assertion',
        label: '确认用户进入已认证页面',
        action: 'expect_visible',
        selector: "[data-testid='dashboard']",
        target_url: null,
        value: null,
        expected: '已认证页面外壳可见'
      }
    ],
    graph: {
      nodes: [
        { id: 'step-1', data: { label: '1. 打开应用' }, position: { x: 160, y: 80 } },
        { id: 'step-2', data: { label: '2. 提交登录' }, position: { x: 400, y: 80 } },
        {
          id: 'step-3',
          data: { label: '3. 已认证页面可见' },
          position: { x: 640, y: 80 }
        }
      ],
      edges: [
        { id: 'e1', source: 'step-1', target: 'step-2' },
        { id: 'e2', source: 'step-2', target: 'step-3' }
      ]
    }
  }
];
