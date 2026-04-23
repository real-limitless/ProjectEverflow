import { useParams, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { Button as PatternFlyButton } from '@patternfly/react-core';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ArrowLeft, Users, UserPlus, Calendar, User, Loader2, Trash2 } from 'lucide-react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Page, PageSection } from '@patternfly/react-core';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTeam, getCurrentUser, deleteTeam } from '@/lib/api';
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

const ViewTeam = () => {
  const { teamId } = useParams();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Delete team mutation
  const deleteTeamMutation = useMutation({
    mutationFn: deleteTeam,
    onSuccess: () => {
      toast({
        title: "Team Deleted",
        description: "The team has been successfully deleted.",
      });
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      navigate('/my-teamspace');
    },
    onError: (error: any) => {
      toast({
        title: "Error Deleting Team",
        description: error?.error || "An error occurred while deleting the team.",
        variant: "destructive",
      });
    },
  });

  // Fetch team data
  const { data: teamResponse, isLoading, error } = useQuery({
    queryKey: ['team', teamId],
    queryFn: () => getTeam(Number(teamId)),
    enabled: !!teamId,
  });

  // Fetch current user
  const { data: currentUser } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  const team = teamResponse?.data;
  const isMember = currentUser?.data && team ?
    team.members.some(member => member.id === currentUser.data.id) : false;

  if (isLoading) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div className="flex justify-center items-center py-12">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading team...</span>
          </div>
        </PageSection>
      </Page>
    );
  }

  if (error || !team) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div className="text-center py-12">
            <p className="text-destructive">Error loading team: {error?.message || 'Team not found'}</p>
            <Button onClick={() => navigate('/my-teamspace')} className="mt-4">
              Back to Teamspace
            </Button>
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
            <h1 style={{ fontSize: '2rem', fontWeight: 700, margin: 0 }}>{team.name}</h1>
            {isMember && (
              <Badge variant="secondary">Member</Badge>
            )}
          </div>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Team Details
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem' }}>
          {!isMember && (
            <Button variant="secondary" onClick={() => navigate(`/teams/join/${teamId}`)}>
              <UserPlus className="h-4 w-4 mr-2" />
              Join Team
            </Button>
          )}
          {isMember && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive">
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Team
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete Team</AlertDialogTitle>
                  <AlertDialogDescription>
                    Are you sure you want to delete "{team.name}"? This action cannot be undone and will permanently remove the team and all its associated data.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => deleteTeamMutation.mutate(Number(teamId))}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete Team
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
                <p className="text-foreground">{team.description}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Team Members</CardTitle>
                <CardDescription>
                  {team.member_count} member{team.member_count !== 1 ? 's' : ''}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {team.members.map((member) => (
                    <div key={member.id} className="flex items-center gap-3 p-3 rounded-lg border">
                      <Avatar className="h-10 w-10">
                        <AvatarFallback>
                          {member.first_name[0]}{member.last_name[0]}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">
                          {member.first_name} {member.last_name}
                        </p>
                        <p className="text-sm text-muted-foreground truncate">
                          @{member.username}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Team Stats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3">
                  <Users className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">{team.member_count}</p>
                    <p className="text-sm text-muted-foreground">Members</p>
                  </div>
                </div>
                <Separator />
                <div className="flex items-center gap-3">
                  <Calendar className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">
                      {new Date(team.created_at).toLocaleDateString()}
                    </p>
                    <p className="text-sm text-muted-foreground">Created</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Recent Activity</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center py-8 text-muted-foreground">
                  <User className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Activity tracking coming soon</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </PageSection>
    </Page>
  );
};

export default ViewTeam;