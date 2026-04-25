import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Card, CardBody, CardTitle, Button as PatternFlyButton } from '@patternfly/react-core';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from 'lucide-react';
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { createProject, getCurrentUser } from '@/lib/api';

const projectSchema = z.object({
  name: z.string().min(3, "Project name must be at least 3 characters"),
  description: z.string().min(10, "Description must be at least 10 characters"),
  tags: z.string().optional(),
});

type ProjectFormData = z.infer<typeof projectSchema>;

interface BlankProjectFormProps {
  onCancel: () => void;
  onComplete: () => void;
}

export function BlankProjectForm({ onCancel, onComplete }: BlankProjectFormProps) {
  const { toast } = useToast();
  const [isCreating, setIsCreating] = useState(false);

  const form = useForm<ProjectFormData>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: '',
      description: '',
      tags: '',
    },
  });

  const onSubmit = async (data: ProjectFormData) => {
    setIsCreating(true);

    try {
      // Get current user
      const userResponse = await getCurrentUser();
      if (userResponse.error || !userResponse.data) {
        toast({
          title: "Authentication Error",
          description: "Unable to get current user information.",
          variant: "destructive",
        });
        return;
      }

      const response = await createProject({
        name: data.name,
        description: data.description,
        owner: userResponse.data.id,
      });

      if (response.error) {
        toast({
          title: "Error Creating Project",
          description: response.error,
          variant: "destructive",
        });
      } else {
        toast({
          title: "Project Created",
          description: `${data.name} has been created successfully.`,
        });
        onComplete();
      }
    } catch (error) {
      toast({
        title: "Error Creating Project",
        description: "An unexpected error occurred while creating the project.",
        variant: "destructive",
      });
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div>
      <PatternFlyButton 
        variant="link" 
        icon={<ArrowLeftIcon />}
        onClick={onCancel}
        style={{ padding: 0, marginBottom: '1rem' }}
      >
        Back to Options
      </PatternFlyButton>
      
      <Card style={{ maxWidth: '800px' }}>
        <CardBody>
          <CardTitle>Create Blank Project</CardTitle>
          <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
            Set up a new project with basic structure
          </p>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., AI Document Analyzer" {...field} />
                    </FormControl>
                    <FormDescription>
                      Choose a descriptive name for your project
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
                name="tags"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tags (optional)</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="ai, chatbot, automation"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Comma-separated tags to help categorize your project
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div style={{ display: 'flex', gap: '1rem', paddingTop: '1rem' }}>
                <PatternFlyButton type="submit" variant="primary" disabled={isCreating}>
                  {isCreating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    'Create Project'
                  )}
                </PatternFlyButton>
                <PatternFlyButton variant="secondary" onClick={onCancel} disabled={isCreating}>
                  Cancel
                </PatternFlyButton>
              </div>
            </form>
          </Form>
        </CardBody>
      </Card>
    </div>
  );
}