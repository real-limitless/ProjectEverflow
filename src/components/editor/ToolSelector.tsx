import React, { useMemo, useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@patternfly/react-core';
import { Wrench, Check, Loader2 } from 'lucide-react';
import { ProjectTool, ChatbotPersona, ChatMode, getSessionTools } from '@/lib/api';

interface ToolSelectorProps {
  projectId?: number;
  sessionId?: number;
  tools: ProjectTool[];
  selectedToolIds: (string | number)[];
  onToolsChange: (toolIds: (string | number)[]) => void;
  selectedPersona: ChatbotPersona | null;
  chatMode?: ChatMode;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}

interface BackendTool {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  params?: Array<{ name: string; type: string; description: string; required: boolean }>;
}

/**
 * Tool permissions by chat mode:
 * - 'agent' / 'deep': All tools enabled (agent orchestrates tool usage)
 * - 'plan': Read-only tools only (no writes or executions)
 * - 'ask' / 'persona': All tools available, user selects
 */
const getPermittedTools = (
  tools: (ProjectTool | BackendTool)[],
  chatMode?: ChatMode,
  personaName?: string | undefined,
): { permitted: (ProjectTool | BackendTool)[]; restricted: (ProjectTool | BackendTool)[] } => {
  // Agent and Deep modes: all tools
  if (chatMode === 'agent' || chatMode === 'deep') {
    return { permitted: tools, restricted: [] };
  }

  // Plan mode: only read-only tools
  if (chatMode === 'plan') {
    const readOnlyPatterns = ['read', 'search', 'list', 'get', 'describe', 'explain'];
    const permitted = tools.filter((tool) => {
      const name = tool.name.toLowerCase();
      return readOnlyPatterns.some((pattern) => name.includes(pattern));
    });
    const restricted = tools.filter((tool) => !permitted.includes(tool));
    return { permitted, restricted };
  }

  // Ask / Persona: all tools available, user selects
  return { permitted: tools, restricted: [] };
};

export const ToolSelector: React.FC<ToolSelectorProps> = ({
  projectId,
  sessionId,
  tools,
  selectedToolIds,
  onToolsChange,
  selectedPersona,
  chatMode,
  isOpen,
  onOpenChange,
}) => {
  const [backendTools, setBackendTools] = useState<BackendTool[]>([]);
  const [isLoadingTools, setIsLoadingTools] = useState(false);

  // Load tools from backend when session changes and dialog opens
  useEffect(() => {
    if (isOpen && projectId && sessionId) {
      setIsLoadingTools(true);
      getSessionTools(projectId, sessionId)
        .then((response) => {
          if (response.data?.tools) {
            setBackendTools(response.data.tools);
          }
        })
        .catch((error) => {
          console.error('Failed to load session tools:', error);
          // Fall back to empty list
          setBackendTools([]);
        })
        .finally(() => {
          setIsLoadingTools(false);
        });
    }
  }, [isOpen, projectId, sessionId]);

  // Use backend tools if available, otherwise fall back to props tools
  const effectiveTools = backendTools.length > 0 ? backendTools : tools;
  const { permitted, restricted } = useMemo(
    () => getPermittedTools(effectiveTools, chatMode, selectedPersona?.name),
    [effectiveTools, chatMode, selectedPersona]
  );

  const handleToggleTool = (toolId: string | number) => {
    if (selectedToolIds.includes(toolId)) {
      onToolsChange(selectedToolIds.filter((id) => id !== toolId));
    } else {
      onToolsChange([...selectedToolIds, toolId]);
    }
  };

  const allPermittedSelected = permitted.length > 0 && permitted.every((t) => selectedToolIds.includes(t.id));
  const selectAll = () => {
    onToolsChange(permitted.map((t) => t.id));
  };
  const clearAll = () => {
    onToolsChange([]);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>


      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5" />
            Select Tools
          </DialogTitle>
          <DialogDescription>
            {chatMode === 'agent' || chatMode === 'deep' ? (
              <div className="text-sm text-blue-600 dark:text-blue-400">
                All tools are enabled in {chatMode === 'deep' ? 'Deep' : 'Agent'} mode. The agent orchestrates tool usage automatically.
              </div>
            ) : chatMode === 'plan' ? (
              <div className="mt-1 text-sm text-yellow-600 dark:text-yellow-500">
                Plan mode: only read-only tools are available. {restricted.length > 0 ? `${restricted.length} tool(s) restricted.` : ''}
              </div>
            ) : (
              'Choose which tools the LLM can access for this chat'
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {isLoadingTools ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mr-2" />
              <span className="text-muted-foreground">Loading tools...</span>
            </div>
          ) : (
            <>
              {/* Available Tools Section */}
              {permitted.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-semibold text-sm">Available Tools</h3>
                    <div className="flex gap-2">
                      <Button
                        variant="link"
                        size="sm"
                        onClick={selectAll}
                        isDisabled={allPermittedSelected}
                      >
                        Select All
                      </Button>
                      <Button
                        variant="link"
                        size="sm"
                        onClick={clearAll}
                        isDisabled={selectedToolIds.length === 0}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2 border rounded-lg p-4 bg-muted/30">
                    {permitted.map((tool) => {
                      const isSelected = selectedToolIds.includes(tool.id);
                      const toolDescription = 'description' in tool ? tool.description : tool.description;
                      return (
                        <div
                          key={tool.id}
                          className="flex items-start gap-3 p-2 rounded hover:bg-muted/50 transition-colors cursor-pointer"
                          onClick={() => handleToggleTool(tool.id)}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleTool(tool.id)}
                            className="mt-1"
                            aria-label={`Select ${tool.name}`}
                          />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm">{tool.name}</div>
                            <div className="text-xs text-muted-foreground line-clamp-2">
                              {toolDescription || 'No description'}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              <span className="inline-block bg-muted px-2 py-1 rounded">
                                {'workspace_tool' in tool ? (tool.workspace_tool ? '🖥️ Workspace' : '🔌 Plugin') : '🔧 LangChain'}
                              </span>
                            </div>
                          </div>
                          {isSelected && (
                            <Check className="h-5 w-5 text-green-600 flex-shrink-0 mt-1" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Restricted Tools Section */}
              {restricted.length > 0 && (
                <div>
                  <h3 className="font-semibold text-sm mb-3">
                    Restricted in {chatMode === 'plan' ? 'Plan' : selectedPersona?.name || 'current'} Mode
                  </h3>

                  <div className="space-y-2 border border-yellow-200 rounded-lg p-4 bg-yellow-50 dark:bg-yellow-900/20">
                    {restricted.map((tool) => (
                      <div key={tool.id} className="flex items-start gap-3 p-2 rounded opacity-60">
                        <input
                          type="checkbox"
                          disabled
                          className="mt-1"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm">{tool.name}</div>
                          <div className="text-xs text-muted-foreground line-clamp-2">
                            {'description' in tool ? tool.description : tool.description}
                          </div>
                        </div>
                        <span className="text-xs bg-yellow-200 dark:bg-yellow-700 px-2 py-1 rounded flex-shrink-0">
                          Restricted
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {permitted.length === 0 && restricted.length === 0 && (
                <div className="py-8 text-center text-muted-foreground">
                  <Wrench className="h-12 w-12 mx-auto mb-2 opacity-30" />
                  <p>No tools available</p>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => onOpenChange(false)}
          >
            Save ({selectedToolIds.length} selected)
          </Button>
        </div>
      </DialogContent>
    </Dialog>


  );
};
