import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Page, PageSection, Spinner, TreeView, TreeViewDataItem } from '@patternfly/react-core';
import { Building2, FolderKanban, GitBranch, Plus, Rocket, Server, Settings2 } from 'lucide-react';
import { Outlet, useNavigate } from 'react-router-dom';

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
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
import PageHeader from '@/components/ui/PageHeader';
import { toast } from '@/hooks/use-toast';
import {
  ProjectApp,
  createApp,
  createDeployment,
  createEnvironment,
  createOrganization,
  createProject,
  getDeployments,
  Organization,
  Project,
  ProjectEnvironment,
} from '@/lib/api';
import { useOrganizationHierarchyData } from '@/hooks/useOrganizationHierarchyData';
import {
  buildAppOverviewPath,
  buildEnvironmentPath,
  buildOrganizationPath,
  buildOrganizationSettingsPath,
  buildProjectPath,
} from '@/lib/organizationPaths';

type DialogMode = 'organization' | 'project' | 'environment' | 'app' | 'deployment' | null;

interface ProjectFormState {
  name: string;
  description: string;
}

interface EnvironmentFormState {
  name: string;
  description: string;
}

interface AppFormState {
  name: string;
  description: string;
  source_type: ProjectApp['source_type'];
  repository_url: string;
  compose_path: string;
}

interface DeploymentFormState {
  version: string;
  source_ref: string;
  notes: string;
}

export interface OrganizationHierarchyOutletContext {
  organizations: Organization[];
  organizationsLoading: boolean;
  projects: Project[];
  projectsLoading: boolean;
  environments: ProjectEnvironment[];
  environmentsLoading: boolean;
  apps: ProjectApp[];
  appsLoading: boolean;
  deployments: Awaited<ReturnType<typeof getDeployments>>['data'];
  deploymentsLoading: boolean;
  selectedOrganization: Organization | null;
  selectedProject: Project | null;
  selectedEnvironment: ProjectEnvironment | null;
  selectedApp: ProjectApp | null;
}

function findTreeItem(items: TreeViewDataItem[], id: string): TreeViewDataItem | undefined {
  for (const item of items) {
    if (item.id === id) {
      return item;
    }
    if (item.children) {
      const match = findTreeItem(item.children, id);
      if (match) {
        return match;
      }
    }
  }
  return undefined;
}

function filterTreeItems(items: TreeViewDataItem[], term: string): TreeViewDataItem[] {
  if (!term.trim()) {
    return items;
  }

  const normalized = term.trim().toLowerCase();

  return items
    .map((item) => {
      const children = item.children ? filterTreeItems(item.children, normalized) : undefined;
      const name = typeof item.name === 'string' ? item.name.toLowerCase() : '';
      if (name.includes(normalized) || (children && children.length > 0)) {
        return {
          ...item,
          defaultExpanded: true,
          children,
        };
      }
      return null;
    })
    .filter(Boolean) as TreeViewDataItem[];
}

const Organizations = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [dialogMode, setDialogMode] = useState<DialogMode>(null);
  const [organizationForm, setOrganizationForm] = useState({ name: '', description: '' });
  const [projectForm, setProjectForm] = useState<ProjectFormState>({ name: '', description: '' });
  const [environmentForm, setEnvironmentForm] = useState<EnvironmentFormState>({
    name: '',
    description: '',
  });
  const [appForm, setAppForm] = useState<AppFormState>({
    name: '',
    description: '',
    source_type: 'compose',
    repository_url: '',
    compose_path: './container-compose.dev.yml',
  });
  const [deploymentForm, setDeploymentForm] = useState<DeploymentFormState>({
    version: '',
    source_ref: 'main',
    notes: '',
  });

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    apps,
    appsLoading,
    canCreateOrganization,
    currentUser,
    deployments,
    deploymentsLoading,
    environments,
    environmentsLoading,
    organizations,
    organizationsLoading,
    projects,
    projectsLoading,
    selectedApp,
    selectedAppId,
    selectedEnvironment,
    selectedEnvironmentId,
    selectedOrgId,
    selectedOrganization,
    selectedProject,
    selectedProjectId,
  } = useOrganizationHierarchyData();

  const hierarchyTree = useMemo<TreeViewDataItem[]>(() => {
    return organizations.map((organization) => ({
      id: `organization:${organization.id}`,
      name: organization.name,
      icon: <Building2 size={14} />,
      defaultExpanded: organization.id === selectedOrgId,
      children:
        organization.id === selectedOrgId
          ? projects.map((project) => ({
              id: `project:${project.id}`,
              name: project.name,
              icon: <FolderKanban size={14} />,
              defaultExpanded: project.id === selectedProjectId,
              children:
                project.id === selectedProjectId
                  ? environments.map((environment) => ({
                      id: `environment:${environment.id}`,
                      name: environment.name,
                      icon: <GitBranch size={14} />,
                      defaultExpanded: environment.id === selectedEnvironmentId,
                      children:
                        environment.id === selectedEnvironmentId
                          ? apps.map((app) => ({
                              id: `app:${app.id}`,
                              name: app.name,
                              icon: <Server size={14} />,
                            }))
                          : undefined,
                    }))
                  : undefined,
            }))
          : undefined,
    }));
  }, [apps, environments, organizations, projects, selectedAppId, selectedEnvironmentId, selectedOrgId, selectedProjectId]);

  const filteredTree = useMemo(() => filterTreeItems(hierarchyTree, searchTerm), [hierarchyTree, searchTerm]);
  const selectedTreeId = useMemo(() => {
    if (selectedAppId !== null) return `app:${selectedAppId}`;
    if (selectedEnvironmentId !== null) return `environment:${selectedEnvironmentId}`;
    if (selectedProjectId !== null) return `project:${selectedProjectId}`;
    if (selectedOrgId !== null) return `organization:${selectedOrgId}`;
    return null;
  }, [selectedAppId, selectedEnvironmentId, selectedOrgId, selectedProjectId]);
  const activeTreeItems = useMemo(() => {
    if (!selectedTreeId) {
      return undefined;
    }
    const item = findTreeItem(filteredTree, selectedTreeId);
    return item ? [item] : undefined;
  }, [filteredTree, selectedTreeId]);

  const createOrganizationMutation = useMutation({
    mutationFn: createOrganization,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      setOrganizationForm({ name: '', description: '' });
      setDialogMode(null);
      if (response.data?.id) {
        navigate(buildOrganizationPath(response.data.id));
      }
      toast({ title: 'Organization created', description: 'The organization hierarchy is ready for projects.' });
    },
  });

  const createProjectMutation = useMutation({
    mutationFn: createProject,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['organizationProjects', selectedOrgId] });
      setProjectForm({ name: '', description: '' });
      setDialogMode(null);
      if (selectedOrgId && response.data?.id) {
        navigate(buildProjectPath(selectedOrgId, response.data.id));
      }
      toast({ title: 'Project created', description: 'Add environments to separate dev, staging, and production.' });
    },
  });

  const createEnvironmentMutation = useMutation({
    mutationFn: createEnvironment,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['environments', selectedProjectId] });
      setEnvironmentForm({
        name: '',
        description: '',
      });
      setDialogMode(null);
      if (selectedOrgId && selectedProjectId && response.data?.id) {
        navigate(buildEnvironmentPath(selectedOrgId, selectedProjectId, response.data.id));
      }
      toast({ title: 'Environment created', description: 'You can now attach applications to this environment.' });
    },
  });

  const createAppMutation = useMutation({
    mutationFn: createApp,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['apps', selectedEnvironmentId] });
      setAppForm({
        name: '',
        description: '',
        source_type: 'compose',
        repository_url: '',
        compose_path: './container-compose.dev.yml',
      });
      setDialogMode(null);
      if (selectedOrgId && selectedProjectId && selectedEnvironmentId && response.data?.id) {
        navigate(buildAppOverviewPath(selectedOrgId, selectedProjectId, selectedEnvironmentId, response.data.id));
      }
      toast({ title: 'Application created', description: 'Application details are ready to review before opening the workspace.' });
    },
  });

  const createDeploymentMutation = useMutation({
    mutationFn: createDeployment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments', selectedAppId] });
      setDeploymentForm({ version: '', source_ref: 'main', notes: '' });
      setDialogMode(null);
      toast({ title: 'Deployment recorded', description: 'Deployment history has been updated for the selected app.' });
    },
  });

  const isBusy =
    createOrganizationMutation.isPending ||
    createProjectMutation.isPending ||
    createEnvironmentMutation.isPending ||
    createAppMutation.isPending ||
    createDeploymentMutation.isPending;

  const summaryCards = [
    {
      title: 'Organizations',
      value: organizations.length,
      icon: <Building2 className="h-4 w-4 text-muted-foreground" />,
      subtitle: 'Top-level tenant containers',
    },
    {
      title: 'Projects',
      value: projects.length,
      icon: <FolderKanban className="h-4 w-4 text-muted-foreground" />,
      subtitle: selectedOrganization ? `Inside ${selectedOrganization.name}` : 'Select an organization',
    },
    {
      title: 'Environments',
      value: environments.length,
      icon: <GitBranch className="h-4 w-4 text-muted-foreground" />,
      subtitle: selectedProject ? `Inside ${selectedProject.name}` : 'Select a project',
    },
    {
      title: 'Applications',
      value: apps.length,
      icon: <Server className="h-4 w-4 text-muted-foreground" />,
      subtitle: selectedEnvironment ? `Inside ${selectedEnvironment.name}` : 'Select an environment',
    },
  ];

  const openDialog = (mode: DialogMode) => setDialogMode(mode);
  const closeDialog = () => {
    if (isBusy) {
      return;
    }
    setDialogMode(null);
  };

  const handleTreeSelect = (_event: React.MouseEvent, item: TreeViewDataItem) => {
    const rawId = String(item.id);
    const [type, value] = rawId.split(':');
    const id = Number(value);

    if (Number.isNaN(id)) {
      return;
    }

    if (type === 'organization') {
      navigate(buildOrganizationPath(id));
    } else if (type === 'project' && selectedOrgId) {
      navigate(buildProjectPath(selectedOrgId, id));
    } else if (type === 'environment' && selectedOrgId && selectedProjectId) {
      navigate(buildEnvironmentPath(selectedOrgId, selectedProjectId, id));
    } else if (type === 'app' && selectedOrgId && selectedProjectId && selectedEnvironmentId) {
      navigate(buildAppOverviewPath(selectedOrgId, selectedProjectId, selectedEnvironmentId, id));
    }
  };

  const submitOrganization = () => {
    if (!canCreateOrganization) {
      toast({
        title: 'Admin access required',
        description: 'Only global administrators can create organizations.',
        variant: 'destructive',
      });
      return;
    }
    if (!organizationForm.name.trim()) {
      toast({ title: 'Name required', description: 'Organizations need a name before they can be created.', variant: 'destructive' });
      return;
    }
    createOrganizationMutation.mutate(organizationForm);
  };

  const submitProject = () => {
    if (!selectedOrgId || !currentUser?.id) {
      toast({ title: 'Missing context', description: 'Select an organization before creating a project.', variant: 'destructive' });
      return;
    }
    if (!projectForm.name.trim()) {
      toast({ title: 'Name required', description: 'Projects need a name before they can be created.', variant: 'destructive' });
      return;
    }
    createProjectMutation.mutate({
      name: projectForm.name,
      description: projectForm.description,
      owner: currentUser.id,
      organization_id: selectedOrgId,
      workspace_image: 'fedora:43',
      workspace_size: 'standard',
    });
  };

  const submitEnvironment = () => {
    if (!selectedProjectId) {
      toast({ title: 'Missing project', description: 'Select a project before creating an environment.', variant: 'destructive' });
      return;
    }
    if (!environmentForm.name.trim()) {
      toast({ title: 'Name required', description: 'Environments need a name before they can be created.', variant: 'destructive' });
      return;
    }
    createEnvironmentMutation.mutate({
      project_id: selectedProjectId,
      ...environmentForm,
    });
  };

  const submitApp = () => {
    if (!selectedEnvironmentId) {
      toast({ title: 'Missing environment', description: 'Select an environment before creating an application.', variant: 'destructive' });
      return;
    }
    if (!appForm.name.trim()) {
      toast({ title: 'Name required', description: 'Applications need a name before they can be created.', variant: 'destructive' });
      return;
    }
    createAppMutation.mutate({
      environment_id: selectedEnvironmentId,
      ...appForm,
    });
  };

  const submitDeployment = () => {
    if (!selectedAppId) {
      toast({ title: 'Missing app', description: 'Select an app before recording a deployment.', variant: 'destructive' });
      return;
    }
    if (!deploymentForm.version.trim()) {
      toast({ title: 'Version required', description: 'Deployments need a version identifier.', variant: 'destructive' });
      return;
    }
    createDeploymentMutation.mutate({
      app_id: selectedAppId,
      version: deploymentForm.version,
      source_ref: deploymentForm.source_ref,
      notes: deploymentForm.notes,
      status: 'pending',
    });
  };

  const outletContext: OrganizationHierarchyOutletContext = {
    organizations,
    organizationsLoading,
    projects,
    projectsLoading,
    environments,
    environmentsLoading,
    apps,
    appsLoading,
    deployments,
    deploymentsLoading,
    selectedOrganization,
    selectedProject,
    selectedEnvironment,
    selectedApp,
  };

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div className="space-y-6">
          <PageHeader
            title="Organizations"
            description="Manage the new hierarchy: organizations own projects, projects own environments, environments own applications, and applications own deployment history."
            icon={<Building2 size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
            actions={
              <>
                <Button
                  variant="secondary"
                  icon={<Plus size={14} />}
                  onClick={() => openDialog('organization')}
                  isDisabled={!canCreateOrganization}
                >
                  Create organization
                </Button>
                <Button
                  variant="secondary"
                  icon={<Settings2 size={14} />}
                  onClick={() => selectedOrgId && navigate(buildOrganizationSettingsPath(selectedOrgId))}
                  isDisabled={!selectedOrgId}
                >
                  Org settings
                </Button>
                <Button variant="secondary" icon={<Plus size={14} />} onClick={() => openDialog('project')} isDisabled={!selectedOrgId}>
                  Create project
                </Button>
                <Button variant="secondary" icon={<Plus size={14} />} onClick={() => openDialog('environment')} isDisabled={!selectedProjectId}>
                  Create environment
                </Button>
                <Button variant="secondary" icon={<Plus size={14} />} onClick={() => openDialog('app')} isDisabled={!selectedEnvironmentId}>
                  Create application
                </Button>
                <Button variant="primary" icon={<Rocket size={14} />} onClick={() => openDialog('deployment')} isDisabled={!selectedAppId}>
                  Record deployment
                </Button>
              </>
            }
          />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {summaryCards.map((card) => (
              <div key={card.title} className="rounded-lg border bg-card text-card-foreground shadow-sm">
                <div className="flex flex-row items-start justify-between space-y-0 p-6 pb-2">
                  <div>
                    <p className="text-sm text-muted-foreground">{card.title}</p>
                    <h3 className="text-3xl font-semibold">{card.value}</h3>
                  </div>
                  {card.icon}
                </div>
                <div className="p-6 pt-0 text-sm text-muted-foreground">{card.subtitle}</div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
            <div className="rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden">
              <div className="flex flex-col space-y-1.5 p-6">
                <h3 className="text-xl font-semibold">Hierarchy</h3>
                <p className="text-sm text-muted-foreground">
                  PatternFly tree view organizes the organization, project, environment, and application chain in one place.
                </p>
              </div>
              <div className="p-6 pt-0 space-y-4">
                <Input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search organizations, projects, environments, applications"
                />

                <div className="rounded-lg border border-border/80 bg-muted/20 p-3">
                  {organizationsLoading ? (
                    <div className="flex items-center gap-3 py-6 text-sm text-muted-foreground">
                      <Spinner size="md" />
                      Loading organizations...
                    </div>
                  ) : filteredTree.length === 0 ? (
                    <div className="py-8 text-sm text-muted-foreground">
                      No organizations match the current search.
                    </div>
                  ) : (
                    <TreeView
                      data={filteredTree}
                      activeItems={activeTreeItems}
                      onSelect={handleTreeSelect}
                      hasSelectableNodes
                      hasGuides
                      aria-label="Organizations hierarchy"
                    />
                  )}
                </div>

                <div className="rounded-lg border border-dashed border-border/80 bg-background px-4 py-3 text-sm text-muted-foreground">
                  The left rail is now the navigation surface. The right pane is split into nested detail routes for organizations, projects, environments, and applications.
                </div>

                {!canCreateOrganization ? (
                  <div className="rounded-lg border border-dashed border-border/80 bg-background px-4 py-3 text-sm text-muted-foreground">
                    Organization creation is limited to global administrators. You can still browse organizations you belong to and create projects inside accessible organizations.
                  </div>
                ) : null}
              </div>
            </div>

            <Outlet context={outletContext} />
          </div>
        </div>
      </PageSection>

      <Dialog open={dialogMode === 'organization'} onOpenChange={(open) => (open ? openDialog('organization') : closeDialog())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create organization</DialogTitle>
            <DialogDescription>Global admins can create organizations that own projects and delegated admins.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Organization name" value={organizationForm.name} onChange={(event) => setOrganizationForm((current) => ({ ...current, name: event.target.value }))} />
            <Textarea placeholder="Describe the organization" value={organizationForm.description} onChange={(event) => setOrganizationForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={closeDialog} isDisabled={isBusy}>Cancel</Button>
            <Button variant="primary" onClick={submitOrganization} isLoading={createOrganizationMutation.isPending} isDisabled={!canCreateOrganization}>Create organization</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogMode === 'project'} onOpenChange={(open) => (open ? openDialog('project') : closeDialog())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
            <DialogDescription>Projects now live inside the selected organization.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Project name" value={projectForm.name} onChange={(event) => setProjectForm((current) => ({ ...current, name: event.target.value }))} />
            <Textarea placeholder="Describe the project" value={projectForm.description} onChange={(event) => setProjectForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={closeDialog} isDisabled={isBusy}>Cancel</Button>
            <Button variant="primary" onClick={submitProject} isLoading={createProjectMutation.isPending}>Create project</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogMode === 'environment'} onOpenChange={(open) => (open ? openDialog('environment') : closeDialog())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create environment</DialogTitle>
            <DialogDescription>Use environments to group related applications like production, staging, development, or demo.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Environment name" value={environmentForm.name} onChange={(event) => setEnvironmentForm((current) => ({ ...current, name: event.target.value }))} />
            <Textarea placeholder="Describe the environment" value={environmentForm.description} onChange={(event) => setEnvironmentForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={closeDialog} isDisabled={isBusy}>Cancel</Button>
            <Button variant="primary" onClick={submitEnvironment} isLoading={createEnvironmentMutation.isPending}>Create environment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogMode === 'app'} onOpenChange={(open) => (open ? openDialog('app') : closeDialog())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create application</DialogTitle>
            <DialogDescription>Applications are the containers inside an environment that hold services and deployment history.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Application name" value={appForm.name} onChange={(event) => setAppForm((current) => ({ ...current, name: event.target.value }))} />
            <Input placeholder="Source type" value={appForm.source_type} onChange={(event) => setAppForm((current) => ({ ...current, source_type: event.target.value as ProjectApp['source_type'] }))} />
            <Input placeholder="Repository URL" value={appForm.repository_url} onChange={(event) => setAppForm((current) => ({ ...current, repository_url: event.target.value }))} />
            <Input placeholder="Compose path" value={appForm.compose_path} onChange={(event) => setAppForm((current) => ({ ...current, compose_path: event.target.value }))} />
            <Textarea placeholder="Describe the application" value={appForm.description} onChange={(event) => setAppForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={closeDialog} isDisabled={isBusy}>Cancel</Button>
            <Button variant="primary" onClick={submitApp} isLoading={createAppMutation.isPending}>Create application</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dialogMode === 'deployment'} onOpenChange={(open) => (open ? openDialog('deployment') : closeDialog())}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record deployment</DialogTitle>
            <DialogDescription>Deployment records track release history for the selected app.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Version" value={deploymentForm.version} onChange={(event) => setDeploymentForm((current) => ({ ...current, version: event.target.value }))} />
            <Input placeholder="Source ref" value={deploymentForm.source_ref} onChange={(event) => setDeploymentForm((current) => ({ ...current, source_ref: event.target.value }))} />
            <Textarea placeholder="Release notes" value={deploymentForm.notes} onChange={(event) => setDeploymentForm((current) => ({ ...current, notes: event.target.value }))} />
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={closeDialog} isDisabled={isBusy}>Cancel</Button>
            <Button variant="primary" onClick={submitDeployment} isLoading={createDeploymentMutation.isPending}>Record deployment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
};

export default Organizations;