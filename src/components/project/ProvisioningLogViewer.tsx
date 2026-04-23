import React, { useEffect, useState, useRef } from 'react';
import { Alert, AlertVariant } from '@patternfly/react-core';
import { CheckCircleIcon, ExclamationCircleIcon, ExclamationTriangleIcon, InfoCircleIcon } from '@patternfly/react-icons';

interface ProvisioningLog {
  level: 'debug' | 'info' | 'warning' | 'error';
  step_name: string;
  message: string;
  metadata: Record<string, any>;
  timestamp: string;
}

interface ProvisioningLogViewerProps {
  projectId: number;
  autoConnect?: boolean;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export const ProvisioningLogViewer: React.FC<ProvisioningLogViewerProps> = ({
  projectId,
  autoConnect = true,
  onComplete,
  onError,
}) => {
  const [logs, setLogs] = useState<ProvisioningLog[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Use refs to store latest callbacks so re-rendering parents with inline
  // callbacks do not force reconnects.
  const onCompleteRef = useRef<(() => void) | undefined>(onComplete);
  const onErrorRef = useRef<((error: string) => void) | undefined>(onError);
  useEffect(() => { onCompleteRef.current = onComplete; onErrorRef.current = onError; }, [onComplete, onError]);

  useEffect(() => {
    if (!autoConnect) return;

    const connectWebSocket = () => {
      try {
        // Get JWT token from localStorage
        const token = localStorage.getItem('token');
        if (!token) {
          setConnectionError('No authentication token found');
          return;
        }

        // Connect to provisioning logs WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/projects/${projectId}/provisioning-logs?token=${token}`;
        
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('[ProvisioningLog] WebSocket connected');
          setIsConnected(true);
          setConnectionError(null);
        };

        ws.onmessage = (event) => {
          try {
            const log: ProvisioningLog = JSON.parse(event.data);
            setLogs((prev) => [...prev, log]);

            // Check for completion
            if (log.step_name === 'init_complete') {
              onComplete?.();
            }

            // Check for errors
            if (log.level === 'error') {
              onError?.(log.message);
            }
          } catch (error) {
            console.error('[ProvisioningLog] Failed to parse message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('[ProvisioningLog] WebSocket error:', error);
          setConnectionError('WebSocket connection error');
          setIsConnected(false);
        };

        ws.onclose = (event) => {
          console.log('[ProvisioningLog] WebSocket closed:', event.code, event.reason);
          setIsConnected(false);
          
          // Reconnect if not a normal closure
          if (event.code !== 1000 && autoConnect) {
            setTimeout(connectWebSocket, 3000);
          }
        };
      } catch (error) {
        console.error('[ProvisioningLog] Failed to connect:', error);
        setConnectionError('Failed to establish WebSocket connection');
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close(1000);
        wsRef.current = null;
      }
    };
  }, [projectId, autoConnect]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'error':
        return <ExclamationCircleIcon className="text-red-600" />;
      case 'warning':
        return <ExclamationTriangleIcon className="text-yellow-600" />;
      case 'info':
        return <CheckCircleIcon className="text-green-600" />;
      case 'debug':
        return <InfoCircleIcon className="text-blue-600" />;
      default:
        return <InfoCircleIcon />;
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'error':
        return 'text-red-600';
      case 'warning':
        return 'text-yellow-600';
      case 'info':
        return 'text-green-600';
      case 'debug':
        return 'text-gray-500';
      default:
        return 'text-gray-700';
    }
  };

  if (connectionError) {
    return (
      <Alert variant={AlertVariant.danger} title="Connection Error" isInline>
        {connectionError}
      </Alert>
    );
  }

  return (
    <div className="provisioning-log-viewer bg-gray-50 rounded-lg p-4 border border-gray-200">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Provisioning Logs</h3>
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-400'}`} />
          <span className="text-sm text-gray-600">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      <div className="log-entries max-h-96 overflow-y-auto bg-white rounded border border-gray-200 p-3 font-mono text-sm">
        {logs.length === 0 ? (
          <div className="text-gray-500 text-center py-4">
            Waiting for provisioning logs...
          </div>
        ) : (
          <>
            {logs.map((log, index) => (
              <div
                key={index}
                className={`log-entry flex items-start gap-2 py-1 ${getLevelColor(log.level)}`}
              >
                <span className="flex-shrink-0 mt-0.5">{getLevelIcon(log.level)}</span>
                <span className="text-xs text-gray-500 flex-shrink-0 w-20">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                {log.step_name && (
                  <span className="text-xs font-semibold flex-shrink-0 bg-gray-100 px-2 py-0.5 rounded">
                    {log.step_name}
                  </span>
                )}
                <span className="flex-1">{log.message}</span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </>
        )}
      </div>
    </div>
  );
};

export default ProvisioningLogViewer;
