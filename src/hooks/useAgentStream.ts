import { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '@/lib/api';

// ── Event Types ────────────────────────────────────────────────────

export interface AgentTextChunkEvent {
  type: 'text_chunk';
  content: string;
  node?: string;
}

export interface AgentToolStartEvent {
  type: 'tool_start';
  name: string;
  args: Record<string, any> | string;
  run_id?: string;
  id?: string;
}

export interface AgentToolResultEvent {
  type: 'tool_result';
  name: string;
  output: string;
  duration?: number;
  run_id?: string;
}

export interface AgentWorkerStartEvent {
  type: 'worker_start';
  worker: string;
}

export interface AgentWorkerEndEvent {
  type: 'worker_end';
  worker: string;
  content?: string;
}

export interface AgentTodosUpdateEvent {
  type: 'todos_update';
  todos: Array<{ title: string; status: string }>;
}

export interface AgentCompleteEvent {
  type: 'complete';
  content: string;
  tool_calls: Array<{ name: string; output?: string; args?: Record<string, any>; duration?: number }>;
  reasoning?: string;
  elapsed_seconds: number;
}

export interface AgentErrorEvent {
  type: 'error';
  message: string;
}

export interface AgentConnectedEvent {
  type: 'connected';
  session_id: number;
  mode?: string;
  user?: string;
}

export type AgentStreamEvent =
  | AgentTextChunkEvent
  | AgentToolStartEvent
  | AgentToolResultEvent
  | AgentWorkerStartEvent
  | AgentWorkerEndEvent
  | AgentTodosUpdateEvent
  | AgentCompleteEvent
  | AgentErrorEvent
  | AgentConnectedEvent;

export type AgentStreamStatus = 'no-session' | 'connecting' | 'connected' | 'disconnected';

// ── Hook ───────────────────────────────────────────────────────────

/**
 * Bidirectional WebSocket hook for the unified agent consumer.
 *
 * Connects to: /api/projects/{projectId}/chat-sessions/{sessionId}/agent-stream?token=...
 *
 * Returns:
 *  - status: connection status
 *  - sendMessage(content, contextFiles?): send a user message to the agent
 *  - cancel(): cancel a running agent
 */
export const useAgentStream = (
  projectId: number | null,
  sessionId: number | null,
  onEvent?: (ev: AgentStreamEvent) => void,
) => {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<AgentStreamStatus>('no-session');
  const reconnectAttempts = useRef(0);
  const maxReconnects = 3;

  // Stable ref for the callback
  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    if (!projectId || !sessionId) {
      try { wsRef.current?.close(); } catch { /* noop */ }
      wsRef.current = null;
      setStatus('no-session');
      reconnectAttempts.current = 0;
      return;
    }

    // Build WS URL — pointing to the NEW unified consumer route
    const apiBase = (typeof API_BASE_URL === 'string' && API_BASE_URL) ? API_BASE_URL : (window.location.origin + '/api');
    const apiHost = apiBase.replace(/^https?:\/\//, '').replace(/\/api\/?$/, '');
    const protocol = apiBase.startsWith('https') ? 'wss' : 'ws';
    const base = `${protocol}://${apiHost}/api/projects/${projectId}/chat-sessions/${sessionId}/agent-stream`;
    const token = localStorage.getItem('accessToken');
    const url = token ? `${base}?token=${token}` : base;

    let ws: WebSocket | null = null;
    let closedByUs = false;

    const connect = () => {
      setStatus('connecting');
      console.debug('[AgentStream] connecting to', url);
      ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.debug('[AgentStream] connected');
        setStatus('connected');
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data) as AgentStreamEvent;
          onEventRef.current?.(data);
        } catch (e) {
          console.warn('[AgentStream] Invalid message', msg.data);
        }
      };

      ws.onerror = (err) => {
        console.error('[AgentStream] error', err);
      };

      ws.onclose = (ev) => {
        console.debug('[AgentStream] closed', ev.code, ev.reason);
        wsRef.current = null;
        if (!closedByUs) {
          setStatus('disconnected');
          if (reconnectAttempts.current < maxReconnects) {
            const delay = 1000 * Math.pow(2, reconnectAttempts.current);
            reconnectAttempts.current += 1;
            console.debug(`[AgentStream] reconnect in ${delay}ms (${reconnectAttempts.current}/${maxReconnects})`);
            setTimeout(() => {
              if (projectId && sessionId) connect();
            }, delay);
          }
        }
      };
    };

    connect();

    return () => {
      closedByUs = true;
      try { ws?.close(); } catch { /* noop */ }
      wsRef.current = null;
      setStatus('no-session');
    };
  }, [projectId, sessionId]);

  // ── Send helpers ─────────────────────────────────────────────────

  const sendMessage = useCallback((
    content: string,
    contextFiles?: Array<{ path: string; content: string }>,
  ) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[AgentStream] Cannot send — WS not open');
      return false;
    }
    ws.send(JSON.stringify({
      type: 'message',
      content,
      context_files: contextFiles ?? [],
    }));
    return true;
  }, []);

  const cancel = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'cancel' }));
  }, []);

  return { wsRef, status, sendMessage, cancel };
};
