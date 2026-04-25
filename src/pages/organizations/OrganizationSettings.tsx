import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useOutletContext } from 'react-router-dom';
import { BookOpen, Cable, CheckCircle2, GitBranch, Globe, Loader2, LockKeyhole, Pencil, Plus, Settings2, ShieldCheck, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import {
  createOrganizationGitConnection,
  createPersonalGitConnection,
  deleteOrganizationGitConnection,
  deletePersonalGitConnection,
  getOrganizationGitConnections,
  getPersonalGitConnections,
  GitConnectionAuthType,
  GitConnectionScope,
  GitProviderType,
  OrganizationGitConnection,
  PersonalGitConnection,
  testOrganizationGitConnection,
  testPersonalGitConnection,
  updateOrganizationGitConnection,
  updatePersonalGitConnection,
} from '@/lib/api';
import { buildOrganizationPath } from '@/lib/organizationPaths';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

interface ConnectionFormState {
  scope: GitConnectionScope;
  name: string;
  provider: GitProviderType;
  authType: GitConnectionAuthType;
  baseUrl: string;
  notes: string;
  credential: string;
}

interface ManagedConnection {
  id: number;
  name: string;
  provider_type: GitProviderType;
  auth_type: GitConnectionAuthType;
  base_url?: string | null;
  notes: string;
  repository_count: number;
  webhook_enabled: boolean;
  credential_masked?: string | null;
  last_test_status: 'unknown' | 'succeeded' | 'failed';
  scope: GitConnectionScope;
}

interface ConnectionTestResult {
  status: 'unknown' | 'succeeded' | 'failed';
  message: string;
}

function buildEmptyConnectionForm(scope: GitConnectionScope = 'organization'): ConnectionFormState {
  return {
    scope,
    name: '',
    provider: 'github',
    authType: 'pat',
    baseUrl: '',
    notes: '',
    credential: '',
  };
}

interface EditFormState {
  connectionId: number;
  scope: GitConnectionScope;
  name: string;
  provider: GitProviderType;
  authType: GitConnectionAuthType;
  baseUrl: string;
  notes: string;
  credential: string;
}

const OrganizationSettings = () => {
  const { selectedOrganization } = useOutletContext<OrganizationHierarchyOutletContext>();
  const queryClient = useQueryClient();
  const canManageSharedConnections = selectedOrganization?.user_role === 'owner' || selectedOrganization?.user_role === 'admin';
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [formState, setFormState] = useState<ConnectionFormState>(() => buildEmptyConnectionForm());
  const [editTarget, setEditTarget] = useState<EditFormState | null>(null);

  const { data: sharedConnectionsResponse, isLoading: isSharedLoading, error: sharedError } = useQuery({
    queryKey: ['organization-git-connections', selectedOrganization?.id],
    queryFn: () => getOrganizationGitConnections({ organizationId: selectedOrganization!.id }),
    enabled: Boolean(selectedOrganization),
  });

  const { data: personalConnectionsResponse, isLoading: isPersonalLoading, error: personalError } = useQuery({
    queryKey: ['personal-git-connections'],
    queryFn: () => getPersonalGitConnections(),
    enabled: Boolean(selectedOrganization),
  });

  const sharedConnections = sharedConnectionsResponse?.data || [];
  const personalConnections = personalConnectionsResponse?.data || [];

  const connectionSections = useMemo(() => {
    const mapConnection = (
      scope: GitConnectionScope,
      connection: OrganizationGitConnection | PersonalGitConnection,
    ): ManagedConnection => ({
      id: connection.id,
      name: connection.name,
      provider_type: connection.provider_type,
      auth_type: connection.auth_type,
      base_url: connection.base_url,
      notes: connection.notes,
      repository_count: connection.repository_count,
      webhook_enabled: connection.webhook_enabled,
      credential_masked: connection.credential_masked,
      last_test_status: connection.last_test_status,
      scope,
    });

    return {
      organization: sharedConnections.map((connection) => mapConnection('organization', connection)),
      personal: personalConnections.map((connection) => mapConnection('personal', connection)),
    };
  }, [personalConnections, sharedConnections]);

  const invalidateConnections = () => {
    queryClient.invalidateQueries({ queryKey: ['organization-git-connections', selectedOrganization?.id] });
    queryClient.invalidateQueries({ queryKey: ['personal-git-connections'] });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: formState.name.trim(),
        provider_type: formState.provider,
        auth_type: formState.authType,
        base_url: formState.baseUrl.trim() || undefined,
        notes: formState.notes.trim() || undefined,
        credential_plain: formState.credential.trim() || undefined,
      };

      if (formState.scope === 'personal') {
        return createPersonalGitConnection(payload);
      }

      return createOrganizationGitConnection({
        organization_id: selectedOrganization!.id,
        ...payload,
      });
    },
    onSuccess: () => {
      invalidateConnections();
      setFormState(buildEmptyConnectionForm(canManageSharedConnections ? 'organization' : 'personal'));
      setIsCreateOpen(false);
      toast({
        title: formState.scope === 'personal' ? 'Personal Git connection added' : 'Shared Git connection added',
        description:
          formState.scope === 'personal'
            ? 'This connection is now available for your apps and AI-assisted commit workflows.'
            : 'The organization can now reuse this provider connection across apps and deployments.',
      });
    },
    onError: (mutationError) => {
      toast({
        title: 'Unable to add connection',
        description: mutationError instanceof Error ? mutationError.message : 'Connection creation failed.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: ({ connectionId, scope }: { connectionId: number; scope: GitConnectionScope }) => {
      return scope === 'personal'
        ? deletePersonalGitConnection(connectionId)
        : deleteOrganizationGitConnection(connectionId);
    },
    onSuccess: () => {
      invalidateConnections();
      toast({ title: 'Connection removed', description: 'The selected Git connection was removed.' });
    },
    onError: (mutationError) => {
      toast({
        title: 'Unable to remove connection',
        description: mutationError instanceof Error ? mutationError.message : 'Connection removal failed.',
        variant: 'destructive',
      });
    },
  });

  const testMutation = useMutation({
    mutationFn: async ({ connectionId, scope }: { connectionId: number; scope: GitConnectionScope }): Promise<ConnectionTestResult> => {
      const response = scope === 'personal'
        ? testPersonalGitConnection(connectionId)
        : testOrganizationGitConnection(connectionId);
      const resolved = await response;
      return {
        status: resolved.data?.status || 'unknown',
        message: resolved.data?.message || 'Connection validation completed.',
      };
    },
    onSuccess: (response) => {
      invalidateConnections();
      toast({
        title: response.status === 'succeeded' ? 'Connection passed' : 'Connection requires changes',
        description: response.message,
        variant: response.status === 'failed' ? 'destructive' : 'default',
      });
    },
    onError: (mutationError) => {
      toast({
        title: 'Connection test failed',
        description: mutationError instanceof Error ? mutationError.message : 'Unable to test this connection.',
        variant: 'destructive',
      });
    },
  });

  const editMutation = useMutation({
    mutationFn: async () => {
      if (!editTarget) throw new Error('No connection selected for editing.');
      const payload = {
        name: editTarget.name.trim(),
        provider_type: editTarget.provider,
        auth_type: editTarget.authType,
        base_url: editTarget.baseUrl.trim() || undefined,
        notes: editTarget.notes.trim() || undefined,
        ...(editTarget.credential.trim() ? { credential_plain: editTarget.credential.trim() } : {}),
      };
      return editTarget.scope === 'personal'
        ? updatePersonalGitConnection(editTarget.connectionId, payload)
        : updateOrganizationGitConnection(editTarget.connectionId, payload);
    },
    onSuccess: () => {
      invalidateConnections();
      setEditTarget(null);
      toast({
        title: 'Connection updated',
        description: 'The Git connection has been saved. If you updated the credential, test the connection to verify access.',
      });
    },
    onError: (mutationError) => {
      toast({
        title: 'Unable to update connection',
        description: mutationError instanceof Error ? mutationError.message : 'Connection update failed.',
        variant: 'destructive',
      });
    },
  });

  const openEditDialog = (connection: ManagedConnection) => {
    setEditTarget({
      connectionId: connection.id,
      scope: connection.scope,
      name: connection.name,
      provider: connection.provider_type,
      authType: connection.auth_type,
      baseUrl: connection.base_url || '',
      notes: connection.notes || '',
      credential: '',
    });
  };

  const saveEdit = () => {
    if (!editTarget?.name.trim()) {
      toast({ title: 'Name required', description: 'Enter a name before saving.', variant: 'destructive' });
      return;
    }
    editMutation.mutate();
  };

  if (!selectedOrganization) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Organization settings unavailable</CardTitle>
          <CardDescription>Select an organization from the hierarchy to manage shared and personal Git connections.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const createConnection = () => {
    if (!formState.name.trim()) {
      toast({
        title: 'Name required',
        description: 'Git connections need a label before they can be created.',
        variant: 'destructive',
      });
      return;
    }

    if (formState.scope === 'organization' && !canManageSharedConnections) {
      toast({
        title: 'Shared access required',
        description: 'Only organization owners and admins can create shared Git connections.',
        variant: 'destructive',
      });
      return;
    }

    createMutation.mutate();
  };

  const openCreateDialog = () => {
    setFormState(buildEmptyConnectionForm(canManageSharedConnections ? 'organization' : 'personal'));
    setIsCreateOpen(true);
  };

  const renderConnectionCard = (connection: ManagedConnection) => (
    <div key={`${connection.scope}-${connection.id}`} className="rounded-lg border border-border bg-background p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-lg font-semibold">{connection.name}</div>
            <Badge variant="outline">{connection.provider_type}</Badge>
            <Badge variant="secondary">{connection.auth_type}</Badge>
            <Badge variant={connection.scope === 'organization' ? 'secondary' : 'outline'}>
              {connection.scope === 'organization' ? 'Shared' : 'Personal'}
            </Badge>
            <Badge variant={connection.last_test_status === 'failed' ? 'destructive' : 'secondary'}>
              {connection.last_test_status}
            </Badge>
          </div>
          <div className="mt-2 text-sm text-muted-foreground">
            {connection.base_url || 'Hosted provider default URL'}
          </div>
          {connection.credential_masked ? (
            <div className="mt-2 text-xs text-muted-foreground">Credential: {connection.credential_masked}</div>
          ) : (
            <div className="mt-2 text-xs text-muted-foreground">No credential stored yet</div>
          )}
          {connection.notes ? <p className="mt-3 text-sm text-muted-foreground">{connection.notes}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => openEditDialog(connection)}
            disabled={connection.scope === 'organization' && !canManageSharedConnections}
          >
            <Pencil className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => testMutation.mutate({ connectionId: connection.id, scope: connection.scope })}
            disabled={testMutation.isPending}
          >
            {testMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
            Test connection
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => deleteMutation.mutate({ connectionId: connection.id, scope: connection.scope })}
            disabled={deleteMutation.isPending || (connection.scope === 'organization' && !canManageSharedConnections)}
          >
            {deleteMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
            Remove
          </Button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
          <GitBranch className="h-3.5 w-3.5" />
          {connection.repository_count} repositories currently mapped
        </span>
        <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
          <ShieldCheck className="h-3.5 w-3.5" />
          {connection.webhook_enabled ? 'Webhook secret configured' : 'Webhook setup pending'}
        </span>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <Settings2 className="h-5 w-5" />
                Organization settings
              </CardTitle>
              <CardDescription>
                Manage shared and personal Git providers for app source selection, AI-assisted commit back, and deploy-from-source workflows.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" asChild>
                <Link to={buildOrganizationPath(selectedOrganization.id)}>Back to organization</Link>
              </Button>
              <Button onClick={openCreateDialog}>
                <Plus className="mr-2 h-4 w-4" />
                Add Git connection
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Organization: {selectedOrganization.name}</Badge>
          <Badge variant="secondary">Shared connections: {sharedConnections.length}</Badge>
          <Badge variant="secondary">Personal connections: {personalConnections.length}</Badge>
          <Badge variant="secondary">Reusable in app General tab</Badge>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Cable className="h-5 w-5" />
                Shared Git connections
              </CardTitle>
              <CardDescription>
                Shared organization connections back deploy-from-source, branch selection, and app-level source defaults for the whole team.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isSharedLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading shared Git connections...
                </div>
              ) : sharedError ? (
                <p className="text-sm text-destructive">Unable to load shared Git connections right now.</p>
              ) : connectionSections.organization.length === 0 ? (
                <p className="text-sm text-muted-foreground">No shared Git connections have been added for this organization yet.</p>
              ) : (
                connectionSections.organization.map(renderConnectionCard)
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <LockKeyhole className="h-5 w-5" />
                Personal Git connections
              </CardTitle>
              <CardDescription>
                Personal connections stay tied to your user account and are available for AIEditor commit-back or app-specific source control.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isPersonalLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading personal Git connections...
                </div>
              ) : personalError ? (
                <p className="text-sm text-destructive">Unable to load personal Git connections right now.</p>
              ) : connectionSections.personal.length === 0 ? (
                <p className="text-sm text-muted-foreground">You have not added any personal Git connections yet.</p>
              ) : (
                connectionSections.personal.map(renderConnectionCard)
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Globe className="h-5 w-5" />
                What this enables
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>Shared connections let teams standardize which org-level repositories power deployments and branch-based release flows.</p>
              <p>Personal connections let individuals authorize AI-assisted commit-back without exposing personal tokens to the whole organization.</p>
              <p>The app General tab can choose either scope as the source of truth for repository, branch, and deploy-from-source workflows.</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <BookOpen className="h-5 w-5" />
                How connections work
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p><span className="font-medium text-foreground">Personal Access Token (PAT)</span> — Generate a token in your provider's developer settings (GitHub: Settings → Developer settings → Tokens; GitLab: User Settings → Access Tokens). Paste it in the credential field. PAT connections support repository browsing and live credential verification via Test.</p>
              <p><span className="font-medium text-foreground">SSH</span> — Paste an SSH private key. SSH connections support workspace clone and pull operations. Repository browsing and live credential tests are not available for SSH connections.</p>
              <p><span className="font-medium text-foreground">No connection needed for public repos</span> — HTTPS URLs, owner/repo slugs, and public git@ addresses can be used directly in the app General tab without any saved connection.</p>
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Git connection</DialogTitle>
            <DialogDescription>
              Choose whether this provider should be shared across the organization or attached only to your personal account.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="connection-scope">Connection scope</Label>
              <Select
                value={formState.scope}
                onValueChange={(value) => setFormState((current) => ({ ...current, scope: value as GitConnectionScope }))}
              >
                <SelectTrigger id="connection-scope">
                  <SelectValue placeholder="Choose connection scope" />
                </SelectTrigger>
                <SelectContent>
                  {canManageSharedConnections ? <SelectItem value="organization">Shared organization connection</SelectItem> : null}
                  <SelectItem value="personal">Personal connection</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="connection-name">Connection name</Label>
              <Input
                id="connection-name"
                value={formState.name}
                onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
                placeholder={formState.scope === 'personal' ? 'My GitHub account' : 'Engineering GitHub org'}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="provider">Provider</Label>
                <Select
                  value={formState.provider}
                  onValueChange={(value) => setFormState((current) => ({ ...current, provider: value as GitProviderType }))}
                >
                  <SelectTrigger id="provider">
                    <SelectValue placeholder="Choose provider" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="github">GitHub</SelectItem>
                    <SelectItem value="gitlab">GitLab</SelectItem>
                    <SelectItem value="bitbucket">Bitbucket</SelectItem>
                    <SelectItem value="gitea">Gitea</SelectItem>
                    <SelectItem value="generic-git">Generic Git</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="auth-type">Auth type</Label>
                <Select
                  value={formState.authType}
                  onValueChange={(value) => setFormState((current) => ({ ...current, authType: value as GitConnectionAuthType }))}
                >
                  <SelectTrigger id="auth-type">
                    <SelectValue placeholder="Choose auth type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pat">Personal access token</SelectItem>
                    <SelectItem value="ssh">SSH key</SelectItem>
                  </SelectContent>
                </Select>
                {formState.authType === 'ssh' ? (
                  <p className="text-xs text-muted-foreground">SSH connections support workspace clone and pull operations. Repository browsing is not available for SSH connections.</p>
                ) : null}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="base-url">Base URL</Label>
              <Input
                id="base-url"
                value={formState.baseUrl}
                onChange={(event) => setFormState((current) => ({ ...current, baseUrl: event.target.value }))}
                placeholder="https://git.example.com"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="connection-notes">Notes</Label>
              <Textarea
                id="connection-notes"
                value={formState.notes}
                onChange={(event) => setFormState((current) => ({ ...current, notes: event.target.value }))}
                placeholder={
                  formState.scope === 'personal'
                    ? 'Describe which apps should use this personal connection for commit-back or private repos.'
                    : 'Describe which teams and apps should use this shared connection.'
                }
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="connection-credential">Credential or secret</Label>
              <Textarea
                id="connection-credential"
                value={formState.credential}
                onChange={(event) => setFormState((current) => ({ ...current, credential: event.target.value }))}
                placeholder="Paste a PAT, app secret, or SSH private key when applicable."
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)} disabled={createMutation.isPending}>Cancel</Button>
            <Button onClick={createConnection} disabled={createMutation.isPending}>
              {createMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Add {formState.scope === 'personal' ? 'personal' : 'shared'} connection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editTarget !== null} onOpenChange={(open) => { if (!open) setEditTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Git connection</DialogTitle>
            <DialogDescription>
              Update the connection details. Leave the credential field blank to keep the existing credential unchanged.
            </DialogDescription>
          </DialogHeader>

          {editTarget ? (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label>Connection scope</Label>
                <p className="rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                  {editTarget.scope === 'organization' ? 'Shared organization connection' : 'Personal connection'} — cannot be changed after creation
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-connection-name">Connection name</Label>
                <Input
                  id="edit-connection-name"
                  value={editTarget.name}
                  onChange={(event) => setEditTarget((current) => current ? { ...current, name: event.target.value } : current)}
                />
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="edit-provider">Provider</Label>
                  <Select
                    value={editTarget.provider}
                    onValueChange={(value) => setEditTarget((current) => current ? { ...current, provider: value as GitProviderType } : current)}
                  >
                    <SelectTrigger id="edit-provider">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="github">GitHub</SelectItem>
                      <SelectItem value="gitlab">GitLab</SelectItem>
                      <SelectItem value="bitbucket">Bitbucket</SelectItem>
                      <SelectItem value="gitea">Gitea</SelectItem>
                      <SelectItem value="generic-git">Generic Git</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="edit-auth-type">Auth type</Label>
                  <Select
                    value={editTarget.authType}
                    onValueChange={(value) => setEditTarget((current) => current ? { ...current, authType: value as GitConnectionAuthType } : current)}
                  >
                    <SelectTrigger id="edit-auth-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pat">Personal access token</SelectItem>
                      <SelectItem value="ssh">SSH key</SelectItem>
                    </SelectContent>
                  </Select>
                  {editTarget.authType === 'ssh' ? (
                    <p className="text-xs text-muted-foreground">SSH connections support workspace clone and pull. Repository browsing is unavailable.</p>
                  ) : null}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-base-url">Base URL</Label>
                <Input
                  id="edit-base-url"
                  value={editTarget.baseUrl}
                  onChange={(event) => setEditTarget((current) => current ? { ...current, baseUrl: event.target.value } : current)}
                  placeholder="https://git.example.com (leave blank for hosted providers)"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-notes">Notes</Label>
                <Textarea
                  id="edit-notes"
                  value={editTarget.notes}
                  onChange={(event) => setEditTarget((current) => current ? { ...current, notes: event.target.value } : current)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="edit-credential">Replace credential</Label>
                <Textarea
                  id="edit-credential"
                  value={editTarget.credential}
                  onChange={(event) => setEditTarget((current) => current ? { ...current, credential: event.target.value } : current)}
                  placeholder="Leave blank to keep existing credential — only fill to replace it."
                />
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)} disabled={editMutation.isPending}>Cancel</Button>
            <Button onClick={saveEdit} disabled={editMutation.isPending}>
              {editMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default OrganizationSettings;
