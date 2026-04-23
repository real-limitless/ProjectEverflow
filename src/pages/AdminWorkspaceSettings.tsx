import { useState } from 'react';
import { Page, PageSection, PageBody, Card, CardBody, Button, MenuToggle, Dropdown, DropdownList, DropdownItem } from '@patternfly/react-core';
import { EllipsisVIcon } from '@patternfly/react-icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { 
  getWorkspaceTiers, 
  createWorkspaceTier,
  updateWorkspaceTier,
  deleteWorkspaceTier,
  WorkspaceResourceTier
} from '@/lib/api';
import { toast } from '@/hooks/use-toast';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import PageHeader from '@/components/ui/PageHeader';
import { Plus, Edit2, Trash2, Check, Settings, ArrowLeft } from 'lucide-react';

interface TierFormData {
  name: string;
  slug: string;
  cpu_limit: string;
  memory_limit: string;
}

const AdminWorkspaceSettings = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [editingTier, setEditingTier] = useState<WorkspaceResourceTier | null>(null);
  const [formData, setFormData] = useState<TierFormData>({
    name: '',
    slug: '',
    cpu_limit: '',
    memory_limit: '',
  });
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [deleteConfirmTier, setDeleteConfirmTier] = useState<WorkspaceResourceTier | null>(null);

  // Fetch workspace tiers
  const { data: tiersResponse, isLoading } = useQuery({
    queryKey: ['workspace-tiers'],
    queryFn: getWorkspaceTiers,
  });

  const tiers = tiersResponse?.data || [];

  // Create tier mutation
  const createMutation = useMutation({
    mutationFn: (data: TierFormData) => createWorkspaceTier(data),
    onSuccess: () => {
      toast({
        title: "Tier Created",
        description: "Workspace resource tier created successfully.",
      });
      setFormData({ name: '', slug: '', cpu_limit: '', memory_limit: '' });
      setIsCreateDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ['workspace-tiers'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to create tier.",
        variant: "destructive",
      });
    },
  });

  // Update tier mutation
  const updateMutation = useMutation({
    mutationFn: (data: TierFormData) => {
      if (!editingTier) throw new Error('No tier selected');
      return updateWorkspaceTier(editingTier.slug, data);
    },
    onSuccess: () => {
      toast({
        title: "Tier Updated",
        description: "Workspace resource tier updated successfully.",
      });
      setFormData({ name: '', slug: '', cpu_limit: '', memory_limit: '' });
      setEditingTier(null);
      setIsEditDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ['workspace-tiers'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to update tier.",
        variant: "destructive",
      });
    },
  });

  // Delete tier mutation
  const deleteMutation = useMutation({
    mutationFn: (slug: string) => deleteWorkspaceTier(slug),
    onSuccess: () => {
      toast({
        title: "Tier Deleted",
        description: "Workspace resource tier deleted successfully.",
      });
      setDeleteConfirmTier(null);
      queryClient.invalidateQueries({ queryKey: ['workspace-tiers'] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to delete tier.",
        variant: "destructive",
      });
    },
  });

  const handleCreateSubmit = () => {
    if (!formData.name || !formData.slug || !formData.cpu_limit || !formData.memory_limit) {
      toast({
        title: "Validation Error",
        description: "All fields are required.",
        variant: "destructive",
      });
      return;
    }

    // Validate CPU (should be a float >= 0.5)
    const cpuNum = parseFloat(formData.cpu_limit);
    if (isNaN(cpuNum) || cpuNum < 0.5) {
      toast({
        title: "Validation Error",
        description: "CPU limit must be a number >= 0.5",
        variant: "destructive",
      });
      return;
    }

    // Validate memory (should be in format like "512m", "1g", "4g", etc.)
    if (!/^\d+[mg]$/.test(formData.memory_limit.toLowerCase())) {
      toast({
        title: "Validation Error",
        description: "Memory must be in format like '512m' or '4g'",
        variant: "destructive",
      });
      return;
    }

    createMutation.mutate(formData);
  };

  const handleEditSubmit = () => {
    if (!formData.name || !formData.slug || !formData.cpu_limit || !formData.memory_limit) {
      toast({
        title: "Validation Error",
        description: "All fields are required.",
        variant: "destructive",
      });
      return;
    }

    // Validate CPU
    const cpuNum = parseFloat(formData.cpu_limit);
    if (isNaN(cpuNum) || cpuNum < 0.5) {
      toast({
        title: "Validation Error",
        description: "CPU limit must be a number >= 0.5",
        variant: "destructive",
      });
      return;
    }

    // Validate memory
    if (!/^\d+[mg]$/.test(formData.memory_limit.toLowerCase())) {
      toast({
        title: "Validation Error",
        description: "Memory must be in format like '512m' or '4g'",
        variant: "destructive",
      });
      return;
    }

    updateMutation.mutate(formData);
  };

  const openCreateDialog = () => {
    setFormData({ name: '', slug: '', cpu_limit: '', memory_limit: '' });
    setEditingTier(null);
    setIsCreateDialogOpen(true);
  };

  const openEditDialog = (tier: WorkspaceResourceTier) => {
    setEditingTier(tier);
    setFormData({
      name: tier.name,
      slug: tier.slug,
      cpu_limit: tier.cpu_limit.toString(),
      memory_limit: tier.memory_limit,
    });
    setIsEditDialogOpen(true);
  };

  const handleDeleteConfirm = () => {
    if (deleteConfirmTier) {
      deleteMutation.mutate(deleteConfirmTier.slug);
    }
  };

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default" style={{ paddingTop: '1.5rem', paddingBottom: '0' }}>
        <div style={{ marginBottom: '1rem' }}>
          <Button 
            variant="secondary"
            size="sm"
            onClick={() => navigate(-1)}
            icon={<ArrowLeft className="h-4 w-4" />}
          >
            Back
          </Button>
        </div>
        <PageHeader
          title="Workspace Settings"
          description="Manage workspace resource tiers and configurations"
          icon={<Settings size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />
      </PageSection>

      <PageBody>
        <PageSection variant="default">
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1.5rem' }}>
            <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
              <DialogTrigger asChild>
                <Button 
                  variant="primary"
                  onClick={openCreateDialog}
                  icon={<Plus className="h-4 w-4" />}
                >
                  New Tier
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>Create New Resource Tier</DialogTitle>
                  <DialogDescription>
                    Define a new workspace resource tier with CPU and memory limits
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="tier-name">Tier Name</Label>
                      <Input
                        id="tier-name"
                        placeholder="e.g., Light, Standard, Heavy"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label htmlFor="tier-slug">Slug</Label>
                      <Input
                        id="tier-slug"
                        placeholder="e.g., light, standard, heavy"
                        value={formData.slug}
                        onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                        className="mt-1"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="cpu-limit">CPU Limit</Label>
                      <Input
                        id="cpu-limit"
                        type="number"
                        step="0.5"
                        min="0.5"
                        placeholder="e.g., 1.0, 2.0, 4.0"
                        value={formData.cpu_limit}
                        onChange={(e) => setFormData({ ...formData, cpu_limit: e.target.value })}
                        className="mt-1"
                      />
                      <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
                        Minimum: 0.5 CPU cores
                      </p>
                    </div>
                    <div>
                      <Label htmlFor="memory-limit">Memory Limit</Label>
                      <Input
                        id="memory-limit"
                        placeholder="e.g., 512m, 1g, 4g"
                        value={formData.memory_limit}
                        onChange={(e) => setFormData({ ...formData, memory_limit: e.target.value })}
                        className="mt-1"
                      />
                      <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
                        Format: 512m, 1g, 2g, 4g, etc.
                      </p>
                    </div>
                  </div>

                  <div className="flex gap-3 justify-end">
                    <Button 
                      variant="secondary"
                      onClick={() => setIsCreateDialogOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button 
                      variant="primary"
                      onClick={handleCreateSubmit}
                      isLoading={createMutation.isPending}
                    >
                      Create Tier
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          <Card>
            <CardBody>
              <div style={{ overflowX: 'auto' }}>
                <table style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.875rem',
                }}>
                  <thead>
                    <tr style={{
                      borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
                      backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                    }}>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>Name</th>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>Slug</th>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>CPU</th>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>Memory</th>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>Default</th>
                      <th style={{ padding: '1rem', textAlign: 'left', fontWeight: 600 }}>Status</th>
                      <th style={{ padding: '1rem', textAlign: 'center', fontWeight: 600 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading ? (
                      <tr>
                        <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--pf-v6-global--Color--200)' }}>
                          Loading tiers...
                        </td>
                      </tr>
                    ) : tiers.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--pf-v6-global--Color--200)' }}>
                          No resource tiers found. Create one to get started.
                        </td>
                      </tr>
                    ) : (
                      tiers.map((tier) => (
                        <tr key={tier.id} style={{
                          borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
                          backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
                        }}>
                          <td style={{ padding: '1rem' }}>
                            <span style={{ fontWeight: 500 }}>{tier.name}</span>
                          </td>
                          <td style={{ padding: '1rem' }}>
                            <code style={{ 
                              backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                              padding: '0.25rem 0.5rem',
                              borderRadius: '0.25rem',
                              fontSize: '0.8125rem',
                            }}>
                              {tier.slug}
                            </code>
                          </td>
                          <td style={{ padding: '1rem' }}>
                            {tier.cpu_limit} CPU
                          </td>
                          <td style={{ padding: '1rem' }}>
                            {tier.memory_limit}
                          </td>
                          <td style={{ padding: '1rem' }}>
                            {tier.is_default ? (
                              <Badge variant="secondary">
                                <Check className="h-3 w-3 mr-1" />
                                Default
                              </Badge>
                            ) : (
                              <span style={{ color: 'var(--pf-v6-global--Color--200)' }}>—</span>
                            )}
                          </td>
                          <td style={{ padding: '1rem' }}>
                            <Badge variant={tier.is_active ? "secondary" : "outline"}>
                              {tier.is_active ? 'Active' : 'Inactive'}
                            </Badge>
                          </td>
                          <td style={{ padding: '1rem', textAlign: 'center' }}>
                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                              <Button
                                variant="plain"
                                size="sm"
                                icon={<Edit2 className="h-4 w-4" />}
                                onClick={() => openEditDialog(tier)}
                              />
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button
                                    variant="plain"
                                    size="sm"
                                    icon={<Trash2 className="h-4 w-4" />}
                                    onClick={() => setDeleteConfirmTier(tier)}
                                  />
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>Delete Tier</AlertDialogTitle>
                                    <AlertDialogDescription>
                                      Are you sure you want to delete the "{deleteConfirmTier?.name}" tier? This action cannot be undone.
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                                    <AlertDialogAction onClick={handleDeleteConfirm} style={{ backgroundColor: 'var(--pf-v6-global--danger-color--100)' }}>
                                      Delete
                                    </AlertDialogAction>
                                  </div>
                                </AlertDialogContent>
                              </AlertDialog>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>

          {/* Edit Dialog */}
          <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Edit Resource Tier</DialogTitle>
                <DialogDescription>
                  Update workspace resource tier configuration
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="edit-tier-name">Tier Name</Label>
                    <Input
                      id="edit-tier-name"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label htmlFor="edit-tier-slug">Slug</Label>
                    <Input
                      id="edit-tier-slug"
                      value={formData.slug}
                      disabled
                      className="mt-1"
                      style={{ opacity: 0.6 }}
                    />
                    <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
                      Slug cannot be changed
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="edit-cpu-limit">CPU Limit</Label>
                    <Input
                      id="edit-cpu-limit"
                      type="number"
                      step="0.5"
                      min="0.5"
                      value={formData.cpu_limit}
                      onChange={(e) => setFormData({ ...formData, cpu_limit: e.target.value })}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label htmlFor="edit-memory-limit">Memory Limit</Label>
                    <Input
                      id="edit-memory-limit"
                      value={formData.memory_limit}
                      onChange={(e) => setFormData({ ...formData, memory_limit: e.target.value })}
                      className="mt-1"
                    />
                  </div>
                </div>

                <div className="flex gap-3 justify-end">
                  <Button 
                    variant="secondary"
                    onClick={() => setIsEditDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button 
                    variant="primary"
                    onClick={handleEditSubmit}
                    isLoading={updateMutation.isPending}
                  >
                    Update Tier
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </PageSection>
      </PageBody>
    </Page>
  );
};

export default AdminWorkspaceSettings;
