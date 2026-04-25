import { useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Building2, FolderKanban, Loader2, Pencil, Settings2, Trash2, Users } from 'lucide-react';

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
import { deleteOrganization, updateOrganization } from '@/lib/api';
import { buildOrganizationSettingsPath } from '@/lib/organizationPaths';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

const OrganizationDetail = () => {
  const { selectedOrganization, projects, projectsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [formState, setFormState] = useState({ name: '', description: '' });

  const updateMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => updateOrganization(selectedOrganization!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      toast({ title: 'Organization updated', description: 'Organization details were saved.' });
      setIsEditOpen(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the organization.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrganization(selectedOrganization!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      toast({ title: 'Organization deleted', description: 'The organization was removed.' });
      navigate('/organizations');
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the organization.',
        variant: 'destructive',
      });
    },
  });

  if (!selectedOrganization) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Organization not found</CardTitle>
          <CardDescription>Select an organization from the hierarchy to continue.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const openEditDialog = () => {
    setFormState({
      name: selectedOrganization.name,
      description: selectedOrganization.description || '',
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
                <Building2 className="h-5 w-5" />
                {selectedOrganization.name}
              </CardTitle>
              <CardDescription>{selectedOrganization.description || 'This organization does not have a description yet.'}</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={openEditDialog}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit organization
              </Button>
              <Button variant="outline" size="sm" onClick={() => navigate(buildOrganizationSettingsPath(selectedOrganization.id))}>
                <Settings2 className="mr-2 h-4 w-4" />
                Git connections
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete organization
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete organization</AlertDialogTitle>
                    <AlertDialogDescription>
                      Delete {selectedOrganization.name}? This removes the organization from the hierarchy and returns you to the organizations overview.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={deleteMutation.isPending}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      {deleteMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Delete organization
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Role: {selectedOrganization.user_role ?? 'viewer'}</Badge>
          <Badge variant="secondary">Projects: {selectedOrganization.project_count}</Badge>
          <Badge variant="secondary">Members: {selectedOrganization.member_count}</Badge>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Projects in organization</CardTitle>
          <CardDescription>Projects are now the first child resource under the organization.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {projectsLoading ? (
            <p className="text-sm text-muted-foreground">Loading projects...</p>
          ) : projects.length === 0 ? (
            <p className="text-sm text-muted-foreground">No projects exist in this organization yet.</p>
          ) : (
            projects.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={() => navigate(`/organizations/${selectedOrganization.id}/projects/${project.id}`)}
                className="rounded-lg border border-border bg-background p-5 text-left transition hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{project.name}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{project.description || 'No project description yet.'}</div>
                  </div>
                  <Badge variant="outline">{project.status.replace(/_/g, ' ')}</Badge>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <Users className="h-3.5 w-3.5" />
                    {project.contributors.length + 1} contributors
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <FolderKanban className="h-3.5 w-3.5" />
                    Open project
                  </span>
                </div>
              </button>
            ))
          )}
        </CardContent>
      </Card>

      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit organization</DialogTitle>
            <DialogDescription>Update the organization details shown in the hierarchy.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Organization name"
              value={formState.name}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
            />
            <Textarea
              placeholder="Describe the organization"
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

export default OrganizationDetail;