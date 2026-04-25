import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  EmptyState,
  EmptyStateBody,
  FormSelect,
  FormSelectOption,
  Grid,
  GridItem,
  Label,
  Page,
  PageSection,
  SearchInput,
} from '@patternfly/react-core';
import { ArrowRight, FolderKanban, Package, ShieldCheck, Users } from 'lucide-react';

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import PageHeader from '@/components/ui/PageHeader';
import { getCurrentUser, getMyProjects, Project } from '@/lib/api';

type RoleFilter = 'all' | 'owner' | 'contributor';
type StatusFilter = 'all' | Project['status'];
type SortMode = 'recent' | 'name' | 'organization';

const statusColorMap: Record<Project['status'], 'grey' | 'blue' | 'orange' | 'green'> = {
  draft: 'grey',
  in_development: 'blue',
  awaiting_approval: 'orange',
  published: 'green',
};

const MyApplications = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sortBy, setSortBy] = useState<SortMode>('recent');
  const navigate = useNavigate();

  const { data: currentUserResponse } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  const { data: projectsResponse, isLoading, error } = useQuery({
    queryKey: ['myProjects'],
    queryFn: getMyProjects,
  });

  const currentUser = currentUserResponse?.data;
  const projects = projectsResponse?.data ?? [];

  const filteredProjects = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();

    return projects
      .filter((project) => {
        const role = currentUser && project.owner.id === currentUser.id ? 'owner' : 'contributor';
        const matchesRole = roleFilter === 'all' || role === roleFilter;
        const matchesStatus = statusFilter === 'all' || project.status === statusFilter;

        if (!matchesRole || !matchesStatus) {
          return false;
        }

        if (!normalizedSearch) {
          return true;
        }

        const haystack = `${project.name} ${project.description} ${project.organization?.name ?? ''}`.toLowerCase();
        return haystack.includes(normalizedSearch);
      })
      .sort((left, right) => {
        if (sortBy === 'name') {
          return left.name.localeCompare(right.name);
        }
        if (sortBy === 'organization') {
          return (left.organization?.name ?? 'Independent').localeCompare(right.organization?.name ?? 'Independent');
        }
        return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      });
  }, [currentUser, projects, roleFilter, searchQuery, sortBy, statusFilter]);

  const groupedProjects = useMemo(() => {
    return filteredProjects.reduce<Record<string, Project[]>>((groups, project) => {
      const key = project.organization?.name ?? 'Independent projects';
      groups[key] = groups[key] ? [...groups[key], project] : [project];
      return groups;
    }, {});
  }, [filteredProjects]);

  const stats = {
    owned: currentUser ? projects.filter((project) => project.owner.id === currentUser.id).length : 0,
    contributing: currentUser ? projects.filter((project) => project.owner.id !== currentUser.id).length : 0,
    awaitingApproval: projects.filter((project) => project.status === 'awaiting_approval').length,
    published: projects.filter((project) => project.status === 'published').length,
  };

  const errorMessage = error instanceof Error ? error.message : 'Unable to load your projects.';

  const openProject = (project: Project) => {
    if (project.organization) {
      navigate(`/organizations/${project.organization.id}/projects/${project.id}`);
      return;
    }
    navigate('/organizations');
  };

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div className="space-y-6">
          <PageHeader
            title="My Projects"
            description="Projects you own or contribute to, grouped around the new organization hierarchy instead of the old standalone project view."
            icon={<Package size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
            actions={
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => navigate('/my-teamspace')}>
                  Workspace Directory
                </Button>
                <Button variant="primary" onClick={() => navigate('/organizations')}>
                  Open Hierarchy
                </Button>
              </div>
            }
          />

          <Grid hasGutter>
            <GridItem sm={6} xl={3}>
              <Card>
                <CardTitle>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>Owned</span>
                    <ShieldCheck style={{ width: '1rem', height: '1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  </div>
                </CardTitle>
                <CardBody>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{stats.owned}</div>
                </CardBody>
              </Card>
            </GridItem>
            <GridItem sm={6} xl={3}>
              <Card>
                <CardTitle>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>Contributing</span>
                    <Users style={{ width: '1rem', height: '1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  </div>
                </CardTitle>
                <CardBody>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{stats.contributing}</div>
                </CardBody>
              </Card>
            </GridItem>
            <GridItem sm={6} xl={3}>
              <Card>
                <CardTitle>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>Awaiting Approval</span>
                    <FolderKanban style={{ width: '1rem', height: '1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  </div>
                </CardTitle>
                <CardBody>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{stats.awaitingApproval}</div>
                </CardBody>
              </Card>
            </GridItem>
            <GridItem sm={6} xl={3}>
              <Card>
                <CardTitle>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>Published</span>
                    <Package style={{ width: '1rem', height: '1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  </div>
                </CardTitle>
                <CardBody>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{stats.published}</div>
                </CardBody>
              </Card>
            </GridItem>
          </Grid>

          <Card>
            <CardTitle>Filter my projects</CardTitle>
            <CardBody>
              <p style={{ marginBottom: '1rem', color: 'var(--pf-v6-global--Color--200)', fontSize: '0.875rem' }}>
                Search by project or organization, then jump directly into the nested organization routes.
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
                <div style={{ flex: '1 1 200px' }}>
                  <SearchInput
                    value={searchQuery}
                    onChange={(_evt, value) => setSearchQuery(value)}
                    onClear={() => setSearchQuery('')}
                    placeholder="Search projects or organizations..."
                  />
                </div>
                <FormSelect
                  value={roleFilter}
                  onChange={(_evt, value) => setRoleFilter(value as RoleFilter)}
                  style={{ width: '200px' }}
                  aria-label="Filter by role"
                >
                  <FormSelectOption value="all" label="All roles" />
                  <FormSelectOption value="owner" label="Owner" />
                  <FormSelectOption value="contributor" label="Contributor" />
                </FormSelect>
                <FormSelect
                  value={statusFilter}
                  onChange={(_evt, value) => setStatusFilter(value as StatusFilter)}
                  style={{ width: '220px' }}
                  aria-label="Filter by status"
                >
                  <FormSelectOption value="all" label="All statuses" />
                  <FormSelectOption value="draft" label="Draft" />
                  <FormSelectOption value="in_development" label="In development" />
                  <FormSelectOption value="awaiting_approval" label="Awaiting approval" />
                  <FormSelectOption value="published" label="Published" />
                </FormSelect>
                <FormSelect
                  value={sortBy}
                  onChange={(_evt, value) => setSortBy(value as SortMode)}
                  style={{ width: '220px' }}
                  aria-label="Sort projects"
                >
                  <FormSelectOption value="recent" label="Most recent" />
                  <FormSelectOption value="name" label="Name" />
                  <FormSelectOption value="organization" label="Organization" />
                </FormSelect>
              </div>
            </CardBody>
          </Card>

          {isLoading && (
            <Card>
              <CardBody style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--pf-v6-global--Color--200)', fontSize: '0.875rem' }}>
                Loading your projects...
              </CardBody>
            </Card>
          )}

          {error && (
            <Card>
              <CardBody style={{ padding: '2.5rem', textAlign: 'center', fontSize: '0.875rem', color: 'var(--pf-v6-global--danger-color--100)' }}>
                {errorMessage}
              </CardBody>
            </Card>
          )}

          {!isLoading && !error && (
            <div className="space-y-6">
              {Object.entries(groupedProjects).map(([groupName, groupProjects]) => (
                <Card key={groupName}>
                  <CardTitle>{groupName}</CardTitle>
                  <CardBody>
                    <p style={{ marginBottom: '1rem', color: 'var(--pf-v6-global--Color--200)', fontSize: '0.875rem' }}>
                      {groupProjects.length} project{groupProjects.length === 1 ? '' : 's'} in this group.
                    </p>
                    <Grid hasGutter>
                      {groupProjects.map((project) => {
                        const role = currentUser && project.owner.id === currentUser.id ? 'Owner' : 'Contributor';

                        return (
                          <GridItem key={project.id} xl={6}>
                            <div style={{ borderRadius: '8px', border: '1px solid var(--pf-v6-global--BorderColor--100)', padding: '1.25rem' }}>
                              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem' }}>
                                <div>
                                  <div style={{ fontSize: '1.125rem', fontWeight: 600 }}>{project.name}</div>
                                  <div style={{ marginTop: '0.25rem', fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                                    {project.description || 'No project description yet.'}
                                  </div>
                                </div>
                                <Label color={statusColorMap[project.status]}>
                                  {project.status.replaceAll('_', ' ')}
                                </Label>
                              </div>

                              <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                <Label variant="outline">{role}</Label>
                                <Label variant="outline">{project.organization?.name ?? 'No organization'}</Label>
                                <Label variant="outline">{project.contributors.length + 1} collaborators</Label>
                              </div>

                              <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                                <span>Updated {new Date(project.updated_at).toLocaleDateString()}</span>
                                <span>Workspace {project.workspace_image ?? 'fedora:43'}</span>
                              </div>

                              <div style={{ marginTop: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                <Button variant="primary" onClick={() => openProject(project)}>
                                  Open Project
                                </Button>
                                {project.organization ? (
                                  <Button variant="secondary" onClick={() => navigate(`/organizations/${project.organization.id}`)}>
                                    Open Organization
                                  </Button>
                                ) : (
                                  <Button variant="secondary" onClick={() => navigate('/organizations')}>
                                    Open Hierarchy
                                  </Button>
                                )}
                              </div>
                            </div>
                          </GridItem>
                        );
                      })}
                    </Grid>
                  </CardBody>
                </Card>
              ))}

              {filteredProjects.length === 0 && (
                <Card>
                  <CardBody style={{ padding: '2.5rem', textAlign: 'center' }}>
                    <EmptyState>
                      <EmptyStateBody>No projects matched the current filters.</EmptyStateBody>
                      <Button variant="link" isInline onClick={() => navigate('/organizations')}>
                        Open organization hierarchy
                        <ArrowRight style={{ marginLeft: '0.5rem', width: '1rem', height: '1rem' }} />
                      </Button>
                    </EmptyState>
                  </CardBody>
                </Card>
              )}
            </div>
          )}
        </div>
      </PageSection>
    </Page>
  );
};

export default MyApplications;