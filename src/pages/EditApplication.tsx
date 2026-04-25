import { useState, useRef, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Page, PageSection, Card, CardBody, CardTitle, Button, Tabs, Tab, TabTitleText, Grid, GridItem } from '@patternfly/react-core';
import { ArrowLeftIcon, CompressIcon, ExpandIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/use-toast';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import complianceData from '@/data/complianceChecks.json';

import { Settings, Plus, Trash2 } from 'lucide-react';
import { Tabs as UITabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import editApplicationData from '@/data/editApplicationData.json';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { FileTree } from '@/components/editor/FileTree';
import { CodeEditor } from '@/components/editor/CodeEditor';
import { GitDiffViewer } from '@/components/editor/GitDiffViewer';
import { ScrollArea } from '@/components/ui/scroll-area';
import { CompactPageHeader } from '@/components/ui/compact-page-header';
import { IssuesTab } from '@/components/project/IssuesTab';
import { PullRequestsTab } from '@/components/project/PullRequestsTab';
import { WorkflowTab } from '@/components/project/WorkflowTab';
import { AIEditorTab } from '@/components/project/AIEditorTab';
import { FileManagerTab } from '@/components/project/FileManagerTab';
import { RepositoryGitTab } from '@/components/project/RepositoryGitTab';
import { SafetyComplianceTab } from '@/components/project/SafetyComplianceTab';
import { GeneralTab } from '@/components/project/GeneralTab';
import { AppDetailsDialog } from '@/components/project/AppDetailsDialog';
import { ServiceCreationWizard } from '../components/project/ServiceCreationWizard';
import { WebtopTab } from '@/components/project/WebtopTab';
import { ContainerLogsTab } from '@/components/project/ContainerLogsTab';
import { LegacyHierarchyRouteRedirect } from '../components/project/LegacyHierarchyRouteRedirect';
import { WorkspaceOrchestration } from '@/components/project/WorkspaceOrchestration';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteProjectServiceRecord, getProjects, Project, getProjectServices, ProjectService, restartService, startAllServices, startService, stopAllServices, stopService, updateProjectServiceRecord, killService, ProjectApp, ProjectEnvironment } from '@/lib/api';
import { CheckCircle, AlertTriangle, XCircle, FileText, Layers, ListChecks, Target, Shield, Play, Square, ChevronDown, Terminal, RefreshCcw, ExternalLink, RotateCcw, Loader2 } from 'lucide-react';


interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ServicesTabProps {
  project: Project;
  appId?: number;
}

const ServicesTab: React.FC<ServicesTabProps> = ({ project, appId }) => {
  const storageKey = `livePreviewEnabled:${project.id}:${appId ?? 'all'}`;
  const servicesQueryKey = ['project-services', project.id, appId ?? 'all'];
  const queryClient = useQueryClient();
  const { data: services = [], isLoading, isError } = useQuery({
    queryKey: servicesQueryKey,
    queryFn: () => getProjectServices(project.id, appId !== undefined ? { appId } : undefined),
    select: (response) => response?.data || [],
    refetchInterval: 5000,
  });

  const [enabledIds, setEnabledIds] = useState<number[] | null>(null);
  const [expandedService, setExpandedService] = useState<number | null>(null);
  const [isCreateServiceOpen, setIsCreateServiceOpen] = useState(false);
  const [editingServiceId, setEditingServiceId] = useState<number | null>(null);
  const [deletingServiceId, setDeletingServiceId] = useState<number | null>(null);
  const [serviceForm, setServiceForm] = useState({
    name: '',
    image: '',
    serviceType: 'custom' as ProjectService['service_type'],
    ports: '',
    environmentText: '',
    autostart: false,
    cpuLimit: '',
    memoryLimit: '',
  });

  const editingService = services.find((service: ProjectService) => service.id === editingServiceId) ?? null;
  const deletingService = services.find((service: ProjectService) => service.id === deletingServiceId) ?? null;

  const parseEnvironmentText = (environmentText: string) => {
    return environmentText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .reduce<Record<string, string>>((result, line) => {
        const separatorIndex = line.indexOf('=');
        if (separatorIndex === -1) {
          return result;
        }
        const key = line.slice(0, separatorIndex).trim();
        const value = line.slice(separatorIndex + 1).trim();
        if (key) {
          result[key] = value;
        }
        return result;
      }, {});
  };

  const parsePorts = (portsText: string) => portsText.split(',').map((value) => value.trim()).filter(Boolean);

  // Service action mutations
  const startServiceMutation = useMutation({
    mutationFn: (serviceId: number) => startService(project.id, serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service Starting', description: 'Service is being started...' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to start service', variant: 'destructive' }),
  });

  const stopServiceMutation = useMutation({
    mutationFn: (serviceId: number) => stopService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service Stopped', description: 'Service has been stopped.' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to stop service', variant: 'destructive' }),
  });

  const restartServiceMutation = useMutation({
    mutationFn: (serviceId: number) => restartService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service Restarting', description: 'Service is being restarted...' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to restart service', variant: 'destructive' }),
  });

  const killServiceMutation = useMutation({
    mutationFn: (serviceId: number) => killService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service Killed', description: 'Service has been forcefully stopped.' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to kill service', variant: 'destructive' }),
  });

  const updateServiceMutation = useMutation({
    mutationFn: (payload: { id: number; data: Partial<ProjectService> }) => updateProjectServiceRecord(payload.id, payload.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service updated', description: 'Service configuration was saved.' });
      setEditingServiceId(null);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the service.',
        variant: 'destructive',
      });
    },
  });

  const deleteServiceMutation = useMutation({
    mutationFn: (serviceId: number) => deleteProjectServiceRecord(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: servicesQueryKey });
      toast({ title: 'Service deleted', description: 'The service was removed from this application.' });
      setDeletingServiceId(null);
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the service.',
        variant: 'destructive',
      });
    },
  });

  const openEditServiceDialog = (service: ProjectService) => {
    setServiceForm({
      name: service.name,
      image: service.image,
      serviceType: service.service_type,
      ports: service.ports.join(', '),
      environmentText: Object.entries(service.environment || {}).map(([key, value]) => `${key}=${value}`).join('\n'),
      autostart: Boolean(service.autostart),
      cpuLimit: service.cpu_limit || '',
      memoryLimit: service.memory_limit || '',
    });
    setEditingServiceId(service.id);
  };

  useEffect(() => {
    if (!services.length) return;
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setEnabledIds(parsed);
          return;
        }
      } catch (err) {
        console.warn('Failed to parse live preview selection', err);
      }
    }
    const allIds = services.map((s: ProjectService) => s.id);
    setEnabledIds(allIds);
    localStorage.setItem(storageKey, JSON.stringify(allIds));
  }, [services, storageKey]);

  const toggleService = (id: number) => {
    const current = enabledIds ?? services.map((s: ProjectService) => s.id);
    const exists = current.includes(id);
    const next = exists ? current.filter((s) => s !== id) : [...current, id];
    setEnabledIds(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-green-500';
      case 'stopped': return 'text-red-500';
      case 'paused': return 'text-yellow-500';
      default: return 'text-muted-foreground';
    }
  };

  const renderStatus = (status: string) => {
    const variant = status === 'running' ? 'success' : status === 'stopped' ? 'secondary' : 'outline';
    return (
      <Badge variant={variant} className="flex items-center gap-1">
        <span className={`inline-block w-2 h-2 rounded-full ${status === 'running' ? 'bg-green-500 animate-pulse' : status === 'stopped' ? 'bg-red-400' : 'bg-yellow-400'}`} />
        {status}
      </Badge>
    );
  };

  const renderList = useMemo(() => {
    if (isLoading) {
      return <div className="flex items-center justify-center py-8"><Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading services...</div>;
    }
    if (isError) {
      return <div className="text-center py-8 text-destructive">Failed to load services. Ensure workspace is provisioned.</div>;
    }
    if (!services.length) {
      return (
        <div className="text-center py-12 space-y-3">
          <Layers className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="text-muted-foreground">
            {appId !== undefined ? 'No services found for this application.' : 'No services found for this project.'}
          </p>
          <p className="text-sm text-muted-foreground">
            {appId !== undefined
              ? 'Create the first service for this application to define its runtime.'
              : 'Provision your workspace in the AI Editor or Webtop tab to create services.'}
          </p>
        </div>
      );
    }

    return (
      <div className="flex flex-col gap-3">
        {services.map((service: ProjectService) => {
          const envCount = service.environment ? Object.keys(service.environment).length : 0;
          const volumesRaw = (service.config && (service.config as any).volumes) || [];
          const volumes = Array.isArray(volumesRaw) ? volumesRaw : Object.keys(volumesRaw || {});
          const dependsOnRaw = (service.config && (service.config as any).depends_on) || [];
          const dependsOn = Array.isArray(dependsOnRaw) ? dependsOnRaw : Object.keys(dependsOnRaw || {});
          const isExpanded = expandedService === service.id;
          const isRunning = service.status === 'running';

          return (
            <div key={service.id} className="border rounded-lg bg-card overflow-hidden">
              {/* Service Header */}
              <div 
                className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => setExpandedService(isExpanded ? null : service.id)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-base">{service.name}</span>
                  {renderStatus(service.status)}
                  <Badge variant="outline" className="text-xs">{service.service_type}</Badge>
                </div>
                <div className="flex items-center gap-2">
                  {/* Quick Actions */}
                  {isRunning ? (
                    <>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); restartServiceMutation.mutate(service.id); }}
                        isDisabled={restartServiceMutation.isPending}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <RotateCcw style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Restart
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); stopServiceMutation.mutate(service.id); }}
                        isDisabled={stopServiceMutation.isPending}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <Square style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Stop
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); startServiceMutation.mutate(service.id); }}
                      isDisabled={startServiceMutation.isPending}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Play style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Start
                    </Button>
                  )}
                  <span className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                    <ChevronDown style={{ width: '1rem', height: '1rem' }} />
                  </span>
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="border-t border-border p-4 space-y-4">
                  {/* Info Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Image</span>
                      <span className="font-mono text-xs truncate block">{service.image || 'n/a'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">CPU Limit</span>
                      <span className="font-medium">{service.cpu_limit || 'unlimited'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Memory Limit</span>
                      <span className="font-medium">{service.memory_limit || 'unlimited'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Autostart</span>
                      <span className="font-medium">{service.autostart ? 'Yes' : 'No'}</span>
                    </div>
                  </div>

                  {/* Ports - clickable links */}
                  {service.ports?.length > 0 && (
                    <div>
                      <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Exposed Ports</span>
                      <div className="flex gap-2 flex-wrap">
                        {service.ports.map((port, i) => {
                          const hostPort = port.split(':')[0];
                          return (
                            <a
                              key={i}
                              href={`http://localhost:${hostPort}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-mono transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink style={{ width: '0.75rem', height: '0.75rem' }} />
                              :{port}
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Environment & Dependencies */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {envCount > 0 && (
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Environment Variables ({envCount})</span>
                        <div className="bg-muted p-2 rounded max-h-32 overflow-y-auto text-xs font-mono space-y-0.5">
                          {Object.entries(service.environment).map(([key, val]) => (
                            <div key={key}><span className="text-blue-600">{key}</span>=<span className="text-muted-foreground">{String(val).length > 30 ? '***' : String(val)}</span></div>
                          ))}
                        </div>
                      </div>
                    )}
                    {volumes.length > 0 && (
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Volumes ({volumes.length})</span>
                        <div className="bg-muted p-2 rounded max-h-32 overflow-y-auto text-xs font-mono space-y-0.5">
                          {volumes.map((v: string, i: number) => (
                            <div key={i}>{v}</div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {dependsOn.length > 0 && (
                    <div>
                      <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Dependencies</span>
                      <div className="flex gap-1.5 flex-wrap">
                        {dependsOn.map((dep: string) => (
                          <Badge key={dep} variant="outline" className="text-xs">{dep}</Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Advanced Actions */}
                  <div className="flex gap-2 flex-wrap pt-2 border-t border-border">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toast({ title: 'Terminal', description: `Opening terminal for ${service.name}...` })}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Terminal style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Terminal
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toast({ title: 'Rebuilding', description: `Rebuilding ${service.name}...` })}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <RefreshCcw style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Rebuild
                    </Button>
                    {appId !== undefined ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => openEditServiceDialog(service)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <Settings style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Edit
                      </Button>
                    ) : null}
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); killServiceMutation.mutate(service.id); }}
                      isDisabled={killServiceMutation.isPending}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <XCircle style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Force Kill
                    </Button>
                    {appId !== undefined ? (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => setDeletingServiceId(service.id)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <Trash2 style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Delete
                      </Button>
                    ) : null}
                    <div className="ml-auto flex items-center gap-2">
                      <Checkbox
                        id={`live-preview-${service.id}`}
                        checked={enabledIds ? enabledIds.includes(service.id) : true}
                        onCheckedChange={() => toggleService(service.id)}
                      />
                      <Label htmlFor={`live-preview-${service.id}`} className="text-xs">Live Preview</Label>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }, [services, isLoading, isError, enabledIds, expandedService, startServiceMutation, stopServiceMutation, restartServiceMutation, killServiceMutation, appId]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Container Services</h2>
          <p className="text-sm text-muted-foreground">
            {appId !== undefined
              ? 'Manage services attached to this application. Start, stop, restart, or inspect the runtime here.'
              : "Manage your project's containerized services. Start, stop, restart, or access terminals."}
          </p>
        </div>
        <div className="flex gap-2">
          {appId !== undefined ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsCreateServiceOpen(true)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                <Plus style={{ width: '0.875rem', height: '0.875rem' }} />
              </span>
              Create Service
            </Button>
          ) : null}
          {appId === undefined ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  startAllServices(project.id);
                  queryClient.invalidateQueries({ queryKey: servicesQueryKey });
                  toast({ title: 'Starting All', description: 'Starting all services...' });
                }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  <Play style={{ width: '0.875rem', height: '0.875rem' }} />
                </span>
                Start All
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  stopAllServices(project.id);
                  queryClient.invalidateQueries({ queryKey: servicesQueryKey });
                  toast({ title: 'Stopping All', description: 'Stopping all services...' });
                }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
              >
                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                  <Square style={{ width: '0.875rem', height: '0.875rem' }} />
                </span>
                Stop All
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {renderList}

      {appId !== undefined ? (
        <ServiceCreationWizard
          appId={appId}
          isOpen={isCreateServiceOpen}
          onOpenChange={setIsCreateServiceOpen}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: servicesQueryKey });
          }}
        />
      ) : null}

      <Dialog
        open={editingServiceId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingServiceId(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit service</DialogTitle>
            <DialogDescription>Update the runtime configuration for this application service.</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="service-name">Name</Label>
              <Input
                id="service-name"
                value={serviceForm.name}
                onChange={(event) => setServiceForm((current) => ({ ...current, name: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-image">Container image</Label>
              <Input
                id="service-image"
                value={serviceForm.image}
                onChange={(event) => setServiceForm((current) => ({ ...current, image: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-type">Service type</Label>
              <Input
                id="service-type"
                value={serviceForm.serviceType}
                onChange={(event) => setServiceForm((current) => ({ ...current, serviceType: event.target.value as ProjectService['service_type'] }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-ports">Ports</Label>
              <Input
                id="service-ports"
                placeholder="3000:3000, 9229:9229"
                value={serviceForm.ports}
                onChange={(event) => setServiceForm((current) => ({ ...current, ports: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-cpu-limit">CPU limit</Label>
              <Input
                id="service-cpu-limit"
                value={serviceForm.cpuLimit}
                onChange={(event) => setServiceForm((current) => ({ ...current, cpuLimit: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-memory-limit">Memory limit</Label>
              <Input
                id="service-memory-limit"
                value={serviceForm.memoryLimit}
                onChange={(event) => setServiceForm((current) => ({ ...current, memoryLimit: event.target.value }))}
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="service-environment">Environment variables</Label>
              <Textarea
                id="service-environment"
                rows={6}
                placeholder="KEY=VALUE"
                value={serviceForm.environmentText}
                onChange={(event) => setServiceForm((current) => ({ ...current, environmentText: event.target.value }))}
              />
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-border/70 bg-muted/20 px-4 py-3 md:col-span-2">
              <Checkbox
                id="service-autostart-edit"
                checked={serviceForm.autostart}
                onCheckedChange={(checked) => setServiceForm((current) => ({ ...current, autostart: checked === true }))}
              />
              <Label htmlFor="service-autostart-edit">Start this service automatically when the workspace starts</Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="secondary" onClick={() => setEditingServiceId(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                if (!editingService) {
                  return;
                }
                updateServiceMutation.mutate({
                  id: editingService.id,
                  data: {
                    name: serviceForm.name.trim(),
                    image: serviceForm.image.trim(),
                    service_type: serviceForm.serviceType,
                    ports: parsePorts(serviceForm.ports),
                    environment: parseEnvironmentText(serviceForm.environmentText),
                    autostart: serviceForm.autostart,
                    cpu_limit: serviceForm.cpuLimit.trim() || null,
                    memory_limit: serviceForm.memoryLimit.trim() || null,
                  },
                });
              }}
              isDisabled={updateServiceMutation.isPending || !serviceForm.name.trim() || !serviceForm.image.trim()}
            >
              {updateServiceMutation.isPending ? 'Saving...' : 'Save changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deletingServiceId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingServiceId(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Delete service</DialogTitle>
            <DialogDescription>
              {deletingService
                ? `Remove ${deletingService.name} from this application. This does not automatically remove external data volumes.`
                : 'Remove this service from the application.'}
            </DialogDescription>
          </DialogHeader>

          <DialogFooter>
            <Button variant="secondary" onClick={() => setDeletingServiceId(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (deletingServiceId !== null) {
                  deleteServiceMutation.mutate(deletingServiceId);
                }
              }}
              isDisabled={deleteServiceMutation.isPending}
            >
              {deleteServiceMutation.isPending ? 'Deleting...' : 'Delete service'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const applicationFormSchema = z.object({
  name: z.string().trim().min(1, { message: "Project name is required" }).max(100, { message: "Name must be less than 100 characters" }),
  version: z.string().trim().regex(/^\d+\.\d+\.\d+$/, { message: "Version must be in format X.Y.Z (e.g., 1.0.0)" }),
  description: z.string().trim().min(10, { message: "Description must be at least 10 characters" }).max(500, { message: "Description must be less than 500 characters" }),
  category: z.string().min(1, { message: "Please select a category" }),
  aiTechnology: z.string().min(1, { message: "Please select an AI technology" }),
  repositoryUrl: z.string().url({ message: "Must be a valid URL" }).optional().or(z.literal('')),
});

interface ApplicationWorkspaceProps {
  project: Project | null;
  app?: ProjectApp | null;
  environment?: ProjectEnvironment | null;
  applicationName?: string;
  serviceAppId?: number;
  headerTitle?: string;
  subtitle?: string;
  headerMeta?: React.ReactNode;
  backLink?: {
    label: string;
    onClick: () => void;
  };
  embedded?: boolean;
  layoutMode?: 'default' | 'full-page';
}

export const ApplicationWorkspace: React.FC<ApplicationWorkspaceProps> = ({
  project,
  app,
  environment,
  applicationName,
  serviceAppId,
  headerTitle = 'Application workspace',
  subtitle,
  headerMeta,
  backLink,
  embedded = false,
  layoutMode = 'default',
}) => {
  const workspaceLabel = applicationName || project?.name || 'Application';
  const projectIdOrName = project ? project.id.toString() : applicationName || '';
  const [isChatCollapsed, setIsChatCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<string | number>(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Hello! I'm your AI assistant for editing "${workspaceLabel}". How can I help you modify your project today?`
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isAppDetailsOpen, setIsAppDetailsOpen] = useState(false);
  
  // AI Settings State
  const [aiModel, setAiModel] = useState(editApplicationData.defaultSettings.aiModel);
  const [temperature, setTemperature] = useState([editApplicationData.defaultSettings.temperature]);
  const [maxTokens, setMaxTokens] = useState([editApplicationData.defaultSettings.maxTokens]);
  const [topP, setTopP] = useState([editApplicationData.defaultSettings.topP]);
  const [frequencyPenalty, setFrequencyPenalty] = useState([editApplicationData.defaultSettings.frequencyPenalty]);
  const [presencePenalty, setPresencePenalty] = useState([editApplicationData.defaultSettings.presencePenalty]);
  const [streamResponse, setStreamResponse] = useState(editApplicationData.defaultSettings.streamResponse);
  
  // MCP Servers State
  const [mcpServers, setMcpServers] = useState<Array<{ id: string; name: string; url: string; enabled: boolean }>>(editApplicationData.defaultMcpServers);

  // File Manager State
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>(editApplicationData.sampleFiles);
  const [originalContents, setOriginalContents] = useState<Record<string, string>>({});
  const [modifiedFiles, setModifiedFiles] = useState<Set<string>>(new Set());
  
  const fileStructure = editApplicationData.sampleFileStructure as any;

  const [chatSummary, setChatSummary] = useState('');
  const [todoOutline, setTodoOutline] = useState<string[]>([]); // New state for todo outline as array of strings

  // Simulated compliance data (replace with actual data source)
  const complianceChecks = [
    { id: '1', name: 'Security Scan', status: 'Pass', remediation: 'No issues found.' },
    { id: '2', name: 'Code Quality Check', status: 'Warning', remediation: 'Fix unused variables in file.js.' },
    { id: '3', name: 'Performance Audit', status: 'Fail', remediation: 'Optimize database queries.' },
  ];

  // Add state for compliance management
  const [assignedTemplates, setAssignedTemplates] = useState<string[]>([]);
  const [assignedChecks, setAssignedChecks] = useState<string[]>([]);
  const [isRunningChecks, setIsRunningChecks] = useState(false);
  const [checkResults, setCheckResults] = useState<Array<{
    checkId: string;
    checkName: string;
    status: 'Pass' | 'Warning' | 'Fail';
    message: string;
    remediation: string;
  }>>([]);
  const [isAssignDialogOpen, setIsAssignDialogOpen] = useState(false);
  const [selectedTemplatesForAssign, setSelectedTemplatesForAssign] = useState<string[]>([]);

  const form = useForm<z.infer<typeof applicationFormSchema>>({
    resolver: zodResolver(applicationFormSchema),
    defaultValues: {
      name: workspaceLabel,
      version: '1.0.0',
      description: '',
      category: '',
      aiTechnology: '',
      repositoryUrl: '',
    },
  });

  const onSubmit = (values: z.infer<typeof applicationFormSchema>) => {
    console.log('Project details updated:', values);
    toast({
      title: "Changes Saved",
      description: "Project details have been updated successfully.",
    });
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Simulate AI response
    setTimeout(() => {
      const assistantMessage: Message = {
        role: 'assistant',
        content: 'I understand you want to make changes. This is a demo interface. To enable full AI editing capabilities, you would need to integrate with an AI service.'
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1000);

    // Simulate updating summary and todo on send
    setChatSummary(prev => prev + ` ${input}`); // Append to summary
    if (input.toLowerCase().includes('large change')) {
      setTodoOutline(['Step 1: Analyze requirements', 'Step 2: Implement core logic', 'Step 3: Test changes']); // Simulate AI-generated todo
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // File Manager Handlers
  const handleFileSelect = (path: string) => {
    setSelectedFile(path);
    if (!originalContents[path] && fileContents[path]) {
      setOriginalContents(prev => ({ ...prev, [path]: fileContents[path] }));
    }
  };

  const handleContentChange = (content: string) => {
    if (!selectedFile) return;
    setFileContents(prev => ({ ...prev, [selectedFile]: content }));
    
    const isModified = originalContents[selectedFile] !== content;
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      if (isModified) {
        newSet.add(selectedFile);
      } else {
        newSet.delete(selectedFile);
      }
      return newSet;
    });
  };

  const handleSaveFile = () => {
    if (!selectedFile) return;
    setOriginalContents(prev => ({ ...prev, [selectedFile]: fileContents[selectedFile] }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(selectedFile);
      return newSet;
    });
    toast({
      title: "File Saved",
      description: `${selectedFile} has been saved successfully.`,
    });
  };

  const handleDiscardFile = () => {
    if (!selectedFile) return;
    setFileContents(prev => ({ ...prev, [selectedFile]: originalContents[selectedFile] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(selectedFile);
      return newSet;
    });
    toast({
      title: "Changes Discarded",
      description: `Changes to ${selectedFile} have been discarded.`,
    });
  };

  const handleStageFile = (path: string) => {
    toast({
      title: "File Staged",
      description: `${path} has been staged for commit.`,
    });
  };

  const handleDiscardGitFile = (path: string) => {
    setFileContents(prev => ({ ...prev, [path]: originalContents[path] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(path);
      return newSet;
    });
    toast({
      title: "Changes Discarded",
      description: `Changes to ${path} have been discarded.`,
    });
  };

  const handleCommit = () => {
    toast({
      title: "Committing Changes",
      description: "This would open a commit dialog in a full implementation.",
    });
  };

  const getGitDiffs = () => {
    return Array.from(modifiedFiles).map(path => {
      const original = originalContents[path] || '';
      const current = fileContents[path] || '';
      const originalLines = original.split('\n');
      const currentLines = current.split('\n');
      
      let diff = '';
      let additions = 0;
      let deletions = 0;

      const maxLen = Math.max(originalLines.length, currentLines.length);
      for (let i = 0; i < maxLen; i++) {
        if (originalLines[i] !== currentLines[i]) {
          if (originalLines[i]) {
            diff += `- ${originalLines[i]}\n`;
            deletions++;
          }
          if (currentLines[i]) {
            diff += `+ ${currentLines[i]}\n`;
            additions++;
          }
        }
      }

      return { path, additions, deletions, diff };
    });
  };

  // Render tabs for the header
  const renderTabs = () => (
    <Tabs
      activeKey={activeTab}
      onSelect={(event, tabIndex) => setActiveTab(tabIndex)}
      style={{ marginBottom: '1.5rem' }}
    >
      <Tab eventKey={0} title={<TabTitleText>AI Editor</TabTitleText>} />
      <Tab eventKey={1} title={<TabTitleText>General</TabTitleText>} />
      <Tab eventKey={2} title={<TabTitleText>Services</TabTitleText>} />
      <Tab eventKey={3} title={<TabTitleText>File Manager</TabTitleText>} />
      <Tab eventKey={4} title={<TabTitleText>Repository & Git</TabTitleText>} />
      <Tab eventKey={5} title={<TabTitleText>Issues</TabTitleText>} />
      <Tab eventKey={6} title={<TabTitleText>Pull Requests</TabTitleText>} />
      <Tab eventKey={7} title={<TabTitleText>Workflows</TabTitleText>} />
      <Tab eventKey={8} title={<TabTitleText>Safety and Compliance</TabTitleText>} />
      <Tab eventKey={9} title={<TabTitleText>Webtop</TabTitleText>} />
      <Tab eventKey={10} title={<TabTitleText>Container Logs</TabTitleText>} />
    </Tabs>
  );

  const handleAssignTemplates = () => {
    setAssignedTemplates(selectedTemplatesForAssign);
    
    // Also add all checks from selected templates
    const checksFromTemplates = selectedTemplatesForAssign.flatMap(templateId => {
      const template = complianceData.templates.find(t => t.id === templateId);
      return template ? template.checks : [];
    });
    
    setAssignedChecks(prev => [...new Set([...prev, ...checksFromTemplates])]);
    
    toast({
      title: "Templates Assigned",
      description: `${selectedTemplatesForAssign.length} compliance template(s) assigned to this project.`,
    });
    
    setIsAssignDialogOpen(false);
    setSelectedTemplatesForAssign([]);
  };

  const handleToggleCheck = (checkId: string) => {
    setAssignedChecks(prev => 
      prev.includes(checkId) 
        ? prev.filter(id => id !== checkId)
        : [...prev, checkId]
    );
  };

  const handleRunChecks = async () => {
    if (assignedChecks.length === 0) {
      toast({
        title: "No Checks Assigned",
        description: "Please assign templates or checks before running compliance checks.",
        variant: "destructive",
      });
      return;
    }

    setIsRunningChecks(true);
    
    // Simulate running checks
    setTimeout(() => {
      const results = assignedChecks.map(checkId => {
        const check = complianceData.checks.find(c => c.id === checkId);
        if (!check) return null;
        
        // Simulate random results for demo
        const statuses: Array<'Pass' | 'Warning' | 'Fail'> = ['Pass', 'Warning', 'Fail'];
        const randomStatus = statuses[Math.floor(Math.random() * statuses.length)];
        
        return {
          checkId: check.id,
          checkName: check.name,
          status: randomStatus,
          message: randomStatus === 'Pass' 
            ? `${check.name} passed successfully.`
            : randomStatus === 'Warning'
            ? `${check.name} completed with warnings.`
            : `${check.name} failed validation.`,
          remediation: check.aiPrompt,
        };
      }).filter(Boolean) as typeof checkResults;
      
      setCheckResults(results);
      setIsRunningChecks(false);
      
      const passCount = results.filter(r => r.status === 'Pass').length;
      const failCount = results.filter(r => r.status === 'Fail').length;
      const warningCount = results.filter(r => r.status === 'Warning').length;
      
      toast({
        title: "Compliance Checks Complete",
        description: `${passCount} passed, ${warningCount} warnings, ${failCount} failed`,
      });
    }, 2000);
  };

  const getAssignedTemplateNames = () => {
    return assignedTemplates
      .map(id => complianceData.templates.find(t => t.id === id)?.name)
      .filter(Boolean)
      .join(', ');
  };

  return (
    <>
      <PageSection variant="default" style={{ paddingTop: 0, paddingBottom: 0 }}>
        <div style={{ 
          position: embedded ? 'relative' : 'sticky', 
          top: 0, 
          zIndex: 100, 
          backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
          borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
          paddingTop: embedded ? 0 : '1rem'
        }}>
          <CompactPageHeader
            title={headerTitle}
            subtitle={subtitle || workspaceLabel}
            headerMeta={headerMeta}
            backLink={backLink}
            defaultCompact={layoutMode === 'full-page'}
            actions={
              <div className="flex items-center gap-2">
                {project && <WorkspaceOrchestration project={project} showStatusSummary={layoutMode !== 'full-page'} />}
              </div>
            }
            tabs={renderTabs()}
          />
        </div>
      </PageSection>

      <PageSection variant="default" isFilled hasBodyWrapper={false} style={{ paddingTop: '1rem', paddingBottom: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: activeTab === 0 || activeTab === 3 ? 'hidden' : 'auto' }}>
        {activeTab === 0 && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {project ? <AIEditorTab project={project} layoutMode={layoutMode} layoutScope={serviceAppId !== undefined ? `app-${serviceAppId}` : `project-${project.id}`} /> : <div>Loading AI editor...</div>}
          </div>
        )}

        {activeTab === 1 && (
          project ? (
            <GeneralTab
              project={project}
              app={app ?? null}
              environment={environment}
              onOpenAppDetails={() => setIsAppDetailsOpen(true)}
              onOpenTerminal={() => setActiveTab(9)}
            />
          ) : (
            <div>Loading app general settings...</div>
          )
        )}

        {activeTab === 2 && (
          project ? <ServicesTab project={project} appId={serviceAppId} /> : <div>Loading services...</div>
        )}

        {activeTab === 3 && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {project ? <FileManagerTab project={project} layoutMode={layoutMode} /> : <div>Loading file manager...</div>}
          </div>
        )}

        {activeTab === 4 && (
          project ? (
            <RepositoryGitTab
              app={app ?? null}
              projectName={project.name}
              projectId={project.id}
              onOpenGeneral={() => setActiveTab(1)}
            />
          ) : <div>Loading repository...</div>
        )}

        {activeTab === 5 && (
          <IssuesTab projectId={projectIdOrName} projectName={project?.name || workspaceLabel} />
        )}

        {activeTab === 6 && (
          <PullRequestsTab projectId={projectIdOrName} projectName={project?.name || workspaceLabel} />
        )}

        {activeTab === 7 && (
          <WorkflowTab projectId={projectIdOrName} projectName={project?.name || workspaceLabel} />
        )}

        {activeTab === 8 && (
          <SafetyComplianceTab projectName={project?.name || workspaceLabel} />
        )}

        {activeTab === 9 && (
          project ? <WebtopTab project={project} /> : <div>Loading webtop...</div>
        )}

        {activeTab === 10 && (
          project ? <ContainerLogsTab project={project} /> : <div>Loading logs...</div>
        )}
        </div>
      </PageSection>

      <AppDetailsDialog
        app={app ?? null}
        environmentId={environment?.id ?? app?.environment}
        open={isAppDetailsOpen}
        onOpenChange={setIsAppDetailsOpen}
      />
    </>
  );
};

const EditApplication = () => {
  const { appName } = useParams();
  return (
    <LegacyHierarchyRouteRedirect
      projectIdentifier={appName}
      message="Redirecting to the canonical application workspace..."
    />
  );
};

export default EditApplication;

