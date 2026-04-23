import React, { useState, useCallback, useRef, forwardRef, useImperativeHandle } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardBody } from '@patternfly/react-core';
import { Loader2, AlertCircle } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import { updateWorkspaceFile, Project } from '@/lib/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileTabBar, OpenFile } from './FileTabBar';
import { CodeEditor } from './CodeEditor';

interface TabbedEditorProps {
  project: Project;
  onAskAboutFile?: (path: string, content: string) => void;
  onFileDeleted?: (path: string) => void;
  onOpenFilesChange?: (files: { path: string; content: string; isDirty?: boolean }[]) => void;
}

export interface TabbedEditorHandle {
  openFile: (path: string, content: string) => void;
}

/**
 * TabbedEditor manages a set of open files with dirty state tracking
 * and integrates with Monaco CodeEditor.
 *
 * Features:
 * - Multiple file tabs
 * - Dirty state indicators (* on tab)
 * - Context menu: Ask AI, Rename, Delete
 * - Save/Discard buttons
 * - Bidirectional sync with backend
 */
const TabbedEditorInner: React.FC<TabbedEditorProps & { forwardedRef: React.Ref<TabbedEditorHandle> }> = (
  { project, onAskAboutFile, onFileDeleted, onOpenFilesChange, forwardedRef },
) => {
  const [openFiles, setOpenFilesInternal] = useState<OpenFile[]>([]);
  
  // Wrapper to sync openFiles with parent
  const setOpenFiles = useCallback((updater: OpenFile[] | ((prev: OpenFile[]) => OpenFile[])) => {
    setOpenFilesInternal((prev) => {
      const newFiles = typeof updater === 'function' ? updater(prev) : updater;
      // Notify parent of changes
      if (onOpenFilesChange) {
        onOpenFilesChange(newFiles);
      }
      return newFiles;
    });
  }, [onOpenFilesChange]);
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Save file mutation
  const saveFileMutation = useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      updateWorkspaceFile(project.id, path, content),
    onSuccess: (res, { path }) => {
      if (res.data?.success) {
        // Mark file as not dirty
        setOpenFiles((prev) =>
          prev.map((f) =>
            f.path === path ? { ...f, isDirty: false } : f
          )
        );
        toast({
          title: 'File saved',
          description: `${path} saved successfully.`,
          variant: 'default',
        });
        // Invalidate workspace file tree to show changes
        queryClient.invalidateQueries({
          queryKey: ['workspace-file-tree', project.id],
        });
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to save file.',
        variant: 'destructive',
      });
    },
  });

  const activeFile = openFiles.find((f) => f.path === activeFilePath);

  // Open a file (add to tabs or focus existing tab)
  const openFile = useCallback((path: string, content: string) => {
    console.debug(`[TabbedEditor] openFile called: path=${path}, contentLength=${content.length}`);
    
    setOpenFiles((prev) => {
      const existing = prev.find((f) => f.path === path);
      if (existing) {
        console.debug(`[TabbedEditor] File already open, focusing: ${path}`);
        return prev;
      }
      console.debug(`[TabbedEditor] Adding new file: ${path}`);
      return [...prev, { path, content, isDirty: false }];
    });
    
    // Set active file path OUTSIDE the setOpenFiles callback to ensure it triggers
    setActiveFilePath(path);
  }, []);

  // Expose openFile via ref
  useImperativeHandle(forwardedRef, () => ({
    openFile,
  }), [openFile]);

  // Close a tab
  const closeTab = useCallback((path: string) => {
    setOpenFiles((prev) => prev.filter((f) => f.path !== path));
    if (activeFilePath === path) {
      setActiveFilePath(null);
    }
  }, [activeFilePath]);

  // Mark file as dirty (user modified content)
  const markDirty = useCallback((path: string, newContent: string) => {
    setOpenFiles((prev) =>
      prev.map((f) =>
        f.path === path ? { ...f, content: newContent, isDirty: true } : f
      )
    );
  }, []);

  // Save file
  const handleSave = useCallback(() => {
    if (!activeFile) return;
    saveFileMutation.mutate({
      path: activeFile.path,
      content: activeFile.content,
    });
  }, [activeFile, saveFileMutation]);

  // Discard changes
  const handleDiscard = useCallback(() => {
    if (!activeFile) return;
    // Re-open file from backend (revert to last saved)
    // For now, just mark as not dirty
    setOpenFiles((prev) =>
      prev.map((f) =>
        f.path === activeFile.path ? { ...f, isDirty: false } : f
      )
    );
  }, [activeFile]);

  // Rename file (placeholder - would need backend support)
  const handleRenameFile = useCallback((oldPath: string) => {
    const newPath = prompt('New file path:', oldPath);
    if (newPath && newPath !== oldPath) {
      // TODO: Call backend to rename file
      toast({
        title: 'Rename (stub)',
        description: `Would rename ${oldPath} to ${newPath}`,
        variant: 'default',
      });
    }
  }, []);

  // Delete file (with confirmation)
  const handleDeleteFile = useCallback((path: string) => {
    // TODO: Call backend to delete file
    toast({
      title: 'Delete (stub)',
      description: `Would delete ${path}`,
      variant: 'default',
    });
    closeTab(path);
    if (onFileDeleted) onFileDeleted(path);
  }, [closeTab, onFileDeleted]);

  // Expose openFile method to parent via ref
  useImperativeHandle(
    forwardedRef,
    () => ({
      openFile,
    }),
    [openFile]
  );

  return (
    <Card className="h-full flex flex-col border-0 rounded-lg">
      <FileTabBar
        openFiles={openFiles}
        activeFilePath={activeFilePath}
        onSelectTab={setActiveFilePath}
        onCloseTab={closeTab}
        onAskAboutFile={onAskAboutFile}
        onRenameFile={handleRenameFile}
        onDeleteFile={handleDeleteFile}
      />

      <CardBody className="flex-1 overflow-hidden p-0 flex flex-col">
        {activeFile ? (
          <>
            {/* Editor Header with Save/Discard */}
            {activeFile.isDirty && (
              <div className="flex items-center justify-between px-4 py-2 border-b bg-orange-50 dark:bg-orange-950/20">
                <div className="flex items-center gap-2 text-sm text-orange-700 dark:text-orange-300">
                  <AlertCircle size={14} />
                  <span>Unsaved changes</span>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleDiscard}
                    disabled={saveFileMutation.isPending}
                  >
                    Discard
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={saveFileMutation.isPending}
                  >
                    {saveFileMutation.isPending ? (
                      <>
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        Saving…
                      </>
                    ) : (
                      'Save'
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Editor */}
            <div className="flex-1 overflow-hidden">
              <CodeEditor
                content={activeFile.content}
                fileName={activeFile.path}
                isModified={activeFile.isDirty}
                isReadOnly={false}
                onContentChange={(content) =>
                  markDirty(activeFile.path, content)
                }
                onSave={handleSave}
                onDiscard={handleDiscard}
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              {console.debug(`[TabbedEditor] Rendering empty state: activeFilePath=${activeFilePath}, openFiles=${openFiles.length}, activeFile=${activeFile ? 'yes' : 'no'}`)}
              <p className="text-sm mb-2">No file open</p>
              <p className="text-xs text-muted-foreground">
                Click on a file in the explorer to open it
              </p>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
};

export const TabbedEditor = forwardRef<TabbedEditorHandle, TabbedEditorProps>(
  (props, ref) => <TabbedEditorInner {...props} forwardedRef={ref} />
);
