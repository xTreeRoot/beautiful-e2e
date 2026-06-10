import type { DomModuleCompileMode, Repository } from '../api';
import {
  apiRoutesFromRepositories,
  relatedApiRoutesForRefs,
  type DomApiRouteRef
} from './domApiRelations';
import { linkRelatedComponents } from './domComponentRelations';

/**
 * 本文件保留 DOM 图谱兼容门面，旧版扁平目标和新版模块索引都从这里进入。
 * 页面-组件匹配和链路推导已拆到独立 lib，后续新增规则继续外移。
 */

export type DomTargetKind =
  | 'testid'
  | 'aria-label'
  | 'placeholder'
  | 'name'
  | 'id'
  | 'route'
  | string;

export type DomTargetNode = {
  id: string;
  repositoryId: string;
  repositoryKind: string;
  repositoryName: string;
  repositoryPath: string;
  fileId: string;
  filePath: string;
  line: number | null;
  kind: DomTargetKind;
  kindLabel: string;
  value: string;
  hint: string;
  source: string;
  locator: string | null;
  stability: 'high' | 'medium' | 'low';
};

export type DomRelatedComponent = {
  id: string;
  moduleName: string;
  moduleType: 'component';
  path: string;
  targetCount: number;
  kindCounts: Record<string, number>;
  targets: DomTargetNode[];
  apiRefs: string[];
  relatedApiRoutes: DomApiRouteRef[];
};

export type DomFileGroup = {
  id: string;
  repositoryId: string;
  repositoryKind: string;
  repositoryName: string;
  repositoryPath: string;
  moduleName: string;
  moduleType: 'page' | 'component';
  pagePath: string | null;
  source: string;
  framework: string | null;
  previewHtml: string | null;
  previewSource: string | null;
  previewStrategy: string | null;
  previewCompiledAt: string | null;
  isCompiled: boolean;
  evidence: string[];
  componentRefs: string[];
  relatedComponents: DomRelatedComponent[];
  apiRefs: string[];
  relatedApiRoutes: DomApiRouteRef[];
  path: string;
  targetCount: number;
  kindCounts: Record<string, number>;
  targets: DomTargetNode[];
};

export type DomCompileProgressState = {
  moduleId: string;
  mode: DomModuleCompileMode;
  phase: 'running' | 'complete' | 'error';
  percent: number;
  message: string;
};

export type DomRepositoryGroup = {
  id: string;
  kind: string;
  label: string;
  path: string;
  targetCount: number;
  fileCount: number;
  kindCounts: Record<string, number>;
  files: DomFileGroup[];
};

export type DomTargetGraph = {
  repositories: DomRepositoryGroup[];
  files: DomFileGroup[];
  targets: DomTargetNode[];
  kindCounts: Record<string, number>;
};

type SourceLocation = {
  filePath: string;
  line: number | null;
};

/**
 * 把仓库扫描到的扁平 DOM 目标整理成“仓库-文件-目标类型-目标”的图谱契约。
 * 原始扫描结果只保证有 kind/value/source/hint，因此这里必须容错未知字段和旧数据。
 */
export function buildDomTargetGraph(repositories: Repository[]): DomTargetGraph {
  const repositoryMap = new Map<string, DomRepositoryGroup>();
  const fileMap = new Map<string, DomFileGroup>();
  const targets: DomTargetNode[] = [];
  const kindCounts: Record<string, number> = {};
  const apiRoutes = apiRoutesFromRepositories(repositories);

  repositories.forEach((repository) => {
    const rawTargets = domTargetsFromRepository(repository);
    if (!rawTargets.length) return;

    const repositoryId = repository.id;
    const repositoryGroup = ensureRepositoryGroup(repositoryMap, repository);

    rawTargets.forEach((rawTarget, index) => {
      const kind = normalizeKind(rawTarget.kind);
      const value = cleanText(rawTarget.value);
      if (!value) return;

      const source = cleanText(rawTarget.source);
      const sourceLocation = parseSourceLocation(source);
      const filePath = sourceLocation.filePath || '未知来源';
      const fileId = `${repositoryId}:${filePath}`;
      const fileGroup = ensureFileGroup(fileMap, repositoryGroup, fileId, filePath);
      const target: DomTargetNode = {
        id: `${fileId}:${kind}:${value}:${sourceLocation.line ?? 'noline'}:${index}`,
        repositoryId,
        repositoryKind: repository.kind,
        repositoryName: repositoryGroup.label,
        repositoryPath: repository.path,
        fileId,
        filePath,
        line: sourceLocation.line,
        kind,
        kindLabel: domKindLabel(kind),
        value,
        hint: cleanText(rawTarget.hint),
        source,
        locator: locatorForDomTarget(kind, value),
        stability: stabilityForDomKind(kind)
      };

      targets.push(target);
      fileGroup.targets.push(target);
      fileGroup.targetCount += 1;
      repositoryGroup.targetCount += 1;
      incrementKindCount(kindCounts, kind);
      incrementKindCount(fileGroup.kindCounts, kind);
      incrementKindCount(repositoryGroup.kindCounts, kind);
    });
  });

  const moduleRepositories = repositoriesWithDomModules(repositories, targets, apiRoutes);
  if (moduleRepositories.length) {
    const moduleTargets = moduleRepositories.flatMap((repository) =>
      repository.files.flatMap((file) => file.targets)
    );
    return {
      repositories: moduleRepositories,
      files: moduleRepositories.flatMap((repository) => repository.files),
      targets: moduleTargets,
      kindCounts: countKinds(moduleTargets)
    };
  }

  const repositoriesWithTargets = Array.from(repositoryMap.values())
    .map((repository) => {
      const files = repository.files.flatMap(pageModulesForFile).sort(compareFiles);
      const repositoryTargets = files.flatMap((file) => file.targets);
      return {
        ...repository,
        targetCount: repositoryTargets.length,
        fileCount: files.length,
        kindCounts: countKinds(repositoryTargets),
        files
      };
    })
    .filter((repository) => repository.targetCount > 0)
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'));

  const files = repositoriesWithTargets.flatMap((repository) => repository.files);

  return {
    repositories: repositoriesWithTargets,
    files,
    targets: sortTargets(targets),
    kindCounts
  };
}

/**
 * 在已经构建好的图谱内做本地筛选，保留仓库和文件层级，避免搜索后丢失上下文。
 */
export function filterDomTargetGraph(graph: DomTargetGraph, keyword: string): DomTargetGraph {
  const normalized = keyword.trim().toLowerCase();
  if (!normalized) return graph;

  const repositories = graph.repositories
    .map((repository) => {
      const files = repository.files
        .map((file) => {
          const fileMatched = domFileGroupSearchText(file).includes(normalized);
          const targets = fileMatched
            ? file.targets
            : file.targets.filter((target) => domTargetSearchText(target).includes(normalized));
          return fileFromTargets(file, targets);
        })
        .filter((file): file is DomFileGroup => Boolean(file));

      if (!files.length) return null;
      return repositoryFromFiles(repository, files);
    })
    .filter((repository): repository is DomRepositoryGroup => Boolean(repository));

  const targets = repositories.flatMap((repository) => repository.files.flatMap((file) => file.targets));
  return {
    repositories,
    files: repositories.flatMap((repository) => repository.files),
    targets,
    kindCounts: countKinds(targets)
  };
}

export function domKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    testid: '测试标识',
    'aria-label': '可访问标签',
    placeholder: '输入提示',
    name: '表单名称',
    id: '页面 ID',
    route: '页面路由',
    module: '模块摘要'
  };
  return labels[kind] ?? 'DOM 目标';
}

export function domKindEntries(kindCounts: Record<string, number>): Array<[string, number]> {
  return Object.entries(kindCounts).sort(([leftKind, leftCount], [rightKind, rightCount]) => {
    const weight = kindWeight(leftKind) - kindWeight(rightKind);
    return weight || rightCount - leftCount || leftKind.localeCompare(rightKind, 'zh-CN');
  });
}

export function domFileName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function ensureRepositoryGroup(
  repositoryMap: Map<string, DomRepositoryGroup>,
  repository: Repository
): DomRepositoryGroup {
  const existing = repositoryMap.get(repository.id);
  if (existing) return existing;

  const group: DomRepositoryGroup = {
    id: repository.id,
    kind: repository.kind,
    label: repository.name || repositoryKindLabel(repository.kind),
    path: repository.path,
    targetCount: 0,
    fileCount: 0,
    kindCounts: {},
    files: []
  };
  repositoryMap.set(repository.id, group);
  return group;
}

function ensureFileGroup(
  fileMap: Map<string, DomFileGroup>,
  repository: DomRepositoryGroup,
  fileId: string,
  filePath: string
): DomFileGroup {
  const existing = fileMap.get(fileId);
  if (existing) return existing;

  const group: DomFileGroup = {
    id: fileId,
    repositoryId: repository.id,
    repositoryKind: repository.kind,
    repositoryName: repository.label,
    repositoryPath: repository.path,
    moduleName: domFileName(filePath),
    moduleType: 'component',
    pagePath: null,
    source: filePath,
    framework: null,
    previewHtml: null,
    previewSource: null,
    previewStrategy: null,
    previewCompiledAt: null,
    isCompiled: false,
    evidence: [],
    componentRefs: [],
    relatedComponents: [],
    apiRefs: [],
    relatedApiRoutes: [],
    path: filePath,
    targetCount: 0,
    kindCounts: {},
    targets: []
  };
  fileMap.set(fileId, group);
  repository.files.push(group);
  return group;
}

function repositoryFromFiles(
  repository: DomRepositoryGroup,
  files: DomFileGroup[]
): DomRepositoryGroup {
  const linkedFiles = linkRelatedComponents(files);
  const targets = linkedFiles.flatMap((file) => file.targets);
  return {
    ...repository,
    files: linkedFiles,
    fileCount: linkedFiles.length,
    targetCount: targets.length,
    kindCounts: countKinds(targets)
  };
}

function fileFromTargets(file: DomFileGroup, targets: DomTargetNode[]): DomFileGroup | null {
  if (!targets.length) return null;
  return {
    ...file,
    targets,
    relatedComponents: [],
    targetCount: targets.length,
    kindCounts: countKinds(targets)
  };
}

function pageModulesForFile(file: DomFileGroup): DomFileGroup[] {
  const sortedTargets = sortTargets(file.targets);
  const routeTargets = sortedTargets.filter((target) => target.kind === 'route');
  if (!routeTargets.length) {
    return [moduleFromTargets(file, {
      id: file.id,
      moduleName: domFileName(file.path),
      moduleType: 'component',
      pagePath: null,
      source: file.source,
      framework: file.framework,
      previewHtml: file.previewHtml,
      previewSource: file.previewSource,
      previewStrategy: file.previewStrategy,
      evidence: file.evidence,
      targets: sortedTargets
    })];
  }

  const nonRouteTargets = sortedTargets.filter((target) => target.kind !== 'route');
  return routeTargets.map((routeTarget, index) => moduleFromTargets(file, {
    id: `${file.id}:page:${routeTarget.value}:${routeTarget.line ?? index}`,
    moduleName: routeTarget.value,
    moduleType: 'page',
    pagePath: routeTarget.value,
    source: file.source,
    framework: file.framework,
    previewHtml: file.previewHtml,
    previewSource: file.previewSource,
    previewStrategy: file.previewStrategy,
    evidence: file.evidence,
    targets: sortTargets([routeTarget, ...nonRouteTargets])
  }));
}

function moduleFromTargets(
  file: DomFileGroup,
  patch: Pick<
    DomFileGroup,
    | 'id'
    | 'moduleName'
    | 'moduleType'
    | 'pagePath'
    | 'source'
    | 'framework'
    | 'previewHtml'
    | 'previewSource'
    | 'previewStrategy'
    | 'evidence'
    | 'targets'
  >
): DomFileGroup {
  return {
    ...file,
    ...patch,
    targetCount: patch.targets.length,
    kindCounts: countKinds(patch.targets)
  };
}

function repositoriesWithDomModules(
  repositories: Repository[],
  extractedTargets: DomTargetNode[],
  apiRoutes: DomApiRouteRef[]
): DomRepositoryGroup[] {
  const groups = repositories
    .map((repository) => {
      const rawModules = domModulesFromRepository(repository);
      if (!rawModules.length) return null;
      const repositoryGroup = ensureRepositoryGroup(new Map(), repository);
      const files = linkRelatedComponents(rawModules
        .map((module, index) => (
          domFileGroupFromModule(repositoryGroup, module, extractedTargets, apiRoutes, index)
        ))
        .filter((module): module is DomFileGroup => Boolean(module)))
        .sort(compareModules);
      const repositoryTargets = files.flatMap((file) => file.targets);
      return {
        ...repositoryGroup,
        files,
        fileCount: files.length,
        targetCount: repositoryTargets.length,
        kindCounts: countKinds(repositoryTargets)
      };
    })
    .filter((repository): repository is DomRepositoryGroup => Boolean(repository && repository.files.length));
  return groups.sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'));
}

function domFileGroupFromModule(
  repository: DomRepositoryGroup,
  rawModule: Record<string, unknown>,
  extractedTargets: DomTargetNode[],
  apiRoutes: DomApiRouteRef[],
  index: number
): DomFileGroup | null {
  const moduleType = cleanText(rawModule.kind) === 'page' ? 'page' : 'component';
  const source = cleanText(rawModule.source);
  const sourceFile = cleanText(rawModule.source_file) || parseSourceLocation(source).filePath;
  const route = cleanText(rawModule.route) || null;
  const name = cleanText(rawModule.name) || route || domFileName(sourceFile || source || `module-${index + 1}`);
  const rawPreview = rawModule.preview && typeof rawModule.preview === 'object'
    ? rawModule.preview as Record<string, unknown>
    : {};
  const previewCompiledAt = cleanText(rawPreview.compiled_at) || cleanText(rawPreview.compiledAt) || null;
  const matchedTargets = extractedTargets.filter((target) => {
    if (target.repositoryId !== repository.id || !sourceFile || target.filePath !== sourceFile) return false;
    if (moduleType === 'component') return true;
    return target.kind !== 'route' || !route || target.value === route;
  });
  const routeTarget = route
    ? syntheticTargetFromModule(repository, {
      index,
      kind: 'route',
      value: route,
      source: source || sourceFile,
      sourceFile,
      hint: name
    })
    : null;
  const targets = sortTargets([
    ...(routeTarget ? [routeTarget] : []),
    ...matchedTargets.filter((target) => !routeTarget || target.id !== routeTarget.id)
  ]);
  const finalTargets = targets.length
    ? targets
    : [syntheticTargetFromModule(repository, {
      index,
      kind: 'module',
      value: name,
      source: source || sourceFile,
      sourceFile,
      hint: evidenceFromModule(rawModule)[0] ?? ''
    })];
  const apiRefs = textListFromModule(rawModule, 'api_refs', 'apiRefs');
  return {
    id: cleanText(rawModule.id) || `${repository.id}:dom-module:${index}`,
    repositoryId: repository.id,
    repositoryKind: repository.kind,
    repositoryName: repository.label,
    repositoryPath: repository.path,
    moduleName: name,
    moduleType,
    pagePath: route,
    source: source || sourceFile,
    framework: cleanText(rawModule.framework) || null,
    previewHtml: cleanText(rawPreview.html) || null,
    previewSource: cleanText(rawPreview.source_file) || null,
    previewStrategy: cleanText(rawPreview.strategy) || null,
    previewCompiledAt,
    isCompiled: Boolean(previewCompiledAt),
    evidence: evidenceFromModule(rawModule),
    componentRefs: textListFromModule(rawModule, 'component_refs', 'componentRefs'),
    relatedComponents: [],
    apiRefs,
    relatedApiRoutes: relatedApiRoutesForRefs(apiRefs, apiRoutes),
    path: sourceFile || source || name,
    targetCount: finalTargets.length,
    kindCounts: countKinds(finalTargets),
    targets: finalTargets
  };
}

function syntheticTargetFromModule(
  repository: DomRepositoryGroup,
  options: {
    index: number;
    kind: string;
    value: string;
    source: string;
    sourceFile: string;
    hint: string;
  }
): DomTargetNode {
  const sourceLocation = parseSourceLocation(options.source);
  const filePath = options.sourceFile || sourceLocation.filePath || '系统编译模块';
  return {
    id: `${repository.id}:synthetic:${options.kind}:${options.value}:${options.index}`,
    repositoryId: repository.id,
    repositoryKind: repository.kind,
    repositoryName: repository.label,
    repositoryPath: repository.path,
    fileId: `${repository.id}:${filePath}`,
    filePath,
    line: sourceLocation.line,
    kind: options.kind,
    kindLabel: domKindLabel(options.kind),
    value: options.value,
    hint: options.hint,
    source: options.source,
    locator: locatorForDomTarget(options.kind, options.value),
    stability: stabilityForDomKind(options.kind)
  };
}

function domTargetsFromRepository(repository: Repository): Array<Record<string, unknown>> {
  const summary = repository.index_summary;
  if (!summary || typeof summary !== 'object') return [];
  const targets = (summary as { dom_targets?: unknown }).dom_targets;
  if (!Array.isArray(targets)) return [];
  return targets.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
}

function domModulesFromRepository(repository: Repository): Array<Record<string, unknown>> {
  const summary = repository.index_summary;
  if (!summary || typeof summary !== 'object') return [];
  const modules = (summary as { dom_modules?: unknown }).dom_modules;
  if (!Array.isArray(modules)) return [];
  return modules.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
}

function evidenceFromModule(rawModule: Record<string, unknown>): string[] {
  const evidence = rawModule.evidence;
  if (!Array.isArray(evidence)) return [];
  return evidence.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function textListFromModule(
  rawModule: Record<string, unknown>,
  snakeKey: string,
  camelKey: string
): string[] {
  const rawValues = rawModule[snakeKey] ?? rawModule[camelKey];
  if (!Array.isArray(rawValues)) return [];
  return uniqueStrings(rawValues.map((item) => String(item ?? '').trim()).filter(Boolean));
}

function parseSourceLocation(source: string): SourceLocation {
  if (!source) return { filePath: '未知来源', line: null };
  const separatorIndex = source.lastIndexOf(':');
  if (separatorIndex < 0) return { filePath: source, line: null };

  const rawLine = source.slice(separatorIndex + 1);
  const line = Number(rawLine);
  if (!Number.isInteger(line) || line <= 0) return { filePath: source, line: null };
  return {
    filePath: source.slice(0, separatorIndex),
    line
  };
}

function normalizeKind(value: unknown): DomTargetKind {
  const kind = cleanText(value).toLowerCase();
  return kind || 'target';
}

function locatorForDomTarget(kind: string, value: string): string | null {
  if (!value) return null;
  const escapedValue = escapeCssAttributeValue(value);
  if (kind === 'testid') return `[data-testid="${escapedValue}"]`;
  if (kind === 'aria-label') return `[aria-label="${escapedValue}"]`;
  if (kind === 'placeholder') return `getByPlaceholder("${escapePlaywrightText(value)}")`;
  if (kind === 'name') return `[name="${escapedValue}"]`;
  if (kind === 'id') return /^[A-Za-z_][\w-]*$/.test(value) ? `#${value}` : `[id="${escapedValue}"]`;
  if (kind === 'route') return value;
  return null;
}

function stabilityForDomKind(kind: string): DomTargetNode['stability'] {
  if (kind === 'testid' || kind === 'aria-label') return 'high';
  if (kind === 'id' || kind === 'name' || kind === 'placeholder' || kind === 'route') return 'medium';
  return 'low';
}

function domTargetSearchText(target: DomTargetNode): string {
  return [
    target.repositoryKind,
    target.repositoryName,
    target.repositoryPath,
    target.filePath,
    target.kind,
    target.kindLabel,
    target.value,
    target.locator,
    target.hint,
    target.source
  ].map((value) => String(value ?? '').toLowerCase()).join(' ');
}

function domFileGroupSearchText(file: DomFileGroup): string {
  return [
    file.repositoryKind,
    file.repositoryName,
    file.repositoryPath,
    file.moduleName,
    file.moduleType,
    file.pagePath,
    file.source,
    file.framework,
    file.path,
    ...file.evidence,
    ...file.componentRefs,
    ...file.apiRefs,
    ...file.relatedApiRoutes.flatMap((route) => [
      route.method,
      route.path,
      route.summary,
      route.handler,
      route.source,
      route.repositoryName
    ])
  ].map((value) => String(value ?? '').toLowerCase()).join(' ');
}

function repositoryKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    workspace: '工作区',
    frontend: '前端仓库',
    backend: '后端仓库'
  };
  return (labels[kind] ?? kind) || '仓库';
}

function sortTargets(targets: DomTargetNode[]): DomTargetNode[] {
  return [...targets].sort((left, right) => {
    const lineDiff = (left.line ?? Number.MAX_SAFE_INTEGER) - (right.line ?? Number.MAX_SAFE_INTEGER);
    return (
      left.filePath.localeCompare(right.filePath, 'zh-CN')
      || lineDiff
      || kindWeight(left.kind) - kindWeight(right.kind)
      || left.value.localeCompare(right.value, 'zh-CN')
    );
  });
}

function compareFiles(left: DomFileGroup, right: DomFileGroup): number {
  return right.targetCount - left.targetCount || left.path.localeCompare(right.path, 'zh-CN');
}

function compareModules(left: DomFileGroup, right: DomFileGroup): number {
  if (left.moduleType !== right.moduleType) return left.moduleType === 'page' ? -1 : 1;
  return left.moduleName.localeCompare(right.moduleName, 'zh-CN') || compareFiles(left, right);
}

function countKinds(targets: DomTargetNode[]): Record<string, number> {
  const counts: Record<string, number> = {};
  targets.forEach((target) => incrementKindCount(counts, target.kind));
  return counts;
}

function incrementKindCount(counts: Record<string, number>, kind: string): void {
  counts[kind] = (counts[kind] ?? 0) + 1;
}

function kindWeight(kind: string): number {
  const weights: Record<string, number> = {
    route: 0,
    testid: 1,
    'aria-label': 2,
    id: 3,
    name: 4,
    placeholder: 5
  };
  return weights[kind] ?? 20;
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  values.forEach((value) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    unique.push(value);
  });
  return unique;
}


function escapeCssAttributeValue(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function escapePlaywrightText(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}
