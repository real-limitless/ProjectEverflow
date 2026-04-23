import React, { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  AlertVariant,
  Button,
  Modal,
  ModalVariant,
  Checkbox,
  Text,
  TextContent,
  TextVariants,
  List,
  ListItem,
} from '@patternfly/react-core';
import { ExclamationTriangleIcon, SyncAltIcon } from '@patternfly/react-icons';
import { apiCall } from '../../lib/api';
import { ProvisioningLogViewer } from './ProvisioningLogViewer';

interface ContainerHealthStatus {
  healthy: boolean;
  missing_services: string[];
  total_services: number;
  message: string;
}

interface ContainerHealthWarningProps {
  projectId: number;
  pollingInterval?: number; // milliseconds, default 30000 (30s)
}

export const ContainerHealthWarning: React.FC<ContainerHealthWarningProps> = ({
  projectId,
  pollingInterval = 30000,
}) => {
  const [isReprovisionModalOpen, setIsReprovisionModalOpen] = useState(false);
  const [wipeVolumes, setWipeVolumes] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const queryClient = useQueryClient();

  // Check container health
  const { data: healthStatus, refetch } = useQuery<ContainerHealthStatus>({
    queryKey: ['containerHealth', projectId],
    queryFn: async () => {
      const response = await apiCall(`/projects/${projectId}/check-containers/`, {
        method: 'GET',
      });
      return response.data;
    },
    refetchInterval: pollingInterval,
    retry: 1,
  });

  // Reprovision mutation
  const reprovisionMutation = useMutation({
    mutationFn: async () => {
      const response = await apiCall(`/projects/${projectId}/reprovision/?wipe_volumes=${wipeVolumes}`, {
        method: 'POST',
      });
      return response.data;
    },
    onSuccess: () => {
      setIsReprovisionModalOpen(false);
      setShowLogs(true);
      // Refetch health status after a delay
      setTimeout(() => {
        refetch();
        queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      }, 5000);
    },
  });

  const handleReprovision = () => {
    reprovisionMutation.mutate();
  };

  const handleOpenModal = () => {
    setWipeVolumes(false);
    setIsReprovisionModalOpen(true);
  };

  // Don't show warning if containers are healthy
  if (!healthStatus || healthStatus.healthy) {
    return null;
  }

  return (
    <>
      <Alert
        variant={AlertVariant.warning}
        title="Container Health Issue Detected"
        actionLinks={
          <>
            <Button variant="link" onClick={handleOpenModal} icon={<SyncAltIcon />}>
              Recreate Containers
            </Button>
          </>
        }
        isInline
        className="mb-4"
      >
        <TextContent>
          <Text component={TextVariants.p}>{healthStatus.message}</Text>
          {healthStatus.missing_services.length > 0 && (
            <>
              <Text component={TextVariants.p} className="mt-2">
                Missing services:
              </Text>
              <List isPlain>
                {healthStatus.missing_services.map((service) => (
                  <ListItem key={service}>• {service}</ListItem>
                ))}
              </List>
            </>
          )}
        </TextContent>
      </Alert>

      {/* Reprovisioning Modal */}
      <Modal
        variant={ModalVariant.medium}
        title="Recreate Project Containers"
        isOpen={isReprovisionModalOpen}
        onClose={() => setIsReprovisionModalOpen(false)}
        actions={[
          <Button
            key="confirm"
            variant="danger"
            onClick={handleReprovision}
            isLoading={reprovisionMutation.isPending}
            isDisabled={reprovisionMutation.isPending}
          >
            {wipeVolumes ? 'Recreate & Wipe Volumes' : 'Recreate Containers'}
          </Button>,
          <Button
            key="cancel"
            variant="link"
            onClick={() => setIsReprovisionModalOpen(false)}
            isDisabled={reprovisionMutation.isPending}
          >
            Cancel
          </Button>,
        ]}
      >
        <TextContent className="space-y-4">
          <Text component={TextVariants.p}>
            This will delete and recreate all project containers based on your{' '}
            <code>everflow-compose.yml</code> file.
          </Text>

          <Text component={TextVariants.p} className="font-semibold">
            What will happen:
          </Text>
          <List>
            <ListItem>Stop all running services</ListItem>
            <ListItem>Delete the project pod and all service containers</ListItem>
            <ListItem>Recreate the pod with fresh containers</ListItem>
            <ListItem>Re-provision services from compose file</ListItem>
          </List>

          <Checkbox
            id="wipe-volumes-checkbox"
            label="Wipe volumes for clean slate (WARNING: This will delete all data including workspace files!)"
            isChecked={wipeVolumes}
            onChange={(_event, checked) => setWipeVolumes(checked)}
            className="mt-4"
          />

          {wipeVolumes && (
            <Alert
              variant={AlertVariant.danger}
              title="Data Loss Warning"
              isInline
              className="mt-2"
            >
              <Text component={TextVariants.p}>
                Wiping volumes will permanently delete:
              </Text>
              <List>
                <ListItem>All workspace files (uncommitted code changes)</ListItem>
                <ListItem>Database data</ListItem>
                <ListItem>Any other persisted data in volumes</ListItem>
              </List>
              <Text component={TextVariants.p} className="mt-2 font-semibold">
                Make sure you've committed and pushed your code!
              </Text>
            </Alert>
          )}

          {reprovisionMutation.isError && (
            <Alert
              variant={AlertVariant.danger}
              title="Reprovisioning Failed"
              isInline
              className="mt-4"
            >
              {reprovisionMutation.error?.message || 'An error occurred during reprovisioning'}
            </Alert>
          )}
        </TextContent>
      </Modal>

      {/* Provisioning Logs Modal */}
      {showLogs && (
        <Modal
          variant={ModalVariant.large}
          title="Reprovisioning Progress"
          isOpen={showLogs}
          onClose={() => setShowLogs(false)}
          actions={[
            <Button key="close" variant="primary" onClick={() => setShowLogs(false)}>
              Close
            </Button>,
          ]}
        >
          <ProvisioningLogViewer
            projectId={projectId}
            autoConnect={true}
            onComplete={() => {
              // Auto-close after 2 seconds on completion
              setTimeout(() => setShowLogs(false), 2000);
            }}
          />
        </Modal>
      )}
    </>
  );
};

export default ContainerHealthWarning;
