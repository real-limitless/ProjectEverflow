import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { History, Loader2, Pencil, RotateCcw, Rocket, Server, Trash2 } from 'lucide-react';

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
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';
import { ApplicationWorkspace } from '@/pages/EditApplication';
import { deleteApp, deleteDeployment, DeploymentRecord, ProjectApp, rollbackDeployment, updateApp, updateDeployment } from '@/lib/api';

const AppDetail = () => {
  const { selectedOrganization, selectedProject, selectedEnvironment, selectedApp, deployments, deploymentsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [rollbackTargetId, setRollbackTargetId] = useState<number | null>(null);
  const [rollbackNotes, setRollbackNotes] = useState('');
  const [isAppEditOpen, setIsAppEditOpen] = useState(false);
  const [appForm, setAppForm] = useState({
    name: '',
    description: '',
    sourceType: 'compose',
    repositoryUrl: '',
    composePath: '',
    status: 'draft',
  });
  const [editingDeploymentId, setEditingDeploymentId] = useState<number | null>(null);
  const [deploymentForm, setDeploymentForm] = useState({
    version: '',
    sourceRef: '',
    notes: '',
    status: 'pending',
  });

  const updateAppMutation = useMutation({
    mutationFn: (data: Partial<ProjectApp>) => updateApp(selectedApp!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment!.id] });
      toast({ title: 'Application updated', description: 'Application details were saved.' });
      setIsAppEditOpen(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the application.',
        variant: 'destructive',
      });
    },
  });

  const deleteAppMutation = useMutation({
    mutationFn: () => deleteApp(selectedApp!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment!.id] });
      queryClient.invalidateQueries({ queryKey: ['environments', selectedProject!.id] });
      toast({ title: 'Application deleted', description: 'The application was removed from the environment.' });
      navigate(`/organizations/${selectedOrganization!.id}/projects/${selectedProject!.id}/environments/${selectedEnvironment!.id}`);
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the application.',
        variant: 'destructive',
      });
    },
  });

  const updateDeploymentMutation = useMutation({
    mutationFn: (data: { id: number; version: string; source_ref?: string; notes?: string; status: DeploymentRecord['status'] }) =>
      updateDeployment(data.id, {
        version: data.version,
        source_ref: data.source_ref,
        notes: data.notes,
        status: data.status,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments', selectedApp!.id] });
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment!.id] });
      toast({ title: 'Deployment updated', description: 'Deployment details were saved.' });
      setEditingDeploymentId(null);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the deployment.',
        variant: 'destructive',
      });
    },
  });

  const deleteDeploymentMutation = useMutation({
    mutationFn: (deploymentId: number) => deleteDeployment(deploymentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments', selectedApp!.id] });
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment!.id] });
      toast({ title: 'Deployment deleted', description: 'The deployment record was removed.' });
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the deployment.',
        variant: 'destructive',
      });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: ({ deploymentId, notes }: { deploymentId: number; notes: string }) => rollbackDeployment(deploymentId, notes),
    onSuccess: () => {
      if (!selectedApp || !selectedEnvironment) {
        return;
      }
      queryClient.invalidateQueries({ queryKey: ['deployments', selectedApp.id] });
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironment.id] });
      toast({
        title: 'Rollback created',
        description: 'A rollback deployment record was added for this app.',
      });
      setRollbackTargetId(null);
      setRollbackNotes('');
    },
    onError: (error) => {
      toast({
        title: 'Rollback failed',
        description: error instanceof Error ? error.message : 'Unable to create the rollback deployment.',
        variant: 'destructive',
      });
    },
  });

  if (!selectedOrganization || !selectedProject || !selectedEnvironment || !selectedApp) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Application not found</CardTitle>
          <CardDescription>Select an application from the hierarchy to continue.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const rollbackTarget = deployments.find((deployment) => deployment.id === rollbackTargetId) ?? null;
  const editingDeployment = deployments.find((deployment) => deployment.id === editingDeploymentId) ?? null;

  const openAppEditDialog = () => {
    setAppForm({
      name: selectedApp.name,
      description: selectedApp.description || '',
      sourceType: selectedApp.source_type,
      repositoryUrl: selectedApp.repository_url || '',
      composePath: selectedApp.compose_path || '',
      status: selectedApp.status,
    });
    setIsAppEditOpen(true);
  };

  const openDeploymentEditDialog = (deployment: (typeof deployments)[number]) => {
    setDeploymentForm({
      version: deployment.version,
      sourceRef: deployment.source_ref || '',
      notes: deployment.notes || '',
      status: deployment.status,
    });
    setEditingDeploymentId(deployment.id);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-2xl">
                <Server className="h-5 w-5" />
                {selectedApp.name}
              </CardTitle>
              <CardDescription>{selectedApp.description || 'This application does not have a description yet.'}</CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={openAppEditDialog}>
                <Pencil className="mr-2 h-4 w-4" />
                Edit application
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete application
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete application</AlertDialogTitle>
                    <AlertDialogDescription>
                      Delete {selectedApp.name}? This removes the application and returns you to the environment view.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={deleteAppMutation.isPending}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteAppMutation.mutate()}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      {deleteAppMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                      Delete application
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Badge variant="secondary">Environment: {selectedEnvironment.name}</Badge>
          <Badge variant="secondary">Source: {selectedApp.source_type}</Badge>
          <Badge variant="secondary">Status: {selectedApp.status}</Badge>
          {selectedApp.compose_path ? <Badge variant="secondary">Compose: {selectedApp.compose_path}</Badge> : null}
          {selectedApp.repository_url ? <Badge variant="secondary">Repository linked</Badge> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl">
            <History className="h-5 w-5" />
            Deployment history
          </CardTitle>
          <CardDescription>Deployments are now first-class records under each app route.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {deploymentsLoading ? (
            <p className="text-sm text-muted-foreground">Loading deployments...</p>
          ) : deployments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No deployments exist for this app yet.</p>
          ) : (
            deployments.map((deployment) => (
              <div key={deployment.id} className="rounded-lg border border-border bg-background p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-lg font-semibold">{deployment.version}</div>
                    <div className="mt-1 text-sm text-muted-foreground">
                      {deployment.source_ref || 'manual'} • {deployment.trigger_type}
                    </div>
                  </div>
                  <Badge variant={deployment.status === 'succeeded' ? 'default' : 'outline'}>
                    {deployment.status.replace(/_/g, ' ')}
                  </Badge>
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <Rocket className="h-3.5 w-3.5" />
                    {deployment.started_at ? `Started ${new Date(deployment.started_at).toLocaleString()}` : 'Pending execution'}
                  </span>
                  {deployment.completed_at ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                      Completed {new Date(deployment.completed_at).toLocaleString()}
                    </span>
                  ) : null}
                  {deployment.rollback_of ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                      Rollback of #{deployment.rollback_of}
                    </span>
                  ) : null}
                </div>

                {deployment.notes ? <p className="mt-3 text-sm text-muted-foreground">{deployment.notes}</p> : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => openDeploymentEditDialog(deployment)}>
                    <Pencil className="mr-2 h-4 w-4" />
                    Edit record
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setRollbackTargetId(deployment.id);
                      setRollbackNotes(`Rollback requested from deployment ${deployment.version}.`);
                    }}
                    disabled={deployment.status !== 'succeeded' || rollbackMutation.isPending}
                  >
                    {rollbackMutation.isPending && rollbackTargetId === deployment.id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <RotateCcw className="mr-2 h-4 w-4" />
                    )}
                    Roll back
                  </Button>
                  {deployment.status !== 'succeeded' ? (
                    <p className="self-center text-xs text-muted-foreground">
                      Only successful deployments can be rolled back from this view.
                    </p>
                  ) : null}
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive" size="sm">
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete record
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete deployment record</AlertDialogTitle>
                        <AlertDialogDescription>
                          Delete deployment {deployment.version}? This removes the record from the application history.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleteDeploymentMutation.isPending}>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteDeploymentMutation.mutate(deployment.id)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {deleteDeploymentMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Delete record
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <ApplicationWorkspace
        project={selectedProject}
        applicationName={selectedApp.name}
        serviceAppId={selectedApp.id}
        headerTitle="Application workspace"
        subtitle={`Manage ${selectedApp.name} in ${selectedEnvironment.name}`}
      />

      <Dialog open={isAppEditOpen} onOpenChange={setIsAppEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit application</DialogTitle>
            <DialogDescription>Update the application details surfaced in the hierarchy and workspace.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Application name" value={appForm.name} onChange={(event) => setAppForm((current) => ({ ...current, name: event.target.value }))} />
            <Input placeholder="Source type" value={appForm.sourceType} onChange={(event) => setAppForm((current) => ({ ...current, sourceType: event.target.value }))} />
            <Input placeholder="Repository URL" value={appForm.repositoryUrl} onChange={(event) => setAppForm((current) => ({ ...current, repositoryUrl: event.target.value }))} />
            <Input placeholder="Compose path" value={appForm.composePath} onChange={(event) => setAppForm((current) => ({ ...current, composePath: event.target.value }))} />
            <Input placeholder="Status" value={appForm.status} onChange={(event) => setAppForm((current) => ({ ...current, status: event.target.value }))} />
            <Textarea placeholder="Describe the application" value={appForm.description} onChange={(event) => setAppForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAppEditOpen(false)} disabled={updateAppMutation.isPending}>Cancel</Button>
            <Button
              onClick={() => updateAppMutation.mutate({
                name: appForm.name.trim(),
                description: appForm.description.trim(),
                source_type: appForm.sourceType as ProjectApp['source_type'],
                repository_url: appForm.repositoryUrl.trim() || undefined,
                compose_path: appForm.composePath.trim() || undefined,
                status: appForm.status as ProjectApp['status'],
              })}
              disabled={!appForm.name.trim() || updateAppMutation.isPending}
            >
              {updateAppMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editingDeployment !== null} onOpenChange={(open) => {
        if (!open) {
          setEditingDeploymentId(null);
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit deployment record</DialogTitle>
            <DialogDescription>Update the version, source ref, notes, or status for this deployment record.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Version" value={deploymentForm.version} onChange={(event) => setDeploymentForm((current) => ({ ...current, version: event.target.value }))} />
            <Input placeholder="Source ref" value={deploymentForm.sourceRef} onChange={(event) => setDeploymentForm((current) => ({ ...current, sourceRef: event.target.value }))} />
            <Input placeholder="Status" value={deploymentForm.status} onChange={(event) => setDeploymentForm((current) => ({ ...current, status: event.target.value }))} />
            <Textarea placeholder="Notes" value={deploymentForm.notes} onChange={(event) => setDeploymentForm((current) => ({ ...current, notes: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditingDeploymentId(null)} disabled={updateDeploymentMutation.isPending}>Cancel</Button>
            <Button
              onClick={() => {
                if (!editingDeployment) {
                  return;
                }
                updateDeploymentMutation.mutate({
                  id: editingDeployment.id,
                  version: deploymentForm.version.trim(),
                  source_ref: deploymentForm.sourceRef.trim() || undefined,
                  notes: deploymentForm.notes.trim() || undefined,
                  status: deploymentForm.status as DeploymentRecord['status'],
                });
              }}
              disabled={!editingDeployment || !deploymentForm.version.trim() || updateDeploymentMutation.isPending}
            >
              {updateDeploymentMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rollbackTarget !== null} onOpenChange={(open) => {
        if (!open) {
          setRollbackTargetId(null);
          setRollbackNotes('');
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Roll back deployment</DialogTitle>
            <DialogDescription>
              {rollbackTarget
                ? `Create a rollback deployment for ${rollbackTarget.version}. This keeps the history explicit under the app.`
                : 'Select a deployment to roll back.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground" htmlFor="rollback-notes">
              Notes
            </label>
            <Textarea
              id="rollback-notes"
              value={rollbackNotes}
              onChange={(event) => setRollbackNotes(event.target.value)}
              placeholder="Why is this rollback needed?"
              rows={4}
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRollbackTargetId(null);
                setRollbackNotes('');
              }}
              disabled={rollbackMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (!rollbackTarget) {
                  return;
                }
                rollbackMutation.mutate({
                  deploymentId: rollbackTarget.id,
                  notes: rollbackNotes.trim(),
                });
              }}
              disabled={!rollbackTarget || rollbackMutation.isPending}
            >
              {rollbackMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Create rollback
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AppDetail;