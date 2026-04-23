import { useState, useEffect, useMemo } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Grid, GridItem, Form, FormGroup, TextInput, Switch, Button, Alert, FormSelect, FormSelectOption } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Settings as SettingsIcon, Plus, AlertTriangle, Brain } from 'lucide-react';
import { 
  getCurrentUser, 
  updateCurrentUser, 
  User, 
  LLMProvider,
  listLLMProviders,
  deleteLLMProvider,
  getTeams,
  getProjects,
  Team,
  Project,
} from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';
import { AddProviderDialog } from '@/components/AddProviderDialog';
import { ProviderCard } from '@/components/ProviderCard';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const Settings = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [userProfile, setUserProfile] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [darkMode, setDarkMode] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  // LLM Provider state
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(false);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<LLMProvider | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [providerToDelete, setProviderToDelete] = useState<LLMProvider | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchUserProfile();
    fetchProviders();
    fetchTeamsAndProjects();
  }, []);

  const fetchUserProfile = async () => {
    try {
      const result = await getCurrentUser();
      if (result.data) {
        setUserProfile(result.data);
        setEmailNotifications(result.data.email_notifications);
        setDarkMode(result.data.dark_mode);
      } else {
        setErrorMessage('Failed to load user profile');
      }
    } catch (error) {
      setErrorMessage('Failed to load user profile');
    } finally {
      setLoading(false);
    }
  };

  const fetchProviders = async () => {
    setLoadingProviders(true);
    try {
      const result = await listLLMProviders();
      if (result.data) {
        setProviders(result.data);
      }
    } catch (error) {
      console.error('Failed to load providers:', error);
    } finally {
      setLoadingProviders(false);
    }
  };

  const fetchTeamsAndProjects = async () => {
    try {
      const [teamsResult, projectsResult] = await Promise.all([
        getTeams(),
        getProjects(),
      ]);
      if (teamsResult.data) setTeams(teamsResult.data);
      if (projectsResult.data) setProjects(projectsResult.data);
    } catch (error) {
      console.error('Failed to load teams/projects:', error);
    }
  };

  const handleAddProvider = () => {
    setEditingProvider(null);
    setAddProviderOpen(true);
  };

  const handleEditProvider = (provider: LLMProvider) => {
    setEditingProvider(provider);
    setAddProviderOpen(true);
  };

  const handleDeleteClick = (provider: LLMProvider) => {
    setProviderToDelete(provider);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!providerToDelete) return;

    setDeleting(true);
    try {
      const result = await deleteLLMProvider(providerToDelete.id);
      if (!result.error) {
        setSuccessMessage(`Deleted provider: ${providerToDelete.instance_name}`);
        fetchProviders();
      } else {
        setErrorMessage(`Failed to delete provider: ${result.error}`);
      }
    } catch (error) {
      setErrorMessage('Failed to delete provider');
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
      setProviderToDelete(null);
    }
  };

  const handleProviderSuccess = () => {
    fetchProviders();
    setSuccessMessage(editingProvider ? 'Provider updated successfully' : 'Provider added successfully');
  };

  const handleProfileUpdate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!userProfile) return;

    setSaving(true);
    setSuccessMessage('');
    setErrorMessage('');

    try {
      const updateData = {
        email: userProfile.email,
        first_name: userProfile.first_name,
        last_name: userProfile.last_name,
        bio: userProfile.bio,
        email_notifications: emailNotifications,
        dark_mode: darkMode,
        default_llm_model: userProfile.default_llm_model,
      };

      const result = await updateCurrentUser(updateData);
      if (result.data) {
        setUserProfile(result.data);
        setEmailNotifications(result.data.email_notifications);
        setDarkMode(result.data.dark_mode);
        setSuccessMessage('Profile updated successfully!');
      } else {
        setErrorMessage('Failed to update profile');
      }
    } catch (error) {
      setErrorMessage('Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const handleInputChange = (field: keyof User, value: string) => {
    if (userProfile) {
      setUserProfile({ ...userProfile, [field]: value });
    }
  };

  // Compute available models from all providers
  const availableModels = useMemo(() => {
    const models: Array<{ value: string; label: string; provider: string }> = [];
    providers.forEach(provider => {
      const providerModels = Array.isArray(provider.available_models)
        ? provider.available_models
        : Object.keys(provider.available_models || {});
      
      providerModels.forEach((model: any) => {
        const modelId = typeof model === 'string' ? model : (model.id || model.name);
        const modelName = typeof model === 'string' ? model : (model.name || model.id);
        models.push({
          value: modelId,
          label: `${modelName} (${provider.instance_name})`,
          provider: provider.instance_name,
        });
      });
    });
    return models;
  }, [providers]);

  if (loading) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div>Loading...</div>
        </PageSection>
      </Page>
    );
  }

  if (!userProfile) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <Alert variant="danger" title="Error loading profile" />
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
        <PageHeader
          title="Settings"
          description="Manage your account preferences, notifications, and profile settings."
          icon={<SettingsIcon size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        {successMessage && (
          <Alert variant="success" title={successMessage} style={{ marginBottom: '1rem' }} />
        )}

        {errorMessage && (
          <Alert variant="danger" title={errorMessage} style={{ marginBottom: '1rem' }} />
        )}

        {/* LLM Provider Management Section */}
        <Card style={{ marginBottom: '1.5rem' }}>
          <CardTitle>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>My LLM Providers</span>
              <Button 
                variant="primary" 
                onClick={handleAddProvider}
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Plus size={16} />
                Add Provider
              </Button>
            </div>
          </CardTitle>
          <CardBody>
            {loadingProviders ? (
              <div>Loading providers...</div>
            ) : providers.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--pf-v6-global--Color--200)' }}>
                <Brain size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                <p style={{ marginBottom: '0.5rem', fontSize: '1.1rem', fontWeight: 600 }}>No LLM Providers Configured</p>
                <p>Add a provider to start using different AI models for your projects.</p>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1rem' }}>
                {providers
                  .filter(p => p.scope === 'user')
                  .map(provider => (
                    <ProviderCard
                      key={provider.id}
                      provider={provider}
                      onEdit={handleEditProvider}
                      onDelete={handleDeleteClick}
                      onRefresh={fetchProviders}
                      canEdit={true}
                      canDelete={true}
                    />
                  ))}
              </div>
            )}

            {/* Project Providers */}
            {providers.filter(p => p.scope === 'project').length > 0 && (
              <div style={{ marginTop: '2rem' }}>
                <h3 style={{ marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 600 }}>
                  Project Providers
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1rem' }}>
                  {providers
                    .filter(p => p.scope === 'project')
                    .map(provider => (
                      <ProviderCard
                        key={provider.id}
                        provider={provider}
                        onEdit={userProfile?.role === 'admin' ? handleEditProvider : undefined}
                        onDelete={userProfile?.role === 'admin' ? handleDeleteClick : undefined}
                        onRefresh={fetchProviders}
                        canEdit={userProfile?.role === 'admin'}
                        canDelete={userProfile?.role === 'admin'}
                      />
                    ))}
                </div>
              </div>
            )}

            {/* Team Providers */}
            {providers.filter(p => p.scope === 'team').length > 0 && (
              <div style={{ marginTop: '2rem' }}>
                <h3 style={{ marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 600 }}>
                  Team Providers
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1rem' }}>
                  {providers
                    .filter(p => p.scope === 'team')
                    .map(provider => (
                      <ProviderCard
                        key={provider.id}
                        provider={provider}
                        onEdit={userProfile?.role === 'admin' ? handleEditProvider : undefined}
                        onDelete={userProfile?.role === 'admin' ? handleDeleteClick : undefined}
                        onRefresh={fetchProviders}
                        canEdit={userProfile?.role === 'admin'}
                        canDelete={userProfile?.role === 'admin'}
                      />
                    ))}
                </div>
              </div>
            )}

            {/* System Providers (Admin Only) */}
            {userProfile?.role === 'admin' && providers.filter(p => p.scope === 'system').length > 0 && (
              <div style={{ marginTop: '2rem' }}>
                <h3 style={{ marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 600, color: 'var(--pf-v6-global--palette--purple-500)' }}>
                  System Providers (Admin)
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1rem' }}>
                  {providers
                    .filter(p => p.scope === 'system')
                    .map(provider => (
                      <ProviderCard
                        key={provider.id}
                        provider={provider}
                        onEdit={handleEditProvider}
                        onDelete={handleDeleteClick}
                        onRefresh={fetchProviders}
                        canEdit={true}
                        canDelete={true}
                      />
                    ))}
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        <Grid hasGutter>
          <GridItem span={12} lg={6}>
            <Card>
              <CardTitle>Profile Settings</CardTitle>
              <CardBody>
                <Form onSubmit={handleProfileUpdate}>
                  <FormGroup label="Username" isRequired>
                    <TextInput
                      type="text"
                      id="username"
                      name="username"
                      value={userProfile.username}
                      isDisabled
                    />
                  </FormGroup>
                  <FormGroup label="First Name">
                    <TextInput
                      type="text"
                      id="first_name"
                      name="first_name"
                      value={userProfile.first_name}
                      onChange={(_event, value) => handleInputChange('first_name', value)}
                    />
                  </FormGroup>
                  <FormGroup label="Last Name">
                    <TextInput
                      type="text"
                      id="last_name"
                      name="last_name"
                      value={userProfile.last_name}
                      onChange={(_event, value) => handleInputChange('last_name', value)}
                    />
                  </FormGroup>
                  <FormGroup label="Email" isRequired>
                    <TextInput
                      type="email"
                      id="email"
                      name="email"
                      value={userProfile.email}
                      onChange={(_event, value) => handleInputChange('email', value)}
                    />
                  </FormGroup>
                  <FormGroup label="Bio">
                    <TextInput
                      type="text"
                      id="bio"
                      name="bio"
                      value={userProfile.bio}
                      onChange={(_event, value) => handleInputChange('bio', value)}
                    />
                  </FormGroup>
                  <Button type="submit" isLoading={saving} isDisabled={saving}>
                    {saving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </Form>
              </CardBody>
            </Card>
          </GridItem>
          <GridItem span={12} lg={6}>
            <Card>
              <CardTitle>Preferences</CardTitle>
              <CardBody>
                <div style={{ marginBottom: '1rem' }}>
                  <Switch
                    id="email-notifications"
                    label="Email Notifications"
                    isChecked={emailNotifications}
                    onChange={() => setEmailNotifications(!emailNotifications)}
                  />
                </div>
                <div style={{ marginBottom: '1rem' }}>
                  <Switch
                    id="dark-mode"
                    label="Dark Mode"
                    isChecked={darkMode}
                    onChange={() => setDarkMode(!darkMode)}
                  />
                </div>
                <FormGroup label="Default LLM Model" fieldId="default-llm-model">
                  <FormSelect
                    id="default-llm-model"
                    value={userProfile.default_llm_model || ''}
                    onChange={(_event, value) => handleInputChange('default_llm_model', value)}
                  >
                    <FormSelectOption key="none" value="" label="No default (use provider default)" />
                    {availableModels.map(model => (
                      <FormSelectOption
                        key={model.value}
                        value={model.value}
                        label={model.label}
                      />
                    ))}
                  </FormSelect>
                  <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                    Select a default model to use across all projects and chatbots
                  </div>
                </FormGroup>
              </CardBody>
            </Card>
          </GridItem>
        </Grid>
      </PageSection>

      {/* Add/Edit Provider Dialog */}
      {userProfile && (
        <AddProviderDialog
          open={addProviderOpen}
          onOpenChange={setAddProviderOpen}
          onSuccess={handleProviderSuccess}
          currentUser={userProfile}
          teams={teams}
          projects={projects}
          editProvider={editingProvider}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              Delete Provider?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{providerToDelete?.instance_name}</strong>? 
              This action cannot be undone. Any chat sessions using this provider will fall back to system defaults.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700"
            >
              {deleting ? 'Deleting...' : 'Delete Provider'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Page>
  );
};

export default Settings;
