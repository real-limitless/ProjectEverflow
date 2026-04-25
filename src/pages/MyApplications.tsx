import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Page, PageSection } from '@patternfly/react-core';
import { ArrowRight, FolderKanban, Package, Search, ShieldCheck, Users } from 'lucide-react';

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import PageHeader from '@/components/ui/PageHeader';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getCurrentUser, getMyProjects, Project } from '@/lib/api';

type RoleFilter = 'all' | 'owner' | 'contributor';
type StatusFilter = 'all' | Project['status'];
type SortMode = 'recent' | 'name' | 'organization';

const statusVariantMap: Record<Project['status'], 'secondary' | 'warning' | 'info' | 'success'> = {
  draft: 'secondary',
  in_development: 'info',
  awaiting_approval: 'warning',
  published: 'success',
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

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Owned</CardTitle>
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.owned}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Contributing</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.contributing}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Awaiting Approval</CardTitle>
                <FolderKanban className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.awaitingApproval}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Published</CardTitle>
                <Package className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.published}</div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Filter my projects</CardTitle>
              <CardDescription>Search by project or organization, then jump directly into the nested organization routes.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 lg:flex-row">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search projects or organizations..."
                  className="pl-10"
                />
              </div>
              <Select value={roleFilter} onValueChange={(value) => setRoleFilter(value as RoleFilter)}>
                <SelectTrigger className="w-full lg:w-[200px]">
                  <SelectValue placeholder="Filter by role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All roles</SelectItem>
                  <SelectItem value="owner">Owner</SelectItem>
                  <SelectItem value="contributor">Contributor</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
                <SelectTrigger className="w-full lg:w-[220px]">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="in_development">In development</SelectItem>
                  <SelectItem value="awaiting_approval">Awaiting approval</SelectItem>
                  <SelectItem value="published">Published</SelectItem>
                </SelectContent>
              </Select>
              <Select value={sortBy} onValueChange={(value) => setSortBy(value as SortMode)}>
                <SelectTrigger className="w-full lg:w-[220px]">
                  <SelectValue placeholder="Sort projects" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="recent">Most recent</SelectItem>
                  <SelectItem value="name">Name</SelectItem>
                  <SelectItem value="organization">Organization</SelectItem>
                </SelectContent>
              </Select>
            </CardContent>
          </Card>

          {isLoading && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">Loading your projects...</CardContent>
            </Card>
          )}

          {error && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-destructive">{errorMessage}</CardContent>
            </Card>
          )}

          {!isLoading && !error && (
            <div className="space-y-6">
              {Object.entries(groupedProjects).map(([groupName, groupProjects]) => (
                <Card key={groupName}>
                  <CardHeader>
                    <CardTitle>{groupName}</CardTitle>
                    <CardDescription>
                      {groupProjects.length} project{groupProjects.length === 1 ? '' : 's'} in this group.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    {groupProjects.map((project) => {
                      const role = currentUser && project.owner.id === currentUser.id ? 'Owner' : 'Contributor';

                      return (
                        <div key={project.id} className="rounded-lg border border-border p-5">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-lg font-semibold">{project.name}</div>
                              <div className="mt-1 text-sm text-muted-foreground">{project.description || 'No project description yet.'}</div>
                            </div>
                            <Badge variant={statusVariantMap[project.status]}>{project.status.replaceAll('_', ' ')}</Badge>
                          </div>

                          <div className="mt-4 flex flex-wrap gap-2">
                            <Badge variant="outline">{role}</Badge>
                            <Badge variant="outline">{project.organization?.name ?? 'No organization'}</Badge>
                            <Badge variant="outline">{project.contributors.length + 1} collaborators</Badge>
                          </div>

                          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                            <span>Updated {new Date(project.updated_at).toLocaleDateString()}</span>
                            <span>Workspace {project.workspace_image ?? 'fedora:43'}</span>
                          </div>

                          <div className="mt-5 flex flex-wrap gap-2">
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
                      );
                    })}
                  </CardContent>
                </Card>
              ))}

              {filteredProjects.length === 0 && (
                <Card>
                  <CardContent className="py-10 text-center">
                    <p className="text-sm text-muted-foreground">No projects matched the current filters.</p>
                    <Button variant="link" isInline onClick={() => navigate('/organizations')}>
                      Open organization hierarchy
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </CardContent>
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