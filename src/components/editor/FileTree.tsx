import { useState } from 'react';
import { ChevronRight, ChevronDown, File, Folder, FolderOpen, GitCommit } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FileNode {
  name: string;
  type: 'file' | 'folder';
  path: string;
  children?: FileNode[];
  modified?: boolean;
}

interface FileTreeProps {
  files: FileNode[];
  selectedFile: string | null;
  onFileSelect: (path: string) => void;
  modifiedFiles: Set<string>;
  gitModifiedFiles?: Set<string>; // Files with uncommitted changes
  gitStagedFiles?: Set<string>; // Files staged for commit
}

const FileTreeItem = ({ 
  node, 
  level = 0, 
  selectedFile, 
  onFileSelect,
  modifiedFiles,
  gitModifiedFiles = new Set(),
  gitStagedFiles = new Set(),
}: { 
  node: FileNode; 
  level?: number;
  selectedFile: string | null;
  onFileSelect: (path: string) => void;
  modifiedFiles: Set<string>;
  gitModifiedFiles?: Set<string>;
  gitStagedFiles?: Set<string>;
}) => {
  const [isOpen, setIsOpen] = useState(level === 0);
  const isModified = modifiedFiles.has(node.path);
  const isGitModified = gitModifiedFiles.has(node.path);
  const isGitStaged = gitStagedFiles.has(node.path);
  const isSelected = selectedFile === node.path;

  if (node.type === 'folder') {
    return (
      <div>
        <div
          className={cn(
            "flex items-center gap-2 px-2 py-1.5 cursor-pointer hover:bg-muted/50 rounded-md transition-colors",
            isSelected && "bg-muted"
          )}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          {isOpen ? <FolderOpen size={16} className="text-blue-500" /> : <Folder size={16} className="text-blue-500" />}
          <span className="text-sm">{node.name}</span>
        </div>
        {isOpen && node.children && (
          <div>
            {node.children.map((child, idx) => (
              <FileTreeItem
                key={idx}
                node={child}
                level={level + 1}
                selectedFile={selectedFile}
                onFileSelect={onFileSelect}
                modifiedFiles={modifiedFiles}
                gitModifiedFiles={gitModifiedFiles}
                gitStagedFiles={gitStagedFiles}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 cursor-pointer hover:bg-muted/50 rounded-md transition-colors",
        isSelected && "bg-muted"
      )}
      style={{ paddingLeft: `${level * 12 + 24}px` }}
      onClick={() => onFileSelect(node.path)}
    >
      <File size={16} className="text-muted-foreground" />
      <span className={cn("text-sm flex-1", isModified && "text-orange-500 font-medium")}>
        {node.name}
      </span>
      <div className="flex items-center gap-1">
        {isModified && <span className="text-orange-500 text-xs font-bold" title="Unsaved changes">●</span>}
        {isGitStaged && <GitCommit size={12} className="text-green-600" title="Staged for commit" />}
        {isGitModified && !isGitStaged && <span className="text-blue-500 text-xs font-bold" title="Uncommitted changes">M</span>}
      </div>
    </div>
  );
};

export const FileTree = ({ files, selectedFile, onFileSelect, modifiedFiles, gitModifiedFiles, gitStagedFiles }: FileTreeProps) => {
  return (
    <div className="h-full overflow-y-auto">
      {files.map((node, idx) => (
        <FileTreeItem
          key={idx}
          node={node}
          selectedFile={selectedFile}
          onFileSelect={onFileSelect}
          modifiedFiles={modifiedFiles}
          gitModifiedFiles={gitModifiedFiles}
          gitStagedFiles={gitStagedFiles}
        />
      ))}
    </div>
  );
};
