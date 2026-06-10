import type { DomFileGroup, DomRelatedComponent } from './domTargetGraph';

export function linkRelatedComponents(files: DomFileGroup[]): DomFileGroup[] {
  const components = files.filter((file) => file.moduleType === 'component');
  const componentIndex = new Map<string, DomFileGroup[]>();

  components.forEach((component) => {
    componentReferenceKeys(component).forEach((key) => {
      const bucket = componentIndex.get(key) ?? [];
      bucket.push(component);
      componentIndex.set(key, bucket);
    });
  });

  return files.map((file) => {
    if (file.moduleType !== 'page' || !file.componentRefs.length) {
      return { ...file, relatedComponents: [] };
    }

    const relatedMap = new Map<string, DomRelatedComponent>();
    componentRefKeys(file.componentRefs).forEach((key) => {
      (componentIndex.get(key) ?? []).forEach((component) => {
        if (component.id === file.id || component.repositoryId !== file.repositoryId) return;
        relatedMap.set(component.id, relatedComponentFromModule(component));
      });
    });

    return {
      ...file,
      relatedComponents: Array.from(relatedMap.values()).sort(compareRelatedComponents)
    };
  });
}

function relatedComponentFromModule(component: DomFileGroup): DomRelatedComponent {
  return {
    id: component.id,
    moduleName: component.moduleName,
    moduleType: 'component',
    path: component.path,
    targetCount: component.targetCount,
    kindCounts: component.kindCounts,
    targets: component.targets,
    apiRefs: component.apiRefs,
    relatedApiRoutes: component.relatedApiRoutes
  };
}

function componentRefKeys(refs: string[]): Set<string> {
  const keys = new Set<string>();
  refs.forEach((ref) => {
    componentTokens(ref).forEach((token) => keys.add(token));
  });
  return keys;
}

function componentReferenceKeys(component: DomFileGroup): Set<string> {
  const keys = new Set<string>();
  [component.moduleName, component.path, fileName(component.path)].forEach((value) => {
    componentTokens(value).forEach((token) => keys.add(token));
  });
  return keys;
}

function componentTokens(value: string): string[] {
  const normalized = value.replace(/\.(vue|nvue|tsx|jsx|wxml|axml|svelte|html|js|ts)$/i, '');
  const parts = normalized.split(/[\\/]/).filter(Boolean);
  const candidates = [
    normalized,
    fileName(normalized),
    ...parts,
    parts[parts.length - 1] === 'index' ? parts[parts.length - 2] : ''
  ];
  return uniqueStrings(
    candidates
      .filter((candidate): candidate is string => Boolean(candidate))
      .map(canonicalComponentToken)
      .filter(Boolean)
  );
}

function canonicalComponentToken(value: string): string {
  const token = value.replace(/[^a-zA-Z0-9]+/g, '').toLowerCase();
  return IGNORED_COMPONENT_TOKENS.has(token) ? '' : token;
}

function compareRelatedComponents(left: DomRelatedComponent, right: DomRelatedComponent): number {
  return right.targetCount - left.targetCount || left.moduleName.localeCompare(right.moduleName, 'zh-CN');
}

function fileName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
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

const IGNORED_COMPONENT_TOKENS = new Set([
  'component',
  'components',
  'index',
  'page',
  'pages',
  'src',
  'view'
]);
