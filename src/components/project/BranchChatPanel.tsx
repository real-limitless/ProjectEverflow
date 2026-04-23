import { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@patternfly/react-core';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  GitBranch,
  MessageSquare,
  Send,
  Bot,
  User,
  Users,
  X,
  AtSign,
  Paperclip,
  Hash,
  ChevronDown,
  Circle,
} from 'lucide-react';
import { getGitBranches } from '@/lib/api';

// ─── Types ───────────────────────────────────────────────────────────
interface ChatUser {
  id: string;
  name: string;
  avatar?: string;
  isBot?: boolean;
  isOnline?: boolean;
}

interface BranchMessage {
  id: string;
  userId: string;
  content: string;
  timestamp: Date;
  branch: string;
  replyTo?: string;
  mentions?: string[];
  attachments?: { name: string; url: string }[];
}

interface BranchChatPanelProps {
  projectId: number;
  projectName: string;
  isOpen: boolean;
  onClose: () => void;
}

// ─── Mock Data ───────────────────────────────────────────────────────
const MOCK_USERS: ChatUser[] = [
  { id: 'u1', name: 'You', isOnline: true },
  { id: 'u2', name: 'Alice Chen', isOnline: true },
  { id: 'u3', name: 'Marcus Rivera', isOnline: false },
  { id: 'u4', name: 'Priya Sharma', isOnline: true },
  { id: 'bot', name: 'Copilot', isBot: true, isOnline: true },
];

const generateMockMessages = (branch: string): BranchMessage[] => {
  const base: BranchMessage[] = [
    {
      id: 'm1',
      userId: 'u2',
      content: `Hey team, I just pushed the initial changes to \`${branch}\`. Can someone review the auth middleware?`,
      timestamp: new Date(Date.now() - 3600000 * 2),
      branch,
    },
    {
      id: 'm2',
      userId: 'u4',
      content: "On it! I'll take a look at the middleware. Also @Copilot can you summarize the recent changes?",
      timestamp: new Date(Date.now() - 3600000 * 1.5),
      branch,
      mentions: ['bot'],
    },
    {
      id: 'm3',
      userId: 'bot',
      content:
        "Here's a summary of the recent changes on this branch:\n\n• **3 files modified** — `auth.ts`, `middleware.ts`, `routes.ts`\n• Added JWT token validation with refresh support\n• New error handling middleware for 401/403 responses\n• Updated route guards for protected endpoints\n\nThe changes look structurally sound. I'd recommend adding unit tests for the token refresh logic.",
      timestamp: new Date(Date.now() - 3600000 * 1.4),
      branch,
    },
    {
      id: 'm4',
      userId: 'u3',
      content: 'Good catch on the tests. I can write those tomorrow. Any blockers from your side, Alice?',
      timestamp: new Date(Date.now() - 3600000),
      branch,
    },
    {
      id: 'm5',
      userId: 'u2',
      content: "No blockers! Once the tests are in, we can open a PR to merge into main. Let's try to get it done by EOD Thursday.",
      timestamp: new Date(Date.now() - 1800000),
      branch,
    },
  ];
  return base;
};

// ─── Component ───────────────────────────────────────────────────────
export const BranchChatPanel: React.FC<BranchChatPanelProps> = ({
  projectId,
  projectName,
  isOpen,
  onClose,
}) => {
  const [inputValue, setInputValue] = useState('');
  const [selectedBranch, setSelectedBranch] = useState<string>('');
  const [messages, setMessages] = useState<BranchMessage[]>([]);
  const [showMembers, setShowMembers] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch branches
  const { data: branchesData } = useQuery({
    queryKey: ['git-branches', projectId],
    queryFn: () => getGitBranches(projectId),
    refetchInterval: 30000,
  });

  const branches = useMemo(() => branchesData?.data?.branches ?? [], [branchesData]);
  const currentBranch = branchesData?.data?.currentBranch ?? 'main';

  // Auto-select current branch
  useEffect(() => {
    if (!selectedBranch && currentBranch) {
      setSelectedBranch(currentBranch);
    }
  }, [currentBranch, selectedBranch]);

  // Load messages for selected branch
  useEffect(() => {
    if (selectedBranch) {
      setMessages(generateMockMessages(selectedBranch));
    }
  }, [selectedBranch]);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!inputValue.trim()) return;

    const newMsg: BranchMessage = {
      id: `m-${Date.now()}`,
      userId: 'u1',
      content: inputValue,
      timestamp: new Date(),
      branch: selectedBranch,
    };

    setMessages((prev) => [...prev, newMsg]);
    setInputValue('');

    // Simulate bot response if @Copilot is mentioned
    if (inputValue.toLowerCase().includes('@copilot')) {
      setTimeout(() => {
        const botReply: BranchMessage = {
          id: `m-${Date.now() + 1}`,
          userId: 'bot',
          content:
            "I'm here to help! Based on the current branch state, everything looks good. Let me know if you need a code review, diff summary, or help resolving merge conflicts.",
          timestamp: new Date(),
          branch: selectedBranch,
        };
        setMessages((prev) => [...prev, botReply]);
      }, 1200);
    }
  };

  const getUserById = (id: string) => MOCK_USERS.find((u) => u.id === id);

  const formatTime = (date: Date) =>
    date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const onlineCount = MOCK_USERS.filter((u) => u.isOnline).length;
  const localBranches = branches.filter((b) => !b.isRemote);

  if (!isOpen) return null;

  return (
    <div className="flex flex-col h-full border-l border-border bg-background" style={{ width: 360 }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2 min-w-0">
          <MessageSquare className="h-4 w-4 text-primary shrink-0" />
          <span className="text-sm font-semibold truncate">Branch Chat</span>
          <Badge variant="secondary" className="text-xs shrink-0">
            {onlineCount} online
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowMembers(!showMembers)}
            className="p-1 rounded hover:bg-muted"
            title="Show members"
          >
            <Users className="h-4 w-4 text-muted-foreground" />
          </button>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted" title="Close chat">
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Branch Selector */}
      <div className="px-3 py-2 border-b border-border">
        <Select value={selectedBranch} onValueChange={setSelectedBranch}>
          <SelectTrigger className="h-8 text-xs">
            <div className="flex items-center gap-1.5">
              <GitBranch className="h-3 w-3" />
              <SelectValue placeholder="Select branch..." />
            </div>
          </SelectTrigger>
          <SelectContent>
            {localBranches.length > 0 ? (
              localBranches.map((b) => (
                <SelectItem key={b.fullName} value={b.name}>
                  <div className="flex items-center gap-2">
                    <Hash className="h-3 w-3 text-muted-foreground" />
                    <span>{b.name}</span>
                    {b.isCurrent && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        current
                      </Badge>
                    )}
                  </div>
                </SelectItem>
              ))
            ) : (
              <>
                <SelectItem value="main">main</SelectItem>
                <SelectItem value="develop">develop</SelectItem>
                <SelectItem value="feature/auth">feature/auth</SelectItem>
              </>
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Members panel (collapsible) */}
      {showMembers && (
        <div className="px-3 py-2 border-b border-border bg-muted/20">
          <p className="text-xs font-semibold text-muted-foreground mb-1.5">
            Members on <code className="text-primary">{selectedBranch}</code>
          </p>
          <div className="space-y-1">
            {MOCK_USERS.map((user) => (
              <div key={user.id} className="flex items-center gap-2 text-xs py-0.5">
                <Circle
                  className={`h-2 w-2 shrink-0 ${
                    user.isOnline ? 'fill-green-500 text-green-500' : 'fill-gray-300 text-gray-300'
                  }`}
                />
                {user.isBot ? (
                  <Bot className="h-3 w-3 text-primary shrink-0" />
                ) : (
                  <User className="h-3 w-3 text-muted-foreground shrink-0" />
                )}
                <span className={user.isBot ? 'text-primary font-medium' : ''}>
                  {user.name}
                </span>
                {user.isBot && (
                  <Badge variant="outline" className="text-[10px] px-1 py-0">
                    AI
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-3 py-2 space-y-3">
          {/* Branch channel header */}
          <div className="text-center py-4">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-muted text-xs text-muted-foreground">
              <Hash className="h-3 w-3" />
              <span className="font-medium">{selectedBranch}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              This is the start of the conversation for this branch.
            </p>
          </div>

          {messages.map((msg) => {
            const user = getUserById(msg.userId);
            const isOwn = msg.userId === 'u1';
            const isBot = user?.isBot;

            return (
              <div key={msg.id} className={`flex gap-2 ${isOwn ? 'flex-row-reverse' : ''}`}>
                {/* Avatar */}
                <div
                  className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
                    isBot
                      ? 'bg-primary/10 text-primary'
                      : isOwn
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {isBot ? (
                    <Bot className="h-3.5 w-3.5" />
                  ) : (
                    user?.name?.charAt(0).toUpperCase() ?? '?'
                  )}
                </div>

                {/* Bubble */}
                <div className={`max-w-[75%] min-w-0 ${isOwn ? 'text-right' : ''}`}>
                  <div className="flex items-baseline gap-1.5 mb-0.5">
                    {!isOwn && (
                      <span
                        className={`text-xs font-semibold ${
                          isBot ? 'text-primary' : 'text-foreground'
                        }`}
                      >
                        {user?.name}
                      </span>
                    )}
                    <span className="text-[10px] text-muted-foreground">
                      {formatTime(msg.timestamp)}
                    </span>
                  </div>
                  <div
                    className={`rounded-lg px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                      isOwn
                        ? 'bg-primary text-primary-foreground'
                        : isBot
                        ? 'bg-primary/5 border border-primary/20'
                        : 'bg-muted'
                    }`}
                  >
                    {msg.content.split(/(`[^`]+`|\*\*[^*]+\*\*|•)/).map((part, i) => {
                      if (part.startsWith('`') && part.endsWith('`')) {
                        return (
                          <code
                            key={i}
                            className="px-1 py-0.5 rounded bg-muted/50 text-primary text-[11px] font-mono"
                          >
                            {part.slice(1, -1)}
                          </code>
                        );
                      }
                      if (part.startsWith('**') && part.endsWith('**')) {
                        return (
                          <strong key={i} className="font-semibold">
                            {part.slice(2, -2)}
                          </strong>
                        );
                      }
                      if (part === '•') {
                        return (
                          <span key={i} className="text-primary">
                            •
                          </span>
                        );
                      }
                      return <span key={i}>{part}</span>;
                    })}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="px-3 py-2 border-t border-border bg-background">
        <div className="flex items-center gap-1.5">
          <button className="p-1.5 rounded hover:bg-muted shrink-0" title="Mention @Copilot">
            <AtSign className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          <button className="p-1.5 rounded hover:bg-muted shrink-0" title="Attach file">
            <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={`Message #${selectedBranch}...`}
            className="h-8 text-xs flex-1"
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim()}
            className="p-1.5 rounded hover:bg-muted shrink-0 disabled:opacity-40"
            title="Send"
          >
            <Send className="h-3.5 w-3.5 text-primary" />
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-1 text-center">
          Type <code className="text-primary">@Copilot</code> to ask the AI assistant
        </p>
      </div>
    </div>
  );
};
