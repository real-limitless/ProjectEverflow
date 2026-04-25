import { useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { GitBranch, Globe, Loader2, Pencil, Server, Trash2, Workflow } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import { deleteEnvironment, ProjectEnvironment, updateEnvironment } from '@/lib/api';
import { buildAppOverviewPath } from '@/lib/organizationPaths';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

const EnvironmentDetail = () => {
  const { selectedOrganization, selectedProject, selectedEnvironment, apps, appsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [formState, setFormState] = useState({
    name: '',
    description: '',
    environmentType: 'development',
    workspaceSize: 'standard',
    workspaceMode: 'shared',
    domain: '',
  });

  const updateMutation = useMutation({
    mutationFn: (data: Partial<ProjectEnvironment>) => updateEnvironment(selectedEnvironment!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['environments', selectedProject!.id] });
      toast({ title: 'Environment updated', description: 'Environment details were saved.' });
      setIsEditOpen(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the environment.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteEnvironment(selectedEnvironment!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['environments', selectedProject!.id] });
      queryClient.invalidateQueries({ queryKey: ['organizationProjects', selectedOrganization!.id] });
      toast({ title: 'Environment deleted', description: 'The environment was removed.' });
      navigate(`/organizations/${selectedOrganization!.id}/projects/${selectedProject!.id}`);
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the environment.',
        variant: 'destructive',
      });
    },
  });

  if (!selectedOrganization || !selectedProject || !selectedEnvironment) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Environment not found</CardTitle>
          <CardDescription>Select an environment from the hierarchy to continue.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const openEditDialog = () => {
    setFormState({
      name: selectedEnvironment.name,
      description: selectedEnvironment.description || '',
      environmentType: selectedEnvironment.environment_type,
      workspaceSize: selectedEnvironment.workspace_size,
      workspaceMode: selectedEnvironment.workspace_mode,
      domain: selectedEnvironment.domain || '',
    });
    setIsEditOpen(true);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <GitBranch className="h-5 w-5" />
                {selectedEnvironment.name}
              </CardTitle>
              <CardDescription>{selectedEnvironment.description || 'This environment does not have a description yet.'}</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={openEditDialog}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit environment
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete environment
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete environment</AlertDialogTitle>
                    <AlertDialogDescription>
                      Delete {selectedEnvironment.name}? This removes the environment and returns you to the project view.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      {deleteMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Delete environment
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Project: {selectedProject.name}</Badge>
          <Badge variant="secondary">Type: {selectedEnvironment.environment_type}</Badge>
          <Badge variant="secondary">Workspace: {selectedEnvironment.workspace_image}</Badge>
          <Badge variant="secondary">Size: {selectedEnvironment.workspace_size}</Badge>
          {selectedEnvironment.domain ? <Badge variant="secondary">Domain: {selectedEnvironment.domain}</Badge> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Applications in environment</CardTitle>
          <CardDescription>Applications are the containers attached to this environment.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {appsLoading ? (
            <p className="text-sm text-muted-foreground">Loading applications...</p>
          ) : apps.length === 0 ? (
            <p className="text-sm text-muted-foreground">No applications exist in this environment yet.</p>
          ) : (
            apps.map((app) => (
              <button
                key={app.id}
                type="button"
                onClick={() =>
                  navigate(buildAppOverviewPath(selectedOrganization.id, selectedProject.id, selectedEnvironment.id, app.id))
                }
                className="rounded-lg border border-border bg-background p-5 text-left transition hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{app.name}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{app.description || `${app.source_type} application`}</div>
                  </div>
                  <Badge variant="outline">{app.status}</Badge>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <Server className="h-3.5 w-3.5" />
                    {app.service_count} services
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <Workflow className="h-3.5 w-3.5" />
                    {app.latest_deployment ? `Latest ${app.latest_deployment.version}` : 'No deployments yet'}
                  </span>
                  {selectedEnvironment.domain ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                      <Globe className="h-3.5 w-3.5" />
                      {selectedEnvironment.domain}
                    </span>
                  ) : null}
                </div>
              </button>
            ))
          )}
        </CardContent>
      </Card>

      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit environment</DialogTitle>
            <DialogDescription>Advanced environment settings live here instead of the creation dialog.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Environment name"
              value={formState.name}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
            />
            <Input
              placeholder="Environment type"
              value={formState.environmentType}
              onChange={(event) => setFormState((current) => ({ ...current, environmentType: event.target.value }))}
            />
            <Input
              placeholder="Workspace size"
              value={formState.workspaceSize}
              onChange={(event) => setFormState((current) => ({ ...current, workspaceSize: event.target.value }))}
            />
            <Input
              placeholder="Workspace mode"
              value={formState.workspaceMode}
              onChange={(event) => setFormState((current) => ({ ...current, workspaceMode: event.target.value }))}
            />
            <Input
              placeholder="Domain"
              value={formState.domain}
              onChange={(event) => setFormState((current) => ({ ...current, domain: event.target.value }))}
            />
            <Textarea
              placeholder="Describe the environment"
              value={formState.description}
              onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditOpen(false)} disabled={updateMutation.isPending}>Cancel</Button>
            <Button
              onClick={() => updateMutation.mutate({
                name: formState.name.trim(),
                description: formState.description.trim(),
                environment_type: formState.environmentType as ProjectEnvironment['environment_type'],
                workspace_size: formState.workspaceSize,
                workspace_mode: formState.workspaceMode as ProjectEnvironment['workspace_mode'],
                domain: formState.domain.trim() || undefined,
              })}
              disabled={!formState.name.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default EnvironmentDetail;