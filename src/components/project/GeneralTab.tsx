import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Clock3, Eye, FolderGit2, Loader2, PlugZap, Rocket, Server, Settings, Square, Terminal } from 'lucide-react';

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
import {
  createDeployment,
  GitConnectionBranch,
  GitConnectionRepository,
  getAppSourceSettings,
  getDeployments,
  getOrganizationGitConnectionBranches,
  getOrganizationGitConnectionRepositories,
  getOrganizationGitConnections,
  getPersonalGitConnectionBranches,
  getPersonalGitConnectionRepositories,
  getPersonalGitConnections,
  getProjectServices,
  GitConnectionScope,
  GitProviderType,
  normalizeApiList,
  Project,
  ProjectApp,
  ProjectEnvironment,
  restartService,
  stopService,
  updateApp,
  updateAppSourceSettings,
} from '@/lib/api';

type SourceProviderType =
  | 'github'
  | 'gitlab'
  | 'bitbucket'
  | 'gitea'
  | 'generic-git'
  | 'raw-compose'
  | 'docker-registry';

type TriggerType = 'manual' | 'push' | 'schedule';

interface DeploymentSettingsFormState {
  providerType: SourceProviderType;
  connectionScope: GitConnectionScope | '';
  connectionId: number | null;
  connectionName: string;
  sourceReference: string;
  sourceRef: string;
  composePath: string;
  watchPaths: string;
  triggerType: TriggerType;
  autoDeployEnabled: boolean;
  submodulesEnabled: boolean;
  schedule: string;
}

interface GitConnectionOption {
  scope: GitConnectionScope;
  id: number;
  name: string;
  provider_type: GitProviderType;
}

interface GeneralTabProps {
  project: Project;
  app: ProjectApp | null;
  environment?: ProjectEnvironment | null;
  onOpenAppDetails: () => void;
  onOpenTerminal: () => void;
}

const defaultSettings: DeploymentSettingsFormState = {
  providerType: 'github',
  connectionScope: '',
  connectionId: null,
  connectionName: '',
  sourceReference: '',
  sourceRef: 'main',
  composePath: './docker-compose.yml',
  watchPaths: 'src/**',
  triggerType: 'manual',
  autoDeployEnabled: false,
  submodulesEnabled: false,
  schedule: '0 */6 * * *',
};

function isGitProvider(providerType: SourceProviderType) {
  return providerType !== 'raw-compose' && providerType !== 'docker-registry';
}

function buildSettingsFromApp(
  app: ProjectApp,
  sourceSettings?: {
    connection_scope: GitConnectionScope | '';
    organization_connection?: number | null;
    personal_connection?: number | null;
    selected_connection_name?: string | null;
    source_provider: SourceProviderType;
    source_ref: string;
    watch_paths: string[];
    trigger_type: TriggerType;
    auto_deploy_enabled: boolean;
    submodules_enabled: boolean;
    schedule: string;
    repository_url: string;
    compose_path: string;
  } | null,
): DeploymentSettingsFormState {
  const config = app.config?.deploymentSettings as Partial<DeploymentSettingsFormState> | undefined;
  const rawConnectionId = config?.connectionId;
  const connectionId = typeof rawConnectionId === 'number' ? rawConnectionId : null;
  const legacyConnectionName = (config as { organizationConnectionName?: string } | undefined)?.organizationConnectionName || '';

  if (sourceSettings) {
    const selectedConnectionId = sourceSettings.connection_scope === 'organization'
      ? sourceSettings.organization_connection ?? null
      : sourceSettings.connection_scope === 'personal'
        ? sourceSettings.personal_connection ?? null
        : null;

    return {
      providerType: sourceSettings.source_provider,
      connectionScope: sourceSettings.connection_scope || '',
      connectionId: selectedConnectionId,
      connectionName: sourceSettings.selected_connection_name || '',
      sourceReference: sourceSettings.repository_url || app.repository_url || '',
      sourceRef: sourceSettings.source_ref || 'main',
      composePath: sourceSettings.compose_path || app.compose_path || './docker-compose.yml',
      watchPaths: sourceSettings.watch_paths.length > 0 ? sourceSettings.watch_paths.join('\n') : 'src/**',
      triggerType: sourceSettings.trigger_type || 'manual',
      autoDeployEnabled: Boolean(sourceSettings.auto_deploy_enabled),
      submodulesEnabled: Boolean(sourceSettings.submodules_enabled),
      schedule: sourceSettings.schedule || '0 */6 * * *',
    };
  }

  return {
    providerType: config?.providerType || 'github',
    connectionScope: config?.connectionScope || (connectionId !== null ? 'organization' : ''),
    connectionId,
    connectionName: config?.connectionName || legacyConnectionName,
    sourceReference: config?.sourceReference || app.repository_url || '',
    sourceRef: config?.sourceRef || 'main',
    composePath: config?.composePath || app.compose_path || './docker-compose.yml',
    watchPaths: config?.watchPaths || 'src/**',
    triggerType: config?.triggerType || 'manual',
    autoDeployEnabled: Boolean(config?.autoDeployEnabled),
    submodulesEnabled: Boolean(config?.submodulesEnabled),
    schedule: config?.schedule || '0 */6 * * *',
  };
}

function getSourceReferenceLabel(providerType: SourceProviderType) {
  if (providerType === 'docker-registry') {
    return 'Image reference';
  }
  if (providerType === 'raw-compose') {
    return 'Raw source location';
  }
  return 'Repository URL or slug';
}

function normalizeRepositoryValue(value: string) {
  const normalized = value.trim().replace(/\.git$/i, '').replace(/\/+$/g, '');
  return normalized.toLowerCase();
}

function getRepositoryOptionValue(repository: GitConnectionRepository) {
  return repository.clone_url || repository.full_name || repository.name;
}

function repositoryMatches(repository: GitConnectionRepository, candidate: string) {
  const normalizedCandidate = normalizeRepositoryValue(candidate);
  if (!normalizedCandidate) {
    return false;
  }

  return [
    repository.id,
    repository.name,
    repository.full_name,
    repository.clone_url,
    repository.ssh_url,
    repository.web_url,
  ]
    .filter(Boolean)
    .some((value) => normalizeRepositoryValue(value) === normalizedCandidate);
}

export function GeneralTab({ project, app, environment, onOpenAppDetails, onOpenTerminal }: GeneralTabProps) {
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState<DeploymentSettingsFormState>(defaultSettings);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const deferredSourceReference = useDeferredValue(settings.sourceReference.trim());

  const { data: sourceSettingsResponse, isLoading: sourceSettingsLoading } = useQuery({
    queryKey: ['app-source-settings', app?.id],
    queryFn: () => getAppSourceSettings(app!.id),
    enabled: app !== null,
  });

  useEffect(() => {
    if (!app) {
      setSettings(defaultSettings);
      return;
    }

    setSettings(buildSettingsFromApp(app, sourceSettingsResponse?.data || null));
  }, [app, sourceSettingsResponse?.data]);

  const { data: deployments = [], isLoading: deploymentsLoading } = useQuery({
    queryKey: ['deployments', app?.id],
    queryFn: async () => {
      const response = await getDeployments({ appId: app!.id });
      return response.data || [];
    },
    select: (value) => normalizeApiList(value),
    enabled: app !== null,
  });

  const { data: appServices = [], isLoading: servicesLoading } = useQuery({
    queryKey: ['project-services', project.id, app?.id ?? 'all'],
    queryFn: async () => {
      const response = await getProjectServices(project.id, app ? { appId: app.id } : undefined);
      return response.data || [];
    },
    enabled: app !== null,
  });

  const { data: organizationConnectionsResponse, isLoading: organizationConnectionsLoading } = useQuery({
    queryKey: ['organization-git-connections', project.organization?.id],
    queryFn: () => getOrganizationGitConnections({ organizationId: project.organization!.id }),
    enabled: app !== null && Boolean(project.organization?.id),
  });

  const { data: personalConnectionsResponse, isLoading: personalConnectionsLoading } = useQuery({
    queryKey: ['personal-git-connections'],
    queryFn: () => getPersonalGitConnections(),
    enabled: app !== null,
  });

  const availableGitConnections = useMemo<GitConnectionOption[]>(() => {
    const organizationConnections = (organizationConnectionsResponse?.data || []).map((connection) => ({
      scope: 'organization' as const,
      id: connection.id,
      name: connection.name,
      provider_type: connection.provider_type,
    }));
    const personalConnections = (personalConnectionsResponse?.data || []).map((connection) => ({
      scope: 'personal' as const,
      id: connection.id,
      name: connection.name,
      provider_type: connection.provider_type,
    }));

    return [...organizationConnections, ...personalConnections];
  }, [organizationConnectionsResponse?.data, personalConnectionsResponse?.data]);

  const matchingGitConnections = useMemo(
    () => availableGitConnections.filter((connection) => connection.provider_type === settings.providerType),
    [availableGitConnections, settings.providerType],
  );

  const selectedGitConnection = useMemo(
    () =>
      settings.connectionId !== null && settings.connectionScope
        ? availableGitConnections.find(
            (connection) => connection.id === settings.connectionId && connection.scope === settings.connectionScope,
          )
        : undefined,
    [availableGitConnections, settings.connectionId, settings.connectionScope],
  );

  const { data: repositoryDiscoveryResponse, isLoading: repositoriesLoading, error: repositoriesError } = useQuery({
    queryKey: ['git-connection-repositories', settings.connectionScope, settings.connectionId],
    queryFn: () => {
      if (!selectedGitConnection) {
        throw new Error('A Git connection is required before repository discovery can run.');
      }

      return selectedGitConnection.scope === 'organization'
        ? getOrganizationGitConnectionRepositories(selectedGitConnection.id)
        : getPersonalGitConnectionRepositories(selectedGitConnection.id);
    },
    enabled: app !== null && isGitProvider(settings.providerType) && Boolean(selectedGitConnection),
  });

  const discoveredRepositories = repositoryDiscoveryResponse?.data?.repositories || [];

  const selectedDiscoveredRepository = useMemo(
    () => discoveredRepositories.find((repository) => repositoryMatches(repository, settings.sourceReference)),
    [discoveredRepositories, settings.sourceReference],
  );

  const deferredSelectedRepository = useDeferredValue(
    selectedDiscoveredRepository ? getRepositoryOptionValue(selectedDiscoveredRepository) : '',
  );

  const { data: branchDiscoveryResponse, isLoading: branchesLoading, error: branchesError } = useQuery({
    queryKey: ['git-connection-branches', settings.connectionScope, settings.connectionId, deferredSelectedRepository],
    queryFn: () => {
      if (!selectedGitConnection) {
        throw new Error('A Git connection is required before branch discovery can run.');
      }

      return selectedGitConnection.scope === 'organization'
        ? getOrganizationGitConnectionBranches(selectedGitConnection.id, deferredSelectedRepository)
        : getPersonalGitConnectionBranches(selectedGitConnection.id, deferredSelectedRepository);
    },
    enabled:
      app !== null &&
      isGitProvider(settings.providerType) &&
      Boolean(selectedGitConnection) &&
      Boolean(deferredSelectedRepository),
  });

  const discoveredBranches = branchDiscoveryResponse?.data?.branches || [];

  useEffect(() => {
    if (!isGitProvider(settings.providerType)) {
      if (settings.connectionId !== null || settings.connectionScope || settings.connectionName) {
        setSettings((current) => ({
          ...current,
          connectionScope: '',
          connectionId: null,
          connectionName: '',
        }));
      }
      return;
    }

    if (
      settings.connectionId !== null &&
      settings.connectionScope &&
      !matchingGitConnections.some(
        (connection) => connection.id === settings.connectionId && connection.scope === settings.connectionScope,
      )
    ) {
      setSettings((current) => ({
        ...current,
        connectionScope: '',
        connectionId: null,
        connectionName: '',
      }));
    }
  }, [matchingGitConnections, settings.connectionId, settings.connectionName, settings.connectionScope, settings.providerType]);

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      const normalizedWatchPaths = settings.watchPaths
        .split('\n')
        .map((value) => value.trim())
        .filter(Boolean);
      const selectedConnection =
        settings.connectionId !== null && settings.connectionScope
          ? availableGitConnections.find(
              (connection) => connection.id === settings.connectionId && connection.scope === settings.connectionScope,
            )
          : undefined;

      await updateApp(app!.id, {
        repository_url: settings.sourceReference.trim() || undefined,
        compose_path: settings.composePath.trim() || undefined,
        config: {
          ...app!.config,
          deploymentSettings: {
            ...settings,
            connectionName: selectedConnection?.name || '',
            watchPaths: settings.watchPaths,
            organizationConnectionName:
              settings.connectionScope === 'organization' ? selectedConnection?.name || settings.connectionName : '',
          },
        },
      });

      await updateAppSourceSettings(app!.id, {
        connection_scope: isGitProvider(settings.providerType) ? settings.connectionScope : '',
        organization_connection_id:
          isGitProvider(settings.providerType) && settings.connectionScope === 'organization' ? settings.connectionId : null,
        personal_connection_id:
          isGitProvider(settings.providerType) && settings.connectionScope === 'personal' ? settings.connectionId : null,
        source_provider: settings.providerType,
        source_ref: settings.sourceRef.trim() || 'main',
        watch_paths: normalizedWatchPaths,
        trigger_type: settings.triggerType,
        auto_deploy_enabled: settings.autoDeployEnabled,
        submodules_enabled: settings.submodulesEnabled,
        schedule: settings.schedule.trim(),
      });
    },
    onSuccess: () => {
      if (environment) {
        queryClient.invalidateQueries({ queryKey: ['apps', environment.id] });
      }
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      queryClient.invalidateQueries({ queryKey: ['app-source-settings', app!.id] });
      toast({ title: 'General settings saved', description: 'Deployment source settings were updated.' });
    },
    onError: (error) => {
      toast({
        title: 'Save failed',
        description: error instanceof Error ? error.message : 'Unable to save deployment settings.',
        variant: 'destructive',
      });
    },
  });

  const deployMutation = useMutation({
    mutationFn: () =>
      createDeployment({
        app_id: app!.id,
        version: `manual-${new Date().toISOString()}`,
        status: 'pending',
        trigger_type: 'manual',
        source_ref: settings.sourceRef.trim() || undefined,
        compose_path: settings.composePath.trim() || undefined,
        notes: `Manual deploy requested from General tab using ${settings.providerType}.`,
        config_snapshot: {
          deploymentSettings: settings,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments', app!.id] });
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      toast({ title: 'Deployment queued', description: 'A deployment record has been created for this app.' });
    },
    onError: (error) => {
      toast({
        title: 'Deploy failed',
        description: error instanceof Error ? error.message : 'Unable to create a deployment record.',
        variant: 'destructive',
      });
    },
  });

  const reloadMutation = useMutation({
    mutationFn: async () => {
      if (appServices.length === 0) {
        throw new Error('No services are attached to this app yet.');
      }

      await Promise.all(appServices.map((service) => restartService(service.id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id, app?.id ?? 'all'] });
      toast({ title: 'Services reloaded', description: 'All app services were restarted.' });
    },
    onError: (error) => {
      toast({
        title: 'Reload failed',
        description: error instanceof Error ? error.message : 'Unable to restart app services.',
        variant: 'destructive',
      });
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      if (appServices.length === 0) {
        throw new Error('No services are attached to this app yet.');
      }

      await Promise.all(appServices.map((service) => stopService(service.id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id, app?.id ?? 'all'] });
      toast({ title: 'Services stopping', description: 'App services are being stopped.' });
    },
    onError: (error) => {
      toast({
        title: 'Stop failed',
        description: error instanceof Error ? error.message : 'Unable to stop app services.',
        variant: 'destructive',
      });
    },
  });

  const previewData = useMemo(
    () => ({
      provider: settings.providerType,
      connection: settings.connectionName || 'Not configured',
      connectionScope: settings.connectionScope || 'none',
      sourceReference: settings.sourceReference || 'Not configured',
      sourceRef: settings.sourceRef || 'main',
      composePath: settings.composePath || './docker-compose.yml',
      watchPaths: settings.watchPaths
        .split('\n')
        .map((value) => value.trim())
        .filter(Boolean),
      triggerType: settings.triggerType,
      autoDeployEnabled: settings.autoDeployEnabled,
      submodulesEnabled: settings.submodulesEnabled,
      schedule: settings.triggerType === 'schedule' ? settings.schedule : null,
    }),
    [settings],
  );

  if (!app) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>Select an application to configure deployment and source controls.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const recentDeployments = deployments.slice(0, 10);
  const gitConnectionValue = settings.connectionScope && settings.connectionId !== null
    ? `${settings.connectionScope}:${settings.connectionId}`
    : 'none';
  const discoveredRepositoryValue = selectedDiscoveredRepository
    ? getRepositoryOptionValue(selectedDiscoveredRepository)
    : 'manual';
  const discoveredBranchValue = discoveredBranches.some((branch) => branch.name === settings.sourceRef)
    ? settings.sourceRef
    : 'manual';
  const gitConnectionsLoading = organizationConnectionsLoading || personalConnectionsLoading;
  const selectedConnectionLabel = settings.connectionName || 'Not configured';
  const repositoryDiscoveryMessage = repositoriesLoading
    ? 'Loading repositories from the selected Git connection...'
    : repositoriesError instanceof Error
      ? repositoriesError.message
      : discoveredRepositories.length === 0
        ? 'No repositories were returned for this connection. Manual repository entry still works.'
        : selectedDiscoveredRepository
          ? `Selected repository default branch: ${selectedDiscoveredRepository.default_branch || 'unknown'}`
          : 'Choose a discovered repository to autofill the source URL, or keep using a manual value.';
  const branchDiscoveryMessage = branchesLoading
    ? 'Loading branches for the selected repository...'
    : branchesError instanceof Error
      ? branchesError.message
      : discoveredBranches.length === 0
        ? 'No branches were returned for this repository. Manual branch entry still works.'
        : `Default branch: ${branchDiscoveryResponse?.data?.default_branch || 'unknown'}`;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <Server className="h-5 w-5" />
                {app.name}
              </CardTitle>
              <CardDescription>
                App-scoped deployment source controls now live here. Each app can point at either a shared team connection or a personal Git credential.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={onOpenAppDetails}>
                <Settings className="mr-2 h-4 w-4" />
                App details
              </Button>
              <Button size="sm" onClick={() => deployMutation.mutate()} disabled={deployMutation.isPending}>
                {deployMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Rocket className="mr-2 h-4 w-4" />}
                Deploy
              </Button>
              <Button variant="outline" size="sm" onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending || appServices.length === 0}>
                {reloadMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlugZap className="mr-2 h-4 w-4" />}
                Reload
              </Button>
              <Button variant="outline" size="sm" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || appServices.length === 0}>
                {stopMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Square className="mr-2 h-4 w-4" />}
                Stop
              </Button>
              <Button variant="outline" size="sm" onClick={onOpenTerminal}>
                <Terminal className="mr-2 h-4 w-4" />
                Open terminal
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Environment: {environment?.name || 'Unknown environment'}</Badge>
          <Badge variant="secondary">Source type: {app.source_type}</Badge>
          <Badge variant="secondary">Status: {app.status}</Badge>
          <Badge variant="secondary">Services: {servicesLoading ? 'Loading' : appServices.length}</Badge>
          <Badge variant="secondary">Source settings: {sourceSettingsLoading ? 'Loading' : 'Ready'}</Badge>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <FolderGit2 className="h-5 w-5" />
              Core Deployment & Git Integration
            </CardTitle>
            <CardDescription>
              Configure provider, repository, branch, compose path, triggers, and autodeploy. Connection selection is persisted as app source-of-truth.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider-type">Source provider</Label>
                <Select
                  value={settings.providerType}
                  onValueChange={(value) => setSettings((current) => ({ ...current, providerType: value as SourceProviderType }))}
                >
                  <SelectTrigger id="provider-type">
                    <SelectValue placeholder="Choose provider" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="github">GitHub</SelectItem>
                    <SelectItem value="gitlab">GitLab</SelectItem>
                    <SelectItem value="bitbucket">Bitbucket</SelectItem>
                    <SelectItem value="gitea">Gitea</SelectItem>
                    <SelectItem value="generic-git">Generic Git</SelectItem>
                    <SelectItem value="raw-compose">Raw compose / Dockerfile</SelectItem>
                    <SelectItem value="docker-registry">Docker registry / Docker Hub</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="connection-name">Git connection</Label>
                <Select
                  value={gitConnectionValue}
                  onValueChange={(value) => {
                    if (value === 'none') {
                      setSettings((current) => ({
                        ...current,
                        connectionScope: '',
                        connectionId: null,
                        connectionName: '',
                      }));
                      return;
                    }

                    const [scope, rawId] = value.split(':');
                    const connectionScope = scope as GitConnectionScope;
                    const connectionId = Number(rawId);
                    const selectedConnection = availableGitConnections.find(
                      (connection) => connection.scope === connectionScope && connection.id === connectionId,
                    );

                    setSettings((current) => ({
                      ...current,
                      connectionScope,
                      connectionId,
                      connectionName: selectedConnection?.name || '',
                    }));
                  }}
                  disabled={!isGitProvider(settings.providerType) || gitConnectionsLoading}
                >
                  <SelectTrigger id="connection-name">
                    <SelectValue
                      placeholder={
                        !isGitProvider(settings.providerType)
                          ? 'Not required for this source provider'
                          : gitConnectionsLoading
                            ? 'Loading Git connections...'
                            : 'Choose a shared or personal connection'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No connection selected</SelectItem>
                    {matchingGitConnections.map((connection) => (
                      <SelectItem key={`${connection.scope}:${connection.id}`} value={`${connection.scope}:${connection.id}`}>
                        {connection.scope === 'organization' ? '[Shared]' : '[Personal]'} {connection.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {isGitProvider(settings.providerType) ? (
                  <p className="text-xs text-muted-foreground">
                    {matchingGitConnections.length === 0
                      ? 'No matching Git connections exist for this provider yet. Add one from organization settings.'
                      : `Current selection: ${selectedConnectionLabel}`}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="source-reference">{getSourceReferenceLabel(settings.providerType)}</Label>
                <Input
                  id="source-reference"
                  value={settings.sourceReference}
                  onChange={(event) => setSettings((current) => ({ ...current, sourceReference: event.target.value }))}
                  placeholder="org/repo, clone URL, image:tag, or raw file location"
                />
              </div>

              {isGitProvider(settings.providerType) && selectedGitConnection ? (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="discovered-repository">Discovered repositories</Label>
                  <Select
                    value={discoveredRepositoryValue}
                    onValueChange={(value) => {
                      if (value === 'manual') {
                        return;
                      }

                      const repository = discoveredRepositories.find(
                        (candidate) => getRepositoryOptionValue(candidate) === value,
                      );
                      if (!repository) {
                        return;
                      }

                      setSettings((current) => ({
                        ...current,
                        sourceReference: getRepositoryOptionValue(repository),
                        sourceRef: repository.default_branch || current.sourceRef || 'main',
                      }));
                    }}
                    disabled={repositoriesLoading || discoveredRepositories.length === 0}
                  >
                    <SelectTrigger id="discovered-repository">
                      <SelectValue placeholder="Choose a discovered repository" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="manual">Keep manual repository value</SelectItem>
                      {discoveredRepositories.map((repository) => (
                        <SelectItem
                          key={`${repository.id}:${getRepositoryOptionValue(repository)}`}
                          value={getRepositoryOptionValue(repository)}
                        >
                          {repository.full_name || repository.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{repositoryDiscoveryMessage}</p>
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="source-ref">Branch / source ref</Label>
                <Input
                  id="source-ref"
                  value={settings.sourceRef}
                  onChange={(event) => setSettings((current) => ({ ...current, sourceRef: event.target.value }))}
                  placeholder="main"
                />
                {isGitProvider(settings.providerType) && selectedGitConnection && !selectedDiscoveredRepository ? (
                  <p className="text-xs text-muted-foreground">
                    Choose one of the discovered repositories to browse branches, or keep entering a branch manually.
                  </p>
                ) : null}
              </div>

              <div className="space-y-2">
                <Label htmlFor="compose-path">Compose path</Label>
                <Input
                  id="compose-path"
                  value={settings.composePath}
                  onChange={(event) => setSettings((current) => ({ ...current, composePath: event.target.value }))}
                  placeholder="./docker-compose.yml"
                />
              </div>

              {selectedDiscoveredRepository ? (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="discovered-branch">Discovered branches</Label>
                  <Select
                    value={discoveredBranchValue}
                    onValueChange={(value) => {
                      if (value === 'manual') {
                        return;
                      }

                      setSettings((current) => ({ ...current, sourceRef: value }));
                    }}
                    disabled={branchesLoading || discoveredBranches.length === 0}
                  >
                    <SelectTrigger id="discovered-branch">
                      <SelectValue placeholder="Choose a discovered branch" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="manual">Keep manual branch value</SelectItem>
                      {discoveredBranches.map((branch: GitConnectionBranch) => (
                        <SelectItem key={branch.name} value={branch.name}>
                          {branch.is_default ? `[Default] ${branch.name}` : branch.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{branchDiscoveryMessage}</p>
                </div>
              ) : null}

              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="watch-paths">Watch paths</Label>
                <Textarea
                  id="watch-paths"
                  value={settings.watchPaths}
                  onChange={(event) => setSettings((current) => ({ ...current, watchPaths: event.target.value }))}
                  placeholder={"src/**\ncompose/**"}
                  rows={4}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="trigger-type">Trigger type</Label>
                <Select
                  value={settings.triggerType}
                  onValueChange={(value) => setSettings((current) => ({ ...current, triggerType: value as TriggerType }))}
                >
                  <SelectTrigger id="trigger-type">
                    <SelectValue placeholder="Choose trigger" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual deploy</SelectItem>
                    <SelectItem value="push">On push</SelectItem>
                    <SelectItem value="schedule">Schedule</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="schedule">Schedule</Label>
                <Input
                  id="schedule"
                  value={settings.schedule}
                  onChange={(event) => setSettings((current) => ({ ...current, schedule: event.target.value }))}
                  placeholder="0 */6 * * *"
                  disabled={settings.triggerType !== 'schedule'}
                />
              </div>
            </div>

            <div className="grid gap-4 rounded-lg border border-border/80 bg-muted/20 p-4 md:grid-cols-2">
              <div className="flex items-center justify-between gap-3 rounded-lg border bg-background px-4 py-3">
                <div>
                  <div className="text-sm font-medium">Autodeploy</div>
                  <div className="text-xs text-muted-foreground">Toggle automatic deployments for matching triggers.</div>
                </div>
                <Switch
                  checked={settings.autoDeployEnabled}
                  onCheckedChange={(checked) => setSettings((current) => ({ ...current, autoDeployEnabled: checked }))}
                />
              </div>

              <div className="flex items-center justify-between gap-3 rounded-lg border bg-background px-4 py-3">
                <div>
                  <div className="text-sm font-medium">Git submodules</div>
                  <div className="text-xs text-muted-foreground">Pull submodules during deployment preparation.</div>
                </div>
                <Switch
                  checked={settings.submodulesEnabled}
                  onCheckedChange={(checked) => setSettings((current) => ({ ...current, submodulesEnabled: checked }))}
                />
              </div>
            </div>

            <div className="rounded-lg border border-dashed border-border/80 bg-background px-4 py-3 text-sm text-muted-foreground">
              The selected connection becomes the app source-of-truth for future AIEditor commit-back and deploy-from-source flows. Use a shared connection for team-owned repos and a personal connection for user-owned credentials.
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => saveSettingsMutation.mutate()} disabled={saveSettingsMutation.isPending}>
                {saveSettingsMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Save General settings
              </Button>
              <Button variant="outline" onClick={() => setIsPreviewOpen(true)}>
                <Eye className="mr-2 h-4 w-4" />
                Preview Compose
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Clock3 className="h-5 w-5" />
                Webhooks & build queue
              </CardTitle>
              <CardDescription>
                The queue control shell is ready here. Webhook URLs, cancel queue, kill build, and live logs still need the next backend slice.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="webhook-url">Webhook URL</Label>
                <Input id="webhook-url" value="Pending backend support" readOnly />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" disabled>
                  Cancel queue
                </Button>
                <Button variant="outline" size="sm" disabled>
                  Kill build
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Rocket className="h-5 w-5" />
                Last 10 deployments
              </CardTitle>
              <CardDescription>Recent deployment history for this app. Real-time build logs will connect here in the next backend slice.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {deploymentsLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading deployments...
                </div>
              ) : recentDeployments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deployments exist for this app yet.</p>
              ) : (
                recentDeployments.map((deployment) => (
                  <div key={deployment.id} className="rounded-lg border border-border bg-background p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold">{deployment.version}</div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {deployment.source_ref || 'manual'} • {deployment.trigger_type}
                        </div>
                      </div>
                      <Badge variant={deployment.status === 'succeeded' ? 'default' : 'outline'}>
                        {deployment.status.replace(/_/g, ' ')}
                      </Badge>
                    </div>
                    <div className="mt-3 text-xs text-muted-foreground">
                      {new Date(deployment.created_at).toLocaleString()}
                    </div>
                    {deployment.notes ? <p className="mt-3 text-sm text-muted-foreground">{deployment.notes}</p> : null}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Compose preview</DialogTitle>
            <DialogDescription>
              This preview shows the current deployment source settings that will feed the compose/runtime pipeline.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-[420px] overflow-auto rounded-lg border border-border bg-muted/30 p-4 text-xs">
{JSON.stringify(previewData, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
