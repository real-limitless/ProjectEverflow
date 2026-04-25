import React from 'react';
import { X, MoreVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export interface OpenFile {
  path: string;
  content: string;
  isDirty: boolean;
}

interface FileTabBarProps {
  openFiles: OpenFile[];
  activeFilePath: string | null;
  onSelectTab: (path: string) => void;
  onCloseTab: (path: string) => void;
  onAskAboutFile?: (path: string, content: string) => void;
  onRenameFile?: (oldPath: string) => void;
  onDeleteFile?: (path: string) => void;
}

export const FileTabBar: React.FC<FileTabBarProps> = ({
  openFiles,
  activeFilePath,
  onSelectTab,
  onCloseTab,
  onAskAboutFile,
  onRenameFile,
  onDeleteFile,
}) => {


  return (
    <div className="flex items-center h-10 bg-muted/30 border-b border-border overflow-x-auto gap-1 px-2">
      {openFiles.map((file) => (
        <div
          key={file.path}
          className={`flex items-center gap-1 px-3 py-1 rounded-t border border-b-0 cursor-pointer whitespace-nowrap transition-colors ${
            activeFilePath === file.path
              ? 'bg-background border-border'
              : 'bg-muted/50 border-muted hover:bg-muted'
          }`}
          onClick={() => onSelectTab(file.path)}
        >
          <span className="text-xs font-medium">
            {file.path.split('/').pop()}
          </span>
          {file.isDirty && (
            <span className="text-xs text-orange-500 font-bold">●</span>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-4 w-4 p-0 ml-1 hover:bg-muted"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreVertical className="h-3 w-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              {onAskAboutFile && (
                <DropdownMenuItem
                  onClick={() => {
                    onAskAboutFile(file.path, file.content);
                  }}
                >
                  Ask AI about this file
                </DropdownMenuItem>
              )}
              {onRenameFile && (
                <DropdownMenuItem onClick={() => onRenameFile(file.path)}>
                  Rename…
                </DropdownMenuItem>
              )}
              {onDeleteFile && (
                <DropdownMenuItem
                  className="text-destructive"
                  onClick={() => {
                    if (confirm(`Delete ${file.path}?`)) {
                      onDeleteFile(file.path);
                    }
                  }}
                >
                  Delete…
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <Button
            variant="ghost"
            size="sm"
            className="h-4 w-4 p-0 hover:bg-muted"
            onClick={(e) => {
              e.stopPropagation();
              onCloseTab(file.path);
            }}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      ))}
    </div>
  );
};
