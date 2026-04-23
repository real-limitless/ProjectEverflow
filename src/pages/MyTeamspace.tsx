import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button, Page, PageSection } from '@patternfly/react-core';
import { ArrowRight, Building2, FolderKanban, FolderTree, Search, ShieldCheck, Users } from 'lucide-react';

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import PageHeader from '@/components/ui/PageHeader';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getCurrentUser, getOrganizations, getProjects } from '@/lib/api';

type RoleFilter = 'all' | 'owner-admin' | 'member';
type SortMode = 'projects' | 'members' | 'name';

const MyTeamspace = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all');
  const [sortBy, setSortBy] = useState<SortMode>('projects');
  const navigate = useNavigate();

  const { data: currentUserResponse } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  const { data: organizationsResponse, isLoading: organizationsLoading, error: organizationsError } = useQuery({
    queryKey: ['organizations'],
    queryFn: getOrganizations,
  });

  const { data: projectsResponse, isLoading: projectsLoading, error: projectsError } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  const currentUser = currentUserResponse?.data;
  const organizations = organizationsResponse?.data ?? [];
  const projects = projectsResponse?.data ?? [];

  const organizationCards = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();

    return organizations
      .map((organization) => {
        const orgProjects = projects.filter((project) => project.organization?.id === organization.id);
        return {
          ...organization,
          projects: orgProjects,
        };
      })
      .filter((organization) => {
        const matchesRole = roleFilter === 'all'
          ? true
          : roleFilter === 'owner-admin'
            ? organization.user_role === 'owner' || organization.user_role === 'admin'
            : organization.user_role === 'member';

        if (!matchesRole) {
          return false;
        }

        if (!normalizedSearch) {
          return true;
        }

        const projectMatch = organization.projects.some((project) => {
          const haystack = `${project.name} ${project.description} ${project.owner.username}`.toLowerCase();
          return haystack.includes(normalizedSearch);
        });

        const orgHaystack = `${organization.name} ${organization.description}`.toLowerCase();
        return orgHaystack.includes(normalizedSearch) || projectMatch;
      })
      .sort((left, right) => {
        if (sortBy === 'name') {
          return left.name.localeCompare(right.name);
        }
        if (sortBy === 'members') {
          return right.member_count - left.member_count;
        }
        return right.project_count - left.project_count;
      });
  }, [organizations, projects, roleFilter, searchQuery, sortBy]);

  const legacyProjects = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();
    return projects.filter((project) => {
      if (project.organization) {
        return false;
      }
      if (!normalizedSearch) {
        return true;
      }
      const haystack = `${project.name} ${project.description} ${project.owner.username}`.toLowerCase();
      return haystack.includes(normalizedSearch);
    });
  }, [projects, searchQuery]);

  const stats = {
    organizations: organizations.length,
    projects: projects.length,
    ownedProjects: currentUser ? projects.filter((project) => project.owner.id === currentUser.id).length : 0,
    adminOrganizations: organizations.filter((organization) => organization.user_role === 'owner' || organization.user_role === 'admin').length,
  };

  const hasError = organizationsError || projectsError;
  const errorMessage = hasError instanceof Error ? hasError.message : 'Unable to load workspace hierarchy.';

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div className="space-y-6">
          <PageHeader
            title="My Teamspace"
            description="The old teamspace model has been replaced by organizations. Browse accessible organizations and jump directly into project, environment, and app routes."
            icon={<FolderTree size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
            actions={
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={() => navigate('/my-applications')}>
                  My Projects
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
                <CardTitle className="text-sm font-medium">Organizations</CardTitle>
                <Building2 className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.organizations}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Accessible Projects</CardTitle>
                <FolderKanban className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.projects}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Projects I Own</CardTitle>
                <ShieldCheck className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.ownedProjects}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Admin Roles</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stats.adminOrganizations}</div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Filter workspace hierarchy</CardTitle>
              <CardDescription>Search organizations and projects, then jump into the routed hierarchy.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 lg:flex-row">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Search organizations, projects, or owners..."
                  className="pl-10"
                />
              </div>
              <Select value={roleFilter} onValueChange={(value) => setRoleFilter(value as RoleFilter)}>
                <SelectTrigger className="w-full lg:w-[220px]">
                  <SelectValue placeholder="Filter by org role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All organization roles</SelectItem>
                  <SelectItem value="owner-admin">Owner or admin</SelectItem>
                  <SelectItem value="member">Member</SelectItem>
                </SelectContent>
              </Select>
              <Select value={sortBy} onValueChange={(value) => setSortBy(value as SortMode)}>
                <SelectTrigger className="w-full lg:w-[220px]">
                  <SelectValue placeholder="Sort organizations" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="projects">Most projects</SelectItem>
                  <SelectItem value="members">Most members</SelectItem>
                  <SelectItem value="name">Name</SelectItem>
                </SelectContent>
              </Select>
            </CardContent>
          </Card>

          {(organizationsLoading || projectsLoading) && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Loading organization hierarchy...
              </CardContent>
            </Card>
          )}

          {hasError && (
            <Card>
              <CardContent className="py-10 text-center text-sm text-destructive">{errorMessage}</CardContent>
            </Card>
          )}

          {!organizationsLoading && !projectsLoading && !hasError && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                {organizationCards.map((organization) => (
                  <Card key={organization.id}>
                    <CardHeader className="gap-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <CardTitle className="text-xl">{organization.name}</CardTitle>
                          <CardDescription>{organization.description || 'No organization description yet.'}</CardDescription>
                        </div>
                        <Badge variant={organization.user_role === 'owner' || organization.user_role === 'admin' ? 'info' : 'secondary'}>
                          {organization.user_role ?? 'viewer'}
                        </Badge>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge variant="outline">{organization.project_count} projects</Badge>
                        <Badge variant="outline">{organization.member_count} members</Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        {organization.projects.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No projects exist in this organization yet.</p>
                        ) : (
                          organization.projects.slice(0, 3).map((project) => (
                            <button
                              key={project.id}
                              type="button"
                              onClick={() => navigate(`/organizations/${organization.id}/projects/${project.id}`)}
                              className="flex w-full items-center justify-between rounded-lg border border-border px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5"
                            >
                              <div>
                                <div className="font-medium">{project.name}</div>
                                <div className="text-sm text-muted-foreground">{project.description || 'No project description yet.'}</div>
                              </div>
                              <Badge variant="outline">{project.status.replaceAll('_', ' ')}</Badge>
                            </button>
                          ))
                        )}
                      </div>
                      <Button variant="link" isInline onClick={() => navigate(`/organizations/${organization.id}`)}>
                        Open organization
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {legacyProjects.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Legacy standalone projects</CardTitle>
                    <CardDescription>These projects are still accessible, but they are not attached to an organization yet.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {legacyProjects.map((project) => (
                      <div key={project.id} className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
                        <div>
                          <div className="font-medium">{project.name}</div>
                          <div className="text-sm text-muted-foreground">{project.description || 'No project description yet.'}</div>
                        </div>
                        <Button variant="secondary" onClick={() => navigate('/organizations')}>
                          Move through hierarchy
                        </Button>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {organizationCards.length === 0 && legacyProjects.length === 0 && (
                <Card>
                  <CardContent className="py-10 text-center">
                    <p className="text-sm text-muted-foreground">No organizations or accessible projects matched the current filters.</p>
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

export default MyTeamspace;