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
import { ArrowLeft, Users, CheckCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import pageContent from '@/data/pageContent.json';

const JoinApplication = () => {
  const { appName } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [role, setRole] = useState('contributor');
  const [message, setMessage] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast({
      title: pageContent.joinApplication.successTitle,
      description: `${pageContent.joinApplication.successDescription} ${appName} ${pageContent.joinApplication.successDescription2} ${role} ${pageContent.joinApplication.successDescription3}`,
    });
    setTimeout(() => navigate('/my-teamspace'), 1500);
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ marginBottom: '1.5rem' }}>

          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}>Join Team</h1>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            {appName}
          </p>
        </div>

        <div className="max-w-3xl">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <Users className="h-6 w-6 text-primary" />
              <div>
                <CardTitle>Join Application Team</CardTitle>
                <CardDescription>
                  Submit a request to collaborate on this application
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
                    <RadioGroupItem value="contributor" id="contributor" />
                    <div className="flex-1">
                      <Label htmlFor="contributor" className="font-medium cursor-pointer">
                        Contributor
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Contribute code, features, and bug fixes to the application
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3 space-y-0 rounded-md border border-border p-4 hover:bg-accent/50 transition-colors">
                    <RadioGroupItem value="reviewer" id="reviewer" />
                    <div className="flex-1">
                      <Label htmlFor="reviewer" className="font-medium cursor-pointer">
                        Reviewer
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Review code changes and provide feedback
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3 space-y-0 rounded-md border border-border p-4 hover:bg-accent/50 transition-colors">
                    <RadioGroupItem value="viewer" id="viewer" />
                    <div className="flex-1">
                      <Label htmlFor="viewer" className="font-medium cursor-pointer">
                        Viewer
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        View the application and its development progress
                      </p>
                    </div>
                  </div>
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label htmlFor="message">Message to Project Owner (Optional)</Label>
                <Textarea
                  id="message"
                  placeholder="Tell the project owner why you'd like to join and what you can contribute..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={5}
                />
              </div>

              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="flex items-start gap-2">
                  <CheckCircle className="h-5 w-5 text-primary mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium">What happens next?</p>
                    <p className="text-muted-foreground">
                      The project owner will review your request and either approve or decline it. You'll receive a notification with their decision.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3 justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate('/my-teamspace')}
                >
                  Cancel
                </Button>
                <Button type="submit">
                  Submit Request
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

export default JoinApplication;
