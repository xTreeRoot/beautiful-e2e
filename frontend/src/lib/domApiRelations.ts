import type { Repository } from '../api';

export type DomApiRouteRef = {
  id: string;
  repositoryId: string;
  repositoryKind: string;
  repositoryName: string;
  repositoryPath: string;
  method: string;
  path: string;
  summary: string | null;
  handler: string | null;
  source: string | null;
};

/**
 * 从项目分析摘要中整理真实后端路由，供 DOM 页面/组件按源码 API 引用做证据联动。
 * 这里不读取业务词，只使用仓库扫描得到的 method/path/source 等路由事实。
 */
export function apiRoutesFromRepositories(repositories: Repository[]): DomApiRouteRef[] {
  return repositories.flatMap((repository) => {
    const routes = rawRoutesFromRepository(repository);
    return routes
      .map((route, index) => apiRouteFromRaw(repository, route, index))
      .filter((route): route is DomApiRouteRef => Boolean(route));
  });
}

export function relatedApiRoutesForRefs(apiRefs: string[], routes: DomApiRouteRef[]): DomApiRouteRef[] {
  if (!apiRefs.length || !routes.length) return [];

  const normalizedRefs = uniqueStrings(apiRefs.map(normalizeApiPath).filter(Boolean));
  const related = new Map<string, DomApiRouteRef>();
  normalizedRefs.forEach((ref) => {
    routes.forEach((route) => {
      if (apiRefMatchesRoute(ref, route.path)) {
        related.set(route.id, route);
      }
    });
  });
  return Array.from(related.values()).sort(compareApiRoutes).slice(0, 24);
}

export function apiRouteLabel(route: DomApiRouteRef): string {
  return `${route.method || 'ANY'} ${route.path}`;
}

function rawRoutesFromRepository(repository: Repository): Array<Record<string, unknown>> {
  const summary = repository.index_summary;
  if (!summary || typeof summary !== 'object') return [];
  const routes = (summary as { routes?: unknown }).routes;
  if (!Array.isArray(routes)) return [];
  return routes.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
}

function apiRouteFromRaw(
  repository: Repository,
  rawRoute: Record<string, unknown>,
  index: number
): DomApiRouteRef | null {
  const path = normalizeApiPath(cleanText(rawRoute.path));
  if (!path) return null;
  const method = cleanText(rawRoute.method).toUpperCase() || 'ANY';
  return {
    id: `${repository.id}:api-route:${method}:${path}:${index}`,
    repositoryId: repository.id,
    repositoryKind: repository.kind,
    repositoryName: repository.name || repositoryKindLabel(repository.kind),
    repositoryPath: repository.path,
    method,
    path,
    summary: cleanText(rawRoute.summary) || cleanText(rawRoute.description) || null,
    handler: cleanText(rawRoute.handler) || null,
    source: cleanText(rawRoute.source) || null
  };
}

function apiRefMatchesRoute(apiRef: string, routePath: string): boolean {
  const ref = normalizeApiPath(apiRef);
  const route = normalizeApiPath(routePath);
  if (!ref || !route) return false;
  if (ref === route) return true;
  if (pathPatternFromRoute(route).test(ref)) return true;

  const refApiTail = apiTail(ref);
  const routeApiTail = apiTail(route);
  if (!refApiTail || !routeApiTail) return false;
  return refApiTail === routeApiTail || pathPatternFromRoute(routeApiTail).test(refApiTail);
}

function normalizeApiPath(value: string): string {
  const raw = value.trim();
  if (!raw) return '';
  let path = raw.split(/[?#]/, 1)[0];
  const absoluteMatch = path.match(/^[a-z][a-z0-9+.-]*:\/\/[^/]+(?<path>\/.*)?$/i);
  if (absoluteMatch) {
    path = absoluteMatch.groups?.path ?? '/';
  }
  if (!path.startsWith('/')) path = `/${path}`;
  return path.replace(/\/+/g, '/').replace(/\/$/, '') || '/';
}

function apiTail(path: string): string {
  const lowered = path.toLowerCase();
  const index = lowered.indexOf('/api/');
  if (index >= 0) return path.slice(index);
  return lowered === '/api' ? '/api' : '';
}

function pathPatternFromRoute(routePath: string): RegExp {
  const pattern = escapeRegExp(routePath)
    .replace(/\\\{[^/]+\\\}/g, '[^/]+')
    .replace(/:[A-Za-z_][A-Za-z0-9_]*/g, '[^/]+')
    .replace(/<[^/]+>/g, '[^/]+');
  return new RegExp(`^${pattern}$`, 'i');
}

function compareApiRoutes(left: DomApiRouteRef, right: DomApiRouteRef): number {
  return left.path.localeCompare(right.path, 'zh-CN') || left.method.localeCompare(right.method, 'zh-CN');
}

function repositoryKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    workspace: '工作区',
    frontend: '前端仓库',
    backend: '后端仓库'
  };
  return (labels[kind] ?? kind) || '仓库';
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
