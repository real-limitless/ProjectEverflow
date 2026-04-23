import { useState, useEffect } from 'react';
import { Card, CardBody, Button } from '@patternfly/react-core';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { FileTree } from '@/components/editor/FileTree';
import { CodeEditor } from '@/components/editor/CodeEditor';
import { GitDiffViewer } from '@/components/editor/GitDiffViewer';
import { toast } from '@/hooks/use-toast';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  getWorkspaceFileTree, 
  readWorkspaceFile, 
  updateWorkspaceFile,
  FileNode,
  Project,
  apiCall
} from '@/lib/api';
import { Loader2, Archive, Undo2, FileWarning } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface GitStatusResponse {
  modified: string[];
  staged: string[];
  untracked: string[];
}

interface FileManagerTabProps {
  project: Project;
}

export const FileManagerTab: React.FC<FileManagerTabProps> = ({ project }) => {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [originalContents, setOriginalContents] = useState<Record<string, string>>({});
  const [modifiedFiles, setModifiedFiles] = useState<Set<string>>(new Set());
  const [gitModifiedFiles, setGitModifiedFiles] = useState<Set<string>>(new Set());
  const [gitStagedFiles, setGitStagedFiles] = useState<Set<string>>(new Set());
  const queryClient = useQueryClient();

  // Fetch file tree
  const { data: fileTreeResponse, isLoading: treeLoading, error: treeError } = useQuery({
    queryKey: ['workspace-file-tree', project.id],
    queryFn: () => getWorkspaceFileTree(project.id),
    retry: 3,
  });

  const fileTree = fileTreeResponse?.data?.tree?.children || [];

  // Fetch git status
  const { data: gitStatusResponse } = useQuery<GitStatusResponse>({
    queryKey: ['git-status', project.id],
    queryFn: async () => {
      const response = await apiCall(`/projects/${project.id}/workspace/files/git-status/`, {
        method: 'GET',
      });
      return response.data;
    },
    refetchInterval: 10000, // Refetch every 10 seconds
    retry: 1,
  });

  // Update git file sets when git status changes
  useEffect(() => {
    if (gitStatusResponse) {
      setGitModifiedFiles(new Set([...gitStatusResponse.modified, ...gitStatusResponse.untracked]));
      setGitStagedFiles(new Set(gitStatusResponse.staged));
    }
  }, [gitStatusResponse]);

  // Fetch file content when selected
  const readFileMutation = useMutation({
    mutationFn: (filepath: string) => readWorkspaceFile(project.id, filepath),
    onSuccess: (response, filepath) => {
      if (response.data?.success) {
        setFileContents(prev => ({ ...prev, [filepath]: response.data.content }));
        setOriginalContents(prev => ({ ...prev, [filepath]: response.data.content }));
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to read file',
        variant: 'destructive',
      });
    },
  });

  // Save file mutation
  const saveFileMutation = useMutation({
    mutationFn: (filepath: string) => 
      updateWorkspaceFile(project.id, filepath, fileContents[filepath]),
    onSuccess: (response, filepath) => {
      if (response.data?.success) {
        setOriginalContents(prev => ({ ...prev, [filepath]: fileContents[filepath] }));
        setModifiedFiles(prev => {
          const newSet = new Set(prev);
          newSet.delete(filepath);
          return newSet;
        });
        toast({
          title: 'Success',
          description: `${filepath} saved successfully`,
        });
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to save file',
        variant: 'destructive',
      });
    },
  });

  const handleFileSelect = (path: string) => {
    setSelectedFile(path);
    
    // Load file content if not already loaded
    if (!(path in fileContents)) {
      readFileMutation.mutate(path);
    }
  };

  const handleContentChange = (content: string) => {
    if (!selectedFile) return;
    
    setFileContents(prev => ({ ...prev, [selectedFile]: content }));
    
    const isModified = originalContents[selectedFile] !== content;
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      if (isModified) {
        newSet.add(selectedFile);
      } else {
        newSet.delete(selectedFile);
      }
      return newSet;
    });
  };

  const handleSaveFile = () => {
    if (!selectedFile) return;
    saveFileMutation.mutate(selectedFile);
  };

  const handleDiscardFile = () => {
    if (!selectedFile) return;
    setFileContents(prev => ({ ...prev, [selectedFile]: originalContents[selectedFile] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(selectedFile);
      return newSet;
    });
    toast({
      title: 'Changes Discarded',
      description: `Changes to ${selectedFile} have been discarded.`,
    });
  };

  const handleStageFile = (path: string) => {
    toast({
      title: 'File Staged',
      description: `${path} has been staged for commit.`,
    });
  };

  const handleDiscardGitFile = (path: string) => {
    setFileContents(prev => ({ ...prev, [path]: originalContents[path] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(path);
      return newSet;
    });
    toast({
      title: 'Changes Discarded',
      description: `Changes to ${path} have been discarded.`,
    });
  };

  const handleCommit = () => {
    toast({
      title: 'Committing Changes',
      description: 'This would open a commit dialog in a full implementation.',
    });
  };

  const handleStashChanges = async () => {
    try {
      await apiCall(`/projects/${project.id}/workspace/git/stash/`, { method: 'POST', body: JSON.stringify({}) });
      toast({ title: 'Changes Stashed', description: 'Your working changes have been stashed.' });
      queryClient.invalidateQueries({ queryKey: ['git-status', project.id] });
      setModifiedFiles(new Set());
    } catch {
      toast({ title: 'Stash Failed', description: 'Could not stash changes. Make sure there are changes to stash.', variant: 'destructive' });
    }
  };

  const handleDiscardAll = () => {
    // Reset all modified files to their original content
    const resetContents = { ...fileContents };
    modifiedFiles.forEach(path => {
      resetContents[path] = originalContents[path] || '';
    });
    setFileContents(resetContents);
    setModifiedFiles(new Set());
    toast({ title: 'All Changes Discarded', description: 'All unsaved changes have been reverted.' });
  };

  const getGitDiffs = () => {
    return Array.from(modifiedFiles).map(path => {
      const original = originalContents[path] || '';
      const current = fileContents[path] || '';
      const originalLines = original.split('\n');
      const currentLines = current.split('\n');
      
      let diff = '';
      let additions = 0;
      let deletions = 0;

      const maxLen = Math.max(originalLines.length, currentLines.length);
      for (let i = 0; i < maxLen; i++) {
        if (originalLines[i] !== currentLines[i]) {
          if (originalLines[i]) {
            diff += `- ${originalLines[i]}\n`;
            deletions++;
          }
          if (currentLines[i]) {
            diff += `+ ${currentLines[i]}\n`;
            additions++;
          }
        }
      }

      return { path, additions, deletions, diff };
    });
  };

  if (treeError) {
    return (
      <div style={{ height: 'calc(100vh - 330px)', padding: '20px' }}>
        <Card>
          <CardBody>
            <p style={{ color: 'var(--pf-v6-global--danger-color--100)' }}>
              Error loading workspace files. Make sure the workspace is started.
            </p>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ height: 'calc(100vh - 330px)' }}>
      <ResizablePanelGroup direction="horizontal" className="h-full w-full">
        {/* File Tree Panel */}
        <ResizablePanel defaultSize={20} minSize={15} maxSize={30}>
          <Card className="h-full m-0 rounded-lg border-0">
            <CardBody style={{ padding: '1rem' }}>
              <h3 className="text-sm font-semibold mb-3">Files</h3>
              {treeLoading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  <span className="text-xs text-muted-foreground">Loading...</span>
                </div>
              ) : (
                <FileTree
                  files={fileTree as FileNode[]}
                  selectedFile={selectedFile}
                  onFileSelect={handleFileSelect}
                  modifiedFiles={modifiedFiles}
                  gitModifiedFiles={gitModifiedFiles}
                  gitStagedFiles={gitStagedFiles}
                />
              )}
            </CardBody>
          </Card>
        </ResizablePanel>

        <ResizableHandle withHandle className="w-2 bg-border hover:bg-primary/20 transition-colors" />

        {/* Code Editor Panel */}
        <ResizablePanel defaultSize={50} minSize={30}>
          <Card className="h-full m-0 rounded-lg border-0">
            <CardBody style={{ padding: 0, height: '100%' }}>
              {selectedFile ? (
                <CodeEditor
                  content={fileContents[selectedFile] || ''}
                  fileName={selectedFile}
                  isModified={modifiedFiles.has(selectedFile)}
                  isReadOnly={readFileMutation.isPending || saveFileMutation.isPending}
                  onContentChange={handleContentChange}
                  onSave={handleSaveFile}
                  onDiscard={handleDiscardFile}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <p className="text-sm">Select a file to edit</p>
                </div>
              )}
            </CardBody>
          </Card>
        </ResizablePanel>

        <ResizableHandle withHandle className="w-2 bg-border hover:bg-primary/20 transition-colors" />

        {/* Git Changes Panel */}
        <ResizablePanel defaultSize={30} minSize={20} maxSize={40}>
          <Card className="h-full m-0 rounded-lg border-0">
            <CardBody style={{ padding: 0, height: '100%', display: 'flex', flexDirection: 'column' }}>
              {/* Git Status Summary */}
              {gitStatusResponse && (gitStatusResponse.modified.length > 0 || gitStatusResponse.untracked.length > 0 || gitStatusResponse.staged.length > 0) && (
                <div className="px-3 py-2 border-b bg-muted/30 space-y-2">
                  <div className="flex items-center gap-2 flex-wrap text-xs">
                    {gitStatusResponse.modified.length > 0 && (
                      <Badge variant="outline" className="bg-yellow-500/10 text-yellow-700 border-yellow-200">
                        <FileWarning className="h-3 w-3 mr-1" />
                        {gitStatusResponse.modified.length} modified
                      </Badge>
                    )}
                    {gitStatusResponse.untracked.length > 0 && (
                      <Badge variant="outline" className="bg-blue-500/10 text-blue-700 border-blue-200">
                        {gitStatusResponse.untracked.length} untracked
                      </Badge>
                    )}
                    {gitStatusResponse.staged.length > 0 && (
                      <Badge variant="outline" className="bg-green-500/10 text-green-700 border-green-200">
                        {gitStatusResponse.staged.length} staged
                      </Badge>
                    )}
                  </div>
                  <div className="flex gap-1.5">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleStashChanges}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Archive style={{ width: '0.75rem', height: '0.75rem' }} />
                      </span>
                      Stash
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleDiscardAll}
                      isDisabled={modifiedFiles.size === 0}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Undo2 style={{ width: '0.75rem', height: '0.75rem' }} />
                      </span>
                      Discard All
                    </Button>
                  </div>
                </div>
              )}
              <div style={{ flex: 1, minHeight: 0 }}>
                <GitDiffViewer
                  modifiedFiles={getGitDiffs()}
                  onStageFile={handleStageFile}
                  onDiscardFile={handleDiscardGitFile}
                  onCommit={handleCommit}
                />
              </div>
            </CardBody>
          </Card>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
};
