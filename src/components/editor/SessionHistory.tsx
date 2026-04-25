import { useState, useEffect } from 'react';
import { Card, CardBody, CardHeader } from '@patternfly/react-core';
import { Loader2, MessageSquare, Trash2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@patternfly/react-core/dist/js/components/Button/Button';
import { ChatSession } from '@/lib/api';

interface SessionHistoryProps {
  projectId: number;
  currentSessionId: number | null;
  onSelectSession: (sessionId: number) => void;
  sessions: ChatSession[];
  isLoading?: boolean;
  onDeleteSession?: (sessionId: number) => Promise<void>;
}

export function SessionHistory({
  projectId,
  currentSessionId,
  onSelectSession,
  sessions,
  isLoading = false,
  onDeleteSession,
}: SessionHistoryProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const handleDelete = async (e: React.MouseEvent, sessionId: number) => {
    e.stopPropagation();
    if (onDeleteSession) {
      try {
        await onDeleteSession(sessionId);
      } catch (error) {
        console.error('Failed to delete session:', error);
      }
    }
  };

  const sortedSessions = [...sessions].sort((a, b) => {
    const dateA = new Date(a.created_at || 0).getTime();
    const dateB = new Date(b.created_at || 0).getTime();
    return dateB - dateA;
  });

  return (
    <Card isFlat className="w-full h-full flex flex-col">
      <CardHeader className="flex-shrink-0 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">Chat History</h3>
          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
            {sessions.length}
          </span>
        </div>
      </CardHeader>

      <CardBody className="flex-1 min-h-0 p-0">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 p-4">
            <MessageSquare className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-sm">No previous sessions</p>
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="space-y-1 p-2">
              {sortedSessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-colors border-l-2 group ${
                    currentSessionId === session.id
                      ? 'bg-blue-50 border-l-blue-500 border border-blue-200'
                      : 'hover:bg-gray-50 border-l-gray-300 border border-gray-200'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium text-gray-900 truncate line-clamp-1">
                        {session.title || 'Untitled Session'}
                      </h4>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-gray-500">
                          {formatDate(session.created_at || '')}
                        </span>
                        {/* Placeholder for message count if available */}
                        {session.message_count !== undefined && (
                          <span className="text-xs text-gray-400">
                            {session.message_count} msg{session.message_count !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    </div>
                    {onDeleteSession && (
                      <button
                        type="button"
                        onClick={(e) => handleDelete(e, session.id)}
                        className="p-1 opacity-0 group-hover:opacity-100 transition-opacity hover:text-red-600 text-gray-400 flex-shrink-0"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardBody>
    </Card>
  );
}
