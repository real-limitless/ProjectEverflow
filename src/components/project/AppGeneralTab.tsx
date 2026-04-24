import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ExternalLink,
  GitBranch,
  History,
  Loader2,
  Play,
  RefreshCcw,
  Server,
  Settings,
  Square,
  Terminal,
} from 'lucide-react';

import { AppDetailsDialog } from '@/components/project/AppDetailsDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import { useOrganizationHierarchyData } from '@/hooks/useOrganizationHierarchyData';
import {
  createDeployment,
  getProjectServices,
  getServiceLogs,
  restartService,
  startService,
  stopService,
  type Project,
  type ProjectApp,
  type ProjectService,
  updateApp,
  updateDeployment,
} from '@/lib/api';

interface AppGeneralTabProps {
  project: Project;
  appId?: number;
  onOpenTerminal?: () => void;
}

type DeploymentSourceProvider =
  | 'github'
  | 'gitlab'
  | 'bitbucket'
  | 'gitea'
  | 'generic-git'
  | 'raw'
  | 'docker-registry';

type DeploymentTriggerType = 'manual' | 'push' | 'schedule';

interface GeneralSettingsState {
  sourceType: ProjectApp['source_type'];
  repositoryUrl: string;
  composePath: string;
  sourceProvider: DeploymentSourceProvider;
  branch: string;
  watchPaths: string;
  includeSubmodules: boolean;
  triggerType: DeploymentTriggerType;
  schedule: string;
  autoDeploy: boolean;
}

const DEFAULT_GENERAL_SETTINGS: GeneralSettingsState = {
  sourceType: 'compose',
  repositoryUrl: '',
  composePath: './docker-compose.yml',
  sourceProvider: 'github',
  branch: 'main',
  watchPaths: 'src/**',
  includeSubmodules: false,
  triggerType: 'manual',
  schedule: '',
  autoDeploy: false,
};

function getGeneralSettings(app: ProjectApp): GeneralSettingsState {
  const deploymentConfig = (app.config?.deployment ?? {}) as Partial<GeneralSettingsState> & {
    watchPaths?: string[] | string;
  };

  const watchPaths = Array.isArray(deploymentConfig.watchPaths)
    ? deploymentConfig.watchPaths.join('\n')
    : deploymentConfig.watchPaths;

  return {
    sourceType: app.source_type,
    repositoryUrl: app.repository_url || '',
    composePath: app.compose_path || DEFAULT_GENERAL_SETTINGS.composePath,
    sourceProvider: deploymentConfig.sourceProvider ?? DEFAULT_GENERAL_SETTINGS.sourceProvider,
    branch: deploymentConfig.branch ?? DEFAULT_GENERAL_SETTINGS.branch,
    watchPaths: watchPaths ?? DEFAULT_GENERAL_SETTINGS.watchPaths,
    includeSubmodules:
      deploymentConfig.includeSubmodules ?? DEFAULT_GENERAL_SETTINGS.includeSubmodules,
    triggerType: deploymentConfig.triggerType ?? DEFAULT_GENERAL_SETTINGS.triggerType,
    schedule: deploymentConfig.schedule ?? DEFAULT_GENERAL_SETTINGS.schedule,
    autoDeploy: deploymentConfig.autoDeploy ?? DEFAULT_GENERAL_SETTINGS.autoDeploy,
  };
}

function buildComposePreview(app: ProjectApp, settings: GeneralSettingsState, services: ProjectService[]) {
  const watchedPaths = settings.watchPaths
    .split('\n')
    .map((path) => path.trim())
    .filter(Boolean);

  const servicePreview = services
    .map((service) => {
      const ports = service.ports.length > 0 ? `\n    ports:\n${service.ports.map((port) => `      - ${port}`).join('\n')}` : '';
      const environmentEntries = Object.entries(service.environment || {});
      const environment = environmentEntries.length > 0
        ? `\n    environment:\n${environmentEntries
            .map(([key, value]) => `      ${key}: ${value}`)
            .join('\n')}`
        : '';

      return `  ${service.name}:\n    image: ${service.image}${ports}${environment}`;
    })
    .join('\n\n');

  return [
    '# Compose preview',
    `app: ${app.name}`,
    `source_type: ${settings.sourceType}`,
    `source_provider: ${settings.sourceProvider}`,
    `repository_url: ${settings.repositoryUrl || 'not configured'}`,
    `branch: ${settings.branch || 'main'}`,
    `compose_path: ${settings.composePath || './docker-compose.yml'}`,
    `trigger_type: ${settings.triggerType}`,
    `auto_deploy: ${settings.autoDeploy ? 'true' : 'false'}`,
    watchedPaths.length > 0 ? `watch_paths:\n${watchedPaths.map((path) => `  - ${path}`).join('\n')}` : 'watch_paths: []',
    services.length > 0 ? `services:\n${servicePreview}` : 'services: {}',
  ].join('\n');
}

export const AppGeneralTab = ({ project, appId, onOpenTerminal }: AppGeneralTabProps) => {
  const queryClient = useQueryClient();
  const {
    deployments,
    deploymentsLoading,
    selectedApp,
    selectedEnvironment,
    selectedOrganization,
    selectedProject,
  } = useOrganizationHierarchyData();

  const effectiveApp = selectedApp && (appId === undefined || selectedApp.id === appId) ? selectedApp : null;
  const [isAppDetailsOpen, setIsAppDetailsOpen] = useState(false);
  const [isComposePreviewOpen, setIsComposePreviewOpen] = useState(false);
  const [selectedLogServiceId, setSelectedLogServiceId] = useState<number | null>(null);
  const [settings, setSettings] = useState<GeneralSettingsState>(DEFAULT_GENERAL_SETTINGS);

  const { data: servicesResponse, isLoading: servicesLoading } = useQuery({
    queryKey: ['project-services', project.id, appId ?? 'all', 'general-tab'],
    queryFn: () => getProjectServices(project.id, appId !== undefined ? { appId } : undefined),
    enabled: effectiveApp !== null,
  });

  const services = servicesResponse?.data ?? [];

  useEffect(() => {
    if (effectiveApp) {
      setSettings(getGeneralSettings(effectiveApp));
    }
  }, [effectiveApp]);

  useEffect(() => {
    if (!services.length) {
      setSelectedLogServiceId(null);
      return;
    }

    setSelectedLogServiceId((current) => {
      if (current && services.some((service) => service.id === current)) {
        return current;
      }
      return services[0].id;
    });
  }, [services]);

  const { data: logsResponse, isLoading: logsLoading } = useQuery({
    queryKey: ['project-service-logs', selectedLogServiceId],
    queryFn: () => getServiceLogs(selectedLogServiceId as number, { tail: 200 }),
    enabled: selectedLogServiceId !== null,
    refetchInterval: 5000,
  });

  const selectedLogService = services.find((service) => service.id === selectedLogServiceId) ?? null;

  const updateAppMutation = useMutation({
    mutationFn: (data: Partial<ProjectApp>) => updateApp(effectiveApp!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment!.id] });
      toast({
        title: 'General settings saved',
        description: 'Deployment source and trigger settings were updated for this app.',
      });
    },
    onError: (error) => {
      toast({
        title: 'Save failed',
        description: error instanceof Error ? error.message : 'Unable to save app settings.',
        variant: 'destructive',
      });
    },
  });

  const deployMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveApp) {
        throw new Error('No app selected.');
      }

      const deploymentResponse = await createDeployment({
        app_id: effectiveApp.id,
        version: `${effectiveApp.slug}-${Date.now()}`,
        status: 'in_progress',
        trigger_type: 'manual',
        source_ref: settings.branch || undefined,
        compose_path: settings.composePath || undefined,
        notes: `Manual deploy from the General tab using ${settings.sourceProvider}.`,
        config_snapshot: {
          deployment: {
            sourceProvider: settings.sourceProvider,
            branch: settings.branch,
            watchPaths: settings.watchPaths
              .split('\n')
              .map((path) => path.trim())
              .filter(Boolean),
            includeSubmodules: settings.includeSubmodules,
            triggerType: settings.triggerType,
            schedule: settings.schedule,
            autoDeploy: settings.autoDeploy,
          },
        },
      });

      if (!deploymentResponse.data) {
        throw new Error(deploymentResponse.error || 'Unable to create deployment record.');
      }

      const startedAt = new Date().toISOString();
      const results = await Promise.allSettled(
        services.map((service) =>
          service.status === 'running'
            ? restartService(service.id)
            : startService(project.id, service.id),
        ),
      );

      const failureCount = results.filter((result) => result.status === 'rejected').length;

      await updateDeployment(deploymentResponse.data.id, {
        status: failureCount > 0 ? 'failed' : 'succeeded',
        notes:
          failureCount > 0
            ? `Deploy finished with ${failureCount} service action failure(s).`
            : 'Deploy finished successfully from the General tab.',
        started_at: startedAt,
        completed_at: new Date().toISOString(),
      });

      return failureCount;
    },
    onSuccess: (failureCount) => {
      queryClient.invalidateQueries({ queryKey: ['deployments', effectiveApp?.id] });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({
        title: failureCount > 0 ? 'Deploy finished with issues' : 'Deploy completed',
        description:
          failureCount > 0
            ? 'The deployment record was created, but one or more service actions failed.'
            : 'A deployment record was created and the app services were refreshed.',
        variant: failureCount > 0 ? 'destructive' : 'default',
      });
    },
    onError: (error) => {
      toast({
        title: 'Deploy failed',
        description: error instanceof Error ? error.message : 'Unable to deploy this app.',
        variant: 'destructive',
      });
    },
  });

  const reloadMutation = useMutation({
    mutationFn: async () => {
      const runningServices = services.filter((service) => service.status === 'running');

      if (runningServices.length === 0) {
        throw new Error('No running app services are available to reload.');
      }

      await Promise.all(runningServices.map((service) => restartService(service.id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Services reloaded', description: 'Running app services were restarted.' });
    },
    onError: (error) => {
      toast({
        title: 'Reload failed',
        description: error instanceof Error ? error.message : 'Unable to reload app services.',
        variant: 'destructive',
      });
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      const runningServices = services.filter((service) => service.status === 'running');

      if (runningServices.length === 0) {
        throw new Error('No running app services are available to stop.');
      }

      await Promise.all(runningServices.map((service) => stopService(service.id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Services stopped', description: 'Running app services were stopped.' });
    },
    onError: (error) => {
      toast({
        title: 'Stop failed',
        description: error instanceof Error ? error.message : 'Unable to stop app services.',
        variant: 'destructive',
      });
    },
  });

  const composePreview = useMemo(() => {
    if (!effectiveApp) {
      return '';
    }
    return buildComposePreview(effectiveApp, settings, services);
  }, [effectiveApp, settings, services]);

  if (!effectiveApp || !selectedEnvironment || !selectedOrganization || !selectedProject) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>General settings unavailable</CardTitle>
          <CardDescription>Select an app from the hierarchy to manage deployment source settings.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const saveGeneralSettings = () => {
    updateAppMutation.mutate({
      source_type: settings.sourceType,
      repository_url: settings.repositoryUrl.trim() || undefined,
      compose_path: settings.composePath.trim() || undefined,
      config: {
        ...effectiveApp.config,
        deployment: {
          sourceProvider: settings.sourceProvider,
          branch: settings.branch,
          watchPaths: settings.watchPaths
            .split('\n')
            .map((path) => path.trim())
            .filter(Boolean),
          includeSubmodules: settings.includeSubmodules,
          triggerType: settings.triggerType,
          schedule: settings.schedule.trim(),
          autoDeploy: settings.autoDeploy,
        },
      },
    });
  };

  const lastDeployments = deployments.slice(0, 10);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <Server className="h-5 w-5" />
                {effectiveApp.name}
              </CardTitle>
              <CardDescription>
                General now owns deployment source wiring, runtime controls, and the shared app settings entrypoint.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => setIsAppDetailsOpen(true)}>
                <Settings className="mr-2 h-4 w-4" />
                App Details
              </Button>
              <Button variant="outline" size="sm" onClick={() => setIsComposePreviewOpen(true)}>
                <ExternalLink className="mr-2 h-4 w-4" />
                Preview compose
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Organization: {selectedOrganization.name}</Badge>
          <Badge variant="secondary">Project: {selectedProject.name}</Badge>
          <Badge variant="secondary">Environment: {selectedEnvironment.name}</Badge>
          <Badge variant="secondary">Source: {effectiveApp.source_type}</Badge>
          <Badge variant="secondary">Status: {effectiveApp.status}</Badge>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Core Deployment and Git Integration</CardTitle>
              <CardDescription>
                Configure the source provider, repository reference, watched paths, and trigger policy for this app.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="source-type">Source type</Label>
                  <Select
                    value={settings.sourceType}
                    onValueChange={(value) =>
                      setSettings((current) => ({
                        ...current,
                        sourceType: value as ProjectApp['source_type'],
                      }))
                    }
                  >
                    <SelectTrigger id="source-type">
                      <SelectValue placeholder="Select source type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="compose">Compose</SelectItem>
                      <SelectItem value="container">Container image</SelectItem>
                      <SelectItem value="repository">Repository</SelectItem>
                      <SelectItem value="custom">Custom</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="source-provider">Source provider</Label>
                  <Select
                    value={settings.sourceProvider}
                    onValueChange={(value) =>
                      setSettings((current) => ({
                        ...current,
                        sourceProvider: value as DeploymentSourceProvider,
                      }))
                    }
                  >
                    <SelectTrigger id="source-provider">
                      <SelectValue placeholder="Select source provider" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="github">GitHub</SelectItem>
                      <SelectItem value="gitlab">GitLab</SelectItem>
                      <SelectItem value="bitbucket">Bitbucket</SelectItem>
                      <SelectItem value="gitea">Gitea</SelectItem>
                      <SelectItem value="generic-git">Generic Git</SelectItem>
                      <SelectItem value="raw">Raw compose or Dockerfile</SelectItem>
                      <SelectItem value="docker-registry">Docker Registry or Hub</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="repository-url">Repository URL</Label>
                  <Input
                    id="repository-url"
                    value={settings.repositoryUrl}
                    onChange={(event) =>
                      setSettings((current) => ({
                        ...current,
                        repositoryUrl: event.target.value,
                      }))
                    }
                    placeholder="https://github.com/org/repository"
                  />
                  <p className="text-xs text-muted-foreground">
                    Shared organization Git connections will plug into this slot from the Organizations settings route.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="branch">Branch or source ref</Label>
                  <Input
                    id="branch"
                    value={settings.branch}
                    onChange={(event) =>
                      setSettings((current) => ({
                        ...current,
                        branch: event.target.value,
                      }))
                    }
                    placeholder="main"
                  />
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="compose-path">Compose path</Label>
                  <Input
                    id="compose-path"
                    value={settings.composePath}
                    onChange={(event) =>
                      setSettings((current) => ({
                        ...current,
                        composePath: event.target.value,
                      }))
                    }
                    placeholder="./docker-compose.yml"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="trigger-type">Trigger type</Label>
                  <Select
                    value={settings.triggerType}
                    onValueChange={(value) =>
                      setSettings((current) => ({
                        ...current,
                        triggerType: value as DeploymentTriggerType,
                      }))
                    }
                  >
                    <SelectTrigger id="trigger-type">
                      <SelectValue placeholder="Select trigger type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="manual">Manual deploy</SelectItem>
                      <SelectItem value="push">On push</SelectItem>
                      <SelectItem value="schedule">Schedule</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="watch-paths">Watch paths</Label>
                <Textarea
                  id="watch-paths"
                  value={settings.watchPaths}
                  onChange={(event) =>
                    setSettings((current) => ({
                      ...current,
                      watchPaths: event.target.value,
                    }))
                  }
                  placeholder={'src/**\ncompose/**'}
                  rows={4}
                />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="schedule">Schedule</Label>
                  <Input
                    id="schedule"
                    value={settings.schedule}
                    onChange={(event) =>
                      setSettings((current) => ({
                        ...current,
                        schedule: event.target.value,
                      }))
                    }
                    placeholder="0 0 * * *"
                    disabled={settings.triggerType !== 'schedule'}
                  />
                </div>

                <div className="rounded-lg border border-border/80 bg-muted/20 p-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium">Autodeploy</div>
                        <p className="text-xs text-muted-foreground">Enable app-level deploys when the selected trigger fires.</p>
                      </div>
                      <Switch
                        checked={settings.autoDeploy}
                        onCheckedChange={(checked) =>
                          setSettings((current) => ({ ...current, autoDeploy: checked }))
                        }
                      />
                    </div>

                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm font-medium">Git submodules</div>
                        <p className="text-xs text-muted-foreground">Persist whether this app expects submodule-aware checkout behavior.</p>
                      </div>
                      <Switch
                        checked={settings.includeSubmodules}
                        onCheckedChange={(checked) =>
                          setSettings((current) => ({
                            ...current,
                            includeSubmodules: checked,
                          }))
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button onClick={() => deployMutation.mutate()} disabled={deployMutation.isPending || servicesLoading}>
                  {deployMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  Deploy
                </Button>
                <Button variant="outline" onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending || servicesLoading}>
                  {reloadMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCcw className="mr-2 h-4 w-4" />
                  )}
                  Reload
                </Button>
                <Button variant="outline" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || servicesLoading}>
                  {stopMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Square className="mr-2 h-4 w-4" />
                  )}
                  Stop
                </Button>
                <Button variant="outline" onClick={onOpenTerminal} disabled={!onOpenTerminal}>
                  <Terminal className="mr-2 h-4 w-4" />
                  Open terminal
                </Button>
                <Button variant="secondary" onClick={saveGeneralSettings} disabled={updateAppMutation.isPending}>
                  {updateAppMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Save general settings
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <History className="h-5 w-5" />
                Recent deployments
              </CardTitle>
              <CardDescription>
                The last ten deployment records stay visible from the workspace while queue and streaming support are expanded.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {deploymentsLoading ? (
                <p className="text-sm text-muted-foreground">Loading deployments...</p>
              ) : lastDeployments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deployments exist for this app yet.</p>
              ) : (
                lastDeployments.map((deployment) => (
                  <div key={deployment.id} className="rounded-lg border border-border bg-background p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="text-base font-semibold">{deployment.version}</div>
                        <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                          <GitBranch className="h-4 w-4" />
                          {deployment.source_ref || 'manual'}
                        </div>
                      </div>
                      <Badge variant={deployment.status === 'succeeded' ? 'default' : 'outline'}>
                        {deployment.status.replace(/_/g, ' ')}
                      </Badge>
                    </div>
                    {deployment.notes ? (
                      <p className="mt-3 text-sm text-muted-foreground">{deployment.notes}</p>
                    ) : null}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Application services</CardTitle>
              <CardDescription>
                Runtime actions in General currently operate on services attached to this app.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {servicesLoading ? (
                <p className="text-sm text-muted-foreground">Loading services...</p>
              ) : services.length === 0 ? (
                <p className="text-sm text-muted-foreground">No services are attached to this app yet.</p>
              ) : (
                services.map((service) => (
                  <div key={service.id} className="rounded-lg border border-border bg-background p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{service.name}</div>
                        <div className="text-sm text-muted-foreground">{service.image}</div>
                      </div>
                      <Badge variant={service.status === 'running' ? 'default' : 'outline'}>
                        {service.status}
                      </Badge>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Service logs</CardTitle>
              <CardDescription>
                Recent logs are pulled from the selected app service while deployment-native streaming is added.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {services.length > 0 ? (
                <div className="space-y-2">
                  <Label htmlFor="service-log-target">Service</Label>
                  <Select
                    value={selectedLogServiceId ? String(selectedLogServiceId) : undefined}
                    onValueChange={(value) => setSelectedLogServiceId(Number(value))}
                  >
                    <SelectTrigger id="service-log-target">
                      <SelectValue placeholder="Select a service" />
                    </SelectTrigger>
                    <SelectContent>
                      {services.map((service) => (
                        <SelectItem key={service.id} value={String(service.id)}>
                          {service.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : null}

              <div className="rounded-lg border border-border bg-black p-4">
                {logsLoading ? (
                  <div className="flex items-center gap-2 text-sm text-slate-200">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading logs...
                  </div>
                ) : selectedLogService ? (
                  <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap text-xs text-slate-100">
                    {logsResponse?.data?.logs || `No logs available yet for ${selectedLogService.name}.`}
                  </pre>
                ) : (
                  <p className="text-sm text-slate-300">Attach a service to this app to inspect runtime logs here.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={isComposePreviewOpen} onOpenChange={setIsComposePreviewOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Compose preview</DialogTitle>
            <DialogDescription>
              Preview the persisted deployment source settings alongside the services currently attached to this app.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[70vh] overflow-auto rounded-lg border border-border bg-muted/30 p-4 text-xs">
            {composePreview}
          </pre>
        </DialogContent>
      </Dialog>

      <AppDetailsDialog
        app={effectiveApp}
        environmentId={selectedEnvironment.id}
        open={isAppDetailsOpen}
        onOpenChange={setIsAppDetailsOpen}
      />
    </div>
  );
};