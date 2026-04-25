/**
 * ChatPanel — PatternFly Chatbot–powered chat panel.
 *
 * Replaces the previous custom message rendering, ChatComposer input, and
 * session history with @patternfly/chatbot components while keeping the
 * existing resizable-panel layout, custom header toolbar, and specialised
 * sub-components (MessageEdit, ToolOutput, AnalysisStreamModal).
 */
import { useState, useRef, useEffect, useMemo, useCallback } from 'react';

// ── PatternFly Chatbot ────────────────────────────────────────────────
import Chatbot, { ChatbotDisplayMode } from '@patternfly/chatbot/dist/dynamic/Chatbot';
import ChatbotContent from '@patternfly/chatbot/dist/dynamic/ChatbotContent';
import ChatbotWelcomePrompt from '@patternfly/chatbot/dist/dynamic/ChatbotWelcomePrompt';
import ChatbotFooter, { ChatbotFootnote } from '@patternfly/chatbot/dist/dynamic/ChatbotFooter';
import MessageBar from '@patternfly/chatbot/dist/dynamic/MessageBar';
import MessageBox from '@patternfly/chatbot/dist/dynamic/MessageBox';
import Message from '@patternfly/chatbot/dist/dynamic/Message';
import type { MessageProps } from '@patternfly/chatbot/dist/dynamic/Message';
import ChatbotHeader, {
  ChatbotHeaderMenu,
  ChatbotHeaderMain,
  ChatbotHeaderTitle,
  ChatbotHeaderActions,
} from '@patternfly/chatbot/dist/dynamic/ChatbotHeader';
import ChatbotConversationHistoryNav, {
  Conversation,
} from '@patternfly/chatbot/dist/dynamic/ChatbotConversationHistoryNav';

// ── PatternFly core ──────────────────────────────────────────────────
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Dropdown,
  DropdownItem,
  DropdownList,
  Flex,
  FlexItem,
  Label as PFLabel,
  MenuToggle,
  Spinner,
  Tab,
  Tabs,
  TabTitleText,
  TextArea,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core';
import { TrashIcon } from '@patternfly/react-icons';

// ── Shadcn / custom UI ──────────────────────────────────────────────
import { Label as FieldLabel } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ToggleGroup as ModeToggleGroup, ToggleGroupItem as ModeToggleGroupItem } from '@/components/ui/toggle-group';

// ── Custom editor components ────────────────────────────────────────
import { MessageEdit } from '@/components/editor/MessageEdit';
import { FileContextSelector } from '@/components/editor/FileContextSelector';
import { ToolSelector } from '@/components/editor/ToolSelector';
import { ModelSelectorDialog } from '@/components/project/ModelSelectorDialog';
import ToolOutput from '@/components/project/ToolOutput';
import AnalysisStreamModal from '@/components/project/AnalysisStreamModal';

// ── Icons ────────────────────────────────────────────────────────────
import {
  Settings,
  Loader2,
  Bot,
  MessageCircle,
  Workflow,
  Sparkles,
  FileText,
  CheckSquare,
  Clock,
  CheckCircle,
  AlertTriangle,
  Wrench,
  SquarePen,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────
import type { ChatMessage, ChatMode, ChatSession, ChatbotPersona, Project, ProjectTool } from '@/lib/api';
import type { LLMModelOption } from '@/hooks/use-llm-models';

// Bot / user avatar SVGs (inline data-URIs for simplicity)
const BOT_AVATAR =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%234a90d9" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="3"/><line x1="12" y1="8" x2="12" y2="11"/><circle cx="8" cy="16" r="1.5" fill="%234a90d9"/><circle cx="16" cy="16" r="1.5" fill="%234a90d9"/></svg>'
  );
const USER_AVATAR =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%23666" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 1 0 -16 0"/></svg>'
  );

const CHAT_MODES: Array<{ value: ChatMode; label: string; description: string; icon: typeof MessageCircle }> = [
  { value: 'ask', label: 'Ask', description: 'Direct answers', icon: MessageCircle },
  { value: 'plan', label: 'Plan', description: 'Outline the next steps before editing', icon: Sparkles },
  { value: 'agent', label: 'Agent', description: 'Run autonomous multi-step work', icon: Workflow },
  { value: 'persona', label: 'Persona', description: 'Respond with a selected persona', icon: Sparkles },
  { value: 'deep', label: 'Deep', description: 'Spend more time reasoning across context', icon: Bot },
];

const PRIMARY_CHAT_MODES = CHAT_MODES.filter(({ value }) => value === 'ask' || value === 'plan' || value === 'agent');

type UtilityDialogTab = 'summary' | 'memory' | 'agent-todos';

// ── Helper ───────────────────────────────────────────────────────────
const getMessageTimestamp = (message: Partial<ChatMessage> & { timestamp?: Date | string }) => {
  const source = (message as any).created_at || message.timestamp;
  if (!source) return null;
  const parsed = new Date(source);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

// ── Props ────────────────────────────────────────────────────────────
export interface ChatPanelProps {
  project: Project;

  // Messages
  allDisplayMessages: Array<Partial<ChatMessage> & { id?: string | number; timestamp?: Date | string }>;
  messagesLoading: boolean;
  isStreaming: boolean;
  streamingContent: string;

  // Session
  currentSessionId: number | null;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  onSelectSession: (sessionId: number) => void;
  onNewSession: () => void;

  // Sending
  isLoading: boolean;
  onSend: (message: string) => void;
  chatMode: ChatMode;
  onChatModeChange: (mode: ChatMode) => void;

  // Editing
  editingMessageId: number | string | null;
  savingMessageId: number | string | null;
  onEditMessage: (messageId: number | string, newContent: string) => Promise<void>;
  onSetEditingMessageId: (id: number | string | null) => void;

  // Actions
  onRegenerateMessage: (messageId: number | string) => Promise<void>;
  onCopyMessage: (content: string) => void;

  // LLM / Model selection
  selectedLLM: string;
  onSelectedLLMChange: (llm: string) => void;
  selectedModelLabel: string;
  llmOptions: LLMModelOption[];
  getModelLabel: (id: string | null) => string;

  // Settings
  temperature: number;
  onTemperatureChange: (t: number) => void;
  maxTokens: number;
  onMaxTokensChange: (t: number) => void;
  isSettingsOpen: boolean;
  onSettingsOpenChange: (open: boolean) => void;
  isModelSelectOpen: boolean;
  onModelSelectOpenChange: (open: boolean) => void;

  // File Context
  openFiles: { path: string; content: string; isDirty?: boolean }[];
  contextFiles: string[];
  onContextChange: (files: string[]) => void;

  // Tool Selector
  allTools: ProjectTool[];
  selectedToolIds: number[];
  onToolsChange: (ids: number[]) => void;
  personas: ChatbotPersona[];
  selectedPersona: ChatbotPersona | null;
  selectedPersonaId: number | null;
  onSelectedPersonaChange: (personaId: number | null) => void;
  isToolSelectorDialogOpen: boolean;
  onToolSelectorDialogOpenChange: (open: boolean) => void;

  // Agent mode
  agentMode: 'assisted' | 'copilot';
  onAgentModeToggle: () => void;
  copilotAvailable: boolean;

  // Agent stream status
  agentWsStatus: string;

  // Analysis modal
  isAnalysisModalOpen: boolean;
  onAnalysisModalOpenChange: (open: boolean) => void;
  analysisChunks: any[];
  analysisFinal: any | null;
  onCreateChangeRequest: (summary: string) => void;

  // Summary & Memory
  chatSummary: string;
  onSummaryChange: (value: string) => void;
  onRegenerateSummary: () => void;
  memoryItems: string[];
  onAddMemory: () => void;
  onEditMemory: (index: number, value: string) => void;
  onDeleteMemory: (index: number) => void;
  onClearAllMemory: () => void;

  // Agent tasks
  agentTodos: Array<{ description: string; status: 'pending' | 'in_progress' | 'completed' | 'failed'; details?: string }>;

  // Workspace chrome controls
  isSidebarCollapsed: boolean;
  onSidebarToggle: () => void;
  isPreviewHidden: boolean;
  onPreviewToggle: () => void;

  // Stop handler for streaming
  onStopStreaming?: () => void;

  // Scroll ref
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

export const ChatPanel: React.FC<ChatPanelProps> = (props) => {
  const {
    project,
    allDisplayMessages,
    messagesLoading,
    isStreaming,
    streamingContent,
    currentSessionId,
    sessions,
    sessionsLoading,
    onSelectSession,
    onNewSession,
    isLoading,
    onSend,
    chatMode,
    onChatModeChange,
    editingMessageId,
    savingMessageId,
    onEditMessage,
    onSetEditingMessageId,
    onRegenerateMessage,
    onCopyMessage,
    selectedLLM,
    onSelectedLLMChange,
    selectedModelLabel,
    llmOptions,
    getModelLabel,
    temperature,
    onTemperatureChange,
    maxTokens,
    onMaxTokensChange,
    isSettingsOpen,
    onSettingsOpenChange,
    isModelSelectOpen,
    onModelSelectOpenChange,
    openFiles,
    contextFiles,
    onContextChange,
    allTools,
    selectedToolIds,
    onToolsChange,
    personas,
    selectedPersona,
    selectedPersonaId,
    onSelectedPersonaChange,
    isToolSelectorDialogOpen,
    onToolSelectorDialogOpenChange,
    agentMode,
    onAgentModeToggle,
    copilotAvailable,
    agentWsStatus,
    isAnalysisModalOpen,
    onAnalysisModalOpenChange,
    analysisChunks,
    analysisFinal,
    onCreateChangeRequest,
    chatSummary,
    onSummaryChange,
    onRegenerateSummary,
    memoryItems,
    onAddMemory,
    onEditMemory,
    onDeleteMemory,
    onClearAllMemory,
    agentTodos,
    isSidebarCollapsed,
    onSidebarToggle,
    isPreviewHidden,
    onPreviewToggle,
    onStopStreaming,
    messagesEndRef,
  } = props;

  // ── Conversation history drawer ─────────────────────────────────
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState('');
  const historyRef = useRef<HTMLButtonElement>(null);

  const [isAgentModeMenuOpen, setIsAgentModeMenuOpen] = useState(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [isUtilityDialogOpen, setIsUtilityDialogOpen] = useState(false);
  const [isPersonaDialogOpen, setIsPersonaDialogOpen] = useState(false);
  const [activeUtilityTab, setActiveUtilityTab] = useState<UtilityDialogTab>('summary');

  // Build PF Conversation[] from sessions, grouped by date
  const conversations = useMemo<{ [key: string]: Conversation[] }>(() => {
    if (!sessions || sessions.length === 0) return {};

    const filtered = historySearch
      ? sessions.filter((s) =>
          (s.title || s.subject || '').toLowerCase().includes(historySearch.toLowerCase())
        )
      : sessions;

    const groups: { [key: string]: Conversation[] } = {};
    const now = new Date();

    for (const session of filtered) {
      const created = new Date((session as any).created_at || Date.now());
      const diffDays = Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24));
      const groupLabel = diffDays === 0 ? 'Today' : diffDays <= 7 ? 'This week' : diffDays <= 30 ? 'This month' : 'Older';

      if (!groups[groupLabel]) groups[groupLabel] = [];
      groups[groupLabel].push({
        id: String(session.id),
        text: session.title || session.subject || `Session ${session.id}`,
      });
    }
    return groups;
  }, [sessions, historySearch]);

  // ── Welcome prompts ─────────────────────────────────────────────
  const welcomePrompts = useMemo(
    () => [
      { title: 'Analyze project', message: `Analyze the ${project.name} project structure and summarize potential issues` },
      { title: 'Find TODOs', message: `Find all TODO and FIXME comments in the ${project.name} codebase` },
      { title: 'Explain codebase', message: `Give me a high-level overview of how ${project.name} is structured` },
    ],
    [project.name]
  );

  const primaryChatMode = useMemo<ChatMode>(() => {
    if (chatMode === 'plan' || chatMode === 'agent') {
      return chatMode;
    }
    return 'ask';
  }, [chatMode]);

  const activeModeDescription = useMemo(() => {
    if (chatMode === 'persona') {
      return selectedPersona
        ? `${selectedPersona.name} shapes the reply and tool choices.`
        : 'Choose a persona to tailor how the assistant responds.';
    }

    return CHAT_MODES.find((mode) => mode.value === chatMode)?.description || 'Direct answers';
  }, [chatMode, selectedPersona]);

  const activeAdvancedModeLabel = chatMode === 'persona' ? 'Persona' : chatMode === 'deep' ? 'Deep' : null;
  const agentModeLabel = agentMode === 'copilot' ? 'Copilot' : 'Assisted';

  // ── Build PF Message list ──────────────────────────────────────
  // We convert the app's ChatMessage[] into PF MessageProps[].
  // For messages being edited, we render a custom child (MessageEdit).
  // For assistant messages with tool_calls, we render ToolOutput as children.
  const pfMessages: (MessageProps & { _raw: any })[] = useMemo(() => {
    return allDisplayMessages.map((msg, idx) => {
      const timestamp = getMessageTimestamp(msg);
      const role: 'user' | 'bot' =
        (msg as any).message_type === 'user' || (msg as any).role === 'user' ? 'user' : 'bot';
      const id = String(
        msg.id ?? (timestamp ? `ts-${timestamp.getTime()}` : `temp-${idx}`)
      );
      const isLastAndStreaming = idx === allDisplayMessages.length - 1 && isStreaming && role === 'bot';

      return {
        id,
        role,
        content: msg.content || '',
        name: role === 'user' ? 'You' : 'AI Assistant',
        avatar: role === 'user' ? USER_AVATAR : BOT_AVATAR,
        timestamp: timestamp ? timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : undefined,
        isLoading: isLastAndStreaming && !msg.content,
        avatarProps: role === 'user' ? { isBordered: true } : undefined,
        _raw: msg,
      };
    });
  }, [allDisplayMessages, isStreaming]);

  // ── Handler: send via PF MessageBar ─────────────────────────────
  const handlePFSend = useCallback(
    (message: string | number) => {
      const text = String(message).trim();
      if (!text) return;
      onSend(text);
    },
    [onSend]
  );

  // ── Handler: history item select ────────────────────────────────
  const handleHistorySelect = useCallback(
    (_e: React.MouseEvent | undefined, itemId: string | number | undefined) => {
      if (itemId != null) {
        onSelectSession(Number(itemId));
        setIsDrawerOpen(false);
      }
    },
    [onSelectSession]
  );

  const openUtilityDialog = useCallback((tab: UtilityDialogTab) => {
    setActiveUtilityTab(tab);
    setIsUtilityDialogOpen(true);
    setIsUtilityMenuOpen(false);
  }, []);

  const handlePersonaChoice = useCallback((personaId: number | null) => {
    onSelectedPersonaChange(personaId);
    setIsPersonaDialogOpen(false);
    setIsMoreMenuOpen(false);
    if (personaId === null) {
      if (chatMode === 'persona') {
        onChatModeChange('ask');
      }
      return;
    }
    onChatModeChange('persona');
  }, [chatMode, onChatModeChange, onSelectedPersonaChange]);

  const handleAgentModeSelect = useCallback((nextMode: 'assisted' | 'copilot') => {
    setIsAgentModeMenuOpen(false);
    if (nextMode === agentMode) {
      return;
    }
    if (nextMode === 'copilot' && !copilotAvailable) {
      return;
    }
    onAgentModeToggle();
  }, [agentMode, copilotAvailable, onAgentModeToggle]);

  // Auto-scroll using the end-of-message anchor.
  useEffect(() => {
    if (allDisplayMessages.length > 1) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [allDisplayMessages.length, messagesEndRef]);

  return (
    <div className="pf-chatbot-container" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
      {/* ── PF Chatbot wrapper (embedded mode, fills parent) ────── */}
      <Chatbot displayMode={ChatbotDisplayMode.embedded} className="pf-chatbot--embedded-fill">
        <ChatbotConversationHistoryNav
          displayMode={ChatbotDisplayMode.embedded}
          onDrawerToggle={() => {
            setIsDrawerOpen(!isDrawerOpen);
            setHistorySearch('');
          }}
          isDrawerOpen={isDrawerOpen}
          setIsDrawerOpen={setIsDrawerOpen}
          activeItemId={currentSessionId ? String(currentSessionId) : undefined}
          onSelectActiveItem={handleHistorySelect}
          conversations={
            Object.keys(conversations).length > 0
              ? conversations
              : [{ id: '__empty__', noIcon: true, text: 'No conversations yet' }]
          }
          onNewChat={onNewSession}
          handleTextInputChange={(value: string) => setHistorySearch(value)}
          searchInputPlaceholder="Search conversations..."
          drawerContent={
            <div className="pf-chatbot-drawer-layout">
              {/* ── PF Chatbot Header ──────────────────────────── */}
              <ChatbotHeader>
                <ChatbotHeaderMain>
                  <ChatbotHeaderMenu
                    ref={historyRef}
                    aria-expanded={isDrawerOpen}
                    onMenuToggle={() => setIsDrawerOpen(!isDrawerOpen)}
                  />
                  <ChatbotHeaderTitle>
                    <span className="text-sm font-semibold leading-none">AI Editor</span>
                    <span
                      className={`ml-2 inline-block w-2 h-2 rounded-full ${
                        agentWsStatus === 'connected' ? 'bg-green-500' :
                        agentWsStatus === 'connecting' ? 'bg-orange-500' :
                        agentWsStatus === 'no-session' ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      title={`Stream: ${agentWsStatus}`}
                    />
                  </ChatbotHeaderTitle>
                </ChatbotHeaderMain>
                <ChatbotHeaderActions>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={isSidebarCollapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
                    onClick={onSidebarToggle}
                    className="text-xs"
                    title={isSidebarCollapsed ? 'Show files panel' : 'Hide files panel'}
                  >
                    Files
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={isPreviewHidden ? <PanelRightOpen size={14} /> : <PanelRightClose size={14} />}
                    onClick={onPreviewToggle}
                    className="text-xs"
                    title={isPreviewHidden ? 'Show live preview' : 'Hide live preview'}
                  >
                    Preview
                  </Button>
                  <Dropdown
                    isOpen={isAgentModeMenuOpen}
                    onSelect={() => setIsAgentModeMenuOpen(false)}
                    toggle={(toggleRef) => (
                      <MenuToggle
                        ref={toggleRef}
                        isExpanded={isAgentModeMenuOpen}
                        onClick={() => setIsAgentModeMenuOpen((prev) => !prev)}
                        variant="secondary"
                        size="sm"
                        icon={<Workflow size={14} />}
                        className="text-xs"
                      >
                        {agentModeLabel}
                      </MenuToggle>
                    )}
                    popperProps={{ position: 'end' }}
                  >
                    <DropdownList>
                      <DropdownItem onClick={() => handleAgentModeSelect('assisted')}>Assisted</DropdownItem>
                      <DropdownItem
                        onClick={() => handleAgentModeSelect('copilot')}
                        isDisabled={!copilotAvailable}
                        description={copilotAvailable ? undefined : 'Requires a workspace started with COPILOT_MODE=true'}
                      >
                        Copilot
                      </DropdownItem>
                    </DropdownList>
                  </Dropdown>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<SquarePen size={16} />}
                    aria-label="New chat"
                    onClick={onNewSession}
                  />
                </ChatbotHeaderActions>
              </ChatbotHeader>

              {/* ── Main chat content ────────────────────────────── */}
              <div style={{ display: 'flex', flex: 1, minHeight: 0, flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ flex: '1 1 0%', minHeight: 0, position: 'relative' }}>
                  <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', overscrollBehavior: 'contain' }}>
                    <ChatbotContent>
                      <MessageBox announcement={isStreaming ? 'AI is responding…' : undefined}>
                        {!messagesLoading && allDisplayMessages.length === 0 && (
                          <ChatbotWelcomePrompt
                            title={`Welcome to ${project.name}`}
                            description="Ask a question, sketch a plan, or hand off a task to the agent."
                            prompts={welcomePrompts}
                            isCompact
                          />
                        )}

                        {messagesLoading && (
                          <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin" />
                            <span className="ml-2 text-xs text-muted-foreground">Loading messages…</span>
                          </div>
                        )}

                        {!messagesLoading &&
                          pfMessages.map((msg, idx) => {
                            const raw = msg._raw;
                            const isEditing = editingMessageId === raw.id;
                            const key = msg.id || `msg-${idx}`;

                            if (isEditing && msg.role === 'user') {
                              return (
                                <div key={key} className="pf-chatbot__message-editing-wrapper" style={{ padding: '0 var(--pf-t--global--spacer--lg)' }}>
                                  <MessageEdit
                                    message={raw}
                                    isEditing={true}
                                    onEdit={() => {}}
                                    onSave={(content) => onEditMessage(raw.id || key, content)}
                                    onCancel={() => onSetEditingMessageId(null)}
                                    isSaving={savingMessageId === raw.id}
                                  />
                                </div>
                              );
                            }

                            const actions =
                              msg.role === 'bot'
                                ? {
                                    positive: {
                                      onClick: () => {},
                                      ariaLabel: 'Good response',
                                    },
                                    negative: {
                                      onClick: () => {},
                                      ariaLabel: 'Bad response',
                                    },
                                    copy: {
                                      onClick: () => onCopyMessage(raw.content || ''),
                                      ariaLabel: 'Copy response',
                                    },
                                    regenerate: {
                                      onClick: () => onRegenerateMessage(raw.id || key),
                                      ariaLabel: 'Regenerate response',
                                      icon: (
                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                                          <path d="M3 3v5h5" />
                                          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                                          <path d="M16 16h5v5" />
                                        </svg>
                                      ),
                                      tooltipContent: 'Regenerate',
                                    },
                                  }
                                : undefined;

                            const toolCalls =
                              raw.tool_calls?.length > 0
                                ? raw.tool_calls
                                : raw.metadata?.tool_calls?.length > 0
                                ? raw.metadata.tool_calls
                                : null;

                            const hasReasoning = (raw as any).reasoning;

                            return (
                              <div key={key} className="group">
                                <Message
                                  id={key}
                                  role={msg.role}
                                  content={msg.content}
                                  name={msg.name}
                                  avatar={msg.avatar}
                                  timestamp={msg.timestamp}
                                  isLoading={msg.isLoading}
                                  avatarProps={msg.avatarProps}
                                  actions={actions}
                                  hasRoundAvatar
                                >
                                  {hasReasoning && (
                                    <details className="mb-2 text-xs">
                                      <summary className="flex cursor-pointer items-center gap-1 text-muted-foreground">
                                        💭 <span className="underline">Show reasoning</span>
                                      </summary>
                                      <div className="mt-1 rounded bg-muted p-2 text-[11px] whitespace-pre-wrap">
                                        {(raw as any).reasoning}
                                      </div>
                                    </details>
                                  )}
                                </Message>

                                {toolCalls && (
                                  <div className="ml-12 mt-1 space-y-1">
                                    {toolCalls.map((tc: any, tIdx: number) => (
                                      <ToolOutput
                                        key={tc.id || tIdx}
                                        toolCall={tc}
                                        projectId={project.id}
                                        projectTools={allTools}
                                      />
                                    ))}
                                  </div>
                                )}

                                {msg.role === 'user' && (
                                  <div className="ml-12 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button
                                      variant="link"
                                      size="sm"
                                      onClick={() => onSetEditingMessageId(raw.id || key)}
                                      className="text-xs"
                                    >
                                      Edit
                                    </Button>
                                  </div>
                                )}

                                {idx === pfMessages.length - 1 && <div ref={messagesEndRef} />}
                              </div>
                            );
                          })}
                      </MessageBox>
                    </ChatbotContent>
                  </div>
                </div>

                <ChatbotFooter>
                  {(selectedPersona || selectedToolIds.length > 0 || activeAdvancedModeLabel) && (
                    <Flex gap={{ default: 'gapSm' }} className="px-4 pb-2">
                      {selectedPersona && (
                        <PFLabel color="green" icon={<Sparkles className="h-3 w-3" />}>
                          {selectedPersona.name}
                        </PFLabel>
                      )}
                      {activeAdvancedModeLabel && (
                        <PFLabel color="orange">{activeAdvancedModeLabel} mode</PFLabel>
                      )}
                      {allTools
                        .filter((t) => selectedToolIds.includes(t.id))
                        .slice(0, 2)
                        .map((tool) => (
                          <PFLabel key={tool.id} color="blue" icon={<Wrench className="h-3 w-3" />}>
                            {tool.name}
                          </PFLabel>
                        ))}
                      {selectedToolIds.length > 2 && (
                        <PFLabel color="grey">+{selectedToolIds.length - 2} more</PFLabel>
                      )}
                    </Flex>
                  )}

                  <div className="px-4 pb-2">
                    <div className="rounded-xl border border-border/80 bg-background/95 p-2.5 shadow-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <ModeToggleGroup
                          type="single"
                          value={primaryChatMode}
                          aria-label="Primary chat modes"
                          variant="pill"
                          size="pill"
                          className="rounded-full bg-muted/70 p-0.5"
                        >
                          {PRIMARY_CHAT_MODES.map((mode) => (
                            <ModeToggleGroupItem
                              key={mode.value}
                              value={mode.value}
                              aria-label={mode.label}
                              onClick={() => onChatModeChange(mode.value)}
                              title={mode.description}
                            >
                              {mode.label}
                            </ModeToggleGroupItem>
                          ))}
                        </ModeToggleGroup>
                        <div className="ml-auto flex items-center gap-2">
                            <Button
                              variant="plainText"
                              size="sm"
                              onClick={() => openUtilityDialog('summary')}
                              className="h-8 rounded-full border border-input bg-muted/70 px-3 text-xs font-medium text-foreground hover:bg-background"
                            >
                              Utilities
                            </Button>
                            <Button
                              variant="plainText"
                              size="sm"
                              onClick={() => onModelSelectOpenChange(true)}
                              className="max-w-[14rem] h-8 rounded-full border border-input bg-muted/70 px-3 text-xs font-medium text-foreground hover:bg-background"
                            >
                              <span className="truncate">{selectedModelLabel}</span>
                            </Button>
                          <Dropdown
                            isOpen={isMoreMenuOpen}
                            onSelect={() => setIsMoreMenuOpen(false)}
                            toggle={(toggleRef) => (
                              <MenuToggle
                                ref={toggleRef}
                                isExpanded={isMoreMenuOpen}
                                onClick={() => setIsMoreMenuOpen((prev) => !prev)}
                                variant="plainText"
                                size="sm"
                                className="h-8 rounded-full border border-input bg-muted/70 px-3 text-xs font-medium text-foreground hover:bg-background"
                              >
                                More
                              </MenuToggle>
                            )}
                            popperProps={{ position: 'end' }}
                          >
                            <DropdownList>
                              <DropdownItem onClick={() => setIsPersonaDialogOpen(true)}>
                                {selectedPersona ? `Persona: ${selectedPersona.name}` : 'Choose persona'}
                              </DropdownItem>
                              {selectedPersona && (
                                <DropdownItem onClick={() => handlePersonaChoice(null)}>
                                  Clear persona
                                </DropdownItem>
                              )}
                              <DropdownItem onClick={() => onChatModeChange('deep')}>
                                Deep reasoning
                              </DropdownItem>
                            </DropdownList>
                          </Dropdown>
                        </div>
                      </div>

                      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                        <span>{activeModeDescription}</span>
                        {isStreaming && <span className="font-medium text-[var(--pf-v6-global--primary-color--100,#0066cc)]">AI is thinking…</span>}
                      </div>

                      {(openFiles.length > 0 || contextFiles.length > 0) && (
                        <div className="mt-2">
                          <FileContextSelector
                            openFiles={openFiles}
                            selectedContext={contextFiles}
                            onContextChange={onContextChange}
                          />
                        </div>
                      )}

                      <div className="mt-2 flex items-center gap-1.5 px-1">
                        <div className="flex-1">
                          <MessageBar
                            onSendMessage={handlePFSend}
                            hasMicrophoneButton
                            hasStopButton={isStreaming}
                            handleStopButton={onStopStreaming ? () => onStopStreaming() : undefined}
                            isSendButtonDisabled={isLoading}
                            placeholder="Ask about your code…"
                          />
                        </div>
                        <Button
                          variant="plain"
                          size="sm"
                          icon={<Wrench size={16} />}
                          aria-label="Tool selector"
                          onClick={() => onToolSelectorDialogOpenChange(true)}
                        />
                        <Button
                          variant="plain"
                          size="sm"
                          icon={<Settings size={16} />}
                          aria-label="Chat settings"
                          onClick={() => onSettingsOpenChange(true)}
                        />
                      </div>
                    </div>
                  </div>
                  <ChatbotFootnote
                    label="AI may make mistakes. Verify important information."
                  />
                </ChatbotFooter>
              </div>

              <Dialog open={isUtilityDialogOpen} onOpenChange={setIsUtilityDialogOpen}>
                <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden">
                  <DialogHeader>
                    <DialogTitle>Workspace notes</DialogTitle>
                    <DialogDescription>Review the working summary, saved memory, and agent task list without leaving the conversation.</DialogDescription>
                  </DialogHeader>
                  <Tabs activeKey={activeUtilityTab} onSelect={(_e, key) => setActiveUtilityTab(String(key) as UtilityDialogTab)}>
                    <Tab eventKey="summary" title={<TabTitleText>Summary</TabTitleText>}>
                      <div className="space-y-4 mt-4 max-h-[55vh] overflow-y-auto pr-1">
                        <Card>
                          <CardBody>
                            <CardTitle>Chat Summary</CardTitle>
                            <TextArea
                              value={chatSummary}
                              onChange={(_, value) => onSummaryChange(value)}
                              placeholder="Capture the current direction and decisions from this session."
                              resizeOrientation="vertical"
                              className="min-h-32"
                            />
                            <Flex className="mt-3" gap={{ default: 'gapSm' }}>
                              <Button variant="secondary" onClick={onRegenerateSummary} isDisabled={!currentSessionId}>
                                Regenerate Summary
                              </Button>
                            </Flex>
                          </CardBody>
                        </Card>
                      </div>
                    </Tab>
                    <Tab eventKey="memory" title={<TabTitleText>Memory</TabTitleText>}>
                      <div className="space-y-4 mt-4 max-h-[55vh] overflow-y-auto pr-1">
                        <Card>
                          <CardBody>
                            <CardTitle>Session Memory</CardTitle>
                            <p className="text-sm text-muted-foreground mb-4">
                              Store useful context and constraints for this conversation.
                            </p>
                            {memoryItems.length > 0 ? (
                              <div className="space-y-3">
                                {memoryItems.map((item, idx) => (
                                  <Flex key={idx} gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsFlexStart' }}>
                                    <TextArea
                                      value={item}
                                      onChange={(_, value) => onEditMemory(idx, value)}
                                      placeholder="Edit memory item…"
                                      resizeOrientation="vertical"
                                      className="flex-1 min-h-16 text-sm"
                                    />
                                    <Button
                                      variant="plain"
                                      icon={<TrashIcon />}
                                      onClick={() => onDeleteMemory(idx)}
                                      aria-label="Delete memory item"
                                    />
                                  </Flex>
                                ))}
                              </div>
                            ) : (
                              <div className="py-8 text-center text-muted-foreground">
                                <p>No memory items yet.</p>
                                <p className="text-xs mt-1">Add memory to preserve useful context for later turns.</p>
                              </div>
                            )}
                            <Flex className="mt-4" gap={{ default: 'gapSm' }}>
                              <Button variant="secondary" onClick={onAddMemory}>
                                Add Memory Item
                              </Button>
                              {memoryItems.length > 0 && (
                                <Button variant="plain" onClick={onClearAllMemory} className="text-red-600 hover:text-red-700">
                                  Clear All
                                </Button>
                              )}
                            </Flex>
                          </CardBody>
                        </Card>
                      </div>
                    </Tab>
                    <Tab eventKey="agent-todos" title={<TabTitleText>Tasks</TabTitleText>}>
                      <div className="space-y-4 mt-4 max-h-[55vh] overflow-y-auto pr-1">
                        <Card>
                          <CardBody>
                            <CardTitle>Agent Tasks</CardTitle>
                            {agentTodos.length > 0 ? (
                              <div className="space-y-3">
                                {agentTodos.map((task, idx) => (
                                  <Flex key={idx} gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                                    <div className="flex-1">
                                      <Flex gap={{ default: 'gapSm' }} alignItems={{ default: 'alignItemsCenter' }}>
                                        {task.status === 'pending' && <Clock className="w-4 h-4 text-yellow-500" />}
                                        {task.status === 'in_progress' && <Spinner size="sm" />}
                                        {task.status === 'completed' && <CheckCircle className="w-4 h-4 text-green-500" />}
                                        {task.status === 'failed' && <AlertTriangle className="w-4 h-4 text-red-500" />}
                                        <span className="flex-1">{typeof task.description === 'string' ? task.description : String(task.description)}</span>
                                      </Flex>
                                      {task.details && (
                                        <span className="text-sm text-muted-foreground mt-1 ml-6">
                                          {typeof task.details === 'string' ? task.details : JSON.stringify(task.details)}
                                        </span>
                                      )}
                                    </div>
                                  </Flex>
                                ))}
                              </div>
                            ) : (
                              <p className="text-muted-foreground">No agent tasks yet.</p>
                            )}
                          </CardBody>
                        </Card>
                      </div>
                    </Tab>
                  </Tabs>
                </DialogContent>
              </Dialog>

              <Dialog open={isPersonaDialogOpen} onOpenChange={setIsPersonaDialogOpen}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Choose a persona</DialogTitle>
                    <DialogDescription>Select a persona to shape how the assistant responds in persona mode.</DialogDescription>
                  </DialogHeader>
                  <div className="grid gap-3 py-2">
                    {personas.length > 0 ? (
                      personas.map((persona) => (
                        <button
                          key={persona.id}
                          type="button"
                          onClick={() => handlePersonaChoice(persona.id)}
                          className={`rounded-lg border p-3 text-left transition-colors ${
                            selectedPersonaId === persona.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium text-foreground">{persona.name}</p>
                              {persona.description && (
                                <p className="mt-1 text-sm text-muted-foreground">{persona.description}</p>
                              )}
                            </div>
                            {selectedPersonaId === persona.id && <PFLabel color="green">Active</PFLabel>}
                          </div>
                        </button>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No personas are available for this workspace yet.</p>
                    )}
                  </div>
                  <Flex justifyContent={{ default: 'justifyContentSpaceBetween' }}>
                    <Button variant="secondary" onClick={() => handlePersonaChoice(null)}>
                      Clear persona
                    </Button>
                    <Button variant="link" onClick={() => setIsPersonaDialogOpen(false)}>
                      Close
                    </Button>
                  </Flex>
                </DialogContent>
              </Dialog>

              <Dialog open={isSettingsOpen} onOpenChange={onSettingsOpenChange}>
                <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>AI Chat Settings</DialogTitle>
                    <DialogDescription>Configure AI model parameters for this chat session</DialogDescription>
                  </DialogHeader>
                  <Tabs defaultActiveKey="model" className="w-full">
                    <Tab eventKey="model" title={<TabTitleText>AI Model</TabTitleText>}>
                      <div className="space-y-4 mt-4">
                        <div>
                          <FieldLabel>AI Model</FieldLabel>
                          <div className="mt-2">
                            <Button
                              variant="outline"
                              className="w-full justify-start text-left font-normal"
                              onClick={() => onModelSelectOpenChange(true)}
                            >
                              {selectedModelLabel}
                            </Button>
                          </div>
                          <p className="mt-2 text-xs text-muted-foreground">
                            Search across all available providers from the model picker.
                          </p>
                        </div>
                        <div>
                          <div className="flex justify-between mb-2">
                            <FieldLabel>Temperature: {temperature}</FieldLabel>
                          </div>
                          <Slider
                            value={[temperature]}
                            onValueChange={(value) => onTemperatureChange(value[0])}
                            min={0}
                            max={2}
                            step={0.1}
                            className="mt-2"
                          />
                        </div>
                        <div>
                          <div className="flex justify-between mb-2">
                            <FieldLabel>Max Tokens{maxTokens ? `: ${maxTokens}` : ' (unlimited)'}</FieldLabel>
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <input
                              type="number"
                              min={0}
                              step={100}
                              value={maxTokens}
                              onChange={(e) => onMaxTokensChange(Math.max(0, Number(e.target.value)))}
                              className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm"
                              placeholder="0 = unlimited"
                            />
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">Set to 0 for unlimited (model default).</p>
                        </div>
                      </div>
                    </Tab>
                    <Tab eventKey="advanced" title={<TabTitleText>Advanced Settings</TabTitleText>}>
                      <div className="space-y-4 mt-4">
                        <p className="text-sm text-muted-foreground">Advanced settings coming soon…</p>
                      </div>
                    </Tab>
                  </Tabs>
                </DialogContent>
              </Dialog>

              <ModelSelectorDialog
                isOpen={isModelSelectOpen}
                onOpenChange={onModelSelectOpenChange}
                selectedModelId={selectedLLM}
                defaultModelLabel={getModelLabel(null)}
                models={llmOptions}
                onSelectModel={onSelectedLLMChange}
              />

              <AnalysisStreamModal
                isOpen={isAnalysisModalOpen}
                onOpenChange={onAnalysisModalOpenChange}
                chunks={analysisChunks}
                final={analysisFinal}
                onCreateChangeRequest={onCreateChangeRequest as (summary: string) => Promise<void>}
              />
            </div>
          }
        />

            {/* ── Dialogs & modals (rendered outside tabs) ──── */}
              <ToolSelector
                projectId={project.id}
                sessionId={currentSessionId ?? undefined}
                tools={allTools}
                selectedToolIds={selectedToolIds}
                onToolsChange={onToolsChange}
                selectedPersona={selectedPersona}
                chatMode={chatMode}
                isOpen={isToolSelectorDialogOpen}
                onOpenChange={onToolSelectorDialogOpenChange}
              />
      </Chatbot>



      {/* Scoped styles for the embedded chatbot */}
      <style>{`
        .pf-chatbot-container { overflow: hidden !important; }

        .pf-chatbot--embedded-fill {
          height: 100% !important;
          max-height: 100% !important;
          min-height: 0 !important;
          width: 100% !important;
          overflow: hidden !important;
          border-radius: var(--pf-t--global--border-radius--medium, 8px);
          box-shadow: none;
        }
        .pf-chatbot--embedded-fill > section {
          display: flex !important;
          flex-direction: column !important;
          flex: 1 !important;
          min-height: 0 !important;
          height: 100% !important;
          overflow: hidden !important;
        }

        .pf-chatbot--embedded-fill .pf-v6-c-drawer {
          height: 100% !important;
          overflow: hidden !important;
        }

        /* Drawer panel (conversation history sidebar) */
        .pf-chatbot--embedded-fill .pf-v6-c-drawer__panel {
          width: 280px !important;
          max-width: 30vw !important;
          flex-shrink: 0 !important;
          overflow: hidden !important;
          display: flex !important;
          flex-direction: column !important;
        }
        .pf-chatbot--embedded-fill .pf-v6-c-drawer__panel-main {
          height: 100% !important;
          overflow: hidden !important;
          display: flex !important;
          flex-direction: column !important;
        }
        .pf-chatbot--embedded-fill .pf-v6-c-drawer__panel .pf-v6-c-drawer__body {
          overflow-y: auto !important;
        }
        .pf-chatbot--embedded-fill [class*="chatbot-conversation-history"] {
          flex: 1 !important;
          min-height: 0 !important;
          overflow-y: auto !important;
        }

        /* Drawer layout wrapper */
        .pf-chatbot-drawer-layout {
          display: flex !important;
          flex-direction: column !important;
          flex: 1 !important;
          min-height: 0 !important;
          height: 100% !important;
          overflow: hidden !important;
        }

        /* Active tab content must fill space for relative+absolute children */
        .pf-chatbot-drawer-layout .pf-v6-c-tab-content:not([hidden]) {
          display: flex !important;
          flex-direction: column !important;
          flex: 1 !important;
          min-height: 0 !important;
          overflow: hidden !important;
        }

        /* Header / footer pinned */
        .pf-chatbot__header-container,
        .pf-chatbot-drawer-layout > .pf-chatbot__header-container {
          flex: 0 0 auto !important;
        }
        .pf-chatbot__footer,
        .pf-chatbot-drawer-layout > .pf-chatbot__footer {
          flex: 0 0 auto !important;
        }
      `}</style>
    </div>
  );
};

export default ChatPanel;
