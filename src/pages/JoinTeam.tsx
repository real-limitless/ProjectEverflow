import { useParams, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { Page, PageSection, Button as PatternFlyButton } from '@patternfly/react-core';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ArrowLeft, Users, CheckCircle, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTeam, getCurrentUser, addTeamMember } from '@/lib/api';

const JoinTeam = () => {
  const { teamId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [role, setRole] = useState('member');
  const [message, setMessage] = useState('');

  // Fetch team data
  const { data: teamResponse, isLoading: teamLoading } = useQuery({
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
  const currentUserId = currentUser?.data?.id;

  const joinTeamMutation = useMutation({
    mutationFn: () => addTeamMember(Number(teamId), currentUserId!),
    onSuccess: (response) => {
      if (response.data) {
        toast({
          title: "Join Request Sent!",
          description: `Your request to join ${team?.name} has been sent successfully.`,
        });
        // Invalidate queries to refresh team data
        queryClient.invalidateQueries({ queryKey: ['teams'] });
        queryClient.invalidateQueries({ queryKey: ['team', teamId] });
        setTimeout(() => navigate('/my-teamspace'), 1500);
      } else if (response.error) {
        toast({
          title: "Error",
          description: response.error,
          variant: "destructive",
        });
      }
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.message || "Failed to join team",
        variant: "destructive",
      });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUserId) {
      toast({
        title: "Error",
        description: "You must be logged in to join a team",
        variant: "destructive",
      });
      return;
    }
    joinTeamMutation.mutate();
  };

  if (teamLoading) {
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

  if (!team) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div className="text-center py-12">
            <p className="text-destructive">Team not found</p>
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
          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}>Join Team</h1>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            {team.name}
          </p>
        </div>

        <div className="max-w-3xl">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <Users className="h-6 w-6 text-primary" />
              <div>
                <CardTitle>Join Team</CardTitle>
                <CardDescription>
                  Submit a request to become a member of this team
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-3">
                <Label>Select Your Role</Label>
                <RadioGroup value={role} onValueChange={setRole}>
                  <div className="flex items-start space-x-3 space-y-0 rounded-md border border-border p-4 hover:bg-accent/50 transition-colors">
                    <RadioGroupItem value="member" id="member" />
                    <div className="flex-1">
                      <Label htmlFor="member" className="font-medium cursor-pointer">
                        Team Member
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Contribute to team projects and collaborate with other members
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3 space-y-0 rounded-md border border-border p-4 hover:bg-accent/50 transition-colors">
                    <RadioGroupItem value="contributor" id="contributor" />
                    <div className="flex-1">
                      <Label htmlFor="contributor" className="font-medium cursor-pointer">
                        Active Contributor
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Actively contribute code and participate in team discussions
                      </p>
                    </div>
                  </div>
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label htmlFor="message">Message (Optional)</Label>
                <Textarea
                  id="message"
                  placeholder="Tell the team why you'd like to join and what you can contribute..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  className="min-h-[100px]"
                />
                <p className="text-sm text-muted-foreground">
                  This message will be sent with your join request
                </p>
              </div>

              <div className="flex gap-3 pt-4">
                <Button
                  type="submit"
                  disabled={joinTeamMutation.isPending}
                  className="flex items-center gap-2"
                >
                  {joinTeamMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                  {joinTeamMutation.isPending ? 'Sending Request...' : 'Send Join Request'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => navigate('/my-teamspace')}
                  disabled={joinTeamMutation.isPending}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        </div>
      </PageSection>
    </Page>
  );
};

export default JoinTeam;