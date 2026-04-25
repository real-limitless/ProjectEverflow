import { Card, CardBody, Button, Alert, AlertActionCloseButton, Spinner } from '@patternfly/react-core';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { toast } from '@/hooks/use-toast';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { updateProject, Project, resetWorkspace, updateWorkspaceImage, getWorkspaceTiers, getProjectServices, WorkspaceResourceTier } from '@/lib/api';
import { Trash2, RotateCcw, Settings, Upload, X, Image, Star, Globe, GlobeLock } from 'lucide-react';
import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';

const applicationFormSchema = z.object({
  name: z.string().trim().min(1, { message: "Project name is required" }).max(100, { message: "Name must be less than 100 characters" }),
  description: z.string().trim().min(10, { message: "Description must be at least 10 characters" }).max(2000, { message: "Description must be less than 2000 characters" }),
  short_description: z.string().trim().max(160, { message: "Short description must be less than 160 characters" }).optional(),
  system_prompt: z.string().optional(),
  category: z.string().optional(),
  version: z.string().trim().regex(/^\d+\.\d+\.\d+$/, { message: "Version must be in format X.Y.Z (e.g., 1.0.0)" }).optional().or(z.literal('')),
  website_url: z.string().url({ message: "Must be a valid URL" }).optional().or(z.literal('')),
  workspace_image: z.string().optional(),
  workspace_size: z.string().optional(),
  workspace_mode: z.string().optional(),
  log_retention_days: z.number().int().min(0, { message: "Must be 0 or greater" }).max(365, { message: "Cannot exceed 365 days" }).optional(),
});

interface ProjectDetailsTabProps {
  project: Project;
}

export const ProjectDetailsTab: React.FC<ProjectDetailsTabProps> = ({ project }) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showImageUpdateConfirm, setShowImageUpdateConfirm] = useState(false);
  const [screenshots, setScreenshots] = useState<string[]>([]);
  const [isPublished, setIsPublished] = useState(project.status === 'published');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const form = useForm<z.infer<typeof applicationFormSchema>>({
    resolver: zodResolver(applicationFormSchema),
    defaultValues: {
      name: project.name || '',
      description: project.description || '',
      short_description: '',
      system_prompt: project.system_prompt || '',
      category: '',
      version: '1.0.0',
      website_url: '',
      workspace_image: project.workspace_image || 'fedora:43',
      workspace_size: project.workspace_size || 'standard',
      workspace_mode: project.workspace_mode || 'personal',
      log_retention_days: project.log_retention_days || 30,
    },
  });

  // Fetch workspace tiers
  const { data: tiersResponse } = useQuery({
    queryKey: ['workspace-tiers'],
    queryFn: getWorkspaceTiers,
  });
  const tiers = tiersResponse?.data || [];

  // Check if workspace service exists
  const { data: servicesResponse } = useQuery({
    queryKey: ['project-services', project.id, 'ai-workspace'],
    queryFn: () => getProjectServices(project.id, 'ai-workspace'),
  });
  const workspaceServices = servicesResponse?.data || [];
  const hasWorkspace = workspaceServices.length > 0;

  const updateProjectMutation = useMutation({
    mutationFn: (data: Partial<Project>) => updateProject(project.id, data),
    onSuccess: () => {
      toast({
        title: "Changes Saved",
        description: "Project details have been updated successfully.",
      });
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.error || "Failed to update project details.",
        variant: "destructive",
      });
    },
  });

  const resetWorkspaceMutation = useMutation({
    mutationFn: () => {
      if (!hasWorkspace) {
        return Promise.reject(new Error('No workspace service found. Please provision workspace first in the AI Editor or Webtop tab.'));
      }
      return resetWorkspace(project.id);
    },
    onSuccess: () => {
      toast({
        title: "Workspace Reset",
        description: "Workspace volume has been reset and reinitialized.",
      });
      setShowResetConfirm(false);
      queryClient.invalidateQueries({ queryKey: ['project-services'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || error?.error || "Failed to reset workspace.",
        variant: "destructive",
      });
    },
  });

  const updateImageMutation = useMutation({
    mutationFn: () => {
      if (!hasWorkspace) {
        return Promise.reject(new Error('No workspace service found. Please provision workspace first in the AI Editor or Webtop tab.'));
      }
      return updateWorkspaceImage(project.id);
    },
    onSuccess: () => {
      toast({
        title: "Workspace Image Updated",
        description: "New image pulled and workspace stopped. Click Start in the Webtop or AI Editor tab to begin using the updated image.",
      });
      setShowImageUpdateConfirm(false);
      queryClient.invalidateQueries({ queryKey: ['project-services'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || error?.error || "Failed to update workspace image.",
        variant: "destructive",
      });
      setShowImageUpdateConfirm(false);
    },
  });

  const onSubmit = (values: z.infer<typeof applicationFormSchema>) => {
    updateProjectMutation.mutate(values);
  };

  const handleScreenshotUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach(file => {
      const reader = new FileReader();
      reader.onloadend = () => {
        setScreenshots(prev => [...prev, reader.result as string]);
      };
      reader.readAsDataURL(file);
    });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeScreenshot = (index: number) => {
    setScreenshots(prev => prev.filter((_, i) => i !== index));
  };

  const togglePublish = () => {
    const newStatus = isPublished ? 'draft' : 'published';
    updateProjectMutation.mutate({ status: newStatus } as any, {
      onSuccess: () => {
        setIsPublished(!isPublished);
        toast({
          title: isPublished ? 'Unpublished' : 'Published',
          description: isPublished 
            ? 'Application removed from Enterprise App Store.' 
            : 'Application is now live on the Enterprise App Store!',
        });
      },
    });
  };

  // Mock ratings for demo
  const ratings = { average: 4.2, count: 18 };

  return (
    <div className="space-y-6">
      {/* Publishing Status Banner */}
      <Card>
        <CardBody>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div className="flex items-center gap-3">
              {isPublished ? (
                <Globe className="h-5 w-5 text-green-500" />
              ) : (
                <GlobeLock className="h-5 w-5 text-muted-foreground" />
              )}
              <div>
                <h3 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>
                  {isPublished ? 'Published on Enterprise App Store' : 'Not Published'}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {isPublished 
                    ? 'Your application is visible to all users in the marketplace.' 
                    : 'Publish your application to make it available in the Enterprise App Store.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {isPublished && (
                <div className="flex items-center gap-1">
                  <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                  <span className="text-sm font-medium">{ratings.average}</span>
                  <span className="text-xs text-muted-foreground">({ratings.count} reviews)</span>
                </div>
              )}
              <Button
                variant={isPublished ? 'secondary' : 'primary'}
                onClick={togglePublish}
              >
                {isPublished ? (
                  <>
                    <GlobeLock className="h-4 w-4 mr-2" />
                    Unpublish
                  </>
                ) : (
                  <>
                    <Globe className="h-4 w-4 mr-2" />
                    Publish to App Store
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* App Store Listing Details */}
      <Card>
        <CardBody>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            App Store Listing
          </h2>
          <p className="text-sm text-muted-foreground mb-6">
            Complete your listing to help users discover and understand your application.
          </p>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Application Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="Enter application name" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="version"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Version</FormLabel>
                      <FormControl>
                        <Input placeholder="1.0.0" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="short_description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Short Description</FormLabel>
                    <FormControl>
                      <Input 
                        placeholder="A brief tagline for your app (shown in search results)"
                        maxLength={160}
                        {...field} 
                      />
                    </FormControl>
                    <p className="text-xs text-muted-foreground mt-1">
                      {(field.value || '').length}/160 characters
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Full Description * (Markdown supported)</FormLabel>
                    <FormControl>
                      <Textarea 
                        placeholder="Describe your application in detail. Use Markdown for formatting: **bold**, *italic*, - bullet points, ## headings, etc."
                        className="min-h-[200px] font-mono text-sm"
                        {...field}
                      />
                    </FormControl>
                    <p className="text-xs text-muted-foreground mt-1">
                      Supports Markdown formatting. {(field.value || '').length}/2000 characters
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="category"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Category</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a category" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="ai-assistant">AI Assistant</SelectItem>
                          <SelectItem value="data-analytics">Data & Analytics</SelectItem>
                          <SelectItem value="developer-tools">Developer Tools</SelectItem>
                          <SelectItem value="automation">Automation</SelectItem>
                          <SelectItem value="security">Security</SelectItem>
                          <SelectItem value="infrastructure">Infrastructure</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="website_url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Website / Documentation URL</FormLabel>
                      <FormControl>
                        <Input placeholder="https://docs.example.com" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="system_prompt"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>AI System Prompt (Optional)</FormLabel>
                    <FormControl>
                      <Textarea 
                        placeholder="Enter a custom system prompt for the AI assistant in this project..."
                        className="min-h-[120px]"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-4">
                <Button 
                  variant="secondary"
                  onClick={() => form.reset()}
                >
                  Reset Changes
                </Button>
                <Button 
                  type="submit" 
                  variant="primary"
                  isLoading={updateProjectMutation.isPending}
                >
                  Save Details
                </Button>
              </div>
            </form>
          </Form>
        </CardBody>
      </Card>

      {/* Screenshots Gallery */}
      <Card>
        <CardBody>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            Screenshots
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Add screenshots to showcase your application. Users will see these on the App Store listing.
          </p>
          
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {screenshots.map((src, idx) => (
              <div key={idx} className="relative group rounded-lg overflow-hidden border border-border aspect-video bg-muted">
                <img src={src} alt={`Screenshot ${idx + 1}`} className="w-full h-full object-cover" />
                <button
                  onClick={() => removeScreenshot(idx)}
                  className="absolute top-1 right-1 p-1 bg-destructive text-destructive-foreground rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="h-3 w-3" />
                </button>
                <div className="absolute bottom-1 left-1">
                  <Badge variant="secondary" className="text-xs">#{idx + 1}</Badge>
                </div>
              </div>
            ))}
            
            {/* Upload placeholder */}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border aspect-video bg-muted/50 hover:bg-muted transition-colors cursor-pointer"
            >
              <Upload className="h-6 w-6 text-muted-foreground mb-1" />
              <span className="text-xs text-muted-foreground">Add Screenshot</span>
            </button>
          </div>
          
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={handleScreenshotUpload}
          />
          <p className="text-xs text-muted-foreground">
            Recommended: 1280x720 or higher. PNG or JPEG. Max 5 screenshots.
          </p>
        </CardBody>
      </Card>

      {/* Ratings & Feedback (Read-only preview) */}
      <Card>
        <CardBody>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            Ratings & Feedback
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            User ratings and feedback from the Enterprise App Store.
          </p>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center p-6 border border-border rounded-lg">
              <div className="text-4xl font-bold mb-1">{ratings.average}</div>
              <div className="flex justify-center gap-0.5 mb-2">
                {[1, 2, 3, 4, 5].map(star => (
                  <Star
                    key={star}
                    className={`h-5 w-5 ${star <= Math.round(ratings.average) ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground'}`}
                  />
                ))}
              </div>
              <div className="text-sm text-muted-foreground">{ratings.count} total ratings</div>
            </div>
            
            <div className="col-span-2 space-y-2">
              {[
                { stars: 5, count: 10, pct: 56 },
                { stars: 4, count: 4, pct: 22 },
                { stars: 3, count: 2, pct: 11 },
                { stars: 2, count: 1, pct: 6 },
                { stars: 1, count: 1, pct: 6 },
              ].map(row => (
                <div key={row.stars} className="flex items-center gap-2 text-sm">
                  <span className="w-4 text-right">{row.stars}</span>
                  <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-yellow-500 rounded-full" style={{ width: `${row.pct}%` }} />
                  </div>
                  <span className="w-6 text-muted-foreground text-right">{row.count}</span>
                </div>
              ))}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Workspace Configuration */}
      <Card>
        <CardBody>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem' }}>
            Workspace Configuration
          </h2>
          
          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1.5rem' }}>
            Configure the development environment for AI-assisted code editing. The workspace will rebuild automatically when you change the image.
          </p>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Workspace Image Selection */}
                <FormField
                  control={form.control}
                  name="workspace_image"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Workspace Base Image</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select base image" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="fedora:43">Fedora 43 (Modern, Latest Tools)</SelectItem>
                          <SelectItem value="registry.access.redhat.com/ubi9/ubi">UBI 9 (Enterprise, RHEL-based)</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Workspace Size (Resource Tier) */}
                <FormField
                  control={form.control}
                  name="workspace_size"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Resource Tier</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select size" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {tiers.map((tier: WorkspaceResourceTier) => (
                            <SelectItem key={tier.slug} value={tier.slug}>
                              {tier.display_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Workspace Mode */}
                <FormField
                  control={form.control}
                  name="workspace_mode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Workspace Mode</FormLabel>
                      <Select value={field.value} onValueChange={field.onChange}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select mode" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="personal">Personal (Individual workspace per user)</SelectItem>
                          <SelectItem value="shared">Shared (All contributors share workspace)</SelectItem>
                        </SelectContent>
                      </Select>
                      <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
                        {field.value === 'personal' 
                          ? 'Each contributor gets their own workspace container but shares project files.'
                          : 'All contributors access the same workspace container and files.'}
                      </p>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Log Retention Days */}
                <FormField
                  control={form.control}
                  name="log_retention_days"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Log Retention (Days)</FormLabel>
                      <FormControl>
                        <Input 
                          type="number" 
                          min="0" 
                          max="365"
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                        />
                      </FormControl>
                      <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
                        Number of days to keep provisioning logs. Set to 0 to keep forever. Default: 30 days.
                      </p>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="flex justify-end gap-4">
                <Button 
                  variant="secondary"
                  onClick={() => form.reset()}
                >
                  Reset
                </Button>
                <Button 
                  type="submit" 
                  variant="primary"
                  isLoading={updateProjectMutation.isPending}
                >
                  Save Workspace Config
                </Button>
              </div>
            </form>
          </Form>

          {/* Workspace Management Actions */}
          <div className="mt-8 pt-8 border-t border-border">
            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem' }}>
              Workspace Management
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Update Workspace Image */}
              <div className="p-4 border border-border rounded-lg">
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Update Workspace Image
                </h4>
                <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
                  Pull the latest workspace image and rebuild the container.
                </p>
                {showImageUpdateConfirm ? (
                  <div className="space-y-3">
                    <p style={{ fontSize: '0.875rem' }}>
                      This will stop the workspace container and pull the latest image.
                    </p>
                    <div className="flex gap-2">
                      <Button 
                        variant="danger"
                        size="sm"
                        onClick={() => updateImageMutation.mutate()}
                        isLoading={updateImageMutation.isPending}
                      >
                        Confirm Update
                      </Button>
                      <Button 
                        variant="secondary"
                        size="sm"
                        onClick={() => setShowImageUpdateConfirm(false)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button 
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowImageUpdateConfirm(true)}
                    isDisabled={!hasWorkspace}
                  >
                    <RotateCcw className="h-4 w-4 mr-2" />
                    Rebuild Image
                  </Button>
                )}
                {!hasWorkspace && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                    Provision workspace first in the AI Editor or Webtop tab
                  </p>
                )}
              </div>

              {/* Reset Workspace */}
              <div className="p-4 border border-border rounded-lg">
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Reset Workspace
                </h4>
                <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
                  Delete all workspace files and reinitialize based on creation method.
                </p>
                {showResetConfirm ? (
                  <div className="space-y-3">
                    <Alert 
                      variant="warning" 
                      isInline 
                      title="Confirm Workspace Reset"
                      actionClose={
                        <AlertActionCloseButton
                          onClose={() => setShowResetConfirm(false)}
                        />
                      }
                    >
                      This will permanently delete all files in your workspace. Files will be reinitialized based on your project's creation method.
                    </Alert>
                    <div className="flex gap-2">
                      <Button 
                        variant="danger"
                        size="sm"
                        onClick={() => resetWorkspaceMutation.mutate()}
                        isLoading={resetWorkspaceMutation.isPending}
                      >
                        Confirm Reset
                      </Button>
                      <Button 
                        variant="secondary"
                        size="sm"
                        onClick={() => setShowResetConfirm(false)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Button 
                    variant="danger"
                    size="sm"
                    onClick={() => setShowResetConfirm(true)}
                    isDisabled={!hasWorkspace}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Reset Workspace
                  </Button>
                )}
                {!hasWorkspace && (
                  <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                    Provision workspace first in the AI Editor or Webtop tab
                  </p>
                )}
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Admin Workspace Settings Link */}
      <Card>
        <CardBody>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Manage Resource Tiers
              </h3>
              <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                Create, edit, and manage workspace resource tiers for your organization. Define CPU and memory limits for Light, Standard, Heavy, and custom tiers.
              </p>
            </div>
            <Button 
              variant="primary"
              onClick={() => navigate('/admin/workspace-settings')}
            >
              <Settings className="h-4 w-4 mr-2" />
              Admin Settings
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};
