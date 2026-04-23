import { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';

interface FileContextSelectorProps {
  openFiles: { path: string; content: string; isDirty?: boolean }[];
  selectedContext?: string[];
  onContextChange?: (selected: string[]) => void;
}

export function FileContextSelector({
  openFiles,
  selectedContext = [],
  onContextChange,
}: FileContextSelectorProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleToggleFile = (path: string) => {
    const newContext = selectedContext.includes(path)
      ? selectedContext.filter((p) => p !== path)
      : [...selectedContext, path];
    onContextChange?.(newContext);
  };

  const contextSize = useMemo(() => {
    const selected = openFiles.filter((f) => selectedContext.includes(f.path));
    return selected.reduce((acc, f) => acc + (f.content?.length || 0), 0);
  }, [openFiles, selectedContext]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const hasAnyOpen = openFiles.length > 0;

  if (!hasAnyOpen) {
    return (
      <div className="text-xs text-gray-500 px-3 py-2">
        No files open. Open files to add as context.
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="flex items-center justify-between w-full gap-2 py-1">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-foreground flex-1 transition-colors"
        >
          <span className="text-[10px]">{isExpanded ? '▼' : '▶'}</span>
          <span>Context Files</span>
          <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full">
            {selectedContext.length}/{openFiles.length}
          </span>
        </button>
        {selectedContext.length > 0 && (
          <button
            type="button"
            onClick={() => onContextChange?.([])}
            className="text-[10px] text-red-500 hover:text-red-700 font-medium"
          >
            Clear
          </button>
        )}
        <span className="text-[10px] text-muted-foreground">{formatSize(contextSize)}</span>
      </div>

      {isExpanded && (
        <div className="space-y-0.5 max-h-40 overflow-y-auto py-1">
          {openFiles.map((file) => {
            const isSelected = selectedContext.includes(file.path);
            const fileName = file.path.split('/').pop() || file.path;
            const dirPath = file.path.substring(0, file.path.lastIndexOf('/'));

            return (
              <div
                key={file.path}
                className={cn(
                  'flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors text-xs',
                  isSelected
                    ? 'bg-blue-50 dark:bg-blue-950/30'
                    : 'hover:bg-muted/50'
                )}
                onClick={() => handleToggleFile(file.path)}
              >
                <span className={cn(
                  'w-3 h-3 rounded-full border-2 flex-shrink-0 transition-colors',
                  isSelected
                    ? 'bg-blue-500 border-blue-500'
                    : 'border-gray-400'
                )} />

                <div className="flex-1 min-w-0">
                  <span className="font-medium truncate block">{fileName}</span>
                  {dirPath && (
                    <span className="text-[10px] text-muted-foreground truncate block">{dirPath}</span>
                  )}
                </div>

                {file.isDirty && (
                  <span className="text-orange-500 font-bold flex-shrink-0">●</span>
                )}

                <span className="text-[10px] text-muted-foreground flex-shrink-0">
                  {formatSize(file.content?.length || 0)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
