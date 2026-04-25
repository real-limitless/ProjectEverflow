import { useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Dropdown,
  DropdownItem,
  DropdownList,
  Grid,
  GridItem,
  Label,
  MenuToggle,
  Modal,
  ModalVariant,
  TextInput,
  TextArea,
} from '@patternfly/react-core';
import { EllipsisVIcon } from '@patternfly/react-icons';
import { Building2, FolderKanban, Users } from 'lucide-react';

import { toast } from '@/hooks/use-toast';
import { deleteOrganization, updateOrganization } from '@/lib/api';
import { buildOrganizationSettingsPath } from '@/lib/organizationPaths';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

const OrganizationDetail = () => {
  const { selectedOrganization, projects, projectsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isActionsOpen, setIsActionsOpen] = useState(false);
  const [formState, setFormState] = useState({ name: '', description: '' });

  const updateMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => updateOrganization(selectedOrganization!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      toast({ title: 'Organization updated', description: 'Organization details were saved.' });
      setIsEditOpen(false);
    },
    onError: (error) => {
      toast({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Unable to update the organization.',
        variant: 'destructive',
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrganization(selectedOrganization!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizations'] });
      toast({ title: 'Organization deleted', description: 'The organization was removed.' });
      navigate('/organizations');
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: error instanceof Error ? error.message : 'Unable to delete the organization.',
        variant: 'destructive',
      });
    },
  });

  if (!selectedOrganization) {
    return (
      <Card>
        <CardTitle>Organization not found</CardTitle>
        <CardBody>Select an organization from the hierarchy to continue.</CardBody>
      </Card>
    );
  }

  const openEditDialog = () => {
    setFormState({
      name: selectedOrganization.name,
      description: selectedOrganization.description || '',
    });
    setIsEditOpen(true);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardTitle>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.5rem' }}>
              <Building2 size={20} />
              {selectedOrganization.name}
            </div>
            {/* Kebab actions menu */}
            <Dropdown
              isOpen={isActionsOpen}
              onSelect={() => setIsActionsOpen(false)}
              onOpenChange={setIsActionsOpen}
              toggle={(toggleRef) => (
                <MenuToggle
                  ref={toggleRef}
                  aria-label="Organization actions"
                  variant="plain"
                  onClick={() => setIsActionsOpen(!isActionsOpen)}
                  isExpanded={isActionsOpen}
                >
                  <EllipsisVIcon />
                </MenuToggle>
              )}
            >
              <DropdownList>
                <DropdownItem key="edit" onClick={openEditDialog}>
                  Edit organization
                </DropdownItem>
                <DropdownItem key="connections" onClick={() => navigate(buildOrganizationSettingsPath(selectedOrganization.id))}>
                  Git connections
                </DropdownItem>
                <DropdownItem key="delete" isDanger onClick={() => setIsDeleteOpen(true)}>
                  Delete organization
                </DropdownItem>
              </DropdownList>
            </Dropdown>
          </div>
          <div style={{ fontSize: '0.875rem', fontWeight: 400, color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
            {selectedOrganization.description || 'This organization does not have a description yet.'}
          </div>
        </CardTitle>
        <CardBody>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            <Label variant="outline">Role: {selectedOrganization.user_role ?? 'viewer'}</Label>
            <Label variant="outline">Projects: {selectedOrganization.project_count}</Label>
            <Label variant="outline">Members: {selectedOrganization.member_count}</Label>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardTitle>Projects in organization</CardTitle>
        <CardBody>
          <p style={{ marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Projects are now the first child resource under the organization.
          </p>
          <Grid hasGutter>
            {projectsLoading ? (
              <GridItem><p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>Loading projects...</p></GridItem>
            ) : projects.length === 0 ? (
              <GridItem><p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>No projects exist in this organization yet.</p></GridItem>
            ) : (
              projects.map((project) => (
                <GridItem key={project.id} sm={6}>
                  <button
                    type="button"
                    onClick={() => navigate(`/organizations/${selectedOrganization.id}/projects/${project.id}`)}
                    style={{ width: '100%', textAlign: 'left', background: 'none', border: '1px solid var(--pf-v6-global--BorderColor--100)', borderRadius: '8px', padding: '1.25rem', cursor: 'pointer', transition: 'border-color 0.15s' }}
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem' }}>
                      <div>
                        <div style={{ fontSize: '1.125rem', fontWeight: 600 }}>{project.name}</div>
                        <div style={{ marginTop: '0.25rem', fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>{project.description || 'No project description yet.'}</div>
                      </div>
                      <Label variant="outline">{project.status.replace(/_/g, ' ')}</Label>
                    </div>
                    <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', background: 'var(--pf-v6-global--BackgroundColor--200)', padding: '0.25rem 0.5rem', borderRadius: '9999px' }}>
                        <Users size={14} />
                        {project.contributors.length + 1} contributors
                      </span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', background: 'var(--pf-v6-global--BackgroundColor--200)', padding: '0.25rem 0.5rem', borderRadius: '9999px' }}>
                        <FolderKanban size={14} />
                        Open project
                      </span>
                    </div>
                  </button>
                </GridItem>
              ))
            )}
          </Grid>
        </CardBody>
      </Card>

      {/* Edit Organization Modal */}
      <Modal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        title="Edit organization"
        description="Update the organization details shown in the hierarchy."
        variant={ModalVariant.small}
        actions={[
          <Button
            key="save"
            variant="primary"
            onClick={() => updateMutation.mutate({ name: formState.name.trim(), description: formState.description.trim() })}
            isDisabled={!formState.name.trim() || updateMutation.isPending}
            isLoading={updateMutation.isPending}
          >
            Save changes
          </Button>,
          <Button key="cancel" variant="link" onClick={() => setIsEditOpen(false)} isDisabled={updateMutation.isPending}>
            Cancel
          </Button>,
        ]}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <TextInput
            id="org-name"
            placeholder="Organization name"
            value={formState.name}
            onChange={(_evt, value) => setFormState((current) => ({ ...current, name: value }))}
          />
          <TextArea
            id="org-description"
            placeholder="Describe the organization"
            value={formState.description}
            onChange={(_evt, value) => setFormState((current) => ({ ...current, description: value }))}
          />
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteOpen}
        onClose={() => setIsDeleteOpen(false)}
        title="Delete organization"
        variant={ModalVariant.small}
        actions={[
          <Button
            key="delete"
            variant="danger"
            onClick={() => deleteMutation.mutate()}
            isDisabled={deleteMutation.isPending}
            isLoading={deleteMutation.isPending}
          >
            Delete organization
          </Button>,
          <Button key="cancel" variant="link" onClick={() => setIsDeleteOpen(false)} isDisabled={deleteMutation.isPending}>
            Cancel
          </Button>,
        ]}
      >
        <p>Delete <strong>{selectedOrganization.name}</strong>? This removes the organization from the hierarchy and returns you to the organizations overview.</p>
      </Modal>
    </div>
  );
};

export default OrganizationDetail;