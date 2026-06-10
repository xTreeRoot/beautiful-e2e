import type {
  KnowledgeGraphModule,
  KnowledgeGraphRoute
} from '../types/projectKnowledgeGraph';

export type KnowledgeGraphRouteSearchResult = {
  route: KnowledgeGraphRoute;
  module: KnowledgeGraphModule;
  score: number;
  reasons: string[];
};

type RouteCandidate = {
  route: KnowledgeGraphRoute;
  module: KnowledgeGraphModule;
  searchText: string;
  pathTokens: string[];
  semanticTokens: string[];
  variableTokens: string[];
};

const ACTION_ALIASES: string[][] = [
  ['list', 'page', 'search', 'query', 'find', '分页', '列表', '搜索', '查询'],
  ['detail', 'info', 'get', 'view', '详情', '明细', '信息'],
  ['create', 'add', 'save', 'insert', 'new', '创建', '新增', '保存'],
  ['update', 'edit', 'modify', 'change', '更新', '编辑', '修改'],
  ['delete', 'remove', 'del', '删除', '移除'],
  ['complete', 'finish', 'submit', 'execute', 'action', '完成', '提交', '执行', '动作']
];

/**
 * 在已生成的项目知识图谱中搜索相似接口。
 * 评分同时看路径片段、方法、摘要证据、变量产消和请求体字段，避免只做简单字符串 contains。
 */
export function searchKnowledgeGraphRoutes(
  modules: KnowledgeGraphModule[],
  query: string,
  limit = 24
): KnowledgeGraphRouteSearchResult[] {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return [];

  const queryTokens = uniqueTokens(tokensFromText(normalizedQuery));
  const queryMethod = methodFromQuery(query);
  const candidates = routeCandidates(modules);
  return candidates
    .map((candidate) => scoreCandidate(candidate, normalizedQuery, queryTokens, queryMethod))
    .filter((result): result is KnowledgeGraphRouteSearchResult => Boolean(result && result.score > 0))
    .sort((left, right) => right.score - left.score || routeLabel(left.route).localeCompare(routeLabel(right.route)))
    .slice(0, limit);
}

/** 生成界面展示用的接口标签，缺失方法时按 GET 兜底。 */
export function routeLabel(route: KnowledgeGraphRoute): string {
  return `${route.method ?? 'GET'} ${route.path ?? '/'}`;
}

function routeCandidates(modules: KnowledgeGraphModule[]): RouteCandidate[] {
  return modules.flatMap((module) => (
    (module.routes ?? []).map((route) => {
      const semanticValues = [
        route.summary,
        route.handler,
        route.source,
        route.source_file,
        module.name,
        module.domain,
        module.scope_boundary,
        ...(route.applicable_scenarios ?? []),
        ...(route.excluded_scenarios ?? []),
        ...(route.evidence ?? []),
        ...(module.evidence ?? [])
      ];
      const variableValues = [
        ...(route.produces ?? []),
        ...(route.consumes ?? []),
        ...(route.request_body_fields ?? [])
      ];
      return {
        route,
        module,
        searchText: normalizeSearchText([
          route.method,
          route.path,
          ...semanticValues,
          ...variableValues
        ].join(' ')),
        pathTokens: uniqueTokens(tokensFromText(route.path ?? '')),
        semanticTokens: uniqueTokens(tokensFromText(semanticValues.join(' '))),
        variableTokens: uniqueTokens(tokensFromText(variableValues.join(' ')))
      };
    })
  ));
}

function scoreCandidate(
  candidate: RouteCandidate,
  normalizedQuery: string,
  queryTokens: string[],
  queryMethod: string | null
): KnowledgeGraphRouteSearchResult | null {
  const reasons: string[] = [];
  let score = 0;
  const routeMethod = String(candidate.route.method ?? '').toUpperCase();
  const routePath = normalizeSearchText(candidate.route.path ?? '');
  const routeSummary = normalizeSearchText(candidate.route.summary ?? '');

  if (queryMethod && routeMethod === queryMethod) {
    score += 12;
    reasons.push(`方法 ${queryMethod} 匹配`);
  }
  if (routePath && routePath.includes(normalizedQuery)) {
    score += 70;
    reasons.push('路径完整命中');
  } else if (candidate.searchText.includes(normalizedQuery)) {
    score += 44;
    reasons.push('接口文本命中');
  }

  const pathOverlap = overlapCount(queryTokens, candidate.pathTokens);
  if (pathOverlap > 0) {
    score += pathOverlap * 16;
    reasons.push(`路径片段相同 ${pathOverlap} 个`);
  }

  const semanticOverlap = overlapCount(queryTokens, candidate.semanticTokens);
  if (semanticOverlap > 0) {
    score += semanticOverlap * 7;
    reasons.push(`摘要/证据相近 ${semanticOverlap} 项`);
  }

  const variableOverlap = overlapCount(queryTokens, candidate.variableTokens);
  if (variableOverlap > 0) {
    score += variableOverlap * 12;
    reasons.push(`变量或 Body 字段相同 ${variableOverlap} 项`);
  }

  const actionOverlap = actionAliasOverlap(queryTokens, candidate.pathTokens);
  if (actionOverlap > 0) {
    score += actionOverlap * 8;
    reasons.push('动作语义相近');
  }

  if (routeSummary && routeSummary.includes(normalizedQuery)) {
    score += 24;
    reasons.push('接口摘要命中');
  }

  if (score <= 0) return null;
  return {
    route: candidate.route,
    module: candidate.module,
    score,
    reasons: uniqueReasons(reasons)
  };
}

function normalizeSearchText(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[{}[\]().,;:?&=#]/g, ' ')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function tokensFromText(value: string): string[] {
  return normalizeSearchText(value)
    .split(/[\s/]+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 2);
}

function uniqueTokens(tokens: string[]): string[] {
  return Array.from(new Set(tokens));
}

function uniqueReasons(reasons: string[]): string[] {
  return Array.from(new Set(reasons)).slice(0, 3);
}

function overlapCount(left: string[], right: string[]): number {
  const rightSet = new Set(right);
  return left.filter((token) => rightSet.has(token)).length;
}

function actionAliasOverlap(queryTokens: string[], routeTokens: string[]): number {
  return ACTION_ALIASES.filter((aliases) => (
    aliases.some((alias) => queryTokens.includes(alias))
    && aliases.some((alias) => routeTokens.includes(alias))
  )).length;
}

function methodFromQuery(query: string): string | null {
  const match = query.match(/\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/i);
  return match ? match[1].toUpperCase() : null;
}
