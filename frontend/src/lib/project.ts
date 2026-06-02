import type { Group, Project } from '../api';
import { normalizeProjectEnvironments } from './projectEnvironments';
import type { ExecutionMode } from '../types/workbench';

export function getProjectSetting(project: Project | undefined, key: string): string {
  const value = project?.settings?.[key];
  return typeof value === 'string' ? value : '';
}

export function getProjectExecutionMode(project: Project | undefined): ExecutionMode {
  return project?.settings?.execution_mode === 'backend_api' ? 'backend_api' : 'fullstack';
}

export function formatExecutionMode(mode: ExecutionMode): string {
  return mode === 'backend_api' ? '纯后端接口' : '前后端配合';
}

export function withProjectSettings(
  project: Project,
  settings: Partial<Project['settings']>
): Project {
  return {
    ...project,
    settings: {
      ...project.settings,
      ...settings
    }
  };
}

export function formatProjectMeta(project: Project): string {
  const { activeFrontendEnvironment, activeApiEnvironment } = normalizeProjectEnvironments(project.settings);
  const updatedAt = new Date(project.updated_at).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
  return `前端 ${activeFrontendEnvironment.name} · 接口 ${activeApiEnvironment.name} · 更新 ${updatedAt}`;
}

export function sortGroups(a: Group, b: Group): number {
  return a.sort_order - b.sort_order || a.name.localeCompare(b.name);
}
