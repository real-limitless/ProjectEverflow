import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Table, Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table';
import { useNavigate } from 'react-router-dom';
import { PlusCircleIcon, PlayIcon, EditIcon, CodeBranchIcon, DownloadIcon } from '@patternfly/react-icons';
import { toast } from '@/hooks/use-toast';
import { Package, CheckCircle2, Clock, Users, Search, BarChart3, Share2, MoreVertical, Loader2, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Card as ShadcnCard, CardContent, CardHeader, CardTitle as ShadcnCardTitle } from '@/components/ui/card';
import { useQuery } from '@tanstack/react-query';
import PageHeader from '@/components/ui/PageHeader';
import { getMyProjects, Project } from '@/lib/api';
import CreateWorkflowDialog from '@/components/CreateWorkflowDialog';

const MyApplications = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('recent');
  const navigate = useNavigate();

  // Fetch user's projects
  const { data: projectsResponse, isLoading, error } = useQuery({
    queryKey: ['myProjects'],
    queryFn: getMyProjects,
  });

  const projects = projectsResponse?.data || [];

  // Transform projects to match the expected interface
  const applications = projects.map(project => ({
    id: project.id,
    name: project.name,
    version: '1.0.0', // Default version
    status: project.status === 'published' ? 'Live' :
            project.status === 'awaiting_approval' ? 'Under Review' :
            project.status === 'in_development' ? 'In Development' : 'Draft',
    users: project.contributors.length + 1,
    approvalDate: project.status === 'published' ? new Date(project.updated_at).toLocaleDateString() : 'Pending',
    role: 'Owner',
    activePRs: 0,
    description: project.description,
  }));

  // Filter and sort applications
  const filteredApplications = applications
    .filter(app => {
      const matchesSearch = app.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesRole = statusFilter === 'all' || app.role === statusFilter;
      return matchesSearch && matchesRole;
    })
    .sort((a, b) => {
      if (sortBy === 'users') return b.users - a.users;
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      return new Date(b.approvalDate).getTime() - new Date(a.approvalDate).getTime(); // recent
    });

  // Calculate stats
  const stats = {
    totalOwned: applications.filter(app => app.role === 'Owner').length,
    totalContributing: applications.filter(app => app.role === 'Contributor').length,
    activePRs: applications.reduce((sum, app) => sum + app.activePRs, 0),
    pendingJoinRequests: 0, // Will be implemented later
  };

  const handleRunApplication = (appId: number, status: string) => {
    if (status !== 'Live') {
      toast({
        title: "Cannot Run Application",
        description: `Application is not live yet. Only live applications can be run.`,
        variant: "destructive",
      });
      return;
    }

    navigate(`/my-applications/run/${appId}`);
  };

  const handleEditApplication = (appId: number) => {
    navigate(`/my-applications/edit/${appId}`);
  };

  const handleForkApplication = (appId: number) => {
    toast({
      title: "Forking Application",
      description: `Creating a copy of application...`,
    });
  };

  const handleDownloadApplication = (appId: number) => {
    toast({
      title: "Downloading",
      description: `Preparing application for download...`,
    });
  };

  const handleViewAnalytics = (appId: number) => {
    toast({
      title: "Analytics",
      description: `Opening analytics for application...`,
    });
  };

  const handleShareApplication = (appId: number) => {
    toast({
      title: "Share",
      description: `Generating share link for application...`,
    });
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="My Projects"
          description="Projects you own or contribute to. Manage versions, review changes, and monitor usage."
          icon={<Package size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
          actions={
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <Button 
                variant="secondary" 
                icon={<PlusCircleIcon />}
                onClick={() => navigate('/my-applications/create')}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                New Standalone Project
              </Button>
              <Button 
                variant="primary" 
                icon={<PlusCircleIcon />}
                onClick={() => navigate('/my-teamspace')}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                From Teamspace
              </Button>
            </div>
          }
        />

        {/* Quick Stats Dashboard */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <ShadcnCard>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <ShadcnCardTitle className="text-sm font-medium">Projects I Own</ShadcnCardTitle>
              <Package className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalOwned}</div>
            </CardContent>
          </ShadcnCard>

          <ShadcnCard>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <ShadcnCardTitle className="text-sm font-medium">Projects I Contribute To</ShadcnCardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.totalContributing}</div>
            </CardContent>
          </ShadcnCard>

          <ShadcnCard>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <ShadcnCardTitle className="text-sm font-medium">My Active PRs</ShadcnCardTitle>
              <CheckCircle2 className="h-4 w-4 text-success" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.activePRs}</div>
            </CardContent>
          </ShadcnCard>

          <ShadcnCard>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <ShadcnCardTitle className="text-sm font-medium">Pending Join Requests</ShadcnCardTitle>
              <Clock className="h-4 w-4 text-warning" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.pendingJoinRequests}</div>
            </CardContent>
          </ShadcnCard>
        </div>

        {/* Search and Filter Controls */}
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ flex: '1 1 300px', position: 'relative' }}>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search applications..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by role" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All My Projects</SelectItem>
              <SelectItem value="Owner">Projects I Own</SelectItem>
              <SelectItem value="Contributor">Projects I Contribute To</SelectItem>
            </SelectContent>
          </Select>

          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">Most Recent</SelectItem>
              <SelectItem value="users">Most Users</SelectItem>
              <SelectItem value="name">Name A-Z</SelectItem>
            </SelectContent>
          </Select>

          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Showing {filteredApplications.length} of {applications.length} projects
          </p>
        </div>
        {/* Loading and Error States */}
        {isLoading && (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading your projects...</span>
          </div>
        )}

        {error && (
          <div className="text-center py-12">
            <p className="text-destructive">Error loading projects: {error.message}</p>
          </div>
        )}

        {!isLoading && !error && (
          <>
            {filteredApplications.length === 0 ? (
              <Card style={{ marginTop: '1.5rem' }}>
                <CardBody style={{ textAlign: 'center', padding: '3rem' }}>
                  <Package size={48} style={{ margin: '0 auto 1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No projects found</h3>
                  <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
                    {searchQuery || statusFilter !== 'all'
                      ? 'Try adjusting your search or filters'
                      : 'Get started by creating a new project or joining an existing one from your teamspace'}
                  </p>
                  <Button variant="primary" onClick={() => navigate('/my-teamspace')}>
                    Go to Teamspace
                  </Button>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardBody>
                  <Table variant="compact">
                    <Thead>
                      <Tr>
                        <Th>Project Name</Th>
                        <Th>Version</Th>
                        <Th>My Role</Th>
                        <Th>Status</Th>
                        <Th>Active Users</Th>
                        <Th>Actions</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {filteredApplications.map((app, idx) => (
                        <Tr key={idx}>
                          <Td><strong>{app.name}</strong></Td>
                          <Td>{app.version}</Td>
                          <Td>
                            <Badge variant={app.role === 'Owner' ? 'info' : 'secondary'} className="inline-flex items-center gap-1">
                              {app.role}
                            </Badge>
                          </Td>
                          <Td>
                            <Badge variant={app.status === 'Live' ? 'success' : 'warning'} className="inline-flex items-center gap-1">
                              {app.status === 'Live' ? (
                                <CheckCircle2 className="h-3 w-3" />
                              ) : (
                                <Clock className="h-3 w-3" />
                              )}
                              {app.status}
                            </Badge>
                          </Td>
                          <Td>{app.users > 0 ? app.users.toLocaleString() : '-'}</Td>
                          <Td>
                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={() => handleEditApplication(app.id)}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.375rem',
                                  minWidth: 'auto'
                                }}
                              >
                                <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                                  <EditIcon />
                                </span>
                                Edit
                              </Button>
                              <Button
                                variant={app.status === 'Live' ? 'secondary' : 'tertiary'}
                                size="sm"
                                onClick={() => handleRunApplication(app.id, app.status)}
                                isDisabled={app.status !== 'Live'}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '0.375rem',
                                  minWidth: 'auto'
                                }}
                          >
                            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                              <PlayIcon />
                            </span>
                            Run
                          </Button>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button 
                                variant="plain" 
                                size="sm" 
                                style={{ 
                                  padding: '0.375rem 0.5rem',
                                  minWidth: 'auto',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center'
                                }}
                              >
                                <MoreVertical className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent 
                              align="end"
                              className="bg-background border border-border shadow-lg z-[9999]"
                            >
                              <CreateWorkflowDialog
                                projectId={app.id}
                                projectName={app.name}
                                trigger={
                                  <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                                    <Plus className="mr-2 h-4 w-4" />
                                    Create Workflow
                                  </DropdownMenuItem>
                                }
                              />
                              <DropdownMenuItem onClick={() => handleForkApplication(app.id)}>
                                <CodeBranchIcon style={{ marginRight: '0.5rem', width: '1rem', height: '1rem' }} />
                                Fork
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleDownloadApplication(app.id)}>
                                <DownloadIcon style={{ marginRight: '0.5rem', width: '1rem', height: '1rem' }} />
                                Download
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleViewAnalytics(app.id)}>
                                <BarChart3 className="mr-2 h-4 w-4" />
                                View Analytics
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleShareApplication(app.id)}>
                                <Share2 className="mr-2 h-4 w-4" />
                                Share
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </CardBody>
          </Card>
            )}
          </>
        )}
      </PageSection>
    </Page>
  );
};

export default MyApplications;
