import { Button as UIButton } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { GitBranch, Plus, Minus, Check, X } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

interface FileDiff {
  path: string;
  additions: number;
  deletions: number;
  diff: string;
}

interface GitDiffViewerProps {
  modifiedFiles: FileDiff[];
  onStageFile: (path: string) => void;
  onDiscardFile: (path: string) => void;
  onCommit: () => void;
}

export const GitDiffViewer = ({ 
  modifiedFiles, 
  onStageFile, 
  onDiscardFile, 
  onCommit 
}: GitDiffViewerProps) => {
  if (modifiedFiles.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center">
          <GitBranch size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-sm">No local edits yet</p>
          <p className="text-xs mt-1">Edit a file in this workspace to review the diff here.</p>
        </div>
      </div>
    );
  }

  const totalAdditions = modifiedFiles.reduce((sum, file) => sum + file.additions, 0);
  const totalDeletions = modifiedFiles.reduce((sum, file) => sum + file.deletions, 0);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b bg-muted/30">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <GitBranch size={16} />
            Changes ({modifiedFiles.length} files)
          </h3>
          <UIButton size="sm" onClick={onCommit}>
            <Check size={14} className="mr-1" />
            Commit Changes
          </UIButton>
        </div>
        <div className="flex gap-3 text-xs">
          <Badge variant="outline" className="bg-green-500/10 text-green-700 border-green-200">
            <Plus size={12} className="mr-1" />
            {totalAdditions} additions
          </Badge>
          <Badge variant="outline" className="bg-red-500/10 text-red-700 border-red-200">
            <Minus size={12} className="mr-1" />
            {totalDeletions} deletions
          </Badge>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {modifiedFiles.map((file) => (
            <div key={file.path} className="border rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{file.path}</span>
                  <div className="flex gap-1.5 text-xs">
                    <span className="text-green-600">+{file.additions}</span>
                    <span className="text-red-600">-{file.deletions}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <UIButton
                    size="sm"
                    variant="ghost"
                    onClick={() => onDiscardFile(file.path)}
                  >
                    <X size={14} className="mr-1" />
                    Discard
                  </UIButton>
                  <UIButton
                    size="sm"
                    variant="outline"
                    onClick={() => onStageFile(file.path)}
                  >
                    <Check size={14} className="mr-1" />
                    Stage
                  </UIButton>
                </div>
              </div>
              <div className="bg-muted/20 p-3 overflow-x-auto">
                <pre className="text-xs font-mono whitespace-pre-wrap">
                  {file.diff.split('\n').map((line, idx) => {
                    const isAddition = line.startsWith('+');
                    const isDeletion = line.startsWith('-');
                    return (
                      <div
                        key={idx}
                        className={
                          isAddition
                            ? 'bg-green-500/10 text-green-700'
                            : isDeletion
                            ? 'bg-red-500/10 text-red-700'
                            : 'text-muted-foreground'
                        }
                      >
                        {line}
                      </div>
                    );
                  })}
                </pre>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
};
