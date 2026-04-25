import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CheckCircle2, FolderGit2, LayoutTemplate, PackagePlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
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
import { createProjectService, ProjectService } from '@/lib/api';

type CreationMethod = 'blank' | 'repository' | 'template';

interface ServiceCreationWizardProps {
  appId: number;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

const stepLabels = ['Choose method', 'Configure service', 'Review'];

const serviceTemplates: Array<{
  key: string;
  label: string;
  description: string;
  image: string;
  serviceType: ProjectService['service_type'];
  ports: string;
}> = [
  {
    key: 'frontend-web',
    label: 'Frontend web service',
    description: 'Browser-facing app service with a default Node image and port 3000.',
    image: 'node:20',
    serviceType: 'frontend',
    ports: '3000:3000',
  },
  {
    key: 'python-api',
    label: 'Python API service',
    description: 'Backend API service with a default Python image and port 8000.',
    image: 'python:3.12',
    serviceType: 'backend',
    ports: '8000:8000',
  },
  {
    key: 'postgres-db',
    label: 'PostgreSQL database',
    description: 'Stateful data service with the standard Postgres image and port 5432.',
    image: 'postgres:16',
    serviceType: 'custom',
    ports: '5432:5432',
  },
];

const parsePorts = (portsText: string) =>
  portsText
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

const parseEnvironmentText = (environmentText: string) => {
  return environmentText
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce<Record<string, string>>((result, line) => {
      const separatorIndex = line.indexOf('=');
      if (separatorIndex === -1) {
        return result;
      }

      const key = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();
      if (key) {
        result[key] = value;
      }
      return result;
    }, {});
};

export const ServiceCreationWizard = ({ appId, isOpen, onOpenChange, onCreated }: ServiceCreationWizardProps) => {
  const [stepIndex, setStepIndex] = useState(0);
  const [method, setMethod] = useState<CreationMethod | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [formState, setFormState] = useState({
    name: '',
    image: '',
    serviceType: 'custom' as ProjectService['service_type'],
    ports: '',
    environmentText: '',
    repositoryUrl: '',
    autostart: false,
    cpuLimit: '',
    memoryLimit: '',
  });

  const resetWizard = () => {
    setStepIndex(0);
    setMethod(null);
    setSelectedTemplate(null);
    setFormState({
      name: '',
      image: '',
      serviceType: 'custom',
      ports: '',
      environmentText: '',
      repositoryUrl: '',
      autostart: false,
      cpuLimit: '',
      memoryLimit: '',
    });
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      const config: Record<string, any> = {};
      if (method === 'repository' && formState.repositoryUrl.trim()) {
        config.repository_url = formState.repositoryUrl.trim();
      }
      if (method === 'template' && selectedTemplate) {
        config.template_key = selectedTemplate;
      }

      return createProjectService({
        app: appId,
        name: formState.name.trim(),
        image: formState.image.trim(),
        service_type: formState.serviceType,
        ports: parsePorts(formState.ports),
        environment: parseEnvironmentText(formState.environmentText),
        config,
        autostart: formState.autostart,
        cpu_limit: formState.cpuLimit.trim() || undefined,
        memory_limit: formState.memoryLimit.trim() || undefined,
      });
    },
    onSuccess: () => {
      toast({ title: 'Service created', description: 'The service was added to this application.' });
      onCreated();
      onOpenChange(false);
      resetWizard();
    },
    onError: (error) => {
      toast({
        title: 'Create failed',
        description: error instanceof Error ? error.message : 'Unable to create the service.',
        variant: 'destructive',
      });
    },
  });

  const reviewItems = useMemo(() => [
    ['Method', method ?? 'Not selected'],
    ['Name', formState.name || 'Not provided'],
    ['Image', formState.image || 'Not provided'],
    ['Type', formState.serviceType],
    ['Ports', formState.ports || 'None'],
    ['Repository', formState.repositoryUrl || 'None'],
    ['Autostart', formState.autostart ? 'Enabled' : 'Disabled'],
    ['CPU limit', formState.cpuLimit || 'Not set'],
    ['Memory limit', formState.memoryLimit || 'Not set'],
  ], [formState, method]);

  const canAdvanceFromSetup = Boolean(
    method &&
    formState.name.trim() &&
    formState.image.trim() &&
    (method !== 'repository' || formState.repositoryUrl.trim()) &&
    (method !== 'template' || selectedTemplate)
  );

  const handleOpenChange = (open: boolean) => {
    onOpenChange(open);
    if (!open) {
      resetWizard();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Create service</DialogTitle>
          <DialogDescription>Create a runnable service inside this application using a step-by-step flow.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="space-y-2 rounded-lg border border-border/70 bg-muted/20 p-4">
            {stepLabels.map((label, index) => (
              <div key={label} className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${index === stepIndex ? 'bg-background font-semibold text-foreground shadow-sm' : 'text-muted-foreground'}`}>
                <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs ${index <= stepIndex ? 'border-primary text-primary' : 'border-border text-muted-foreground'}`}>
                  {index < stepIndex ? <CheckCircle2 className="h-4 w-4" /> : index + 1}
                </span>
                {label}
              </div>
            ))}
          </div>

          <div className="space-y-4">
            {stepIndex === 0 ? (
              <div className="grid gap-4 md:grid-cols-3">
                <Card className={method === 'blank' ? 'border-primary ring-1 ring-primary/30' : ''}>
                  <button type="button" className="h-full w-full text-left" onClick={() => setMethod('blank')}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-lg">
                        <PackagePlus className="h-5 w-5" />
                        Blank service
                      </CardTitle>
                      <CardDescription>Start from an image, ports, and runtime limits.</CardDescription>
                    </CardHeader>
                  </button>
                </Card>
                <Card className={method === 'repository' ? 'border-primary ring-1 ring-primary/30' : ''}>
                  <button type="button" className="h-full w-full text-left" onClick={() => setMethod('repository')}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-lg">
                        <FolderGit2 className="h-5 w-5" />
                        Repository-backed
                      </CardTitle>
                      <CardDescription>Track a repository URL in the service config for later automation.</CardDescription>
                    </CardHeader>
                  </button>
                </Card>
                <Card className={method === 'template' ? 'border-primary ring-1 ring-primary/30' : ''}>
                  <button type="button" className="h-full w-full text-left" onClick={() => setMethod('template')}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-lg">
                        <LayoutTemplate className="h-5 w-5" />
                        Template-based
                      </CardTitle>
                      <CardDescription>Use a preset image and ports as a faster starting point.</CardDescription>
                    </CardHeader>
                  </button>
                </Card>
              </div>
            ) : null}

            {stepIndex === 1 ? (
              <div className="space-y-4">
                {method === 'template' ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    {serviceTemplates.map((template) => (
                      <Card key={template.key} className={selectedTemplate === template.key ? 'border-primary ring-1 ring-primary/30' : ''}>
                        <button
                          type="button"
                          className="h-full w-full text-left"
                          onClick={() => {
                            setSelectedTemplate(template.key);
                            setFormState((current) => ({
                              ...current,
                              image: template.image,
                              serviceType: template.serviceType,
                              ports: template.ports,
                            }));
                          }}
                        >
                          <CardHeader>
                            <CardTitle className="text-base">{template.label}</CardTitle>
                            <CardDescription>{template.description}</CardDescription>
                          </CardHeader>
                        </button>
                      </Card>
                    ))}
                  </div>
                ) : null}

                <div className="grid gap-4 md:grid-cols-2">
                  <Input placeholder="Service name" value={formState.name} onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))} />
                  <Input placeholder="Container image" value={formState.image} onChange={(event) => setFormState((current) => ({ ...current, image: event.target.value }))} />
                  <Input placeholder="Service type" value={formState.serviceType} onChange={(event) => setFormState((current) => ({ ...current, serviceType: event.target.value as ProjectService['service_type'] }))} />
                  <Input placeholder="Ports (comma separated, e.g. 3000:3000,9229:9229)" value={formState.ports} onChange={(event) => setFormState((current) => ({ ...current, ports: event.target.value }))} />
                  <Input placeholder="CPU limit" value={formState.cpuLimit} onChange={(event) => setFormState((current) => ({ ...current, cpuLimit: event.target.value }))} />
                  <Input placeholder="Memory limit" value={formState.memoryLimit} onChange={(event) => setFormState((current) => ({ ...current, memoryLimit: event.target.value }))} />
                </div>

                {method === 'repository' ? (
                  <Input placeholder="Repository URL" value={formState.repositoryUrl} onChange={(event) => setFormState((current) => ({ ...current, repositoryUrl: event.target.value }))} />
                ) : null}

                <Textarea
                  placeholder="Environment variables (one KEY=VALUE pair per line)"
                  rows={5}
                  value={formState.environmentText}
                  onChange={(event) => setFormState((current) => ({ ...current, environmentText: event.target.value }))}
                />

                <div className="flex items-center gap-3 rounded-lg border border-border/70 bg-muted/20 px-4 py-3">
                  <Checkbox
                    id="service-autostart"
                    checked={formState.autostart}
                    onCheckedChange={(checked) => setFormState((current) => ({ ...current, autostart: checked === true }))}
                  />
                  <label htmlFor="service-autostart" className="text-sm font-medium">
                    Start this service automatically when the workspace starts
                  </label>
                </div>
              </div>
            ) : null}

            {stepIndex === 2 ? (
              <div className="space-y-3">
                {reviewItems.map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-4 rounded-lg border border-border/70 px-4 py-3">
                    <div className="text-sm font-medium text-foreground">{label}</div>
                    <div className="text-sm text-muted-foreground text-right">{value}</div>
                  </div>
                ))}
                {formState.environmentText.trim() ? (
                  <div className="rounded-lg border border-border/70 px-4 py-3">
                    <div className="text-sm font-medium text-foreground">Environment variables</div>
                    <pre className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{formState.environmentText}</pre>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          <Button
            variant="outline"
            onClick={() => {
              if (stepIndex === 0) {
                handleOpenChange(false);
                return;
              }
              setStepIndex((current) => current - 1);
            }}
            disabled={createMutation.isPending}
          >
            {stepIndex === 0 ? 'Cancel' : 'Back'}
          </Button>

          {stepIndex < 2 ? (
            <Button
              onClick={() => setStepIndex((current) => current + 1)}
              disabled={(stepIndex === 0 && !method) || (stepIndex === 1 && !canAdvanceFromSetup)}
            >
              Next
            </Button>
          ) : (
            <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create service'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};