import { useState } from 'react';
import { Button, Badge, Card, CardBody, CardTitle, TextInput } from '@patternfly/react-core';
import { Clock, Trash2, MessageSquare, Loader2, User, Briefcase, Code, Heart, Lightbulb, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getChatSessions, deleteChatSession, ChatSession } from '@/lib/api';
import { toast } from '@/hooks/use-toast';

const getIconComponent = (iconName: string) => {
  switch (iconName) {
    case 'User': return User;
    case 'Briefcase': return Briefcase;
    case 'Code': return Code;
    case 'Heart': return Heart;
    case 'Lightbulb': return Lightbulb;
    default: return MessageSquare;
  }
};

interface ChatHistoryProps {
  selectedSession: string | null;
  onSessionSelect: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewChat: () => void;
  personasData?: any[];
}

export const ChatHistory = ({ 
  selectedSession, 
  onSessionSelect, 
  onDeleteSession,
  onNewChat,
  personasData = []
}: ChatHistoryProps) => {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");

  const { data: sessions, isLoading, error } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => getChatSessions(),
    select: (response) => response.data,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteChatSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat-sessions'] });
      toast({
        title: 'Session Deleted',
        description: 'Chat session has been removed successfully.',
        variant: 'destructive',
      });
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to delete session. Please try again.',
        variant: 'destructive',
      });
    },
  });

  const formatTimestamp = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) {
      return `${diffMins} min${diffMins !== 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
    } else if (diffDays < 7) {
      return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  const handleDeleteSession = (sessionId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteMutation.mutate(sessionId);
    onDeleteSession(sessionId.toString());
  };

  if (error) {
    toast({
      title: "Error loading sessions",
      description: "Failed to load chat sessions. Please try again.",
      variant: "destructive",
    });
  }

  const filteredSessions = sessions?.filter((session) => {
    const query = searchQuery.toLowerCase();
    return (
      (session.subject || session.title || '').toLowerCase().includes(query) ||
      (session.last_message_preview || '').toLowerCase().includes(query) ||
      (session.persona_name || '').toLowerCase().includes(query)
    );
  }) || [];

  const content = sessions && sessions.length > 0 ? (
    filteredSessions.length > 0 ? (
      <div className="space-y-2">
        {filteredSessions.map((session) => (
          <Card
            key={session.id}
            onClick={() => onSessionSelect(session.id.toString())}
            className={cn(
              "cursor-pointer transition-all hover:border-primary hover:bg-muted/50",
              selectedSession === session.id.toString() && "border-primary bg-muted"
            )}
            style={{ border: '1px solid var(--pf-v6-global--BorderColor--100)' }}
          >
            <CardBody className="p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {(() => {
                      let IconComponent = MessageSquare;
                      if (session.started_by_persona && session.persona) {
                        const persona = personasData.find((p: any) => p.id.toString() === session.persona.toString());
                        if (persona) {
                          IconComponent = getIconComponent(persona.icon);
                        }
                      }
                      return <IconComponent size={14} className="text-muted-foreground" />;
                    })()}
                    <CardTitle 
                      className="pf-u-text-truncate text-sm font-medium flex-1" 
                      title={session.subject || session.title}
                    >
                      {session.subject || session.title}
                    </CardTitle>
                    <Badge className="text-xs border">
                      {session.message_count} messages
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2 mb-2">
                    {session.last_message_preview || 'No messages yet'}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock size={12} />
                    <span>{formatTimestamp(session.updated_at)}</span>
                    {session.persona_name && (
                      <>
                        <span>•</span>
                        <span>{session.persona_name}</span>
                      </>
                    )}
                  </div>
                </div>
                <Button
                  variant="plain"
                  size="sm"
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>
    ) : (
      <div className="text-center py-8">
        <Search className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">No sessions match your search</p>
        <p className="text-xs text-muted-foreground mt-1">Try adjusting your search terms</p>
      </div>
    )
  ) : (
    <div className="text-center py-8">
      <MessageSquare className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
      <p className="text-sm text-muted-foreground">No chat sessions yet</p>
      <p className="text-xs text-muted-foreground mt-1">Start a new conversation to see it here</p>
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-4 py-3 border-b flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold">Chat History</h3>
          <Button size="sm" variant="secondary" onClick={onNewChat}>
            <MessageSquare size={14} className="mr-1" />
            New Chat
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Your previous conversations
        </p>
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <TextInput
            placeholder="Search sessions..."
            value={searchQuery}
            onChange={(_event, value) => setSearchQuery(value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Session list — relative+absolute scroll containment */}
      <div className="flex-1 min-h-0 relative">
        <div className="absolute inset-0 overflow-y-auto overscroll-contain">
          <div className="p-4">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="ml-2 text-sm text-muted-foreground">Loading sessions...</span>
              </div>
            ) : (
              content
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
