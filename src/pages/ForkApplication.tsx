import { useParams, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { Page, PageSection, Card as PatternFlyCard, CardBody, Button as PatternFlyButton } from '@patternfly/react-core';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { ArrowLeft, GitFork, Info } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import pageContent from '@/data/pageContent.json';

const ForkApplication = () => {
  const { appName } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [forkName, setForkName] = useState(`${appName}${pageContent.forkApplication.defaultForkName}`);
  const [description, setDescription] = useState('');
  const [isPublic, setIsPublic] = useState(false);

  const handleFork = (e: React.FormEvent) => {
    e.preventDefault();
    toast({
      title: pageContent.forkApplication.successTitle,
      description: `${forkName} ${pageContent.forkApplication.successDescription}`,
    });
    setTimeout(() => navigate('/my-applications'), 1500);
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ marginBottom: '1.5rem' }}>

          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}>Fork Application</h1>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            {appName}
          </p>
        </div>

        <div className="max-w-3xl">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <GitFork className="h-6 w-6 text-primary" />
              <div>
                <CardTitle>Create a Fork</CardTitle>
                <CardDescription>
                  Create your own copy of this application to customize and modify
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleFork} className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="forkName">Application Name *</Label>
                <Input
                  id="forkName"
                  value={forkName}
                  onChange={(e) => setForkName(e.target.value)}
                  placeholder="Enter a name for your fork"
                  required
                />
                <p className="text-sm text-muted-foreground">
                  Choose a descriptive name for your forked application
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what makes your fork different or what you plan to build..."
                  rows={4}
                />
              </div>

              <div className="flex items-center justify-between rounded-lg border border-border p-4">
                <div className="space-y-0.5">
                  <Label htmlFor="public-fork" className="cursor-pointer">
                    Make this fork public
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    Allow others in your organization to view and fork this application
                  </p>
                </div>
                <Switch
                  id="public-fork"
                  checked={isPublic}
                  onCheckedChange={setIsPublic}
                />
              </div>

              <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                <div className="flex items-start gap-2">
                  <Info className="h-5 w-5 text-primary mt-0.5" />
                  <div className="text-sm space-y-1">
                    <p className="font-medium">What is a fork?</p>
                    <p className="text-muted-foreground">
                      A fork is an independent copy of an application. You can modify it freely without affecting the original application. Your changes won't sync back to the original.
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-accent/50 rounded-lg p-4 space-y-1">
                <p className="text-sm font-medium">Source Application</p>
                <p className="text-sm text-muted-foreground">{appName}</p>
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
                  <GitFork className="h-4 w-4 mr-2" />
                  Create Fork
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

export default ForkApplication;
