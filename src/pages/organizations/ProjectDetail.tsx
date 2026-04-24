import { useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FolderKanban, GitBranch, Loader2, Pencil, Trash2, UserRound } from 'lucide-react';

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
import { ProjectWorkspaceSettingsPanel } from '@/components/project/ProjectWorkspaceSettingsPanel';
import { toast } from '@/hooks/use-toast';
import { deleteProject, updateProject } from '@/lib/api';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

const ProjectDetail = () => {
  const { selectedOrganization, selectedProject, environments, environmentsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [formState, setFormState] = useState({ name: '', description: '' });

  const updateMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => updateProject(selectedProject!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizationProjects', selectedOrganization!.id] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast({ title: 'Project updated', description: 'Project details were saved.' });
      setIsEditOpen(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the project.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(selectedProject!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizationProjects', selectedOrganization!.id] });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      toast({ title: 'Project deleted', description: 'The project was removed from the organization.' });
      navigate(`/organizations/${selectedOrganization!.id}`);
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the project.',
        variant: 'destructive',
      });
    },
  });

  if (!selectedOrganization || !selectedProject) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Project not found</CardTitle>
          <CardDescription>Select a project from the hierarchy to continue.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const openEditDialog = () => {
    setFormState({
      name: selectedProject.name,
      description: selectedProject.description || '',
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
                <FolderKanban className="h-5 w-5" />
                {selectedProject.name}
              </CardTitle>
              <CardDescription>{selectedProject.description || 'This project does not have a description yet.'}</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={openEditDialog}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit project
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete project
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete project</AlertDialogTitle>
                    <AlertDialogDescription>
                      Delete {selectedProject.name}? This removes the project from the organization hierarchy.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      {deleteMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Delete project
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Organization: {selectedOrganization.name}</Badge>
          <Badge variant="secondary">Status: {selectedProject.status.replace(/_/g, ' ')}</Badge>
          <Badge variant="secondary">Workspace: {selectedProject.workspace_image ?? 'fedora:43'}</Badge>
          <Badge variant="secondary">Size: {selectedProject.workspace_size ?? 'standard'}</Badge>
          <Badge variant="secondary">Mode: {selectedProject.workspace_mode ?? 'shared'}</Badge>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Environments</CardTitle>
          <CardDescription>Environments segment project runtime surfaces such as production, staging, and development.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {environmentsLoading ? (
            <p className="text-sm text-muted-foreground">Loading environments...</p>
          ) : environments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No environments exist for this project yet.</p>
          ) : (
            environments.map((environment) => (
              <button
                key={environment.id}
                type="button"
                onClick={() => navigate(`/organizations/${selectedOrganization.id}/projects/${selectedProject.id}/environments/${environment.id}`)}
                className="rounded-lg border border-border bg-background p-5 text-left transition hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{environment.name}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{environment.description || `${environment.environment_type} environment`}</div>
                  </div>
                  <Badge variant="outline">{environment.environment_type}</Badge>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <GitBranch className="h-3.5 w-3.5" />
                    {environment.app_count} apps
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <UserRound className="h-3.5 w-3.5" />
                    {environment.workspace_mode}
                  </span>
                </div>
              </button>
            ))
          )}
        </CardContent>
      </Card>

      <ProjectWorkspaceSettingsPanel
        project={selectedProject}
        onOpenAdminSettings={() => navigate('/admin/workspace-settings')}
      />

      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit project</DialogTitle>
            <DialogDescription>Update the project details shown in the hierarchy.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Project name"
              value={formState.name}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
            />
            <Textarea
              placeholder="Describe the project"
              value={formState.description}
              onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditOpen(false)} disabled={updateMutation.isPending}>Cancel</Button>
            <Button
              onClick={() => updateMutation.mutate({ name: formState.name.trim(), description: formState.description.trim() })}
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

export default ProjectDetail;