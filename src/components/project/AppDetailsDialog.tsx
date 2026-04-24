import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import type { ProjectApp } from '@/lib/api';
import { updateApp } from '@/lib/api';

interface AppDetailsDialogProps {
  app: ProjectApp | null;
  environmentId?: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface AppDetailsFormState {
  name: string;
  description: string;
  sourceType: ProjectApp['source_type'];
  repositoryUrl: string;
  composePath: string;
  status: ProjectApp['status'];
}

const emptyFormState: AppDetailsFormState = {
  name: '',
  description: '',
  sourceType: 'compose',
  repositoryUrl: '',
  composePath: '',
  status: 'draft',
};

function buildFormState(app: ProjectApp): AppDetailsFormState {
  return {
    name: app.name,
    description: app.description || '',
    sourceType: app.source_type,
    repositoryUrl: app.repository_url || '',
    composePath: app.compose_path || '',
    status: app.status,
  };
}

export function AppDetailsDialog({ app, environmentId, open, onOpenChange }: AppDetailsDialogProps) {
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<AppDetailsFormState>(emptyFormState);

  useEffect(() => {
    if (!open) {
      setFormState(emptyFormState);
      return;
    }

    if (app) {
      setFormState(buildFormState(app));
    }
  }, [app, open]);

  const updateAppMutation = useMutation({
    mutationFn: (data: Partial<ProjectApp>) => updateApp(app!.id, data),
    onSuccess: () => {
      if (environmentId !== undefined && environmentId !== null) {
        queryClient.invalidateQueries({ queryKey: ['apps', environmentId] });
      }
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      toast({ title: 'Application updated', description: 'Application details were saved.' });
      onOpenChange(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the application.',
        variant: 'destructive',
      });
    },
  });

  if (!app) {
    return null;
  }

  const submit = () => {
    if (!formState.name.trim()) {
      toast({
        title: 'Name required',
        description: 'Applications need a name before they can be updated.',
        variant: 'destructive',
      });
      return;
    }

    updateAppMutation.mutate({
      name: formState.name.trim(),
      description: formState.description.trim(),
      source_type: formState.sourceType,
      repository_url: formState.repositoryUrl.trim() || undefined,
      compose_path: formState.composePath.trim() || undefined,
      status: formState.status,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>App Details</DialogTitle>
          <DialogDescription>Update the application metadata surfaced in the hierarchy and workspace.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="Application name"
            value={formState.name}
            onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
          />
          <Select
            value={formState.sourceType}
            onValueChange={(value) => setFormState((current) => ({ ...current, sourceType: value as ProjectApp['source_type'] }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Source type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="compose">Compose</SelectItem>
              <SelectItem value="container">Container image</SelectItem>
              <SelectItem value="repository">Repository</SelectItem>
              <SelectItem value="custom">Custom</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Repository URL"
            value={formState.repositoryUrl}
            onChange={(event) => setFormState((current) => ({ ...current, repositoryUrl: event.target.value }))}
          />
          <Input
            placeholder="Compose path"
            value={formState.composePath}
            onChange={(event) => setFormState((current) => ({ ...current, composePath: event.target.value }))}
          />
          <Select
            value={formState.status}
            onValueChange={(value) => setFormState((current) => ({ ...current, status: value as ProjectApp['status'] }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="archived">Archived</SelectItem>
            </SelectContent>
          </Select>
          <Textarea
            placeholder="Describe the application"
            value={formState.description}
            onChange={(event) => setFormState((current) => ({ ...current, description: event.target.value }))}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={updateAppMutation.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!formState.name.trim() || updateAppMutation.isPending}>
            {updateAppMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}