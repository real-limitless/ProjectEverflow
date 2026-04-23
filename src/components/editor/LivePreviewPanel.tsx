import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardBody } from '@patternfly/react-core';
import { Loader2, AlertCircle, RefreshCw, Power, Monitor, Maximize2, Minimize2, Play, Trash2, Terminal, ArrowLeft, ArrowRight, ExternalLink, Smartphone, Tablet, MonitorUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/use-toast';
import { useTokenRefresh } from '@/hooks/useTokenRefresh';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ensureWorkspace, provisionServices, startService, deleteService, getWebtopProxyUrl, getServiceProxyUrl, getServiceProxyAuthUrl, getProjectServices } from '@/lib/api';
import { Project, ProjectService } from '@/lib/api';
import { WorkspaceStatsPanel } from './WorkspaceStatsPanel';

interface LivePreviewPanelProps {
  project: Project;
  isCollapsed?: boolean;
  isChatCollapsed?: boolean;
  onChatCollapsedChange?: (collapsed: boolean) => void;
}

interface PreviewService {
  id: string;
  serviceId: number;
  name: string;
  type: string;
  ports: string[];
  url: string;           // Final subdomain URL (for compose services)
  authUrl?: string;      // Auth URL that sets cookie and redirects (for compose services)
  status: string;
  cpuLimit?: string;
  memoryLimit?: string;
  firstPort?: string;
  needsAuth?: boolean;   // Whether this service needs auth redirect flow
}

export const LivePreviewPanel: React.FC<LivePreviewPanelProps> = ({ project, isCollapsed = false, isChatCollapsed = false, onChatCollapsedChange }) => {
  const queryClient = useQueryClient();
  const [previewUrl, setPreviewUrl] = useState<string>('');
  const [isStarting, setIsStarting] = useState(false);
  const [selectedService, setSelectedService] = useState<string>('stats'); // 'stats' or service id
  const [enabledServiceIds, setEnabledServiceIds] = useState<number[] | null>(null);
  const [availableServices, setAvailableServices] = useState<PreviewService[]>([]);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  
  // Viewport presets: null = responsive (fill container)
  const VIEWPORT_PRESETS = [
    { key: 'mobile', label: 'Mobile', width: 375, icon: Smartphone },
    { key: 'tablet', label: 'Tablet', width: 768, icon: Tablet },
    { key: 'desktop', label: 'Desktop', width: 1280, icon: Monitor },
    { key: 'ultrawide', label: 'Ultrawide', width: 1920, icon: MonitorUp },
  ] as const;
  const [viewportWidth, setViewportWidth] = useState<number | null>(null);

  // Token refresh hook - monitors JWT expiry and refreshes proactively
  // refreshKey increments when token is refreshed, triggering iframe reload
  const { refreshKey, timeUntilExpiry, isRefreshing: isTokenRefreshing } = useTokenRefresh({
    refreshBuffer: 2 * 60 * 1000, // Refresh 2 minutes before expiry
    checkInterval: 30 * 1000,     // Check every 30 seconds
  });

  // Fetch all project services
  const { data: servicesData = [], refetch: refetchServices } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: async () => {
      const response = await getProjectServices(project.id);
      if (response.error) throw new Error(response.error);
      return response.data || [];
    },
    // Normalize the response so downstream logic can always treat it as an array
    select: (response) => {
      console.log('[LivePreview] Raw services response:', response);
      if (Array.isArray(response)) return response;
      if (Array.isArray(response?.data)) return response.data;
      return [];
    },
    refetchInterval: 5000,
  });

  const workspaceService = servicesData.find((s: any) => s.service_type === 'ai-workspace') as ProjectService | undefined;
  const isRunning = workspaceService?.status === 'running';
  
  console.log('[LivePreview] All services:', servicesData);
  console.log('[LivePreview] Workspace service:', workspaceService);
  console.log('[LivePreview] Is running:', isRunning);

  useEffect(() => {
    const raw = localStorage.getItem(`livePreviewEnabled:${project.id}`);
    if (!raw) {
      setEnabledServiceIds(null);
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setEnabledServiceIds(parsed);
        return;
      }
    } catch (error) {
      console.warn('Failed to parse live preview selections', error);
    }
    setEnabledServiceIds(null);
  }, [project.id, servicesData]);

  // Build available services list (include workspace service and all services regardless of status)
  useEffect(() => {
    console.log('[LivePreview] Building services list. isRunning:', isRunning, 'servicesData:', servicesData);
    if (servicesData) {
      const services: PreviewService[] = servicesData
        .filter((s: ProjectService) => {
          // Include workspace, services with ports, and custom compose services
          const include = s.service_type === 'ai-workspace' || (s.ports && s.ports.length > 0) || s.service_type === 'custom';
          console.log(`[LivePreview] Service ${s.name} (${s.service_type}): ports=${JSON.stringify(s.ports)}, status=${s.status}, include=${include}`);
          return include;
        })
        .map((s: ProjectService) => {
          const firstPort = s.ports && s.ports.length > 0 ? (s.ports[0]?.split(':')[0] || s.ports[0]) : '';
          const isWorkspace = s.service_type === 'ai-workspace';
          
          // Determine URL based on service type
          let baseUrl: string;
          let authUrl: string | undefined;
          let needsAuth = false;
          
          if (isWorkspace) {
            // Webtop uses path-based proxy with token in URL
            baseUrl = getWebtopProxyUrl(project.id);
          } else if (firstPort) {
            // Compose services use subdomain-based proxy
            // First load goes to auth URL which sets cookie and redirects
            baseUrl = getServiceProxyUrl(project.id, s.id, firstPort);
            authUrl = getServiceProxyAuthUrl(project.id, s.id, firstPort);
            needsAuth = true;
          } else {
            // Fallback for services without ports (shouldn't reach iframe)
            baseUrl = '';
          }

          return {
            id: `service-${s.id}`,
            serviceId: s.id,
            name: isWorkspace ? 'Workspace (webtop)' : s.name,
            type: s.service_type,
            ports: s.ports || [],
            url: baseUrl,
            authUrl: authUrl,
            needsAuth: needsAuth,
            status: s.status,
            cpuLimit: s.cpu_limit,
            memoryLimit: s.memory_limit,
            firstPort: firstPort,
          };
        });

      const filtered = enabledServiceIds && enabledServiceIds.length
        ? services.filter((svc) => enabledServiceIds.includes(svc.serviceId))
        : services;

      console.log('[LivePreview] Available services after filtering:', filtered);
      setAvailableServices(filtered);
    }
  }, [servicesData, project.id, enabledServiceIds]);

  // Start preview dev server
  const startPreviewMutation = useMutation({
    mutationFn: async () => {
      setIsStarting(true);
      try {
        // Route based on selected service
        if (selectedService === 'stats') {
          // Stats panel will be shown directly, no URL needed
          setPreviewUrl('');
        } else {
          const service = availableServices.find(s => s.id === selectedService);
          if (service) {
            setPreviewUrl(service.url);
          }
        }
        
        toast({
          title: 'Preview Started',
          description: selectedService === 'stats' ? 'Showing workspace stats' : 'Dev server is running',
        });
      } finally {
        setIsStarting(false);
      }
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.message || 'Failed to start preview',
        variant: 'destructive',
      });
      setIsStarting(false);
    },
  });

  // Provision services mutation
  const provisionServicesMutation = useMutation({
    mutationFn: () => provisionServices(project.id),
    onSuccess: () => {
      toast({
        title: 'Services Provisioned',
        description: 'Compose services have been provisioned',
      });
      refetchServices();
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.message || 'Failed to provision services',
        variant: 'destructive',
      });
    },
  });

  // Start service mutation
  const startServiceMutation = useMutation({
    mutationFn: (serviceId: number) => startService(project.id, serviceId),
    onSuccess: () => {
      toast({
        title: 'Service Started',
        description: 'Service is starting up',
      });
      refetchServices();
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.message || 'Failed to start service',
        variant: 'destructive',
      });
    },
  });

  // Delete service mutation
  const deleteServiceMutation = useMutation({
    mutationFn: (serviceId: number) => deleteService(project.id, serviceId),
    onSuccess: () => {
      toast({
        title: 'Service Deleted',
        description: 'Service has been removed',
      });
      refetchServices();
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.message || 'Failed to delete service',
        variant: 'destructive',
      });
    },
  });

  // Update preview URL when selected service changes or token refreshes
  // refreshKey changes when JWT token is refreshed, triggering URL regeneration
  useEffect(() => {
    if (!isRunning) {
      setPreviewUrl('');
      return;
    }
    
    if (selectedService === 'stats') {
      setPreviewUrl('');
    } else {
      const service = availableServices.find(s => s.id === selectedService);
      if (service) {
        // For compose services with subdomain proxy, use auth URL on first load
        // The auth endpoint will set a cookie and redirect to the subdomain
        // Re-generate URL with fresh token when refreshKey changes
        const url = service.needsAuth && service.authUrl 
          ? getServiceProxyAuthUrl(project.id, service.serviceId, service.firstPort || '')
          : service.url;
        console.log('[LivePreview] Setting preview URL for service:', service.name, url, 'refreshKey:', refreshKey);
        setPreviewUrl(url);
      } else {
        console.log('[LivePreview] No URL for selected service:', selectedService);
        setPreviewUrl('');
      }
    }
  }, [isRunning, selectedService, availableServices, refreshKey, project.id]);

  if (isCollapsed) {
    return null;
  }

  // Navigation handlers for iframe
  const handleIframeBack = () => {
    try { iframeRef.current?.contentWindow?.history.back(); } catch { /* cross-origin */ }
  };
  const handleIframeForward = () => {
    try { iframeRef.current?.contentWindow?.history.forward(); } catch { /* cross-origin */ }
  };
  const handleIframeRefresh = () => {
    if (iframeRef.current) {
      try { iframeRef.current.contentWindow?.location.reload(); } catch {
        // Cross-origin fallback: re-set src
        iframeRef.current.src = previewUrl;
      }
    }
  };

  const showBrowserToolbar = isRunning && selectedService !== 'stats' && previewUrl;

  return (
    <Card className="h-full m-0 rounded-lg border-0 flex flex-col">
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        padding: '0.5rem 1rem',
        borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
        flexShrink: 0,
      }}>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Live Preview</h2>
          {selectedService === 'stats' ? (
            <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', margin: '0.125rem 0 0 0' }}>
              Container Statistics & Metrics
            </p>
          ) : (
            <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', margin: '0.125rem 0 0 0' }}>
              {availableServices.find(s => s.id === selectedService)?.name || 'Select a service'}
            </p>
          )}
        </div>

        {/* Service Selector */}
        {isRunning && availableServices.length > 0 && (
          <div style={{ minWidth: '180px', marginRight: '0.5rem' }}>
            <Select value={selectedService} onValueChange={setSelectedService}>
              <SelectTrigger style={{ fontSize: '0.8rem', height: '2rem' }}>
                <SelectValue placeholder="Select preview" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="stats">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Monitor size={14} />
                    Container Stats
                  </div>
                </SelectItem>
                {availableServices.map(service => (
                  <SelectItem key={service.id} value={service.id}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        {service.type === 'ai-workspace' && <Terminal size={14} />}
                        <span>{service.name}</span>
                        {service.status === 'stopped' && (
                          <Badge variant="outline" style={{ fontSize: '0.65rem', padding: '0.1rem 0.3rem' }}>Stopped</Badge>
                        )}
                      </div>
                      {(service.cpuLimit || service.memoryLimit) && (
                        <span style={{ fontSize: '0.65rem', color: 'var(--pf-v6-global--Color--200)', marginLeft: '0.5rem' }}>
                          {service.cpuLimit && `CPU:${service.cpuLimit}`}
                          {service.cpuLimit && service.memoryLimit && ' '}
                          {service.memoryLimit && `Mem:${service.memoryLimit}`}
                        </span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div style={{ display: 'flex', gap: '0.25rem' }}>
          {isRunning && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => provisionServicesMutation.mutate()}
              disabled={provisionServicesMutation.isPending}
              style={{ height: '2rem', padding: '0 0.5rem' }}
            >
              {provisionServicesMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
            </Button>
          )}
          {!isRunning && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => ensureWorkspace(project.id)}
            >
              Start Workspace
            </Button>
          )}
          {onChatCollapsedChange && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChatCollapsedChange(!isChatCollapsed)}
              style={{ height: '2rem', padding: '0 0.5rem' }}
            >
              {isChatCollapsed ? <Maximize2 size={14} /> : <Minimize2 size={14} />}
            </Button>
          )}
        </div>
      </div>

      {/* Browser Toolbar (only when showing iframe) */}
      {showBrowserToolbar && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
          padding: '0.375rem 0.5rem',
          borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
          backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
          flexShrink: 0,
        }}>
          {/* Navigation Buttons */}
          <button
            onClick={handleIframeBack}
            className="p-1 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            title="Go back"
          >
            <ArrowLeft size={14} />
          </button>
          <button
            onClick={handleIframeForward}
            className="p-1 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            title="Go forward"
          >
            <ArrowRight size={14} />
          </button>
          <button
            onClick={handleIframeRefresh}
            className="p-1 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>

          {/* Address Bar */}
          <input
            type="text"
            readOnly
            value={previewUrl}
            title={previewUrl}
            style={{
              flex: 1,
              height: '1.625rem',
              padding: '0 0.5rem',
              fontSize: '0.75rem',
              borderRadius: '999px',
              border: '1px solid var(--pf-v6-global--BorderColor--100)',
              backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
              color: 'var(--pf-v6-global--Color--200)',
              outline: 'none',
              fontFamily: 'monospace',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          />

          {/* Open in new tab */}
          <button
            onClick={() => window.open(previewUrl, '_blank')}
            className="p-1 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            title="Open in new tab"
          >
            <ExternalLink size={14} />
          </button>

          {/* Viewport separator */}
          <div style={{ width: 1, height: 18, backgroundColor: 'var(--pf-v6-global--BorderColor--100)', margin: '0 0.25rem' }} />

          {/* Viewport Presets */}
          <button
            onClick={() => setViewportWidth(null)}
            className={`p-1 rounded transition-colors ${
              viewportWidth === null
                ? 'bg-[var(--pf-v6-global--primary-color--100,#0066cc)] text-white'
                : 'hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
            title="Responsive (full width)"
          >
            <Maximize2 size={14} />
          </button>
          {VIEWPORT_PRESETS.map((preset) => (
            <button
              key={preset.key}
              onClick={() => setViewportWidth(viewportWidth === preset.width ? null : preset.width)}
              className={`p-1 rounded transition-colors ${
                viewportWidth === preset.width
                  ? 'bg-[var(--pf-v6-global--primary-color--100,#0066cc)] text-white'
                  : 'hover:bg-gray-300 dark:hover:bg-gray-600'
              }`}
              title={`${preset.label} (${preset.width}px)`}
            >
              <preset.icon size={14} />
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <CardBody style={{ flex: 1, padding: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {!isRunning ? (
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
            flexDirection: 'column',
            gap: '1rem',
          }}>
            <AlertCircle size={32} style={{ opacity: 0.5 }} />
            <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
              Workspace Not Running
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', textAlign: 'center', maxWidth: '80%' }}>
              Start the workspace to enable live preview
            </p>
          </div>
        ) : selectedService === 'stats' ? (
          <WorkspaceStatsPanel project={project} />
        ) : !previewUrl ? (
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
            flexDirection: 'column',
            gap: '1rem',
          }}>
            <Loader2 size={32} style={{ animation: 'spin 2s linear infinite', opacity: 0.7 }} />
            <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
              Starting Preview Server
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
              This may take a moment...
            </p>
          </div>
        ) : (() => {
            const currentService = availableServices.find(s => s.id === selectedService);
            if (currentService && currentService.status === 'stopped') {
              return (
                <div style={{ 
                  flex: 1, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                  flexDirection: 'column',
                  gap: '1rem',
                }}>
                  <Power size={32} style={{ opacity: 0.5 }} />
                  <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                    Service is Stopped
                  </p>
                  <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', textAlign: 'center', maxWidth: '80%' }}>
                    {currentService.name} ({currentService.type})
                  </p>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => startServiceMutation.mutate(currentService.serviceId)}
                      disabled={startServiceMutation.isPending}
                    >
                      {startServiceMutation.isPending ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Play size={16} />
                      )}
                      <span className="ml-2">Start Service</span>
                    </Button>
                    {currentService.type !== 'ai-workspace' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          if (confirm(`Delete ${currentService.name}? This cannot be undone.`)) {
                            deleteServiceMutation.mutate(currentService.serviceId);
                          }
                        }}
                        disabled={deleteServiceMutation.isPending}
                      >
                        <Trash2 size={16} />
                        <span className="ml-2">Delete</span>
                      </Button>
                    )}
                  </div>
                </div>
              );
            }
            return (
              <div style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'center',
                overflow: 'hidden',
                backgroundColor: viewportWidth ? '#e5e7eb' : 'transparent',
                transition: 'background-color 0.3s ease',
              }}>
                <div style={{
                  width: viewportWidth ? `${viewportWidth}px` : '100%',
                  maxWidth: '100%',
                  height: '100%',
                  transition: 'width 0.3s ease',
                  boxShadow: viewportWidth ? '0 0 20px rgba(0,0,0,0.15)' : 'none',
                  position: 'relative',
                }}>
                  {viewportWidth && (
                    <div style={{
                      position: 'absolute',
                      top: 4,
                      right: 8,
                      fontSize: '0.65rem',
                      color: '#888',
                      zIndex: 1,
                      pointerEvents: 'none',
                      backgroundColor: 'rgba(255,255,255,0.8)',
                      padding: '1px 6px',
                      borderRadius: 4,
                    }}>
                      {viewportWidth}px
                    </div>
                  )}
                  <iframe
                    ref={iframeRef}
                    key={`preview-${refreshKey}`}
                    src={previewUrl}
                    style={{
                      width: '100%',
                      height: '100%',
                      border: viewportWidth ? '1px solid var(--pf-v6-global--BorderColor--100)' : 'none',
                      backgroundColor: '#fff',
                    }}
                    title="Live Preview"
                    sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals"
                  />
                </div>
              </div>
            );
          })()
        }
      </CardBody>
    </Card>
  );
};
