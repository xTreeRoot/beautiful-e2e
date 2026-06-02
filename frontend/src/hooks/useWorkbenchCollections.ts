import { useMemo, useState, type Dispatch, type SetStateAction } from 'react';

import { api, type Bootstrap, type Group, type Project, type TestCase } from '../api';
import { findCaseGroup, makeBlankCase, makeDemoCase } from '../lib/canvas';
import { sortGroups } from '../lib/project';
import type { CaseCreateMode, SidebarMenuKey, ExecutionMode } from '../types/workbench';

type UseWorkbenchCollectionsOptions = {
  project?: Project;
  groups: Group[];
  executionMode: ExecutionMode;
  frontendPath: string;
  backendPath: string;
  offlineMode: boolean;
  setBootstrap: Dispatch<SetStateAction<Bootstrap | null>>;
  setStatus: (status: string) => void;
  setActiveSidebarMenu: Dispatch<SetStateAction<SidebarMenuKey>>;
  showToast: (type: 'success' | 'info' | 'warning' | 'error', content: string) => void;
};

/**
 * 管理工作台的分组和用例集合。
 * 分组/用例 CRUD、弹窗表单和选中规则共享同一批状态，独立后 controller 只消费当前选中用例和集合操作。
 */
export function useWorkbenchCollections({
  project,
  groups,
  executionMode,
  frontendPath,
  backendPath,
  offlineMode,
  setBootstrap,
  setStatus,
  setActiveSidebarMenu,
  showToast
}: UseWorkbenchCollectionsOptions) {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [activeGroupId, setActiveGroupId] = useState<string>('all');
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [isGroupCreateOpen, setIsGroupCreateOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupDescription, setNewGroupDescription] = useState('');
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const [editingGroupName, setEditingGroupName] = useState('');
  const [editingGroupDescription, setEditingGroupDescription] = useState('');
  const [groupActionId, setGroupActionId] = useState<string | null>(null);
  const [isCaseCreateOpen, setIsCaseCreateOpen] = useState(false);
  const [newCaseMode, setNewCaseMode] = useState<CaseCreateMode>('blank');
  const [newCaseTitle, setNewCaseTitle] = useState('');
  const [newCaseDescription, setNewCaseDescription] = useState('');
  const [newCaseGroupId, setNewCaseGroupId] = useState<string | null>(null);
  const [newCasePriority, setNewCasePriority] = useState('P1');
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null);
  const [editingCaseTitle, setEditingCaseTitle] = useState('');
  const [editingCaseDescription, setEditingCaseDescription] = useState('');
  const [editingCaseGroupId, setEditingCaseGroupId] = useState<string | null>(null);
  const [editingCasePriority, setEditingCasePriority] = useState('P1');
  const [editingCaseStatus, setEditingCaseStatus] = useState('draft');
  const [caseActionId, setCaseActionId] = useState<string | null>(null);

  const filteredCases = useMemo(() => {
    if (activeGroupId === 'all') return cases;
    return cases.filter((item) => item.group_id === activeGroupId);
  }, [activeGroupId, cases]);

  const selectedCase = useMemo(() => {
    return (
      filteredCases.find((item) => item.id === selectedCaseId) ??
      filteredCases[0] ??
      (activeGroupId === 'all' ? cases[0] : undefined)
    );
  }, [activeGroupId, cases, filteredCases, selectedCaseId]);

  const activeGroup = findCaseGroup(selectedCase, groups, activeGroupId);

  function handleActiveGroupChange(groupId: string) {
    const nextCases =
      groupId === 'all' ? cases : cases.filter((item) => item.group_id === groupId);
    // 从分组页选择时直接进入用例库，让过滤结果和左侧内容保持同步。
    setActiveGroupId(groupId);
    setSelectedCaseId(nextCases[0]?.id ?? null);
    setActiveSidebarMenu('cases');
  }

  function openGroupCreateModal() {
    setNewGroupName('');
    setNewGroupDescription('');
    setIsGroupCreateOpen(true);
  }

  function cancelGroupCreate() {
    setIsGroupCreateOpen(false);
    setNewGroupName('');
    setNewGroupDescription('');
  }

  async function createManagedGroup() {
    if (!project) return;
    const name = newGroupName.trim();
    if (!name) {
      showToast('warning', '请输入分组名称');
      return;
    }
    setGroupActionId('__create');
    try {
      const created = await api.createGroup(project.id, {
        name,
        description: newGroupDescription.trim() || null,
        sort_order: (groups[groups.length - 1]?.sort_order ?? 0) + 10
      });
      setBootstrap((current) =>
        current ? { ...current, groups: [...current.groups, created].sort(sortGroups) } : current
      );
      setActiveGroupId(created.id);
      setNewGroupName('');
      setNewGroupDescription('');
      setIsGroupCreateOpen(false);
      setStatus(`分组已创建到项目：${project.name}`);
      showToast('success', `分组已创建：${created.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '分组创建失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setGroupActionId(null);
    }
  }

  function startGroupEdit(group: Group) {
    setEditingGroupId(group.id);
    setEditingGroupName(group.name);
    setEditingGroupDescription(group.description ?? '');
  }

  function cancelGroupEdit() {
    setEditingGroupId(null);
    setEditingGroupName('');
    setEditingGroupDescription('');
  }

  async function updateManagedGroup(groupId: string) {
    const name = editingGroupName.trim();
    if (!name) {
      showToast('warning', '请输入分组名称');
      return;
    }
    setGroupActionId(groupId);
    try {
      const saved = await api.updateGroup(groupId, {
        name,
        description: editingGroupDescription.trim() || null
      });
      setBootstrap((current) =>
        current
          ? { ...current, groups: current.groups.map((item) => (item.id === saved.id ? saved : item)).sort(sortGroups) }
          : current
      );
      cancelGroupEdit();
      setStatus(`分组已更新：${saved.name}`);
      showToast('success', `分组已更新：${saved.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '分组更新失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setGroupActionId(null);
    }
  }

  async function deleteManagedGroup(groupId: string) {
    setGroupActionId(groupId);
    try {
      await api.deleteGroup(groupId);
      setBootstrap((current) =>
        current ? { ...current, groups: current.groups.filter((item) => item.id !== groupId) } : current
      );
      setCases((current) =>
        current.map((item) => (item.group_id === groupId ? { ...item, group_id: null } : item))
      );
      if (activeGroupId === groupId) setActiveGroupId('all');
      cancelGroupEdit();
      setStatus('分组已从当前项目删除');
      showToast('success', '分组已删除，用例已保留为未分组');
    } catch (error) {
      const message = error instanceof Error ? error.message : '分组删除失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setGroupActionId(null);
    }
  }

  function defaultCaseCreateGroupId(): string | null {
    return activeGroupId === 'all' ? groups[0]?.id ?? null : activeGroupId;
  }

  function openCaseCreateModal() {
    setNewCaseMode('blank');
    setNewCaseTitle('');
    setNewCaseDescription('');
    setNewCaseGroupId(defaultCaseCreateGroupId());
    setNewCasePriority('P1');
    setIsCaseCreateOpen(true);
  }

  function cancelCaseCreate() {
    setIsCaseCreateOpen(false);
    setNewCaseMode('blank');
    setNewCaseTitle('');
    setNewCaseDescription('');
    setNewCaseGroupId(null);
    setNewCasePriority('P1');
  }

  async function createManagedCase() {
    if (!project) return;
    const mode = newCaseMode;
    const title = newCaseTitle.trim();
    const description = newCaseDescription.trim();
    if (!title) {
      showToast('warning', '请输入用例名称');
      return;
    }
    if (mode === 'ai' && description.length < 3) {
      showToast('warning', '请输入至少 3 个字的生成说明');
      return;
    }

    setCaseActionId('__create');
    try {
      const created =
        offlineMode
          ? createOfflineCase(mode, title, description)
          : await createPersistedCase(mode, title, description);
      setCases((current) => [created, ...current]);
      setSelectedCaseId(created.id);
      setActiveGroupId(created.group_id ?? 'all');
      setActiveSidebarMenu('cases');
      cancelCaseCreate();
      setStatus(mode === 'ai' ? '用例已生成' : '用例已创建');
      showToast('success', mode === 'ai' ? `用例已生成：${created.title}` : `用例已创建：${created.title}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '用例创建失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setCaseActionId(null);
    }
  }

  function createOfflineCase(mode: CaseCreateMode, title: string, description: string): TestCase {
    if (mode === 'ai') {
      return {
        ...makeDemoCase(description, newCaseGroupId ?? undefined),
        title,
        description,
        priority: newCasePriority,
        group_id: newCaseGroupId
      };
    }
    return makeBlankCase({
      title,
      description,
      groupId: newCaseGroupId,
      priority: newCasePriority
    });
  }

  async function createPersistedCase(
    mode: CaseCreateMode,
    title: string,
    description: string
  ): Promise<TestCase> {
    if (!project) throw new Error('未选择项目');
    if (mode === 'ai') {
      return api.generateCaseStream(project.id, {
        title,
        description,
        case_description: description,
        execution_mode: executionMode,
        group_id: newCaseGroupId,
        frontend_repo_path: frontendPath || undefined,
        backend_repo_path: backendPath || undefined,
        created_by: 'developer',
        priority: newCasePriority
      });
    }
    return api.createCase(project.id, {
      title,
      description: description || null,
      group_id: newCaseGroupId,
      priority: newCasePriority,
      status: 'draft',
      created_by: 'developer'
    });
  }

  function startCaseEdit(testCase: TestCase) {
    setEditingCaseId(testCase.id);
    setEditingCaseTitle(testCase.title);
    setEditingCaseDescription(testCase.description);
    setEditingCaseGroupId(testCase.group_id);
    setEditingCasePriority(testCase.priority);
    setEditingCaseStatus(testCase.status);
  }

  function cancelCaseEdit() {
    setEditingCaseId(null);
    setEditingCaseTitle('');
    setEditingCaseDescription('');
    setEditingCaseGroupId(null);
    setEditingCasePriority('P1');
    setEditingCaseStatus('draft');
  }

  async function updateManagedCase(caseId: string) {
    const title = editingCaseTitle.trim();
    if (!title) {
      showToast('warning', '请输入用例名称');
      return;
    }
    setCaseActionId(caseId);
    try {
      const saved = await api.updateCase(caseId, {
        title,
        description: editingCaseDescription.trim() || title,
        group_id: editingCaseGroupId,
        priority: editingCasePriority,
        status: editingCaseStatus
      });
      setCases((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      setSelectedCaseId(saved.id);
      cancelCaseEdit();
      setStatus(`用例已更新到项目：${project?.name ?? ''}`);
      showToast('success', `用例已更新：${saved.title}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '用例更新失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setCaseActionId(null);
    }
  }

  async function deleteManagedCase(caseId: string) {
    setCaseActionId(caseId);
    try {
      await api.deleteCase(caseId);
      setCases((current) => {
        const next = current.filter((item) => item.id !== caseId);
        if (selectedCaseId === caseId) setSelectedCaseId(next[0]?.id ?? null);
        return next;
      });
      cancelCaseEdit();
      setStatus('用例已从当前项目删除');
      showToast('success', '用例已删除');
    } catch (error) {
      const message = error instanceof Error ? error.message : '用例删除失败';
      setStatus(message);
      showToast('error', message);
    } finally {
      setCaseActionId(null);
    }
  }

  return {
    cases,
    setCases,
    filteredCases,
    selectedCase,
    activeGroup,
    activeGroupId,
    setActiveGroupId,
    handleActiveGroupChange,
    selectedCaseId,
    setSelectedCaseId,
    isGroupCreateOpen,
    newGroupName,
    setNewGroupName,
    newGroupDescription,
    setNewGroupDescription,
    editingGroupId,
    editingGroupName,
    setEditingGroupName,
    editingGroupDescription,
    setEditingGroupDescription,
    groupActionId,
    isCaseCreateOpen,
    newCaseMode,
    setNewCaseMode,
    newCaseTitle,
    setNewCaseTitle,
    newCaseDescription,
    setNewCaseDescription,
    newCaseGroupId,
    setNewCaseGroupId,
    newCasePriority,
    setNewCasePriority,
    editingCaseId,
    editingCaseTitle,
    setEditingCaseTitle,
    editingCaseDescription,
    setEditingCaseDescription,
    editingCaseGroupId,
    setEditingCaseGroupId,
    editingCasePriority,
    setEditingCasePriority,
    editingCaseStatus,
    setEditingCaseStatus,
    caseActionId,
    openGroupCreateModal,
    cancelGroupCreate,
    createManagedGroup,
    startGroupEdit,
    cancelGroupEdit,
    updateManagedGroup,
    deleteManagedGroup,
    openCaseCreateModal,
    cancelCaseCreate,
    createManagedCase,
    startCaseEdit,
    cancelCaseEdit,
    updateManagedCase,
    deleteManagedCase
  };
}
