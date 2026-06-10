import type { Repository } from '../api';

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

export type DomFileGroup = {
  id: string;
  repositoryId: string;
  repositoryKind: string;
  repositoryName: string;
  repositoryPath: string;
  path: string;
  targetCount: number;
  kindCounts: Record<string, number>;
  targets: DomTargetNode[];
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

  const repositoriesWithTargets = Array.from(repositoryMap.values())
    .map((repository) => ({
      ...repository,
      fileCount: repository.files.length,
      files: repository.files
        .map((file) => ({
          ...file,
          targets: sortTargets(file.targets)
        }))
        .sort(compareFiles)
    }))
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
          const targets = file.targets.filter((target) => domTargetSearchText(target).includes(normalized));
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
    route: '页面路由'
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
  const targets = files.flatMap((file) => file.targets);
  return {
    ...repository,
    files,
    fileCount: files.length,
    targetCount: targets.length,
    kindCounts: countKinds(targets)
  };
}

function fileFromTargets(file: DomFileGroup, targets: DomTargetNode[]): DomFileGroup | null {
  if (!targets.length) return null;
  return {
    ...file,
    targets,
    targetCount: targets.length,
    kindCounts: countKinds(targets)
  };
}

function domTargetsFromRepository(repository: Repository): Array<Record<string, unknown>> {
  const summary = repository.index_summary;
  if (!summary || typeof summary !== 'object') return [];
  const targets = (summary as { dom_targets?: unknown }).dom_targets;
  if (!Array.isArray(targets)) return [];
  return targets.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
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

function escapeCssAttributeValue(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function escapePlaywrightText(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}
