import { useState } from 'react';
import { Page, PageSection, Card, CardBody, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/use-toast';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { Users, Loader2 } from 'lucide-react';
import { createTeam } from '@/lib/api';
import { useMutation, useQueryClient } from '@tanstack/react-query';

const formSchema = z.object({
  name: z.string().min(3, 'Team name must be at least 3 characters').max(255, 'Team name must be less than 255 characters'),
  description: z.string().min(10, 'Description must be at least 10 characters').max(500, 'Description must be less than 500 characters'),
});

type FormValues = z.infer<typeof formSchema>;

const CreateTeam = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      description: '',
    },
  });

  const createTeamMutation = useMutation({
    mutationFn: createTeam,
    onSuccess: (response) => {
      if (response.data) {
        toast({
          title: "Team Created!",
          description: `${response.data.name} has been successfully created.`,
        });
        // Invalidate teams query to refresh the list
        queryClient.invalidateQueries({ queryKey: ['teams'] });
        // Navigate back to teamspace (or teams page if it exists)
        navigate('/my-teamspace');
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
        description: error.message || "Failed to create team",
        variant: "destructive",
      });
    },
  });

  const onSubmit = (data: FormValues) => {
    createTeamMutation.mutate({
      name: data.name,
      description: data.description,
    });
  };

  const isLoading = createTeamMutation.isPending;

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ marginBottom: '1.5rem' }}>

          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Users size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />
            Create New Team
          </h1>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Create a new team to collaborate on AI applications and projects.
          </p>
        </div>

        <Card style={{ maxWidth: '800px' }}>
          <CardBody>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Team Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., AI Development Team" {...field} />
                      </FormControl>
                      <FormDescription>
                        Choose a descriptive name for your team
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Description *</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Describe your team's purpose, goals, and focus areas..."
                          className="min-h-[120px]"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        Provide a clear description of your team's purpose and objectives
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div style={{ display: 'flex', gap: '1rem', paddingTop: '1rem' }}>
                  <Button type="submit" variant="primary" disabled={isLoading}>
                    {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {isLoading ? 'Creating Team...' : 'Create Team'}
                  </Button>
                  <Button variant="secondary" onClick={() => navigate('/my-teamspace')} disabled={isLoading}>
                    Cancel
                  </Button>
                </div>
              </form>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
    </Page>
  );
};

export default CreateTeam;