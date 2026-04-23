import { useState, useMemo } from 'react';
import { Page, PageSection, Card, CardBody, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useNavigate } from 'react-router-dom';
import { FolderOpen, Search, Eye, Users, GitFork, CheckCircle2, Clock, FileText, Loader2, UserPlus, AlertCircle, GitBranch, GitPullRequest, MessageSquare } from 'lucide-react';
import { Card as ShadcnCard, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

import { toast } from '@/hooks/use-toast';
import { useQuery } from '@tanstack/react-query';
import { getProjects, getCurrentUser, getTeams, Project, Team } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface TeamApplication {
  id: number;
  name: string;
  description: string;
  owner: {
    username: string;
    first_name: string;
    last_name: string;
  };
  contributors: any[];
  currentUserIsMember: boolean;
  created_at: string;
  updated_at: string;
}

const MyTeamspace = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('recent');
  const [activeTab, setActiveTab] = useState('projects');
  const navigate = useNavigate();

  // Fetch current user
  const { data: currentUser } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  // Fetch all projects
  const { data: projectsResponse, isLoading: projectsLoading, error: projectsError } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  // Fetch all teams
  const { data: teamsResponse, isLoading: teamsLoading, error: teamsError } = useQuery({
    queryKey: ['teams'],
    queryFn: getTeams,
  });

  const projects = projectsResponse?.data || [];
  const teams = teamsResponse?.data || [];

  // Transform projects to match the expected interface
  const teamApplications: TeamApplication[] = useMemo(() => {
    if (!projects.length) return [];
    
    return projects.map(project => ({
      id: project.id,
      name: project.name,
      description: project.description,
      owner: project.owner,
      contributors: project.contributors,
      currentUserIsMember: currentUser?.data ?
        (project.owner.id === currentUser.data.id ||
         project.contributors.some((c: any) => c.id === currentUser.data.id) ||
         (project.team && teams.some((team: any) => team.id === project.team?.id && team.members.some((member: any) => member.id === currentUser.data.id)))) : false,
      created_at: project.created_at,
      updated_at: project.updated_at,
    }));
  }, [projects, teams, currentUser]);



  const filteredApplications = teamApplications.filter(app => {
    const matchesSearch = app.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         `${app.owner.first_name} ${app.owner.last_name}`.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         app.owner.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         app.description.toLowerCase().includes(searchQuery.toLowerCase());

    let matchesStatus = true;
    if (statusFilter === 'member') {
      matchesStatus = app.currentUserIsMember;
    } else if (statusFilter === 'available') {
      matchesStatus = !app.currentUserIsMember;
    }

    return matchesSearch && matchesStatus;
  }).sort((a, b) => {
    if (sortBy === 'name') return a.name.localeCompare(b.name);
    if (sortBy === 'contributors') return b.contributors.length - a.contributors.length;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const stats = {
    totalProjects: teamApplications.length,
    myProjects: teamApplications.filter(app => app.currentUserIsMember).length,
    totalContributors: new Set(teamApplications.flatMap(app => [app.owner.username, ...app.contributors.map((c: any) => c.username)])).size,
    recentlyUpdated: teamApplications.filter(app => {
      const updated = new Date(app.updated_at);
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      return updated > weekAgo;
    }).length,
  };

  const handleViewDetails = (appId: number) => {
    navigate(`/my-teamspace/view/${appId}`);
  };

  const handleCollaborate = (app: TeamApplication) => {
    if (app.currentUserIsMember) {
      toast({
        title: "Already a Member",
        description: `You are already a member of ${app.name}`,
      });
    } else {
      // Navigate to the join project page
      navigate(`/my-teamspace/join/${app.id}`);
    }
  };

  const handleViewTeam = (teamId: number) => {
    navigate(`/teams/view/${teamId}`);
  };

  const handleJoinTeam = (teamId: number) => {
    navigate(`/teams/join/${teamId}`);
  };

  const handleFork = (appId: number) => {
    navigate(`/my-teamspace/fork/${appId}`);
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div className="space-y-6">
          <PageHeader
            title="My Teamspace"
            description="Browse and discover all projects and teams within your workspace. Join projects to collaborate or create your own."
            icon={<FolderOpen size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
            actions={
              <>
                <Button 
                  variant="secondary" 
                  onClick={() => navigate('/create-team')}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                    <Users style={{ width: '1rem', height: '1rem' }} />
                  </span>
                  Create Team
                </Button>
                <Button 
                  variant="primary" 
                  onClick={() => navigate('/my-teamspace/create')}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                    <FileText style={{ width: '1rem', height: '1rem' }} />
                  </span>
                  New Team Project
                </Button>
              </>
            }
          />

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="mb-4">
              <TabsTrigger value="projects">Projects ({projects.length})</TabsTrigger>
              <TabsTrigger value="teams">Teams ({teams.length})</TabsTrigger>
            </TabsList>

            {/* Projects Tab */}
            <TabsContent value="projects">
              {/* Quick Stats Dashboard */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Total Projects</CardTitle>
                    <FolderOpen className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{stats.totalProjects}</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">My Projects</CardTitle>
                    <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-success">{stats.myProjects}</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Contributors</CardTitle>
                    <Users className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-info">{stats.totalContributors}</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Updated This Week</CardTitle>
                    <Clock className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">{stats.recentlyUpdated}</div>
                  </CardContent>
                </Card>
              </div>

              {/* Search and Filters */}
              <div className="flex flex-col sm:flex-row gap-4 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                  <Input
                    placeholder="Search by name, author, or description..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-full sm:w-[200px]">
                    <SelectValue placeholder="Filter by status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Projects</SelectItem>
                    <SelectItem value="member">Projects I'm In</SelectItem>
                    <SelectItem value="available">Available to Join</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="w-full sm:w-[200px]">
                    <SelectValue placeholder="Sort by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="recent">Most Recent</SelectItem>
                    <SelectItem value="contributors">Most Contributors</SelectItem>
                    <SelectItem value="name">Name</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Results count */}
              <div className="text-sm text-muted-foreground mb-4">
                Showing {filteredApplications.length} of {teamApplications.length} projects
              </div>

              {/* Loading and Error States */}
              {projectsLoading && (
                <div className="flex justify-center items-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="ml-2">Loading projects...</span>
                </div>
              )}

              {projectsError && (
                <div className="text-center py-12">
                  <p className="text-destructive">Error loading projects: {projectsError.message}</p>
                </div>
              )}

              {/* Project Cards */}
              {!projectsLoading && !projectsError && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {filteredApplications.map((app, idx) => {
                    const isMember = app.currentUserIsMember;
                  return (
                  <Card key={idx} className="flex flex-col hover:shadow-lg transition-shadow">
                    <CardHeader>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <CardTitle className="text-lg">{app.name}</CardTitle>
                          {isMember && (
                            <Badge variant="secondary" className="text-xs">Member</Badge>
                          )}
                        </div>
                      </div>
                      <CardDescription className="mt-2">{app.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 space-y-4">
                      <div className="flex items-center gap-2">
                        <Avatar className="h-8 w-8">
                          <AvatarFallback className="bg-primary text-primary-foreground text-xs">
                            {app.owner.first_name && app.owner.last_name 
                              ? `${app.owner.first_name[0]}${app.owner.last_name[0]}`
                              : app.owner.username ? app.owner.username.substring(0, 2).toUpperCase()
                              : 'U'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">
                            {app.owner.first_name && app.owner.last_name 
                              ? `${app.owner.first_name} ${app.owner.last_name}`
                              : app.owner.username || 'Unknown User'}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            Created {new Date(app.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>

                      {/* Project Health Badges */}
                      <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <Users className="h-3.5 w-3.5" />
                          <span>{app.contributors.length + 1}</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <AlertCircle className="h-3.5 w-3.5" />
                          <span>Issues</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <GitPullRequest className="h-3.5 w-3.5" />
                          <span>PRs</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <GitBranch className="h-3.5 w-3.5" />
                          <span>Branches</span>
                        </div>
                      </div>

                      {/* Last Activity */}
                      <div className="text-xs text-muted-foreground">
                        Last updated {new Date(app.updated_at).toLocaleDateString()}
                      </div>
                    </CardContent>
                    <CardFooter className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleViewDetails(app.id)}
                        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <Eye style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        View
                      </Button>
                      {!isMember && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleCollaborate(app)}
                          style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                            <Users style={{ width: '0.875rem', height: '0.875rem' }} />
                          </span>
                          Join
                        </Button>
                      )}
                      {isMember && (
                        <Button
                          variant="tertiary"
                          size="sm"
                          disabled
                          style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                            <Users style={{ width: '0.875rem', height: '0.875rem' }} />
                          </span>
                          Member
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleFork(app.id)}
                        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <GitFork style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Fork
                      </Button>
                    </CardFooter>
                  </Card>
                  );
                })}
                </div>
              )}

              {!projectsLoading && !projectsError && filteredApplications.length === 0 && (
                <Card className="p-12">
                  <div className="text-center space-y-2">
                    <FolderOpen className="h-12 w-12 mx-auto text-muted-foreground" />
                    <h3 className="text-lg font-semibold">No projects found</h3>
                    <p className="text-muted-foreground">
                      Try adjusting your search or filters
                    </p>
                  </div>
                </Card>
              )}
            </TabsContent>

            {/* Teams Tab */}
            <TabsContent value="teams">
              {/* Teams Search */}
              <div className="flex flex-col sm:flex-row gap-4 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                  <Input
                    placeholder="Search teams by name or description..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
              </div>

              {/* Teams Loading and Error States */}
              {teamsLoading && (
                <div className="flex justify-center items-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="ml-2">Loading teams...</span>
                </div>
              )}

              {teamsError && (
                <div className="text-center py-12">
                  <p className="text-destructive">Error loading teams: {teamsError.message}</p>
                </div>
              )}

              {/* Teams Cards */}
              {!teamsLoading && !teamsError && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {teams
                    .filter(team => 
                      team.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                      team.description.toLowerCase().includes(searchQuery.toLowerCase())
                    )
                    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                    .map((team, idx) => {
                      const isMember = currentUser?.data ? 
                        team.members.some(member => member.id === currentUser.data.id) : false;
                      
                      return (
                        <Card key={idx} className="flex flex-col hover:shadow-lg transition-shadow">
                          <CardHeader>
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <CardTitle className="text-lg">{team.name}</CardTitle>
                                {isMember && (
                                  <Badge variant="secondary" className="text-xs">Member</Badge>
                                )}
                              </div>
                            </div>
                            <CardDescription className="mt-2">{team.description}</CardDescription>
                          </CardHeader>
                          <CardContent className="flex-1 space-y-4">
                            <div className="flex items-center gap-4 text-sm text-muted-foreground">
                              <div className="flex items-center gap-1">
                                <Users className="h-4 w-4" />
                                <span>{team.member_count} members</span>
                              </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              Created {new Date(team.created_at).toLocaleDateString()}
                            </div>
                          </CardContent>
                          <CardFooter className="flex gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleViewTeam(team.id)}
                              style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                            >
                              <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                                <Eye style={{ width: '0.875rem', height: '0.875rem' }} />
                              </span>
                              View
                            </Button>
                            {!isMember && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => handleJoinTeam(team.id)}
                                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem' }}
                              >
                                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                                  <UserPlus style={{ width: '0.875rem', height: '0.875rem' }} />
                                </span>
                                Join
                              </Button>
                            )}
                          </CardFooter>
                        </Card>
                      );
                    })}
                </div>
              )}

              {!teamsLoading && !teamsError && teams.filter(team => 
                team.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                team.description.toLowerCase().includes(searchQuery.toLowerCase())
              ).length === 0 && (
                <Card className="p-12">
                  <div className="text-center space-y-2">
                    <Users className="h-12 w-12 mx-auto text-muted-foreground" />
                    <h3 className="text-lg font-semibold">No teams found</h3>
                    <p className="text-muted-foreground">
                      Try adjusting your search or create a new team
                    </p>
                  </div>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </PageSection>
    </Page>
  );
};

export default MyTeamspace;
