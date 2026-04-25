import { useParams, useNavigate } from 'react-router-dom';
import { useState, useMemo } from 'react';
import { Button as PatternFlyButton } from '@patternfly/react-core';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ArrowLeft, Users, Eye, GitFork, Calendar, User, Trash2 } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Page, PageSection } from '@patternfly/react-core';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getProjects, getCurrentUser, getTeams, Project, deleteProject } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
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

const ViewApplication = () => {
  const { appName } = useParams();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Delete project mutation
  const deleteProjectMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      toast({
        title: "Project Deleted",
        description: "The project has been successfully deleted.",
      });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      navigate('/my-teamspace');
    },
    onError: (error: any) => {
      toast({
        title: "Error Deleting Project",
        description: error?.error || "An error occurred while deleting the project.",
        variant: "destructive",
      });
    },
  });

  // Fetch project data
  const { data: projectsResponse, isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  // Fetch current user
  const { data: currentUser } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  // Fetch teams data
  const { data: teamsResponse } = useQuery({
    queryKey: ['teams'],
    queryFn: getTeams,
  });

  const projects = projectsResponse?.data || [];
  const teams = teamsResponse?.data || [];

  // Find the application from API data - try by ID first, then by name
  const application = useMemo(() => {
    if (!projects.length) return null;
    // First try to find by ID (if appName is a number)
    const projectId = parseInt(appName || '');
    if (!isNaN(projectId)) {
      return projects.find(project => project.id === projectId) || null;
    }
    // Otherwise find by name
    return projects.find(project => project.name === appName) || null;
  }, [projects, appName]);

  // Check if current user is a member
  const isCurrentUserMember = useMemo(() => {
    if (!application || !currentUser?.data) return false;
    
    return (
      application.owner.id === currentUser.data.id ||
      application.contributors.some((c: any) => c.id === currentUser.data.id) ||
      (application.team && teams.some((team: any) => team.id === application.team?.id && team.members.some((member: any) => member.id === currentUser.data.id)))
    );
  }, [application, currentUser, teams]);

  // Check if current user is the owner
  const isCurrentUserOwner = useMemo(() => {
    if (!application || !currentUser?.data) return false;
    return application.owner.id === currentUser.data.id;
  }, [application, currentUser]);

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'published': return 'default';
      case 'in_development': return 'secondary';
      case 'draft': return 'outline';
      case 'awaiting_approval': return 'secondary';
      default: return 'secondary';
    }
  };

  // Show loading state while data is being fetched
  if (projectsLoading || !application) {
    return (
      <Page 
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            Loading project details...
          </div>
        </PageSection>
      </Page>
    );
  }

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ marginBottom: '1.5rem' }}>
          <PatternFlyButton 
            variant="link" 
            icon={<ArrowLeftIcon />}
            onClick={() => navigate('/my-teamspace')}
            style={{ padding: 0, marginBottom: '1rem' }}
          >
            Back to My Teamspace
          </PatternFlyButton>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, margin: 0 }}>{application.name}</h1>
            <Badge variant={getStatusVariant(application.status)}>
              {application.status.replace('_', ' ')}
            </Badge>
          </div>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Project Details
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem' }}>
          {!isCurrentUserMember && (
            <Button variant="secondary" onClick={() => navigate(`/my-teamspace/join/${application.id}`)}>
              <Users className="h-4 w-4 mr-2" />
              Join Project
            </Button>
          )}
          <Button variant="secondary" onClick={() => navigate(`/my-teamspace/fork/${application.id}`)}>
            <GitFork className="h-4 w-4 mr-2" />
            Fork
          </Button>
          <Button variant="default" onClick={() => navigate(application.organization ? `/organizations/${application.organization.id}/projects/${application.id}` : '/organizations')}>
            Run Project
          </Button>
          {isCurrentUserOwner && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive">
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Project
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete Project</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to delete "{application.name}"? This action cannot be undone and will permanently remove the project and all its associated data.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => deleteProjectMutation.mutate(application.id)}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete Project
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>About</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-foreground">{application.description}</p>
              </CardContent>
            </Card>

            {application.system_prompt && (
              <Card>
                <CardHeader>
                  <CardTitle>AI System Prompt</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-foreground whitespace-pre-wrap">{application.system_prompt}</p>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Contributors</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {application.contributors.map((contributor, index) => (
                    <Badge key={index} variant="secondary">
                      {contributor.first_name} {contributor.last_name}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Statistics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3">
                  <Users className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <div className="text-2xl font-semibold">{application.contributors.length + 1}</div>
                    <div className="text-sm text-muted-foreground">Contributors</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Owner</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <Avatar>
                    <AvatarFallback>{application.owner.first_name[0]}{application.owner.last_name[0]}</AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="font-medium">{application.owner.first_name} {application.owner.last_name}</div>
                    <div className="text-sm text-muted-foreground">Project Owner</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Timeline</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-start gap-3">
                  <Calendar className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <div className="text-sm font-medium">Created</div>
                    <div className="text-sm text-muted-foreground">{new Date(application.created_at).toLocaleDateString()}</div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Calendar className="h-5 w-5 text-muted-foreground mt-0.5" />
                  <div>
                    <div className="text-sm font-medium">Last Updated</div>
                    <div className="text-sm text-muted-foreground">{new Date(application.updated_at).toLocaleDateString()}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </PageSection>
    </Page>
  );
};

export default ViewApplication;
