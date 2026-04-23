import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from '@/hooks/use-toast';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import applicationFormData from '@/data/applicationFormData.json';

const formSchema = z.object({
  name: z.string().min(3, 'Project name must be at least 3 characters').max(100, 'Project name must be less than 100 characters'),
  description: z.string().min(10, 'Description must be at least 10 characters').max(500, 'Description must be less than 500 characters'),
  version: z.string().regex(/^\d+\.\d+\.\d+$/, 'Version must be in format X.Y.Z (e.g., 1.0.0)'),
  category: z.string().min(1, 'Please select a category'),
  repositoryUrl: z.string().url('Must be a valid URL').optional().or(z.literal('')),
  aiTechnology: z.string().min(1, 'Please select an AI technology'),
});

type FormValues = z.infer<typeof formSchema>;

const CreateApplication = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const navigate = useNavigate();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: '',
      description: '',
      version: '1.0.0',
      category: '',
      repositoryUrl: '',
      aiTechnology: '',
    },
  });

  const onSubmit = (data: FormValues) => {
    console.log('Project data:', data);
    toast({
      title: "Project Created!",
      description: `${data.name} has been successfully created and submitted for review.`,
    });
    navigate('/my-applications');
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ marginBottom: '1.5rem' }}>
          <Button 
            variant="link" 
            icon={<ArrowLeftIcon />}
            onClick={() => navigate('/my-applications')}
            style={{ padding: 0, marginBottom: '1rem' }}
          >
            Back to My Projects
          </Button>
          <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem' }}>Create New Project</h1>
          <p style={{ fontSize: '1rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Publish your AI project to the Everflow platform.
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
                      <FormLabel>Project Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., Smart Code Assistant" {...field} />
                      </FormControl>
                      <FormDescription>
                        Choose a unique name for your project
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
                          placeholder="Describe what your project does and its key features..."
                          className="min-h-[120px]"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        Provide a clear description of your project's purpose and functionality
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="version"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Version *</FormLabel>
                      <FormControl>
                        <Input placeholder="1.0.0" {...field} />
                      </FormControl>
                      <FormDescription>
                        Semantic version number (e.g., 1.0.0)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="category"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Category *</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a category" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {applicationFormData.categories.map((category) => (
                            <SelectItem key={category.id} value={category.id}>
                              {category.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Select the primary category for your project
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="repositoryUrl"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Repository URL (Optional)</FormLabel>
                      <FormControl>
                        <Input placeholder="https://github.com/username/repo" {...field} />
                      </FormControl>
                      <FormDescription>
                        Link to your source code repository
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="aiTechnology"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>AI Technology *</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select AI technology" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {applicationFormData.aiTechnologies.map((tech) => (
                            <SelectItem key={tech.id} value={tech.id}>
                              {tech.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        What AI technology or framework does your project use?
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div style={{ display: 'flex', gap: '1rem', paddingTop: '1rem' }}>
                  <Button type="submit" variant="primary">
                    Create Project
                  </Button>
                  <Button variant="secondary" onClick={() => navigate('/my-applications')}>
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

export default CreateApplication;
