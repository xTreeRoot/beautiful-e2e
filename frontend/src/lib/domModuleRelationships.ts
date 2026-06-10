import type { DomFileGroup, DomRelatedComponent, DomTargetNode } from './domTargetGraph';

export type DomRelationship = {
  id: string;
  from: DomTargetNode;
  to: DomTargetNode;
  reason: string;
  scopeLabel: string | null;
};

export function entrypointTargetsForModule(
  module: DomFileGroup | DomRelatedComponent | null
): DomTargetNode[] {
  if (!module) return [];
  const entryKinds = new Set(['route', 'testid', 'aria-label']);
  const primary = module.targets.filter((target) => entryKinds.has(target.kind));
  if (primary.length) return primary.slice(0, 8);
  return module.targets.filter((target) => target.stability !== 'low').slice(0, 4);
}

export function relationshipsForModule(module: DomFileGroup | null): DomRelationship[] {
  if (!module) return [];
  const entrypoints = entrypointTargetsForModule(module);
  if (!entrypoints.length) return [];
  const pageEntry = entrypoints.find((entry) => entry.kind === 'route') ?? entrypoints[0];
  const ownRelationships = module.targets
    .filter((target) => target.id !== pageEntry.id)
    .slice(0, 24)
    .map((target) => ({
      id: `${pageEntry.id}->${target.id}`,
      from: pageEntry,
      to: target,
      reason: relationshipReason(target),
      scopeLabel: null
    }));
  if (module.moduleType !== 'page' || !module.relatedComponents.length) return ownRelationships;

  const componentRelationships = module.relatedComponents.flatMap((component) => {
    const componentEntry = entrypointTargetsForModule(component)[0] ?? component.targets[0];
    if (!componentEntry) return [];
    const entryRelationship: DomRelationship = {
      id: `${pageEntry.id}->${componentEntry.id}`,
      from: pageEntry,
      to: componentEntry,
      reason: `页面源码引用组件 ${component.moduleName}，该组件入口需要跟随页面链路一起验证。`,
      scopeLabel: component.moduleName
    };
    const childRelationships = component.targets
      .filter((target) => target.id !== componentEntry.id)
      .slice(0, 12)
      .map((target) => ({
        id: `${componentEntry.id}->${target.id}`,
        from: componentEntry,
        to: target,
        reason: componentRelationshipReason(target, component),
        scopeLabel: component.moduleName
      }));
    return [entryRelationship, ...childRelationships];
  });

  return uniqueRelationships([...ownRelationships, ...componentRelationships]).slice(0, 48);
}

export function targetsForModuleScope(module: DomFileGroup | null): DomTargetNode[] {
  if (!module) return [];
  if (module.moduleType !== 'page' || !module.relatedComponents.length) return module.targets;
  return uniqueTargets([
    ...module.targets,
    ...module.relatedComponents.flatMap((component) => component.targets)
  ]);
}

export function kindCountsForTargets(targets: DomTargetNode[]): Record<string, number> {
  const counts: Record<string, number> = {};
  targets.forEach((target) => {
    counts[target.kind] = (counts[target.kind] ?? 0) + 1;
  });
  return counts;
}

function relationshipReason(target: DomTargetNode): string {
  if (target.kind === 'placeholder' || target.kind === 'name') {
    return '该目标看起来是表单输入或参数承载点，适合作为填充步骤或前置数据入口。';
  }
  if (target.kind === 'testid' || target.kind === 'aria-label') {
    return '该目标具备较稳定的自动化定位特征，适合作为点击、断言或关键状态锚点。';
  }
  if (target.kind === 'id') {
    return '该目标来自页面 id，稳定性需要结合源码语义复核，可作为候选定位。';
  }
  return '该目标与当前模块入口同源，可作为后续步骤或断言的候选证据。';
}

function componentRelationshipReason(target: DomTargetNode, component: DomRelatedComponent): string {
  return `该目标来自页面关联组件 ${component.moduleName}，应作为页面流程中的组件内操作或断言候选。${relationshipReason(target)}`;
}

function uniqueTargets(targets: DomTargetNode[]): DomTargetNode[] {
  const seen = new Set<string>();
  return targets.filter((target) => {
    if (seen.has(target.id)) return false;
    seen.add(target.id);
    return true;
  });
}

function uniqueRelationships(relationships: DomRelationship[]): DomRelationship[] {
  const seen = new Set<string>();
  return relationships.filter((relationship) => {
    if (seen.has(relationship.id)) return false;
    seen.add(relationship.id);
    return true;
  });
}
