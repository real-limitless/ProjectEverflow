import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Image, Loader2, RotateCcw, Settings, Trash2 } from 'lucide-react';

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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from '@/hooks/use-toast';
import {
  getProjectServices,
  getWorkspaceTiers,
  Project,
  resetWorkspace,
  updateProject,
  updateWorkspaceImage,
  WorkspaceResourceTier,
} from '@/lib/api';

interface ProjectWorkspaceSettingsPanelProps {
  project: Project;
  onOpenAdminSettings?: () => void;
}

interface WorkspaceFormState {
  workspaceImage: NonNullable<Project['workspace_image']>;
  workspaceSize: string;
  workspaceMode: NonNullable<Project['workspace_mode']>;
  logRetentionDays: number;
}

function buildInitialState(project: Project): WorkspaceFormState {
  return {
    workspaceImage: project.workspace_image || 'fedora:43',
    workspaceSize: project.workspace_size || 'standard',
    workspaceMode: project.workspace_mode || 'personal',
    logRetentionDays: project.log_retention_days || 30,
  };
}

export function ProjectWorkspaceSettingsPanel({ project, onOpenAdminSettings }: ProjectWorkspaceSettingsPanelProps) {
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<WorkspaceFormState>(() => buildInitialState(project));

  const { data: tiersResponse } = useQuery({
    queryKey: ['workspace-tiers'],
    queryFn: getWorkspaceTiers,
  });
  const tiers = tiersResponse?.data || [];

  const { data: servicesResponse } = useQuery({
    queryKey: ['project-services', project.id, 'ai-workspace'],
    queryFn: () => getProjectServices(project.id, 'ai-workspace'),
  });
  const workspaceServices = servicesResponse?.data || [];
  const hasWorkspace = workspaceServices.length > 0;

  const saveMutation = useMutation({
    mutationFn: () =>
      updateProject(project.id, {
        workspace_image: formState.workspaceImage,
        workspace_size: formState.workspaceSize,
        workspace_mode: formState.workspaceMode,
        log_retention_days: formState.logRetentionDays,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['organizationProjects', project.organization?.id] });
      toast({ title: 'Workspace settings saved', description: 'Project workspace configuration was updated.' });
    },
    onError: (error) => {
      toast({
        title: 'Save failed',
        description: error instanceof Error ? error.message : 'Unable to update workspace settings.',
        variant: 'destructive',
      });
    },
  });

  const rebuildMutation = useMutation({
    mutationFn: () => {
      if (!hasWorkspace) {
        return Promise.reject(new Error('No workspace service found. Provision the workspace first from AI Editor or Webtop.'));
      }
      return updateWorkspaceImage(project.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services'] });
      toast({
        title: 'Workspace image updated',
        description: 'The latest image was pulled and the workspace was stopped for restart.',
      });
    },
    onError: (error) => {
      toast({
        title: 'Rebuild failed',
        description: error instanceof Error ? error.message : 'Unable to rebuild the workspace image.',
        variant: 'destructive',
      });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => {
      if (!hasWorkspace) {
        return Promise.reject(new Error('No workspace service found. Provision the workspace first from AI Editor or Webtop.'));
      }
      return resetWorkspace(project.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services'] });
      toast({ title: 'Workspace reset', description: 'Workspace volume has been reset and reinitialized.' });
    },
    onError: (error) => {
      toast({
        title: 'Reset failed',
        description: error instanceof Error ? error.message : 'Unable to reset the workspace.',
        variant: 'destructive',
      });
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-xl">
              <Image className="h-5 w-5" />
              Workspace configuration
            </CardTitle>
            <CardDescription>
              Project-level workspace settings were moved here from the old app workspace details tab.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">Image: {formState.workspaceImage}</Badge>
            <Badge variant="secondary">Tier: {formState.workspaceSize}</Badge>
            <Badge variant="secondary">Mode: {formState.workspaceMode}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="workspace-image">Workspace base image</Label>
            <Select
              value={formState.workspaceImage}
              onValueChange={(value) =>
                setFormState((current) => ({
                  ...current,
                  workspaceImage: value as NonNullable<Project['workspace_image']>,
                }))
              }
            >
              <SelectTrigger id="workspace-image">
                <SelectValue placeholder="Select base image" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fedora:43">Fedora 43</SelectItem>
                <SelectItem value="registry.access.redhat.com/ubi9/ubi">UBI 9</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="workspace-tier">Resource tier</Label>
            <Select
              value={formState.workspaceSize}
              onValueChange={(value) => setFormState((current) => ({ ...current, workspaceSize: value }))}
            >
              <SelectTrigger id="workspace-tier">
                <SelectValue placeholder="Select tier" />
              </SelectTrigger>
              <SelectContent>
                {tiers.map((tier: WorkspaceResourceTier) => (
                  <SelectItem key={tier.slug} value={tier.slug}>
                    {tier.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="workspace-mode">Workspace mode</Label>
            <Select
              value={formState.workspaceMode}
              onValueChange={(value) =>
                setFormState((current) => ({
                  ...current,
                  workspaceMode: value as NonNullable<Project['workspace_mode']>,
                }))
              }
            >
              <SelectTrigger id="workspace-mode">
                <SelectValue placeholder="Select mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">Personal</SelectItem>
                <SelectItem value="shared">Shared</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="log-retention-days">Log retention days</Label>
            <Input
              id="log-retention-days"
              type="number"
              min="0"
              max="365"
              value={formState.logRetentionDays}
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  logRetentionDays: Number.parseInt(event.target.value, 10) || 0,
                }))
              }
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save workspace settings
          </Button>
          <Button variant="outline" onClick={onOpenAdminSettings}>
            <Settings className="mr-2 h-4 w-4" />
            Admin resource tiers
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-border bg-background p-4">
            <h4 className="text-sm font-semibold">Rebuild image</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              Pull the latest workspace image and stop the current workspace so it can be restarted cleanly.
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => rebuildMutation.mutate()}
              disabled={!hasWorkspace || rebuildMutation.isPending}
            >
              {rebuildMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
              Rebuild image
            </Button>
            {!hasWorkspace ? (
              <p className="mt-3 text-xs text-muted-foreground">Provision workspace first in AI Editor or Webtop.</p>
            ) : null}
          </div>

          <div className="rounded-lg border border-border bg-background p-4">
            <h4 className="text-sm font-semibold">Reset workspace</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              Delete workspace files and reinitialize based on the project creation method.
            </p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" className="mt-4" disabled={!hasWorkspace}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Reset workspace
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Reset workspace</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete current workspace files before reinitializing the workspace.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel disabled={resetMutation.isPending}>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => resetMutation.mutate()}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    {resetMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Confirm reset
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
            {!hasWorkspace ? (
              <p className="mt-3 text-xs text-muted-foreground">Provision workspace first in AI Editor or Webtop.</p>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}