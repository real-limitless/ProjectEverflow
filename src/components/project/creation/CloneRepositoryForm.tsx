import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Card, CardBody, CardTitle, Button as PatternFlyButton } from '@patternfly/react-core';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from "@/hooks/use-toast";
import { Github, Gitlab, Lock } from "lucide-react";
import { ArrowLeftIcon } from '@patternfly/react-icons';
import {
  createProject,
  getCurrentUser,
  getOrganizationGitConnections,
  getPersonalGitConnections,
  getOrganizations,
  GitConnectionScope,
  normalizeApiList,
} from '@/lib/api';

const cloneSchema = z.object({
  repositoryUrl: z.string().trim().min(1, "Enter a repository URL, SSH clone URL, or supported owner/repo slug"),
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
  // null = no connection (public), 'personal:N' or 'org:N' = a saved connection
  const [selectedConnectionKey, setSelectedConnectionKey] = useState<string>('none');

  const { data: organizations } = useQuery({
    queryKey: ['organizations'],
    queryFn: async () => {
      const response = await getOrganizations();
      return normalizeApiList(response.data);
    },
  });
  const firstOrgId = organizations?.[0]?.id ?? null;

  const { data: orgConnectionsData } = useQuery({
    queryKey: ['orgGitConnections', firstOrgId],
    queryFn: () => getOrganizationGitConnections({ organizationId: firstOrgId! }),
    enabled: firstOrgId !== null,
    select: (response) => normalizeApiList(response.data),
  });

  const { data: personalConnectionsData } = useQuery({
    queryKey: ['personalGitConnections'],
    queryFn: getPersonalGitConnections,
    select: (response) => normalizeApiList(response.data),
  });

  const allConnections = [
    ...(orgConnectionsData ?? []).map((c) => ({ ...c, connectionScope: 'organization' as GitConnectionScope })),
    ...(personalConnectionsData ?? []).map((c) => ({ ...c, connectionScope: 'personal' as GitConnectionScope })),
  ];

  const form = useForm<CloneFormData>({
    resolver: zodResolver(cloneSchema),
    defaultValues: {
      provider: "github",
      branch: "main",
    },
  });

  const currentProvider = form.watch('provider');

    const onSubmit = async (data: CloneFormData) => {
    setIsCloning(true);

    try {
      const normalizedProviderHint = data.provider === 'other' ? undefined : data.provider;

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

      // Resolve connection fields from the selected connection key
      let connectionScope: GitConnectionScope | undefined;
      let connectionId: number | undefined;
      if (selectedConnectionKey && selectedConnectionKey !== 'none') {
        const [scopePrefix, idStr] = selectedConnectionKey.split(':');
        connectionScope = scopePrefix as GitConnectionScope;
        connectionId = Number(idStr);
      }

      const response = await createProject({
        name: data.projectName,
        description: `Cloned from ${data.provider} repository: ${data.repositoryUrl}`,
        owner: userResponse.data.id,
        creation_method: 'clone',
        git_repo_url: data.repositoryUrl,
        git_provider_hint: normalizedProviderHint,
        branch: data.branch || 'main',
        ...(connectionScope && connectionId ? { connection_scope: connectionScope, connection_id: connectionId } : {}),
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

              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Lock className="h-4 w-4" />
                  Saved connection (for private repositories)
                </Label>
                <Select value={selectedConnectionKey} onValueChange={setSelectedConnectionKey}>
                  <SelectTrigger>
                    <SelectValue placeholder="No connection — public repo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No connection — public repository</SelectItem>
                    {allConnections
                      .filter((c) => c.provider_type === currentProvider || currentProvider === 'other')
                      .map((c) => (
                        <SelectItem key={`${c.connectionScope}:${c.id}`} value={`${c.connectionScope}:${c.id}`}>
                          {c.name} ({c.connectionScope === 'organization' ? 'shared' : 'personal'})
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Select a saved connection to clone private repositories. Connections are filtered by the selected provider. Leave as "No connection" for public repos.
                </p>
              </div>

              <FormField
                control={form.control}
                name="repositoryUrl"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Repository URL *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="https://github.com/username/repo, username/repo, or git@github.com:username/repo.git"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Public repositories do not need a saved connection. For GitHub, GitLab, and Bitbucket you can enter a full HTTPS URL, an owner/repo slug, or a hosted git@ URL.
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