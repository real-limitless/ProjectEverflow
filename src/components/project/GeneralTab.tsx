import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
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
  AppSourceKind,
  AppSourceProviderType,
  AppSourceSettings,
  cloneWorkspaceFromSource,
  createDeployment,
  GitConnectionBranch,
  GitConnectionRepository,
  getAppSourceDiscovery,
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
import { buildOrganizationSettingsPath } from '@/lib/organizationPaths';

type SourceProviderType = AppSourceProviderType;
type SourceKind = AppSourceKind;

type TriggerType = 'manual' | 'push' | 'schedule';

const HOSTED_REPOSITORY_BROWSING_PROVIDERS: SourceProviderType[] = ['github', 'gitlab', 'bitbucket', 'gitea'];
const RAW_SOURCE_KINDS: SourceKind[] = ['raw-compose', 'raw-dockerfile'];

interface DeploymentSettingsFormState {
  providerType: SourceProviderType;
  sourceKind: SourceKind;
  connectionScope: GitConnectionScope | '';
  connectionId: number | null;
  connectionName: string;
  sourceLocation: string;
  sourceRef: string;
  composePath: string;
  buildContextPath: string;
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
  sourceKind: 'git-repository',
  connectionScope: '',
  connectionId: null,
  connectionName: '',
  sourceLocation: '',
  sourceRef: 'main',
  composePath: './docker-compose.yml',
  buildContextPath: '.',
  watchPaths: 'src/**',
  triggerType: 'manual',
  autoDeployEnabled: false,
  submodulesEnabled: false,
  schedule: '0 */6 * * *',
};

function isGitSourceKind(sourceKind: SourceKind) {
  return sourceKind === 'git-repository';
}

function supportsRepositoryBrowsing(providerType: SourceProviderType) {
  return HOSTED_REPOSITORY_BROWSING_PROVIDERS.includes(providerType);
}

function getAllowedSourceKinds(providerType: SourceProviderType): SourceKind[] {
  if (providerType === 'raw-compose') {
    return RAW_SOURCE_KINDS;
  }
  if (providerType === 'docker-registry') {
    return ['container-image'];
  }
  return ['git-repository'];
}

function getDefaultSourceKind(providerType: SourceProviderType, currentSourceKind?: SourceKind): SourceKind {
  if (providerType === 'raw-compose' && currentSourceKind === 'raw-dockerfile') {
    return 'raw-dockerfile';
  }
  return getAllowedSourceKinds(providerType)[0];
}

function normalizeTriggerTypeForKind(sourceKind: SourceKind, triggerType: TriggerType): TriggerType {
  if (!isGitSourceKind(sourceKind) && triggerType === 'push') {
    return 'manual';
  }
  return triggerType;
}

function getDefaultSourceRef(sourceKind: SourceKind, currentValue: string, previousSourceKind?: SourceKind) {
  const trimmedValue = currentValue.trim();

  if (sourceKind === 'container-image') {
    return previousSourceKind === 'container-image' ? trimmedValue || 'latest' : 'latest';
  }
  if (sourceKind === 'git-repository') {
    return previousSourceKind === 'git-repository' ? trimmedValue || 'main' : 'main';
  }
  return '';
}

function splitWatchPaths(value: string) {
  return value
    .split('\n')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function splitContainerImageReference(value: string, fallbackRef = '') {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    return { sourceLocation: '', sourceRef: fallbackRef || 'latest' };
  }

  if (trimmedValue.includes('@')) {
    return { sourceLocation: trimmedValue, sourceRef: fallbackRef || 'latest' };
  }

  const lastSlashIndex = trimmedValue.lastIndexOf('/');
  const lastColonIndex = trimmedValue.lastIndexOf(':');
  if (lastColonIndex > lastSlashIndex) {
    return {
      sourceLocation: trimmedValue.slice(0, lastColonIndex),
      sourceRef: fallbackRef || trimmedValue.slice(lastColonIndex + 1) || 'latest',
    };
  }

  return { sourceLocation: trimmedValue, sourceRef: fallbackRef || 'latest' };
}

function normalizeRegistryRepositoryValue(value: string) {
  const { sourceLocation } = splitContainerImageReference(value, '');
  const normalizedValue = sourceLocation.trim().replace(/^docker\.io\//i, '').replace(/\/+$/g, '').toLowerCase();
  if (!normalizedValue) {
    return '';
  }
  return normalizedValue.includes('/') ? normalizedValue : `library/${normalizedValue}`;
}

function resolveSourceKind(
  providerType: SourceProviderType,
  sourceKind?: SourceKind | null,
  buildContextPath?: string,
): SourceKind {
  if (sourceKind && getAllowedSourceKinds(providerType).includes(sourceKind)) {
    return sourceKind;
  }
  if (providerType === 'raw-compose' && buildContextPath) {
    return 'raw-dockerfile';
  }
  return getDefaultSourceKind(providerType, sourceKind || undefined);
}

function getSourceKindLabel(sourceKind: SourceKind) {
  if (sourceKind === 'container-image') {
    return 'Container image';
  }
  if (sourceKind === 'raw-dockerfile') {
    return 'Raw Dockerfile';
  }
  if (sourceKind === 'raw-compose') {
    return 'Raw compose';
  }
  return 'Git repository';
}

function getSourceLocationLabel(providerType: SourceProviderType, sourceKind: SourceKind) {
  if (sourceKind === 'container-image') {
    return 'Image repository';
  }
  if (sourceKind === 'raw-dockerfile') {
    return 'Dockerfile URL or location';
  }
  if (sourceKind === 'raw-compose') {
    return 'Compose file URL or location';
  }
  if (providerType === 'generic-git') {
    return 'Repository URL or slug';
  }
  return 'Repository URL or slug';
}

function getSourceLocationPlaceholder(providerType: SourceProviderType, sourceKind: SourceKind) {
  if (sourceKind === 'container-image') {
    return 'library/nginx or ghcr.io/team/image';
  }
  if (sourceKind === 'raw-dockerfile') {
    return 'https://example.com/Dockerfile';
  }
  if (sourceKind === 'raw-compose') {
    return 'https://example.com/docker-compose.yml';
  }
  if (providerType === 'generic-git') {
    return 'git@example.com:team/repo.git';
  }
  return 'org/repo or clone URL';
}

function getSourceRefLabel(sourceKind: SourceKind) {
  if (sourceKind === 'container-image') {
    return 'Image tag';
  }
  return 'Branch / source ref';
}

function buildSettingsFromApp(app: ProjectApp, sourceSettings?: AppSourceSettings | null): DeploymentSettingsFormState {
  const config = app.config?.deploymentSettings as
    | (Partial<DeploymentSettingsFormState> & {
        organizationConnectionName?: string;
        sourceKind?: SourceKind;
        sourceLocation?: string;
        sourceReference?: string;
        buildContextPath?: string;
        watchPaths?: string | string[];
      })
    | undefined;
  const rawConnectionId = config?.connectionId;
  const connectionId = typeof rawConnectionId === 'number' ? rawConnectionId : null;
  const legacyConnectionName = (config as { organizationConnectionName?: string } | undefined)?.organizationConnectionName || '';
  const providerType = sourceSettings?.source_provider || config?.providerType || 'github';
  const sourceKind = resolveSourceKind(
    providerType,
    sourceSettings?.source_kind || config?.sourceKind || null,
    sourceSettings?.build_context_path || config?.buildContextPath || '',
  );
  const rawSourceLocation = sourceSettings
    ? sourceSettings.source_location
      || (isGitSourceKind(sourceKind) || sourceKind === 'container-image'
        ? sourceSettings.repository_url || app.repository_url || ''
        : sourceSettings.compose_path || app.compose_path || '')
    : config?.sourceLocation
      || config?.sourceReference
      || (isGitSourceKind(sourceKind) || sourceKind === 'container-image' ? app.repository_url || '' : app.compose_path || '');

  const resolvedContainerSource = sourceKind === 'container-image'
    ? splitContainerImageReference(rawSourceLocation, sourceSettings?.source_ref || config?.sourceRef || '')
    : null;
  const normalizedWatchPaths = sourceSettings
    ? sourceSettings.watch_paths
    : Array.isArray(config?.watchPaths)
      ? config.watchPaths
      : typeof config?.watchPaths === 'string'
        ? splitWatchPaths(config.watchPaths)
        : [];

  if (sourceSettings) {
    const selectedConnectionId = sourceSettings.connection_scope === 'organization'
      ? sourceSettings.organization_connection ?? null
      : sourceSettings.connection_scope === 'personal'
        ? sourceSettings.personal_connection ?? null
        : null;

    return {
      providerType,
      sourceKind,
      connectionScope: sourceSettings.connection_scope || '',
      connectionId: selectedConnectionId,
      connectionName: sourceSettings.selected_connection_name || '',
      sourceLocation: resolvedContainerSource ? resolvedContainerSource.sourceLocation : rawSourceLocation,
      sourceRef: isGitSourceKind(sourceKind)
        ? sourceSettings.source_ref || 'main'
        : sourceKind === 'container-image'
          ? resolvedContainerSource?.sourceRef || 'latest'
          : '',
      composePath: isGitSourceKind(sourceKind)
        ? sourceSettings.compose_path || app.compose_path || './docker-compose.yml'
        : config?.composePath || './docker-compose.yml',
      buildContextPath: sourceKind === 'raw-dockerfile'
        ? sourceSettings.build_context_path || config?.buildContextPath || '.'
        : '',
      watchPaths: isGitSourceKind(sourceKind) ? normalizedWatchPaths.join('\n') : '',
      triggerType: normalizeTriggerTypeForKind(sourceKind, sourceSettings.trigger_type || 'manual'),
      autoDeployEnabled: Boolean(sourceSettings.auto_deploy_enabled),
      submodulesEnabled: isGitSourceKind(sourceKind) ? Boolean(sourceSettings.submodules_enabled) : false,
      schedule: sourceSettings.schedule || '0 */6 * * *',
    };
  }

  return {
    providerType,
    sourceKind,
    connectionScope: config?.connectionScope || (connectionId !== null ? 'organization' : ''),
    connectionId,
    connectionName: config?.connectionName || legacyConnectionName,
    sourceLocation: resolvedContainerSource ? resolvedContainerSource.sourceLocation : rawSourceLocation,
    sourceRef: isGitSourceKind(sourceKind)
      ? config?.sourceRef || 'main'
      : sourceKind === 'container-image'
        ? resolvedContainerSource?.sourceRef || 'latest'
        : '',
    composePath: config?.composePath || app.compose_path || './docker-compose.yml',
    buildContextPath: sourceKind === 'raw-dockerfile' ? config?.buildContextPath || '.' : '',
    watchPaths: isGitSourceKind(sourceKind) ? normalizedWatchPaths.join('\n') : '',
    triggerType: normalizeTriggerTypeForKind(sourceKind, (config?.triggerType as TriggerType | undefined) || 'manual'),
    autoDeployEnabled: Boolean(config?.autoDeployEnabled),
    submodulesEnabled: isGitSourceKind(sourceKind) ? Boolean(config?.submodulesEnabled) : false,
    schedule: config?.schedule || '0 */6 * * *',
  };
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
  const [cloneConfirmOpen, setCloneConfirmOpen] = useState(false);
  const [registrySearch, setRegistrySearch] = useState('');
  const deferredRegistrySearch = useDeferredValue(registrySearch.trim());

  const { data: sourceSettingsResponse, isLoading: sourceSettingsLoading } = useQuery({
    queryKey: ['app-source-settings', app?.id],
    queryFn: () => getAppSourceSettings(app!.id),
    enabled: app !== null,
  });

  useEffect(() => {
    if (!app) {
      setSettings(defaultSettings);
      setRegistrySearch('');
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

  const canBrowseHostedRepositories = isGitSourceKind(settings.sourceKind) && supportsRepositoryBrowsing(settings.providerType);

  const { data: repositoryDiscoveryResponse, isLoading: repositoriesLoading, error: repositoriesError } = useQuery({
    queryKey: ['git-connection-repositories', settings.providerType, settings.connectionScope, settings.connectionId],
    queryFn: () => {
      if (!selectedGitConnection) {
        throw new Error('A Git connection is required before repository discovery can run.');
      }

      return selectedGitConnection.scope === 'organization'
        ? getOrganizationGitConnectionRepositories(selectedGitConnection.id)
        : getPersonalGitConnectionRepositories(selectedGitConnection.id);
    },
    enabled: app !== null && canBrowseHostedRepositories && Boolean(selectedGitConnection),
  });

  const discoveredRepositories = repositoryDiscoveryResponse?.data?.repositories || [];

  const selectedDiscoveredRepository = useMemo(
    () => discoveredRepositories.find((repository) => repositoryMatches(repository, settings.sourceLocation)),
    [discoveredRepositories, settings.sourceLocation],
  );

  const deferredSelectedRepository = useDeferredValue(
    selectedDiscoveredRepository ? getRepositoryOptionValue(selectedDiscoveredRepository) : '',
  );

  const { data: branchDiscoveryResponse, isLoading: branchesLoading, error: branchesError } = useQuery({
    queryKey: ['git-connection-branches', settings.providerType, settings.connectionScope, settings.connectionId, deferredSelectedRepository],
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
      canBrowseHostedRepositories &&
      Boolean(selectedGitConnection) &&
      Boolean(deferredSelectedRepository),
  });

  const discoveredBranches = branchDiscoveryResponse?.data?.branches || [];

  const { data: sourceDiscoveryResponse, isLoading: sourceDiscoveryLoading, error: sourceDiscoveryError } = useQuery({
    queryKey: [
      'app-source-discovery',
      app?.id,
      settings.providerType,
      settings.sourceKind,
      deferredRegistrySearch,
      settings.providerType === 'docker-registry' ? settings.sourceLocation.trim() : '',
    ],
    queryFn: () =>
      getAppSourceDiscovery(app!.id, {
        provider: settings.providerType,
        source_kind: settings.sourceKind,
        search: settings.providerType === 'docker-registry' && deferredRegistrySearch ? deferredRegistrySearch : undefined,
        repository: settings.providerType === 'docker-registry' ? settings.sourceLocation.trim() || undefined : undefined,
      }),
    enabled:
      app !== null
      && (settings.providerType === 'generic-git'
        || settings.providerType === 'raw-compose'
        || settings.providerType === 'docker-registry'),
  });

  const sourceDiscovery = sourceDiscoveryResponse?.data || null;
  const discoveredRegistryRepositories = sourceDiscovery?.repositories || [];
  const discoveredRegistryTags = sourceDiscovery?.tags || [];
  const selectedRegistryRepository = useMemo(
    () =>
      discoveredRegistryRepositories.find(
        (repository) => normalizeRegistryRepositoryValue(repository.full_name) === normalizeRegistryRepositoryValue(settings.sourceLocation)
          || normalizeRegistryRepositoryValue(repository.name) === normalizeRegistryRepositoryValue(settings.sourceLocation),
      ),
    [discoveredRegistryRepositories, settings.sourceLocation],
  );

  useEffect(() => {
    if (settings.providerType !== 'docker-registry' && registrySearch) {
      setRegistrySearch('');
    }
  }, [registrySearch, settings.providerType]);

  useEffect(() => {
    if (!isGitSourceKind(settings.sourceKind)) {
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
  }, [matchingGitConnections, settings.connectionId, settings.connectionName, settings.connectionScope, settings.sourceKind]);

  const cloneWorkspaceMutation = useMutation({
    mutationFn: async () => {
      const result = await cloneWorkspaceFromSource(project.id, {
        git_url: settings.sourceLocation.trim(),
        branch: settings.sourceRef.trim() || undefined,
        connection_scope: (settings.connectionScope as GitConnectionScope) || undefined,
        connection_id: settings.connectionId ?? undefined,
      });
      if (!result.data) throw new Error(result.error || 'Clone failed');
      return result.data;
    },
    onSuccess: () => {
      toast({ title: 'Repository cloned', description: 'Workspace has been populated with the repository contents.' });
      setCloneConfirmOpen(false);
    },
    onError: (error: Error) => {
      toast({ title: 'Clone failed', description: error.message, variant: 'destructive' });
      setCloneConfirmOpen(false);
    },
  });

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      const normalizedWatchPaths = splitWatchPaths(settings.watchPaths);
      const normalizedSourceLocation = settings.sourceLocation.trim();
      const normalizedComposePath = settings.composePath.trim();
      const normalizedBuildContextPath = settings.sourceKind === 'raw-dockerfile'
        ? settings.buildContextPath.trim() || '.'
        : '';
      const normalizedSourceRef = isGitSourceKind(settings.sourceKind)
        ? settings.sourceRef.trim() || 'main'
        : settings.sourceKind === 'container-image'
          ? settings.sourceRef.trim() || 'latest'
          : '';
      const normalizedTriggerType = normalizeTriggerTypeForKind(settings.sourceKind, settings.triggerType);
      const selectedConnection =
        settings.connectionId !== null && settings.connectionScope
          ? availableGitConnections.find(
              (connection) => connection.id === settings.connectionId && connection.scope === settings.connectionScope,
            )
          : undefined;
      const sourceSettingsUpdateResponse = await updateAppSourceSettings(app!.id, {
        connection_scope: isGitSourceKind(settings.sourceKind) ? settings.connectionScope : '',
        organization_connection_id:
          isGitSourceKind(settings.sourceKind) && settings.connectionScope === 'organization' ? settings.connectionId : null,
        personal_connection_id:
          isGitSourceKind(settings.sourceKind) && settings.connectionScope === 'personal' ? settings.connectionId : null,
        source_provider: settings.providerType,
        source_kind: settings.sourceKind,
        source_location: normalizedSourceLocation,
        build_context_path: normalizedBuildContextPath,
        source_ref: normalizedSourceRef,
        watch_paths: isGitSourceKind(settings.sourceKind) ? normalizedWatchPaths : [],
        trigger_type: normalizedTriggerType,
        auto_deploy_enabled: settings.autoDeployEnabled,
        submodules_enabled: isGitSourceKind(settings.sourceKind) ? settings.submodulesEnabled : false,
        schedule: settings.schedule.trim(),
      });

      const persistedSourceSettings = sourceSettingsUpdateResponse.data;
      const persistedSourceKind = persistedSourceSettings?.source_kind || settings.sourceKind;
      const persistedSourceLocation = persistedSourceSettings?.source_location || normalizedSourceLocation;
      const persistedSourceRef = persistedSourceSettings?.source_ref || normalizedSourceRef;
      const persistedBuildContextPath = persistedSourceSettings?.build_context_path || normalizedBuildContextPath;
      const persistedTriggerType = persistedSourceSettings?.trigger_type || normalizedTriggerType;
      const persistedWatchPaths = persistedSourceSettings?.watch_paths || (isGitSourceKind(persistedSourceKind) ? normalizedWatchPaths : []);
      const persistedSubmodulesEnabled = persistedSourceSettings?.submodules_enabled
        ?? (isGitSourceKind(persistedSourceKind) ? settings.submodulesEnabled : false);
      const legacyRepositoryUrl = isGitSourceKind(persistedSourceKind) || persistedSourceKind === 'container-image'
        ? persistedSourceLocation
        : '';
      const legacyComposePath = isGitSourceKind(persistedSourceKind)
        ? normalizedComposePath
        : RAW_SOURCE_KINDS.includes(persistedSourceKind)
          ? persistedSourceLocation
          : '';

      await updateApp(app!.id, {
        repository_url: legacyRepositoryUrl,
        compose_path: legacyComposePath,
        config: {
          ...app!.config,
          deploymentSettings: {
            ...settings,
            sourceKind: persistedSourceKind,
            sourceLocation: persistedSourceLocation,
            sourceReference: persistedSourceLocation,
            sourceRef: persistedSourceRef,
            composePath: normalizedComposePath,
            buildContextPath: persistedBuildContextPath,
            watchPaths: isGitSourceKind(persistedSourceKind) ? persistedWatchPaths.join('\n') : '',
            triggerType: persistedTriggerType,
            submodulesEnabled: persistedSubmodulesEnabled,
            connectionName: selectedConnection?.name || '',
            organizationConnectionName:
              settings.connectionScope === 'organization' ? selectedConnection?.name || settings.connectionName : '',
          },
        },
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
    mutationFn: () => {
      const normalizedSourceRef = isGitSourceKind(settings.sourceKind)
        ? settings.sourceRef.trim() || 'main'
        : settings.sourceKind === 'container-image'
          ? settings.sourceRef.trim() || 'latest'
          : undefined;
      const normalizedComposePath = isGitSourceKind(settings.sourceKind)
        ? settings.composePath.trim() || undefined
        : RAW_SOURCE_KINDS.includes(settings.sourceKind)
          ? settings.sourceLocation.trim() || undefined
          : undefined;

      return createDeployment({
        app_id: app!.id,
        version: `manual-${new Date().toISOString()}`,
        status: 'pending',
        trigger_type: 'manual',
        source_ref: normalizedSourceRef,
        compose_path: normalizedComposePath,
        notes: `Manual deploy requested from General tab using ${settings.providerType} (${settings.sourceKind}).`,
        config_snapshot: {
          deploymentSettings: settings,
        },
      });
    },
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
      sourceKind: settings.sourceKind,
      connection: settings.connectionName || 'Not configured',
      connectionScope: settings.connectionScope || 'none',
      sourceLocation: settings.sourceLocation || 'Not configured',
      sourceRef:
        isGitSourceKind(settings.sourceKind)
          ? settings.sourceRef || 'main'
          : settings.sourceKind === 'container-image'
            ? settings.sourceRef || 'latest'
            : null,
      composePath: isGitSourceKind(settings.sourceKind) ? settings.composePath || './docker-compose.yml' : null,
      buildContextPath: settings.sourceKind === 'raw-dockerfile' ? settings.buildContextPath || '.' : null,
      watchPaths: isGitSourceKind(settings.sourceKind) ? splitWatchPaths(settings.watchPaths) : [],
      triggerType: settings.triggerType,
      autoDeployEnabled: settings.autoDeployEnabled,
      submodulesEnabled: isGitSourceKind(settings.sourceKind) ? settings.submodulesEnabled : false,
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
  const sourceKindOptions = getAllowedSourceKinds(settings.providerType);
  const gitConnectionValue = settings.connectionScope && settings.connectionId !== null
    ? `${settings.connectionScope}:${settings.connectionId}`
    : 'none';
  const discoveredRepositoryValue = selectedDiscoveredRepository
    ? getRepositoryOptionValue(selectedDiscoveredRepository)
    : 'manual';
  const discoveredBranchValue = discoveredBranches.some((branch) => branch.name === settings.sourceRef)
    ? settings.sourceRef
    : 'manual';
  const discoveredRegistryRepositoryValue = selectedRegistryRepository ? selectedRegistryRepository.full_name : 'manual';
  const discoveredRegistryTagValue = discoveredRegistryTags.some((tag) => tag.name === settings.sourceRef)
    ? settings.sourceRef
    : 'manual';
  const gitConnectionsLoading = organizationConnectionsLoading || personalConnectionsLoading;
  const selectedConnectionLabel = settings.connectionName || 'Not configured';
  const sourceLocationLabel = getSourceLocationLabel(settings.providerType, settings.sourceKind);
  const sourceRefLabel = getSourceRefLabel(settings.sourceKind);
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
  const manualGuidanceMessage = sourceDiscoveryLoading
    ? 'Loading provider-specific source guidance...'
    : sourceDiscoveryError instanceof Error
      ? sourceDiscoveryError.message
      : sourceDiscovery?.lookup_error || sourceDiscovery?.manual_guidance || '';
  const registryRepositoryMessage = sourceDiscoveryLoading && deferredRegistrySearch
    ? 'Searching public Docker Hub repositories...'
    : sourceDiscovery?.lookup_error
      ? sourceDiscovery.lookup_error
      : discoveredRegistryRepositories.length === 0
        ? deferredRegistrySearch
          ? 'No public Docker Hub repositories matched that search. Manual image entry still works.'
          : 'Search public Docker Hub repositories or enter an image repository manually.'
        : selectedRegistryRepository
          ? `Selected repository: ${selectedRegistryRepository.full_name}`
          : 'Choose a discovered repository to fill the image name, or keep using manual entry.';
  const registryTagMessage = sourceDiscoveryLoading && settings.sourceLocation.trim()
    ? 'Loading tags for the selected image...'
    : sourceDiscovery?.lookup_error
      ? sourceDiscovery.lookup_error
      : discoveredRegistryTags.length === 0
        ? settings.sourceLocation.trim()
          ? 'No tags were returned for this image. Manual tag entry still works.'
          : 'Enter or select an image repository to browse tags.'
        : `Choose from ${discoveredRegistryTags.length} discovered tags or keep the tag manual.`;
  const publicRepositoryMessage = isGitSourceKind(settings.sourceKind) && supportsRepositoryBrowsing(settings.providerType) && !selectedGitConnection
    ? 'No saved connection is required for a public repository. Enter an HTTPS URL, an owner/repo slug, or a hosted git@ URL and the backend will normalize it for public clone access.'
    : isGitSourceKind(settings.sourceKind) && settings.providerType === 'generic-git' && !selectedGitConnection
      ? 'Enter any full HTTPS Git URL. No saved connection is required for public repositories.'
      : '';

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
              Configure provider, source kind, repository or image location, branch or tag, compose or build context, triggers, and autodeploy. Connection selection is persisted as app source-of-truth.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider-type">Source provider</Label>
                <Select
                  value={settings.providerType}
                  onValueChange={(value) => {
                    const nextProvider = value as SourceProviderType;
                    setSettings((current) => {
                      const nextSourceKind = getDefaultSourceKind(nextProvider, current.sourceKind);
                      return {
                        ...current,
                        providerType: nextProvider,
                        sourceKind: nextSourceKind,
                        sourceRef: getDefaultSourceRef(nextSourceKind, current.sourceRef, current.sourceKind),
                        triggerType: normalizeTriggerTypeForKind(nextSourceKind, current.triggerType),
                        buildContextPath: nextSourceKind === 'raw-dockerfile' ? current.buildContextPath || '.' : '',
                      };
                    });
                  }}
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
                <Label htmlFor="source-kind">Source kind</Label>
                <Select
                  value={settings.sourceKind}
                  onValueChange={(value) => {
                    const nextSourceKind = value as SourceKind;
                    setSettings((current) => ({
                      ...current,
                      sourceKind: nextSourceKind,
                      sourceRef: getDefaultSourceRef(nextSourceKind, current.sourceRef, current.sourceKind),
                      triggerType: normalizeTriggerTypeForKind(nextSourceKind, current.triggerType),
                      buildContextPath: nextSourceKind === 'raw-dockerfile' ? current.buildContextPath || '.' : '',
                    }));
                  }}
                  disabled={sourceKindOptions.length === 1}
                >
                  <SelectTrigger id="source-kind">
                    <SelectValue placeholder="Choose source kind" />
                  </SelectTrigger>
                  <SelectContent>
                    {sourceKindOptions.map((sourceKind) => (
                      <SelectItem key={sourceKind} value={sourceKind}>
                        {getSourceKindLabel(sourceKind)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {settings.providerType === 'raw-compose'
                    ? 'Choose whether this app consumes a raw compose file or a raw Dockerfile.'
                    : settings.sourceKind === 'container-image'
                      ? 'Container image sources persist repository and tag separately.'
                      : 'Git-backed providers persist repository location and source ref explicitly.'}
                </p>
              </div>

              <div className="space-y-2 md:col-span-2">
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
                  disabled={!isGitSourceKind(settings.sourceKind) || gitConnectionsLoading}
                >
                  <SelectTrigger id="connection-name">
                    <SelectValue
                      placeholder={
                        !isGitSourceKind(settings.sourceKind)
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
                {isGitSourceKind(settings.sourceKind) ? (
                  <p className="text-xs text-muted-foreground">
                    {matchingGitConnections.length === 0
                      ? (
                        <>
                          No matching Git connections exist for this provider.{' '}
                          <Link
                            to={buildOrganizationSettingsPath(project.organization?.id)}
                            className="underline underline-offset-2 hover:text-foreground"
                          >
                            Add one in Organization Settings →
                          </Link>
                        </>
                      )
                      : settings.providerType === 'generic-git'
                        ? `Current selection: ${selectedConnectionLabel}. Generic Git uses saved credentials but keeps repository and ref entry manual.`
                      : selectedGitConnection
                        ? `Current selection: ${selectedConnectionLabel}`
                        : 'Leave this empty to use a public repository without a saved connection.'}
                  </p>
                ) : null}
              </div>

              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="source-location">{sourceLocationLabel}</Label>
                <Input
                  id="source-location"
                  value={settings.sourceLocation}
                  onChange={(event) => setSettings((current) => ({ ...current, sourceLocation: event.target.value }))}
                  placeholder={getSourceLocationPlaceholder(settings.providerType, settings.sourceKind)}
                />
                {publicRepositoryMessage ? <p className="text-xs text-muted-foreground">{publicRepositoryMessage}</p> : null}
                {manualGuidanceMessage ? <p className="text-xs text-muted-foreground">{manualGuidanceMessage}</p> : null}
              </div>

              {canBrowseHostedRepositories && selectedGitConnection ? (
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
                        sourceLocation: getRepositoryOptionValue(repository),
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

              {settings.providerType === 'docker-registry' ? (
                <>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="registry-search">Search Docker Hub</Label>
                    <Input
                      id="registry-search"
                      value={registrySearch}
                      onChange={(event) => setRegistrySearch(event.target.value)}
                      placeholder="nginx, postgres, redis..."
                    />
                  </div>

                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="discovered-registry-repository">Docker Hub repositories</Label>
                    <Select
                      value={discoveredRegistryRepositoryValue}
                      onValueChange={(value) => {
                        if (value === 'manual') {
                          return;
                        }

                        const repository = discoveredRegistryRepositories.find((candidate) => candidate.full_name === value);
                        if (!repository) {
                          return;
                        }

                        setSettings((current) => ({
                          ...current,
                          sourceLocation: repository.full_name,
                          sourceRef: current.sourceRef || 'latest',
                        }));
                      }}
                      disabled={sourceDiscoveryLoading || discoveredRegistryRepositories.length === 0}
                    >
                      <SelectTrigger id="discovered-registry-repository">
                        <SelectValue placeholder="Choose a Docker Hub repository" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="manual">Keep manual image repository</SelectItem>
                        {discoveredRegistryRepositories.map((repository) => (
                          <SelectItem key={repository.full_name} value={repository.full_name}>
                            {repository.full_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{registryRepositoryMessage}</p>
                  </div>
                </>
              ) : null}

              {isGitSourceKind(settings.sourceKind) || settings.sourceKind === 'container-image' ? (
                <div className="space-y-2">
                  <Label htmlFor="source-ref">{sourceRefLabel}</Label>
                  <Input
                    id="source-ref"
                    value={settings.sourceRef}
                    onChange={(event) => setSettings((current) => ({ ...current, sourceRef: event.target.value }))}
                    placeholder={settings.sourceKind === 'container-image' ? 'latest' : 'main'}
                  />
                  {canBrowseHostedRepositories && selectedGitConnection && !selectedDiscoveredRepository ? (
                    <p className="text-xs text-muted-foreground">
                      Choose one of the discovered repositories to browse branches, or keep entering a branch manually.
                    </p>
                  ) : null}
                </div>
              ) : null}

              {isGitSourceKind(settings.sourceKind) ? (
                <div className="space-y-2">
                  <Label htmlFor="compose-path">Compose path</Label>
                  <Input
                    id="compose-path"
                    value={settings.composePath}
                    onChange={(event) => setSettings((current) => ({ ...current, composePath: event.target.value }))}
                    placeholder="./docker-compose.yml"
                  />
                </div>
              ) : null}

              {settings.sourceKind === 'raw-dockerfile' ? (
                <div className="space-y-2">
                  <Label htmlFor="build-context-path">Build context path</Label>
                  <Input
                    id="build-context-path"
                    value={settings.buildContextPath}
                    onChange={(event) => setSettings((current) => ({ ...current, buildContextPath: event.target.value }))}
                    placeholder="."
                  />
                </div>
              ) : null}

              {canBrowseHostedRepositories && selectedDiscoveredRepository ? (
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

              {settings.sourceKind === 'container-image' ? (
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="discovered-registry-tag">Discovered tags</Label>
                  <Select
                    value={discoveredRegistryTagValue}
                    onValueChange={(value) => {
                      if (value === 'manual') {
                        return;
                      }

                      setSettings((current) => ({ ...current, sourceRef: value }));
                    }}
                    disabled={sourceDiscoveryLoading || discoveredRegistryTags.length === 0}
                  >
                    <SelectTrigger id="discovered-registry-tag">
                      <SelectValue placeholder="Choose a discovered tag" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="manual">Keep manual tag value</SelectItem>
                      {discoveredRegistryTags.map((tag) => (
                        <SelectItem key={tag.full_name} value={tag.name}>
                          {tag.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{registryTagMessage}</p>
                </div>
              ) : null}

              {isGitSourceKind(settings.sourceKind) ? (
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
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="trigger-type">Trigger type</Label>
                <Select
                  value={settings.triggerType}
                  onValueChange={(value) =>
                    setSettings((current) => ({
                      ...current,
                      triggerType: normalizeTriggerTypeForKind(current.sourceKind, value as TriggerType),
                    }))}
                >
                  <SelectTrigger id="trigger-type">
                    <SelectValue placeholder="Choose trigger" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual deploy</SelectItem>
                    {isGitSourceKind(settings.sourceKind) ? <SelectItem value="push">On push</SelectItem> : null}
                    <SelectItem value="schedule">Schedule</SelectItem>
                  </SelectContent>
                </Select>
                {!isGitSourceKind(settings.sourceKind) ? (
                  <p className="text-xs text-muted-foreground">
                    Push triggers are not available for non-Git source kinds yet.
                  </p>
                ) : null}
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
                  <div className="text-xs text-muted-foreground">
                    {isGitSourceKind(settings.sourceKind)
                      ? 'Pull submodules during deployment preparation.'
                      : 'Available only for Git-backed source kinds.'}
                  </div>
                </div>
                <Switch
                  checked={isGitSourceKind(settings.sourceKind) ? settings.submodulesEnabled : false}
                  onCheckedChange={(checked) => setSettings((current) => ({ ...current, submodulesEnabled: checked }))}
                  disabled={!isGitSourceKind(settings.sourceKind)}
                />
              </div>
            </div>

            <div className="rounded-lg border border-dashed border-border/80 bg-background px-4 py-3 text-sm text-muted-foreground">
              {isGitSourceKind(settings.sourceKind)
                ? 'The selected connection becomes the app source-of-truth for future AIEditor commit-back and deploy-from-source flows. Use a shared connection for team-owned repos and a personal connection for user-owned credentials.'
                : settings.sourceKind === 'container-image'
                  ? 'Container-image sources now persist the image repository and tag explicitly, so deploy-from-source does not have to infer registry behavior from a loose image string.'
                  : 'Raw source settings now persist the exact source kind, location, and optional build context explicitly so non-hosted deploys do not depend on repository assumptions.'}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => saveSettingsMutation.mutate()} disabled={saveSettingsMutation.isPending}>
                {saveSettingsMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Save General settings
              </Button>
              {isGitSourceKind(settings.sourceKind) && settings.sourceLocation.trim() ? (
                <Button
                  variant="outline"
                  onClick={() => setCloneConfirmOpen(true)}
                  disabled={cloneWorkspaceMutation.isPending}
                >
                  {cloneWorkspaceMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderGit2 className="mr-2 h-4 w-4" />}
                  Clone into Workspace
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => setIsPreviewOpen(true)}>
                <Eye className="mr-2 h-4 w-4" />
                Preview source payload
              </Button>
            </div>

            <Dialog open={cloneConfirmOpen} onOpenChange={setCloneConfirmOpen}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Clone repository into workspace?</DialogTitle>
                  <DialogDescription>
                    This will <strong>clear all existing workspace files</strong> and replace them with a fresh clone of{' '}
                    <code className="rounded bg-muted px-1 py-0.5 text-xs">{settings.sourceLocation.trim()}</code>.
                    This action cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setCloneConfirmOpen(false)} disabled={cloneWorkspaceMutation.isPending}>
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={() => cloneWorkspaceMutation.mutate()}
                    disabled={cloneWorkspaceMutation.isPending}
                  >
                    {cloneWorkspaceMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Clone &amp; overwrite workspace
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
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
            <DialogTitle>Source preview</DialogTitle>
            <DialogDescription>
              This preview shows the current deployment source settings that will feed the source and runtime pipeline.
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
