import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Card, CardBody, CardTitle, Button as PatternFlyButton } from '@patternfly/react-core';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from "@/hooks/use-toast";
import { Github, Gitlab } from "lucide-react";
import { ArrowLeftIcon } from '@patternfly/react-icons';
import { createProject, getCurrentUser } from '@/lib/api';

const cloneSchema = z.object({
  repositoryUrl: z.string().url("Must be a valid URL"),
  projectName: z.string().min(3, "Project name must be at least 3 characters"),
  branch: z.string().optional(),
  provider: z.enum(["github", "gitlab", "bitbucket", "other"]),
});

type CloneFormData = z.infer<typeof cloneSchema>;

interface CloneRepositoryFormProps {
  onCancel: () => void;
  onComplete: () => void;
}

export function CloneRepositoryForm({ onCancel, onComplete }: CloneRepositoryFormProps) {
  const { toast } = useToast();
  const [isCloning, setIsCloning] = useState(false);

  const form = useForm<CloneFormData>({
    resolver: zodResolver(cloneSchema),
    defaultValues: {
      provider: "github",
      branch: "main",
    },
  });

    const onSubmit = async (data: CloneFormData) => {
    setIsCloning(true);

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
        name: data.projectName,
        description: `Cloned from ${data.provider} repository: ${data.repositoryUrl}`,
        owner: userResponse.data.id,
        creation_method: 'clone',
        git_repo_url: data.repositoryUrl,
        branch: data.branch || 'main',
      });

      if (response.error) {
        toast({
          title: "Error Cloning Repository",
          description: response.error,
          variant: "destructive",
        });
      } else {
        toast({
          title: "Repository Cloned",
          description: `${data.projectName} has been imported successfully.`,
        });
        onComplete();
      }
    } catch (error) {
      toast({
        title: "Error Cloning Repository",
        description: "An unexpected error occurred while cloning the repository.",
        variant: "destructive",
      });
    } finally {
      setIsCloning(false);
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
          <CardTitle>Clone Existing Repository</CardTitle>
          <p style={{ color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
            Import a project from GitHub, GitLab, or other Git repositories
          </p>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Git Provider</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a Git provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="github">
                          <div className="flex items-center gap-2">
                            <Github className="h-4 w-4" />
                            GitHub
                          </div>
                        </SelectItem>
                        <SelectItem value="gitlab">
                          <div className="flex items-center gap-2">
                            <Gitlab className="h-4 w-4" />
                            GitLab
                          </div>
                        </SelectItem>
                        <SelectItem value="bitbucket">Bitbucket</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Choose the Git provider where your repository is hosted
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
                    <FormLabel>Repository URL *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="https://github.com/username/repo.git"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Enter the full URL of the repository you want to clone
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="projectName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project Name *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="My Cloned Project"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Choose a name for your project in the platform
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="branch"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Branch (optional)</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="main"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Specify a branch to clone (defaults to main/master)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div style={{ display: 'flex', gap: '1rem', paddingTop: '1rem' }}>
                <PatternFlyButton type="submit" variant="primary" disabled={isCloning}>
                  {isCloning ? "Cloning..." : "Clone Repository"}
                </PatternFlyButton>
                <PatternFlyButton variant="secondary" onClick={onCancel} disabled={isCloning}>
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