import { useState, useRef, useEffect, useCallback } from 'react';
import { flushSync } from 'react-dom';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Tabs as UITabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useLLMModels } from '@/hooks/use-llm-models';
import { getChatMessages, sendChatMessage, streamChatMessage, createChatSession, summarizeConversation, updateChatSession, getChatbotPersonas, getAvailableLLMs, getProjectTools, getSessionTools, getCopilotHealth, streamCopilotMessage, ChatMessage, Project, ProjectTool, ChatbotPersona, ChatMode, ChatSession, getChatSessions, AgentMode } from '@/lib/api';
import { toast } from '@/hooks/use-toast';
import { LivePreviewPanel } from '@/components/editor/LivePreviewPanel';
import { FileExplorer } from '@/components/project/FileExplorer';
import { TabbedEditor, TabbedEditorHandle } from '@/components/editor/TabbedEditor';
import { useAgentStream } from '@/hooks/useAgentStream';
import { ChatPanel } from '@/components/project/ChatPanel';

interface AIEditorTabProps {
  project: Project;
  layoutMode?: 'default' | 'full-page';
  layoutScope?: string;
}

// WorkspacePanel Component
interface WorkspacePanelProps {
  project: Project;
  isChatCollapsed: boolean;
  onChatCollapsedChange: (collapsed: boolean) => void;
}

const WorkspacePanel: React.FC<WorkspacePanelProps> = ({ project, isChatCollapsed, onChatCollapsedChange }) => {
  return (
    <LivePreviewPanel 
      project={project} 
      isChatCollapsed={isChatCollapsed}
      onChatCollapsedChange={onChatCollapsedChange}
    />
  );
};

type WorkspaceLayoutMode = 'default' | 'full-page';

const AI_EDITOR_STORAGE_VERSION = 'v2';

const AI_EDITOR_LAYOUT_PRESETS: Record<WorkspaceLayoutMode, {
  panelLayout: [number, number];
  sidebarSize: number;
  sidebarMin: number;
  sidebarMax: number;
  mainMin: number;
  chatMin: number;
  chatMax: number;
  previewMin: number;
}> = {
  default: {
    panelLayout: [40, 60],
    sidebarSize: 18,
    sidebarMin: 12,
    sidebarMax: 35,
    mainMin: 50,
    chatMin: 25,
    chatMax: 75,
    previewMin: 25,
  },
  'full-page': {
    panelLayout: [62, 38],
    sidebarSize: 18,
    sidebarMin: 14,
    sidebarMax: 28,
    mainMin: 56,
    chatMin: 32,
    chatMax: 78,
    previewMin: 22,
  },
};

const readStoredNumber = (storageKey: string, fallback: number) => {
  if (typeof window === 'undefined') return fallback;

  try {
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) return fallback;
    const parsed = JSON.parse(stored);
    return typeof parsed === 'number' && Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
};

const readStoredPanelLayout = (storageKey: string, fallback: [number, number]): [number, number] => {
  if (typeof window === 'undefined') return fallback;

  try {
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) return fallback;
    const parsed = JSON.parse(stored);
    if (
      Array.isArray(parsed) &&
      parsed.length === 2 &&
      parsed.every((size) => typeof size === 'number' && Number.isFinite(size))
    ) {
      return [parsed[0], parsed[1]];
    }
  } catch {
    return fallback;
  }

  return fallback;
};

const readStoredBoolean = (storageKey: string, fallback: boolean) => {
  if (typeof window === 'undefined') return fallback;

  try {
    const stored = window.localStorage.getItem(storageKey);
    if (!stored) return fallback;
    const parsed = JSON.parse(stored);
    return typeof parsed === 'boolean' ? parsed : fallback;
  } catch {
    return fallback;
  }
};

const getMessageTimestamp = (message: Partial<ChatMessage> & { timestamp?: Date | string }) => {
  const source = message.created_at || message.timestamp;
  if (!source) return null;
  const parsed = new Date(source);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const AIEditorTab: React.FC<AIEditorTabProps> = ({ project, layoutMode = 'default', layoutScope }) => {
  const layoutPreset = AI_EDITOR_LAYOUT_PRESETS[layoutMode];
  const storageScope = layoutScope || `project-${project.id}`;
  const [isChatCollapsed, setIsChatCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const tabbedEditorRef = useRef<TabbedEditorHandle>(null);
  const queryClient = useQueryClient();
  const layoutStorageKey = `ai-editor:${AI_EDITOR_STORAGE_VERSION}:panel-layout:${layoutMode}:${storageScope}`;
  const sidebarLayoutKey = `ai-editor:${AI_EDITOR_STORAGE_VERSION}:sidebar-size:${layoutMode}:${storageScope}`;
  const sidebarCollapsedKey = `ai-editor:${AI_EDITOR_STORAGE_VERSION}:sidebar-collapsed:${layoutMode}:${storageScope}`;
  const previewHiddenKey = `ai-editor:${AI_EDITOR_STORAGE_VERSION}:preview-hidden:${layoutMode}:${storageScope}`;
  const [panelLayout, setPanelLayout] = useState<[number, number]>(() =>
    readStoredPanelLayout(layoutStorageKey, layoutPreset.panelLayout)
  );
  const [sidebarSize, setSidebarSize] = useState<number>(() =>
    readStoredNumber(sidebarLayoutKey, layoutPreset.sidebarSize)
  );
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() =>
    readStoredBoolean(sidebarCollapsedKey, layoutMode === 'full-page')
  );
  const [isPreviewHidden, setIsPreviewHidden] = useState<boolean>(() =>
    readStoredBoolean(previewHiddenKey, false)
  );

  // Use LLM models hook for available models and default
  const { models: availableModels, defaultModel, getEffectiveModel, getModelLabel } = useLLMModels(project.id);

  // Callback to create a change request from final analysis (stub - needs backend endpoint)
  const handleCreateChangeRequest = async (summary: string) => {
    try {
      // TODO: Call backend to create a draft change request with diff/summary
      alert('Create Change Request (stub): ' + (summary ? 'summary included' : 'no summary'));
    } catch (e) {
      toast({ title: 'Error', description: 'Failed to create change request', variant: 'destructive' });
    }
  };

  // AI Settings State
  const [selectedLLM, setSelectedLLM] = useState<string>('');
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(0); // 0 = unlimited (model default)

  // New states for summary and memory
  const [chatSummary, setChatSummary] = useState('');
  const [memoryItems, setMemoryItems] = useState<string[]>([]);
  const [activeSidebarTab, setActiveSidebarTab] = useState<'files' | 'editor'>('files');
  const [chatMode, setChatMode] = useState<ChatMode>('ask');
  const [selectedPersonaId, setSelectedPersonaId] = useState<number | null>(null);
  const [selectedToolIds, setSelectedToolIds] = useState<number[]>([]);
  const [isModelSelectOpen, setIsModelSelectOpen] = useState(false);
  const [isToolSelectorDialogOpen, setIsToolSelectorDialogOpen] = useState(false);
  // Agent mode: 'assisted' (backend LLM) or 'copilot' (container-native LLM)
  const [agentMode, setAgentMode] = useState<AgentMode>('assisted');
  const [copilotAvailable, setCopilotAvailable] = useState(false);
  // New state for agent todo list
  const [agentTodos, setAgentTodos] = useState<Array<{description: string, status: 'pending' | 'in_progress' | 'completed' | 'failed', details?: string}>>([]);
  // Analysis streaming state
  const [analysisChunks, setAnalysisChunks] = useState<any[]>([]);
  const [analysisFinal, setAnalysisFinal] = useState<any | null>(null);
  const [isAnalysisModalOpen, setIsAnalysisModalOpen] = useState(false);
  // State for pending message during session creation
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  
  // State for file context selection
  const [contextFiles, setContextFiles] = useState<string[]>([]);
  const [openFiles, setOpenFiles] = useState<{ path: string; content: string; isDirty?: boolean }[]>([]);
  
  // State for pending file to open (when ref not yet available)
  const [pendingFileOpen, setPendingFileOpen] = useState<{ path: string; content: string } | null>(null);
  
  // State for message editing
  const [editingMessageId, setEditingMessageId] = useState<number | string | null>(null);
  const [savingMessageId, setSavingMessageId] = useState<number | string | null>(null);

  // Subscribe to agent stream events (if available)
  const { wsRef: agentWsRef, status: agentWsStatus, sendMessage: wsSendMessage, cancel: wsCancel } = useAgentStream(project.id, currentSessionId, (data: any) => {
    try {
      if (!data) return;

      // ── New unified WS events ──────────────────────────────────
      if (data.type === 'text_chunk') {
        // Accumulate streaming tokens from WS agent
        flushSync(() => {
          setStreamingContent(prev => prev + (data.content || ''));
        });
      } else if (data.type === 'tool_start') {
        toast({ title: `Tool: ${data.name}`, description: typeof data.args === 'string' ? data.args : JSON.stringify(data.args || {}), variant: 'default' });
      } else if (data.type === 'tool_result') {
        toast({ title: `Tool done: ${data.name}`, description: data.output ? String(data.output).slice(0, 200) : 'No output', variant: 'default' });
      } else if (data.type === 'worker_start') {
        toast({ title: `Worker started: ${data.worker}`, variant: 'default' });
      } else if (data.type === 'worker_end') {
        // Worker finished — content may be available
      } else if (data.type === 'todos_update' && data.todos) {
        setAgentTodos(data.todos.map((t: any) => ({
          description: t.title || t.description || String(t),
          status: t.status === 'completed' ? 'completed' : t.status === 'in-progress' ? 'in_progress' : 'pending',
          details: typeof t.details === 'string' ? t.details : (t.details ? JSON.stringify(t.details) : undefined),
        })));
      } else if (data.type === 'complete') {
        // Final event — clear streaming state and refresh from backend
        setStreamingContent('');
        setIsStreaming(false);
        setIsLoading(false);
        queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
        queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
        if (currentSessionId) {
          summarizeConversation(currentSessionId).catch(err =>
            console.error('Failed to summarize:', err)
          );
        }
      } else if (data.type === 'error') {
        setIsStreaming(false);
        setStreamingContent('');
        setIsLoading(false);
        toast({
          title: 'Agent Error',
          description: data.message || 'Unknown error',
          variant: 'destructive',
        });
      } else if (data.type === 'connected') {
        console.debug('[AgentStream] Connected ack:', data);
      }

      // ── Legacy analysis events (still sent via channel layer) ──
      else if (data.type === 'analyze_started') {
        setAnalysisChunks([]);
        setAnalysisFinal(null);
        setIsAnalysisModalOpen(true);
        toast({ title: 'Deep analysis started', description: 'Streaming progress will appear in the Analysis modal.', variant: 'default' });
      } else if (data.type === 'analyze_chunk') {
        setAnalysisChunks(prev => [...prev.filter(c => c.chunk_index !== data.chunk_index), data]);
      } else if (data.type === 'analyze_complete') {
        setAnalysisFinal(data.final || data);
        toast({ title: 'Deep analysis complete', description: `Found ${data.final?.total_todos ?? data.total_todos} TODOs across ${data.final?.total_chunks ?? data.total_chunks} chunks`, variant: 'default' });

        // Auto-inject analysis summary into chat
        const analysisResult = data.final || data;
        if (currentSessionId && analysisResult) {
          const summary = `
## Code Analysis Results

**File Summary:**
- Total Lines: ${analysisResult.total_lines || 0}
- Functions/Classes: ${analysisResult.total_functions || 0}
- TODOs/FIXMEs Found: ${analysisResult.total_todos || 0}
- Chunks Analyzed: ${analysisResult.total_chunks || 0}

**Recommendations:**
${(analysisResult.total_todos || 0) > 0 ? `- Address ${analysisResult.total_todos} outstanding TODOs/FIXMEs` : '- No outstanding TODOs found'}
${(analysisResult.total_functions || 0) > 20 ? `- Consider breaking down ${analysisResult.total_functions} functions into smaller modules` : ''}
- Review code complexity and refactoring opportunities
          `.trim();

          queryClient.setQueryData(['chat-messages', currentSessionId], (old: any) => {
            const messages = old?.data || [];
            return {
              ...old,
              data: [...messages, {
                id: `analysis-${Date.now()}`,
                message_type: 'assistant',
                content: summary,
                created_at: new Date().toISOString(),
              }]
            };
          });
        }
      }
    } catch (e) {
      console.warn('Error handling agent stream event', e);
    }
  });

  // Handler to ask AI about a file selected in the File Explorer
  const handleAskAboutFile = (path: string, content: string) => {
    // Truncate to avoid very large messages
    const snippet = content ? content.slice(0, 1500) : '';
    const message = `Please analyze the file ${path} and summarize potential issues or TODOs.\n\n${snippet}${content && content.length > 1500 ? '\n\n...[truncated]' : ''}`;
    handleSend(message);
  };
  // Load messages for the current session
  const { data: messages = [], isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', currentSessionId],
    queryFn: () => currentSessionId ? getChatMessages(currentSessionId) : Promise.resolve({ data: [] }),
    select: (response) => response.data || [],
    enabled: !!currentSessionId,
  });

  // Load chat sessions for the project
  const { data: sessionsResponse, isLoading: sessionsLoading } = useQuery({
    queryKey: ['chat-sessions', project.id],
    queryFn: () => getChatSessions(project.id),
    select: (response) => response.data || [],
  });

  const sessions = sessionsResponse || [];

  // Load available LLMs for the settings dropdown
  const { data: availableLLMs } = useQuery({
    queryKey: ['available-llms'],
    queryFn: () => getAvailableLLMs(),
    select: (response) => response.data,
  });

  const { data: personasResponse } = useQuery({
    queryKey: ['chatbot-personas'],
    queryFn: () => getChatbotPersonas(),
  });

  const personas = personasResponse?.data || [];

  const { data: projectToolsResponse, isLoading: projectToolsLoading } = useQuery({
    queryKey: ['project-tools', project.id],
    queryFn: () => getProjectTools(project.id),
  });

  // Fetch LangGraph workspace tools when session is available
  const { data: sessionToolsResponse, isLoading: sessionToolsLoading } = useQuery({
    queryKey: ['session-tools', project.id, currentSessionId],
    queryFn: () => getSessionTools(project.id, currentSessionId!),
    enabled: !!currentSessionId,
    staleTime: 60000, // Cache for 1 minute
  });

  // Merge project tools (DB) with session tools (LangGraph workspace tools)
  const projectTools = projectToolsResponse?.data || [];
  const sessionTools = (sessionToolsResponse?.data?.tools || []).map((tool: any) => ({
    ...tool,
    // Mark as LangGraph tool for UI differentiation
    source: 'langgraph' as const,
    is_active: true,
  }));
  
  // Combine both tool sources, avoiding duplicates by name
  const allTools = [...projectTools];
  for (const st of sessionTools) {
    if (!allTools.find(pt => pt.name === st.name || pt.slug === st.id)) {
      allTools.push(st);
    }
  }
  
  const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId) || null;

  // Auto-enable execute-command tool if available
  useEffect(() => {
    const executeTool = projectTools.find(t => t.slug === 'execute-command');
    if (executeTool && !selectedToolIds.includes(executeTool.id)) {
      setSelectedToolIds(prev => [...prev, executeTool.id]);
    }
  }, [projectTools, selectedToolIds]);

  // Check if Copilot Mode is available (agent running in container)
  useEffect(() => {
    const checkCopilotAvailability = async () => {
      try {
        const response = await getCopilotHealth(project.id);
        setCopilotAvailable(response.data?.status === 'healthy');
      } catch {
        setCopilotAvailable(false);
      }
    };
    
    // Check periodically
    checkCopilotAvailability();
    const interval = setInterval(checkCopilotAvailability, 30000);
    return () => clearInterval(interval);
  }, [project.id]);

  // Convert available models to the format expected by dropdowns
  const llmOptions = availableModels.map((model) => ({
    id: model.id,
    label: `${model.label} (${model.providerName})${model.isDefault ? ' ⭐' : ''}`,
  }));

  const selectedModelLabel = selectedLLM
    ? llmOptions.find((option) => option.id === selectedLLM)?.label || getModelLabel(selectedLLM)
    : getModelLabel(null);

  const persistStoredValue = useCallback((storageKey: string, value: unknown) => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(value));
    } catch (error) {
      console.warn(`Failed to persist storage key: ${storageKey}`, error);
    }
  }, []);

  // Handlers for editing summary and todo
  const handleSummaryChange = (value: string) => {
    setChatSummary(value);
    // Store in localStorage for persistence
    if (typeof window !== 'undefined' && currentSessionId) {
      const storageKey = `ai-editor-summary-${currentSessionId}`;
      try {
        window.localStorage.setItem(storageKey, value);
      } catch (error) {
        console.warn('Failed to persist summary', error);
      }
    }
  };

  const handleAddMemory = () => {
    const newItem = prompt('Add memory item (useful context for future chats):');
    if (newItem && newItem.trim()) {
      const newMemory = [...memoryItems, newItem.trim()];
      setMemoryItems(newMemory);
      // Store in localStorage for persistence
      if (typeof window !== 'undefined' && currentSessionId) {
        const storageKey = `ai-editor-memory-${currentSessionId}`;
        try {
          window.localStorage.setItem(storageKey, JSON.stringify(newMemory));
        } catch (error) {
          console.warn('Failed to persist memory', error);
        }
      }
    }
  };

  const handleEditMemory = (index: number, value: string) => {
    const newMemory = [...memoryItems];
    newMemory[index] = value;
    setMemoryItems(newMemory);
    // Store in localStorage for persistence
    if (typeof window !== 'undefined' && currentSessionId) {
      const storageKey = `ai-editor-memory-${currentSessionId}`;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(newMemory));
      } catch (error) {
        console.warn('Failed to persist memory', error);
      }
    }
  };

  const handleDeleteMemory = (index: number) => {
    const newMemory = memoryItems.filter((_, i) => i !== index);
    setMemoryItems(newMemory);
    // Store in localStorage for persistence
    if (typeof window !== 'undefined' && currentSessionId) {
      const storageKey = `ai-editor-memory-${currentSessionId}`;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(newMemory));
      } catch (error) {
        console.warn('Failed to persist memory', error);
      }
    }
  };

  const handleClearAllMemory = () => {
    if (window.confirm('Clear all memory items for this session?')) {
      setMemoryItems([]);
      if (typeof window !== 'undefined' && currentSessionId) {
        const storageKey = `ai-editor-memory-${currentSessionId}`;
        try {
          window.localStorage.removeItem(storageKey);
        } catch (error) {
          console.warn('Failed to clear memory', error);
        }
      }
    }
  };

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: createChatSession,
    onSuccess: (response) => {
      setCurrentSessionId(response.data.id);
      toast({
        title: 'Chat started',
        description: 'New conversation session created.',
      });
      // If there's a pending message, send it now that the session exists
      if (pendingMessage) {
        setIsLoading(true);
        sendMessageMutation.mutate({
          sessionId: response.data.id,
          message: pendingMessage,
        });
        setPendingMessage(null); // Clear the pending message
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to start chat session.',
        variant: 'destructive',
      });
      setPendingMessage(null); // Clear on error to avoid stuck state
    },
  });

  const updateSessionMutation = useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: number; data: Partial<ChatSession> & { enabled_tool_ids?: number[] } }) =>
      updateChatSession(sessionId, data),
  });

  // Send message mutation (fallback for non-streaming, kept for backwards compatibility)
  const sendMessageMutation = useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: number; message: string }) =>
      sendChatMessage(sessionId, message, selectedLLM || undefined, temperature, {
        mode: chatMode,
        personaId: selectedPersonaId,
        enabledTools: selectedToolIds,
      }),
    onSuccess: async (data) => {
      queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      setIsLoading(false);
      
      // Update agent todos if present in AI response
      if (data?.data?.ai_message?.metadata?.todos) {
        setAgentTodos(data.data.ai_message.metadata.todos);
      }
      
      // Trigger summarization after message
      if (currentSessionId) {
        try {
          await summarizeConversation(currentSessionId);
          queryClient.invalidateQueries({ queryKey: ['chat-sessions'] }); // Update subject in history
        } catch (error) {
          console.error('Failed to summarize conversation:', error);
        }
      }
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to send message.',
        variant: 'destructive',
      });
      setIsLoading(false);
    },
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSidebarToggle = useCallback(() => {
    setIsSidebarCollapsed(prev => {
      const next = !prev;
      persistStoredValue(sidebarCollapsedKey, next);
      return next;
    });
  }, [persistStoredValue, sidebarCollapsedKey]);

  const handlePreviewToggle = useCallback(() => {
    setIsPreviewHidden(prev => {
      const next = !prev;
      persistStoredValue(previewHiddenKey, next);
      return next;
    });
  }, [persistStoredValue, previewHiddenKey]);

  // Process pending file open when ref becomes available (editor tab was activated)
  useEffect(() => {
    if (pendingFileOpen) {
      // Use setTimeout to ensure TabbedEditor has fully mounted and ref is assigned
      const timeoutId = setTimeout(() => {
        if (tabbedEditorRef.current) {
          tabbedEditorRef.current.openFile(pendingFileOpen.path, pendingFileOpen.content);
          setPendingFileOpen(null);
        } else {
          console.warn('[AIEditorTab] TabbedEditor ref still not available after timeout');
        }
      }, 50);
      return () => clearTimeout(timeoutId);
    }
  }, [pendingFileOpen, activeSidebarTab]); // Re-check when sidebar tab changes

  useEffect(() => {
    if (!currentSessionId) return;
    updateSessionMutation.mutate({
      sessionId: currentSessionId,
      data: {
        mode: chatMode,
        persona: selectedPersonaId ?? null,
        enabled_tool_ids: selectedToolIds,
      },
    });
  }, [chatMode, selectedPersonaId, selectedToolIds]);

  useEffect(() => {
    setPanelLayout(readStoredPanelLayout(layoutStorageKey, layoutPreset.panelLayout));
    setSidebarSize(readStoredNumber(sidebarLayoutKey, layoutPreset.sidebarSize));
    setIsSidebarCollapsed(readStoredBoolean(sidebarCollapsedKey, layoutMode === 'full-page'));
    setIsPreviewHidden(readStoredBoolean(previewHiddenKey, false));
  }, [layoutMode, layoutPreset, layoutStorageKey, previewHiddenKey, project.id, sidebarCollapsedKey, sidebarLayoutKey]);

  // Load stored summary and memory when session changes
  useEffect(() => {
    if (!currentSessionId || typeof window === 'undefined') return;
    
    const summaryKey = `ai-editor-summary-${currentSessionId}`;
    const memoryKey = `ai-editor-memory-${currentSessionId}`;
    
    try {
      const storedSummary = window.localStorage.getItem(summaryKey);
      if (storedSummary) {
        setChatSummary(storedSummary);
      } else {
        setChatSummary(''); // Reset if no stored summary
      }
      
      const storedMemory = window.localStorage.getItem(memoryKey);
      if (storedMemory) {
        setMemoryItems(JSON.parse(storedMemory));
      } else {
        setMemoryItems([]); // Reset if no stored memory
      }
    } catch (error) {
      console.warn('Failed to load stored summary/memory', error);
      setChatSummary('');
      setMemoryItems([]);
    }
  }, [currentSessionId]);

  // Auto-create session on first load if none exists
  useEffect(() => {
    if (agentWsStatus === 'no-session' && !currentSessionId && !createSessionMutation.isPending) {
      const effectiveModel = getEffectiveModel(selectedLLM);
      createSessionMutation.mutate({
        project: project.id,
        title: `AI Editor Session for ${project.name}`,
        llm_id: effectiveModel || undefined,
        temperature: temperature,
        mode: chatMode,
        persona: selectedPersonaId || undefined,
        enabled_tool_ids: selectedToolIds,
      });
    }
  }, [agentWsStatus, currentSessionId, project.id, project.name, selectedLLM, temperature, chatMode, selectedPersonaId, selectedToolIds, getEffectiveModel, createSessionMutation]);

  // Extract tool calls from messages and populate agent tasks
  useEffect(() => {
    if (!messages || messages.length === 0) return;
    
    const extractedTasks: typeof agentTodos = [];
    
    for (const message of messages) {
      if (message.tool_calls && Array.isArray(message.tool_calls)) {
        for (const toolCall of message.tool_calls) {
          extractedTasks.push({
            description: toolCall.function?.name || toolCall.name || 'Unknown tool',
            status: toolCall.status || 'completed',
            details: typeof toolCall.function?.arguments === 'string'
              ? toolCall.function.arguments
              : typeof toolCall.args === 'string'
                ? toolCall.args
                : JSON.stringify(toolCall.args || toolCall).slice(0, 200),
          });
        }
      }
      
      // Also check metadata for tool_calls
      if (message.metadata?.tool_calls && Array.isArray(message.metadata.tool_calls)) {
        for (const toolCall of message.metadata.tool_calls) {
          extractedTasks.push({
            description: toolCall.function?.name || toolCall.name || 'Unknown tool',
            status: toolCall.status || 'completed',
            details: typeof toolCall.function?.arguments === 'string'
              ? toolCall.function.arguments
              : typeof toolCall.args === 'string'
                ? toolCall.args
                : JSON.stringify(toolCall.args || toolCall).slice(0, 200),
          });
        }
      }
    }
    
    // Only update if we have extracted tasks
    if (extractedTasks.length > 0) {
      setAgentTodos(extractedTasks);
    }
  }, [messages]);

  // Auto-update summary when session changes
  useEffect(() => {
    if (!currentSessionId) return;
    
    // Load latest session to get updated summary/subject
    queryClient.invalidateQueries({ queryKey: ['chat-sessions', project.id] });
    
    // Find the current session in the list and get its subject (which is the summary)
    const sessions = queryClient.getQueryData(['chat-sessions', project.id]) as any[];
    if (sessions && Array.isArray(sessions)) {
      const currentSession = sessions.find(s => s.id === currentSessionId);
      if (currentSession && currentSession.subject && currentSession.subject !== chatSummary) {
        setChatSummary(currentSession.subject);
      }
    }
  }, [currentSessionId, project.id, queryClient, chatSummary]);

  const handlePanelLayoutChange = (sizes: number[]) => {
    if (isChatCollapsed || isPreviewHidden || sizes.length !== 2 || sizes.some((size) => typeof size !== 'number')) return;
    setPanelLayout((prev) => (prev[0] === sizes[0] && prev[1] === sizes[1] ? prev : [sizes[0], sizes[1]]));
    persistStoredValue(layoutStorageKey, sizes);
  };

  const handleSidebarLayoutChange = (sizes: number[]) => {
    if (isSidebarCollapsed || sizes.length < 2 || typeof sizes[0] !== 'number') return;
    setSidebarSize(sizes[0]);
    persistStoredValue(sidebarLayoutKey, sizes[0]);
  };

  const handleSend = async (userMessage: string) => {
    if (!userMessage.trim() || isLoading || pendingMessage) return;

    // Create session if none exists
    if (!currentSessionId) {
      const effectiveModel = getEffectiveModel(selectedLLM);
      setPendingMessage(userMessage);
      createSessionMutation.mutate({
        project: project.id,
        title: `AI Editor Session for ${project.name}`,
        llm_id: effectiveModel || undefined,
        temperature: temperature,
        mode: chatMode,
        persona: selectedPersonaId || undefined,
        enabled_tool_ids: selectedToolIds,
      });
      return;
    }

    setIsLoading(true);

    // Prepare context files to send
    const contextToSend = openFiles
      .filter(f => contextFiles.includes(f.path))
      .map(f => ({ path: f.path, content: f.content }));

    // ── WebSocket-first path ──────────────────────────────────────
    // Try sending via the unified agent WS. The WS consumer handles
    // message persistence, graph creation, and streaming events.
    // All events (text_chunk, tool_*, worker_*, complete, error) are
    // handled in the useAgentStream onEvent callback above.
    if (agentWsStatus === 'connected' && wsSendMessage) {
      setIsStreaming(true);
      setStreamingContent('');

      // Optimistically add user message to the chat
      queryClient.setQueryData(['chat-messages', currentSessionId], (old: any) => {
        const messages = old?.data || old || [];
        return {
          ...(typeof old === 'object' && !Array.isArray(old) ? old : { data: messages }),
          data: [...(Array.isArray(messages) ? messages : []), {
            id: `optimistic-${Date.now()}`,
            message_type: 'user',
            content: userMessage,
            created_at: new Date().toISOString(),
          }],
        };
      });

      const sent = wsSendMessage(userMessage, contextToSend);
      if (!sent) {
        console.warn('[AIEditor] WS send failed, falling back to SSE');
        // Fall through to SSE fallback below
      } else {
        // WS handles everything — isLoading/isStreaming cleared by 'complete' or 'error' events
        return;
      }
    }

    // ── SSE fallback (legacy path) ────────────────────────────────
    try {
      setIsStreaming(true);
      setStreamingContent('');

      await streamChatMessage(
        project.id,
        currentSessionId,
        userMessage,
        (eventType, data) => {
          console.debug(`[AIEditor] SSE event: type=${eventType}`, data);

          if (eventType === 'text_chunk') {
            flushSync(() => {
              setStreamingContent(prev => prev + (data.content || ''));
            });
          } else if (eventType === 'error') {
            console.error('[AIEditor] Backend error:', data.message || data.error);
            setIsStreaming(false);
            setStreamingContent('');
            toast({
              title: 'Stream Error',
              description: data.message || data.error || 'Unknown error occurred',
              variant: 'destructive',
            });
          } else if (eventType === 'complete') {
            setStreamingContent('');
            setIsStreaming(false);
            queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
            queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
            if (currentSessionId) {
              summarizeConversation(currentSessionId).catch(err =>
                console.error('Failed to summarize:', err)
              );
            }
          }
        },
        (error) => {
          console.error('[AIEditor] Stream error:', error);
          setIsLoading(false);
          setIsStreaming(false);
          setStreamingContent('');
          toast({
            title: 'Stream Error',
            description: error.message,
            variant: 'destructive',
          });
        },
        () => {
          console.debug('[AIEditor] SSE stream complete');
          setIsLoading(false);
        },
        {
          llm_id: selectedLLM || undefined,
          temperature,
          ...(maxTokens > 0 ? { max_tokens: maxTokens } : {}),
          mode: chatMode,
          persona_id: selectedPersonaId || undefined,
          enabled_tool_ids: selectedToolIds,
          context_files: contextToSend,
        }
      );
    } catch (error) {
      console.error('[AIEditor] Failed to stream message:', error);
      setIsLoading(false);
      setIsStreaming(false);
      setStreamingContent('');
      toast({
        title: 'Error',
        description: 'Failed to send message.',
        variant: 'destructive',
      });
    }
  };

  const displayMessages = messages && messages.length > 0 ? messages : [];

  // Include streaming message in display if actively streaming
  const allDisplayMessages = isStreaming && streamingContent
    ? [
        ...displayMessages,
        {
          id: 'streaming',
          message_type: 'assistant' as const,
          content: streamingContent,
          created_at: new Date().toISOString(),
        } as any,
      ]
    : displayMessages;

  // Callback to open a file in the TabbedEditor from FileExplorer
  const handleFileSelect = (path: string, content: string) => {
    // Don't auto-switch tabs - let user stay on Explore tab to use Ask AI / Analyze buttons
    // User can manually switch to Editor tab if they want to edit
    
    // Track open file for context selection
    setOpenFiles(prev => {
      const exists = prev.find(f => f.path === path);
      if (exists) {
        return prev.map(f => f.path === path ? { ...f, content } : f);
      }
      return [...prev, { path, content, isDirty: false }];
    });
  };

  // Handler to open file in editor (explicit action)
  const handleOpenInEditor = (path: string, content: string) => {
    setActiveSidebarTab('editor');
    setIsSidebarCollapsed(false);
    persistStoredValue(sidebarCollapsedKey, false);
    
    // Try to open directly, or queue if ref not yet available
    if (tabbedEditorRef.current) {
      tabbedEditorRef.current.openFile(path, content);
    } else {
      // Queue the file to open when ref becomes available
      setPendingFileOpen({ path, content });
    }
    
    // Also track in openFiles for context
    handleFileSelect(path, content);
  };

  // Sync openFiles from TabbedEditor changes - only add/update, never remove
  const handleOpenFilesChange = (files: { path: string; content: string; isDirty?: boolean }[]) => {
    setOpenFiles(prev => {
      const result = [...prev];
      for (const file of files) {
        const idx = result.findIndex(f => f.path === file.path);
        if (idx >= 0) {
          result[idx] = { ...result[idx], content: file.content, isDirty: file.isDirty };
        } else {
          result.push(file);
        }
      }
      return result;
    });
  };

  // Handler to select a previous session from history
  const handleSelectSession = (sessionId: number) => {
    setCurrentSessionId(sessionId);
    queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] });
  };

  // Handler to save edited message and resend
  const handleEditMessage = async (messageId: number | string, newContent: string) => {
    try {
      setSavingMessageId(messageId);
      // Update the message content
      // In a real implementation, this would call a backend API to update the message
      // For now, we'll clear downstream messages and re-send
      
      const messagesData = queryClient.getQueryData(['chat-messages', currentSessionId]);
      const messagesArray = Array.isArray(messagesData) ? messagesData : (messagesData as any)?.data || [];
      const messageIndex = messagesArray.findIndex(m => m.id === messageId);
      
      if (messageIndex >= 0 && currentSessionId) {
        // Remove all messages after this one (clear AI responses)
        const updatedMessages = messagesArray.slice(0, messageIndex + 1);
        queryClient.setQueryData(['chat-messages', currentSessionId], updatedMessages);
        
        // Re-send the edited message via WS (preferred) or SSE fallback
        const contextToSend = openFiles
          .filter(f => contextFiles.includes(f.path))
          .map(f => ({ path: f.path, content: f.content }));

        if (agentWsStatus === 'connected' && wsSendMessage) {
          setIsStreaming(true);
          setStreamingContent('');
          wsSendMessage(newContent, contextToSend);
        } else {
          await new Promise(resolve => {
            streamChatMessage(
              project.id,
              currentSessionId,
              newContent,
              (eventType, data) => {
                if (eventType === 'text_chunk' || eventType === 'complete') {
                  queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
                }
              },
              (error) => console.error('Stream error:', error),
              () => {
                resolve(undefined);
                queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
              },
              {
                llm_id: selectedLLM || undefined,
                temperature,
                ...(maxTokens > 0 ? { max_tokens: maxTokens } : {}),
                mode: chatMode,
                persona_id: selectedPersonaId || undefined,
                enabled_tool_ids: selectedToolIds,
                context_files: contextToSend,
              }
            );
          });
        }
        
        setEditingMessageId(null);
        toast({
          title: 'Message updated',
          description: 'Message sent and response refreshed',
        });
      }
    } catch (error) {
      console.error('Failed to edit message:', error);
      toast({
        title: 'Error',
        description: 'Failed to update message',
        variant: 'destructive',
      });
    } finally {
      setSavingMessageId(null);
    }
  };

  // Handler for copying message content
  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      toast({
        title: 'Copied',
        description: 'Message copied to clipboard',
      });
    });
  };

  // Handler for regenerating - called on assistant messages to re-send the previous user message
  const handleRegenerateMessage = async (messageId: number | string) => {
    try {
      setSavingMessageId(messageId);
      const messagesData = queryClient.getQueryData(['chat-messages', currentSessionId]);
      const messagesArray = Array.isArray(messagesData) ? messagesData : (messagesData as any)?.data || [];
      
      // Find the message that was clicked (should be an assistant message)
      const clickedMessageIndex = messagesArray.findIndex((m: any) => m.id === messageId);
      
      if (clickedMessageIndex < 0 || !currentSessionId) {
        console.error('[Regenerate] Message not found:', messageId);
        setSavingMessageId(null);
        return;
      }
      
      // Find the previous user message before this assistant message
      let userMessageIndex = clickedMessageIndex - 1;
      while (userMessageIndex >= 0 && messagesArray[userMessageIndex].message_type !== 'user') {
        userMessageIndex--;
      }
      
      if (userMessageIndex < 0) {
        console.error('[Regenerate] No user message found before assistant message');
        toast({
          title: 'Cannot regenerate',
          description: 'No user message found to regenerate from',
          variant: 'destructive',
        });
        setSavingMessageId(null);
        return;
      }
      
      const userMessage = messagesArray[userMessageIndex];
      console.debug('[Regenerate] Found user message to regenerate:', userMessage.content?.substring(0, 50));
      
      // Remove the assistant message we're regenerating (and any after it)
      const updatedMessages = messagesArray.slice(0, clickedMessageIndex);
      queryClient.setQueryData(['chat-messages', currentSessionId], updatedMessages);
      
      // Start streaming state
      setIsStreaming(true);
      setStreamingContent('');
      
      // Re-send the user message via WS or SSE
      const contextToSend = openFiles
        .filter(f => contextFiles.includes(f.path))
        .map(f => ({ path: f.path, content: f.content }));

      if (agentWsStatus === 'connected' && wsSendMessage) {
        wsSendMessage(userMessage.content || '', contextToSend);
        // WS events (text_chunk, complete, error) handled by useAgentStream callback
        setSavingMessageId(null);
      } else {
        await streamChatMessage(
          project.id,
          currentSessionId,
          userMessage.content || '',
          (eventType, data) => {
            console.debug(`[Regenerate] Event: ${eventType}`);
            if (eventType === 'text_chunk') {
              flushSync(() => {
                setStreamingContent(prev => prev + (data.content || ''));
              });
            } else if (eventType === 'error') {
              console.error('[Regenerate] Backend error:', data.message || data.error);
              setIsStreaming(false);
              setStreamingContent('');
              toast({
                title: 'Regeneration Error',
                description: data.message || data.error || 'Unknown error occurred',
                variant: 'destructive',
              });
            } else if (eventType === 'complete') {
              setStreamingContent('');
              setIsStreaming(false);
              queryClient.invalidateQueries({ queryKey: ['chat-messages', currentSessionId] });
            }
          },
          (error) => {
            console.error('[Regenerate] Stream error:', error);
            setIsStreaming(false);
            setStreamingContent('');
            setSavingMessageId(null);
            toast({
              title: 'Regeneration Failed',
              description: error.message,
              variant: 'destructive',
            });
          },
          () => {
            console.debug('[Regenerate] Stream complete');
            setSavingMessageId(null);
          },
          {
            llm_id: selectedLLM || undefined,
            temperature,
            ...(maxTokens > 0 ? { max_tokens: maxTokens } : {}),
            mode: chatMode,
            persona_id: selectedPersonaId || undefined,
            enabled_tool_ids: selectedToolIds,
            context_files: contextToSend,
          }
        );
      }
      
      toast({
        title: 'Regenerating response',
        description: 'Generating new response...',
      });
    } catch (error) {
      console.error('[Regenerate] Failed to regenerate:', error);
      setIsStreaming(false);
      setStreamingContent('');
      setSavingMessageId(null);
      toast({
        title: 'Error',
        description: 'Failed to regenerate response',
        variant: 'destructive',
      });
    } finally {
      // Ensure streaming state is always reset, even on unexpected errors
      setIsStreaming(false);
      setStreamingContent('');
      setSavingMessageId(null);
    }
  };

  return (
    <>
      <div className="flex flex-col flex-1 min-h-0 h-full overflow-hidden">
        {/* Main layout: Resizable sidebar | Chat + Preview */}
        <div className="flex-1 min-h-0 h-full overflow-hidden">
          <ResizablePanelGroup
            key={`ai-editor-sidebar:${layoutMode}:${storageScope}:${isSidebarCollapsed ? 'collapsed' : 'expanded'}`}
            direction="horizontal"
            className="h-full w-full"
            onLayout={handleSidebarLayoutChange}
          >
          {!isSidebarCollapsed && (
            <>
              {/* Left Sidebar: File Explorer + Tabbed Editor (resizable) */}
              <ResizablePanel defaultSize={sidebarSize} minSize={layoutPreset.sidebarMin} maxSize={layoutPreset.sidebarMax}>
                <div className="h-full flex flex-col overflow-hidden" style={{ borderRight: '1px solid var(--pf-v6-global--BorderColor--100)' }}>
                <UITabs value={activeSidebarTab} onValueChange={(v) => setActiveSidebarTab(v as 'files' | 'editor')} className="h-full flex flex-col overflow-hidden">
                  <div className="flex items-center border-b flex-shrink-0">
                    <TabsList className="grid flex-1 grid-cols-2 rounded-none border-0">
                      <TabsTrigger value="files">Files</TabsTrigger>
                      <TabsTrigger value="editor">Editor</TabsTrigger>
                    </TabsList>
                  </div>
                  
                  <TabsContent value="files" className="flex-1 min-h-0 overflow-hidden p-0 mt-0 flex flex-col">
                    <FileExplorer
                      project={project}
                      onFileSelect={handleFileSelect}
                      onOpenInEditor={handleOpenInEditor}
                      onAskAboutFile={handleAskAboutFile}
                      chatSessionId={currentSessionId}
                      onEnsureSession={async () => {
                        if (currentSessionId) return currentSessionId;
                        try {
                          const resp = await createChatSession({
                            project: project.id,
                            title: `Deep analysis session for ${project.name}`,
                          });
                          const sid = resp?.data?.id || null;
                          if (sid) {
                            setCurrentSessionId(sid);
                            toast({
                              title: 'Session created',
                              description: `Chat session ${sid} started for streaming.`,
                            });
                            return sid;
                          }
                          return null;
                        } catch (e) {
                          console.error('Failed to create chat session', e);
                          return null;
                        }
                      }}
                    />
                  </TabsContent>

                  <TabsContent value="editor" className="data-[state=active]:flex-1 data-[state=inactive]:h-0 min-h-0 overflow-hidden p-0 mt-0" forceMount>
                    <div className={activeSidebarTab === 'editor' ? 'h-full' : 'hidden'}>
                      <TabbedEditor
                        ref={tabbedEditorRef}
                        project={project}
                        onAskAboutFile={handleAskAboutFile}
                        onOpenFilesChange={handleOpenFilesChange}
                      />
                    </div>
                  </TabsContent>
                </UITabs>
                </div>
              </ResizablePanel>

              <ResizableHandle
                withHandle
                className="w-1.5 bg-border hover:bg-primary/20 transition-colors cursor-col-resize"
              />
            </>
          )}

          {/* Right side: Chat and Preview Area - takes remaining space */}
          <ResizablePanel defaultSize={isSidebarCollapsed ? 100 : 100 - sidebarSize} minSize={layoutPreset.mainMin}>
            <ResizablePanelGroup
              key={`ai-editor-main:${layoutMode}:${storageScope}:${isChatCollapsed ? 'cc' : 'ce'}:${isPreviewHidden ? 'ph' : 'pv'}`}
              direction="horizontal"
              className="h-full w-full gap-4"
              onLayout={handlePanelLayoutChange}
            >
            {/* Chat Panel — PatternFly Chatbot */}
            {!isChatCollapsed && (
              <>
                <ResizablePanel defaultSize={isPreviewHidden ? 100 : panelLayout[0]} minSize={layoutPreset.chatMin} maxSize={isPreviewHidden ? 100 : layoutPreset.chatMax} className="flex flex-col h-full min-h-0">
                  <ChatPanel
                    project={project}
                    allDisplayMessages={allDisplayMessages}
                    messagesLoading={messagesLoading}
                    isStreaming={isStreaming}
                    streamingContent={streamingContent}
                    currentSessionId={currentSessionId}
                    sessions={sessions}
                    sessionsLoading={sessionsLoading}
                    onSelectSession={handleSelectSession}
                    onNewSession={() => {
                      createSessionMutation.mutate({
                        project: project.id,
                        title: `AI Editor Session for ${project.name}`,
                        llm_id: getEffectiveModel(selectedLLM) || undefined,
                        temperature,
                        mode: chatMode,
                        persona: selectedPersonaId || undefined,
                        enabled_tool_ids: selectedToolIds,
                      });
                    }}
                    isLoading={isLoading}
                    onSend={handleSend}
                    chatMode={chatMode}
                    onChatModeChange={setChatMode}
                    editingMessageId={editingMessageId}
                    savingMessageId={savingMessageId}
                    onEditMessage={handleEditMessage}
                    onSetEditingMessageId={setEditingMessageId}
                    onRegenerateMessage={handleRegenerateMessage}
                    onCopyMessage={handleCopyMessage}
                    selectedLLM={selectedLLM}
                    onSelectedLLMChange={setSelectedLLM}
                    selectedModelLabel={selectedModelLabel}
                    llmOptions={llmOptions}
                    getModelLabel={getModelLabel}
                    temperature={temperature}
                    onTemperatureChange={setTemperature}
                    maxTokens={maxTokens}
                    onMaxTokensChange={setMaxTokens}
                    isSettingsOpen={isSettingsOpen}
                    onSettingsOpenChange={setIsSettingsOpen}
                    isModelSelectOpen={isModelSelectOpen}
                    onModelSelectOpenChange={setIsModelSelectOpen}
                    openFiles={openFiles}
                    contextFiles={contextFiles}
                    onContextChange={setContextFiles}
                    allTools={allTools}
                    selectedToolIds={selectedToolIds}
                    onToolsChange={setSelectedToolIds}
                    personas={personas}
                    selectedPersona={selectedPersona}
                    selectedPersonaId={selectedPersonaId}
                    onSelectedPersonaChange={setSelectedPersonaId}
                    isToolSelectorDialogOpen={isToolSelectorDialogOpen}
                    onToolSelectorDialogOpenChange={setIsToolSelectorDialogOpen}
                    agentMode={agentMode}
                    onAgentModeToggle={() => {
                      if (copilotAvailable || agentMode === 'copilot') {
                        setAgentMode(prev => prev === 'assisted' ? 'copilot' : 'assisted');
                      } else {
                        toast({
                          title: 'Copilot Not Available',
                          description: 'Start workspace with COPILOT_MODE=true to enable',
                          variant: 'default',
                        });
                      }
                    }}
                    copilotAvailable={copilotAvailable}
                    agentWsStatus={agentWsStatus}
                    isAnalysisModalOpen={isAnalysisModalOpen}
                    onAnalysisModalOpenChange={setIsAnalysisModalOpen}
                    analysisChunks={analysisChunks}
                    analysisFinal={analysisFinal}
                    onCreateChangeRequest={handleCreateChangeRequest}
                    chatSummary={chatSummary}
                    onSummaryChange={handleSummaryChange}
                    onRegenerateSummary={async () => {
                      if (currentSessionId) {
                        try {
                          await summarizeConversation(currentSessionId);
                          queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
                          toast({ title: 'Summary regenerated', description: 'Check the session subject for the updated summary.' });
                        } catch {
                          toast({ title: 'Error', description: 'Failed to regenerate summary.', variant: 'destructive' });
                        }
                      }
                    }}
                    memoryItems={memoryItems}
                    onAddMemory={handleAddMemory}
                    onEditMemory={handleEditMemory}
                    onDeleteMemory={handleDeleteMemory}
                    onClearAllMemory={handleClearAllMemory}
                    agentTodos={agentTodos}
                    isSidebarCollapsed={isSidebarCollapsed}
                    onSidebarToggle={handleSidebarToggle}
                    isPreviewHidden={isPreviewHidden}
                    onPreviewToggle={handlePreviewToggle}
                    onStopStreaming={wsCancel || undefined}
                    messagesEndRef={messagesEndRef}
                  />
                </ResizablePanel>

                {!isPreviewHidden && (
                  <ResizableHandle
                    withHandle
                    className="w-2 bg-border hover:bg-primary/20 transition-colors cursor-col-resize"
                  />
                )}
              </>
            )}

            {/* Workspace Panel — optional */}
            {!isPreviewHidden && (
              <ResizablePanel defaultSize={isChatCollapsed ? 100 : panelLayout[1]} minSize={layoutPreset.previewMin}>
                <WorkspacePanel 
                  project={project}
                  isChatCollapsed={isChatCollapsed}
                  onChatCollapsedChange={setIsChatCollapsed}
                />
              </ResizablePanel>
            )}
            </ResizablePanelGroup>
          </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>
    </>
  );
};
