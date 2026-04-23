import React, { useState, useMemo } from 'react';
import { Button, Divider, EmptyState, EmptyStateActions, EmptyStateBody, EmptyStateFooter, EmptyStateVariant, TreeView, TreeViewDataItem } from '@patternfly/react-core';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createWorkspaceFile, ensureWorkspace, getProjectServices, getWorkspaceFileTree, readWorkspaceFile, FileNode, Project } from '@/lib/api';
import { Loader2, FolderSearch, Rocket, FilePlus2 } from 'lucide-react';
import FolderIcon from '@patternfly/react-icons/dist/esm/icons/folder-icon';
import FolderOpenIcon from '@patternfly/react-icons/dist/esm/icons/folder-open-icon';
import FileIcon from '@patternfly/react-icons/dist/esm/icons/file-alt-icon';
import { toast } from '@/hooks/use-toast';

interface FileExplorerProps {
  project: Project;
  onFileSelect?: (path: string, content: string) => void;
  onOpenInEditor?: (path: string, content: string) => void;
  onAskAboutFile?: (path: string, content: string) => void;
  chatSessionId?: number | null;
  onEnsureSession?: () => Promise<number | null>;
}

/** Convert API FileNode[] → PF TreeViewDataItem[] */
function toTreeViewData(nodes: FileNode[]): TreeViewDataItem[] {
  return nodes.map((node) => ({
    id: node.path,
    name: node.name,
    icon: node.type === 'folder' ? <FolderIcon /> : <FileIcon />,
    expandedIcon: node.type === 'folder' ? <FolderOpenIcon /> : undefined,
    defaultExpanded: false,
    children: node.children?.length ? toTreeViewData(node.children) : undefined,
  }));
}

/** Walk a TreeViewDataItem tree and return the node matching `id` */
function findTreeItem(items: TreeViewDataItem[], id: string): TreeViewDataItem | undefined {
  for (const item of items) {
    if (item.id === id) return item;
    if (item.children) {
      const found = findTreeItem(item.children, id);
      if (found) return found;
    }
  }
  return undefined;
}

/**
 * FileExplorer provides a PatternFly TreeView file browser that emits file
 * selections to the parent (typically TabbedEditor or AIEditorTab).
 */
export const FileExplorer: React.FC<FileExplorerProps> = ({
  project,
  onFileSelect,
  onOpenInEditor,
  onAskAboutFile,
  chatSessionId,
  onEnsureSession,
}) => {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['workspace-file-tree', project.id],
    queryFn: () => getWorkspaceFileTree(project.id),
    retry: 2,
  });

  const { data: services = [] } = useQuery({
    queryKey: ['project-services', project.id, 'file-explorer'],
    queryFn: () => getProjectServices(project.id),
    select: (response) => response?.data || [],
    retry: 1,
  });

  const rawTree = data?.data?.tree?.children || ([] as FileNode[]);
  const treeData = useMemo(() => toTreeViewData(rawTree), [rawTree]);
  const workspaceService = services.find((service: any) => service.service_type === 'ai-workspace');
  const isWorkspaceRunning = workspaceService?.status === 'running';

  const readFile = useMutation({
    mutationFn: (path: string) => readWorkspaceFile(project.id, path),
    onSuccess: (res, path) => {
      if (res.data?.success) {
        setSelectedFile(path);
        setSelectedFileContent(res.data.content);
        if (onFileSelect) {
          onFileSelect(path, res.data.content);
        }
      } else {
        setSelectedFileContent('// Failed to read file');
      }
    },
    onError: () => setSelectedFileContent('// Error reading file'),
  });

  const createFile = useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) => createWorkspaceFile(project.id, path, content),
    onSuccess: (_response, variables) => {
      setSelectedFile(variables.path);
      setSelectedFileContent(variables.content);
      queryClient.invalidateQueries({ queryKey: ['workspace-file-tree', project.id] });
      toast({ title: 'File created', description: `${variables.path} is ready to edit.` });
      if (onFileSelect) {
        onFileSelect(variables.path, variables.content);
      }
      if (onOpenInEditor) {
        onOpenInEditor(variables.path, variables.content);
      }
    },
    onError: () => {
      toast({ title: 'Unable to create file', description: 'Choose a different path and try again.', variant: 'destructive' });
    },
  });

  const startWorkspace = useMutation({
    mutationFn: () => ensureWorkspace(project.id),
    onSuccess: () => {
      toast({ title: 'Workspace starting', description: 'Refreshing files as the workspace comes online.' });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id, 'file-explorer'] });
      queryClient.invalidateQueries({ queryKey: ['workspace-file-tree', project.id] });
    },
    onError: () => {
      toast({ title: 'Unable to start workspace', description: 'Try again from the workspace controls.', variant: 'destructive' });
    },
  });

  const handleTreeSelect = (_event: React.MouseEvent, item: TreeViewDataItem) => {
    // Only read leaf files, not folders
    if (item.children && item.children.length > 0) return;
    const path = item.id as string;
    console.debug('[FileExplorer] Selected file:', path);
    readFile.mutate(path);
  };

  const activeItems = useMemo(() => {
    if (!selectedFile || treeData.length === 0) return undefined;
    const node = findTreeItem(treeData, selectedFile);
    return node ? [node] : undefined;
  }, [selectedFile, treeData]);

  const handleCreateFile = () => {
    const nextPath = window.prompt('Create a new file', 'src/new-file.tsx');
    if (!nextPath) return;
    const path = nextPath.trim();
    if (!path) return;
    createFile.mutate({ path, content: '' });
  };

  const handleDeepAnalyze = async () => {
    if (!selectedFile || selectedFileContent == null) return;

    if ((selectedFileContent || '').length > 5000) {
      if (
        !confirm(
          'File is large and deep analysis may consume tokens/cost. Start deep analysis?'
        )
      )
        return;
    }

    let sid = typeof chatSessionId === 'number' ? chatSessionId : null;
    if (!sid && onEnsureSession) {
      try {
        const newSid = await onEnsureSession();
        sid = typeof newSid === 'number' ? newSid : sid;
        if (!sid) {
          alert('Could not create session; deep analysis will run without streaming.');
        }
      } catch (e) {
        console.error('Failed to create session for streaming', e);
        alert('Failed to create session; deep analysis will run without streaming.');
      }
    }

    import('@/lib/api').then((api) => {
      api
        .analyzeWorkspaceFile(project.id, selectedFile, 'deep', sid || undefined)
        .then((res) => {
          const streaming = res?.data?.streaming;
          const returnedSid = res?.data?.session_id;
          if (streaming) {
            console.log(`[FileExplorer] Deep analysis started (session: ${returnedSid})`);
          }
        })
        .catch(() => alert('Failed to start deep analysis'));
    });
  };

  return (
    <div className="h-full flex flex-col overflow-hidden" style={{ backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>
      {/* Header */}
      <div
        className="px-3 py-2 flex flex-col gap-0.5 flex-shrink-0"
        style={{
          fontSize: '0.6875rem',
          fontWeight: 'var(--pf-v6-global--FontWeight--bold)' as any,
          color: 'var(--pf-v6-global--Color--200)',
          borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
        }}
      >
        <span>Files</span>
        <span style={{ fontSize: '0.6875rem', fontWeight: 400, lineHeight: 1.4 }}>
          Browse the workspace or open a file in the editor.
        </span>
      </div>

      {/* Tree area — use relative+absolute to guarantee scroll containment */}
      <div className="flex-1 min-h-0 relative">
        <div className="absolute inset-0 overflow-auto overscroll-contain px-1 py-1">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-8">
            <Loader2 className="animate-spin h-4 w-4" />
            <span style={{ fontSize: '0.6875rem', color: 'var(--pf-v6-global--Color--200)' }}>
              Loading…
            </span>
          </div>
        ) : error || (!isWorkspaceRunning && treeData.length === 0) ? (
          <div className="flex min-h-full items-center justify-center px-3 py-5">
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="Start the workspace"
              titleClassName="text-sm"
              headingLevel="h4"
              icon={Rocket}
              className="max-w-[20rem]"
            >
              <EmptyStateBody>
                <span className="text-xs leading-5">
                  Start the workspace before browsing files, or create a new file to start from a blank canvas.
                </span>
              </EmptyStateBody>
              <EmptyStateFooter>
                <EmptyStateActions>
                  <Button size="sm" variant="primary" onClick={() => startWorkspace.mutate()} isDisabled={startWorkspace.isPending}>
                    {startWorkspace.isPending ? 'Starting...' : 'Start workspace'}
                  </Button>
                </EmptyStateActions>
                <EmptyStateActions>
                  <Button size="sm" variant="secondary" onClick={handleCreateFile} isDisabled={createFile.isPending}>
                    Create new file
                  </Button>
                  <Button size="sm" variant="link" onClick={() => refetch()}>
                    Refresh files
                  </Button>
                </EmptyStateActions>
              </EmptyStateFooter>
            </EmptyState>
          </div>
        ) : treeData.length === 0 ? (
          <div className="flex min-h-full items-center justify-center px-3 py-5">
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="Create your first workspace file"
              titleClassName="text-sm"
              headingLevel="h4"
              icon={FolderSearch}
              className="max-w-[20rem]"
            >
              <EmptyStateBody>
                <span className="text-xs leading-5">
                  This workspace is ready, but it does not have any files yet. Create a starter file and open it in the editor.
                </span>
              </EmptyStateBody>
              <EmptyStateFooter>
                <EmptyStateActions>
                  <Button size="sm" variant="primary" icon={<FilePlus2 size={14} />} onClick={handleCreateFile} isDisabled={createFile.isPending}>
                    Create new file
                  </Button>
                </EmptyStateActions>
                <EmptyStateActions>
                  <Button size="sm" variant="link" onClick={() => refetch()}>
                    Refresh files
                  </Button>
                </EmptyStateActions>
              </EmptyStateFooter>
            </EmptyState>
          </div>
        ) : (
          <TreeView
            data={treeData}
            activeItems={activeItems}
            onSelect={handleTreeSelect}
            hasSelectableNodes
            hasGuides
            aria-label="Workspace file tree"
          />
        )}
        </div>
      </div>

      {/* Selected file action panel */}
      {selectedFile && (
        <div className="flex-shrink-0">
          <Divider />
          <div className="px-3 py-2">
            <div
              className="mb-2 truncate"
              style={{
                fontSize: '0.6875rem',
                color: 'var(--pf-v6-global--Color--200)',
                fontFamily: 'var(--pf-v6-global--FontFamily--mono)',
              }}
              title={selectedFile}
            >
              {selectedFile}
            </div>
            <div className="flex flex-col gap-1">
              {onOpenInEditor && (
                <Button
                  size="sm"
                  variant="primary"
                  isBlock
                  onClick={() => {
                    if (selectedFileContent)
                      onOpenInEditor(selectedFile, selectedFileContent);
                  }}
                >
                  Open in Editor
                </Button>
              )}
              {onAskAboutFile && (
                <Button
                  size="sm"
                  variant="secondary"
                  isBlock
                  onClick={() => {
                    if (selectedFileContent)
                      onAskAboutFile(selectedFile, selectedFileContent);
                  }}
                >
                  Ask AI
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                isBlock
                onClick={handleDeepAnalyze}
              >
                Deep analyze
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileExplorer;
