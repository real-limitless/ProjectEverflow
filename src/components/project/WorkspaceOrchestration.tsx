import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Dropdown, DropdownList, DropdownItem, MenuToggle } from '@patternfly/react-core';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/use-toast';
import { getProjectServices, ensureWorkspace, stopWorkspace, restartWorkspace, startAllServices, stopAllServices, Project, ProjectService } from '@/lib/api';
import { Play, Pause, RotateCw, Container, AlertCircle, CheckCircle, Clock, PlayCircle, StopCircle } from 'lucide-react';

interface WorkspaceOrchestrationProps {
  project: Project;
  showStatusSummary?: boolean;
}

type ServiceStatus = 'running' | 'stopped' | 'building' | 'error' | 'unknown';

export const WorkspaceOrchestration = ({ project, showStatusSummary = true }: WorkspaceOrchestrationProps) => {
  const queryClient = useQueryClient();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  
  // Fetch all project services
  const { data: servicesResponse, isLoading } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: () => getProjectServices(project.id),
    refetchInterval: autoRefresh ? 5000 : false,
  });

  const services = servicesResponse?.data || [];
  const aiWorkspace = services.find(s => s.service_type === 'ai-workspace');

  // Ensure workspace mutation
  const ensureWorkspaceMutation = useMutation({
    mutationFn: () => ensureWorkspace(project.id),
    onSuccess: () => {
      toast({
        title: "Workspace Started",
        description: "AI workspace is starting up.",
      });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to start workspace.",
        variant: "destructive",
      });
    },
  });

  // Stop workspace mutation
  const stopWorkspaceMutation = useMutation({
    mutationFn: () => stopWorkspace(project.id),
    onSuccess: () => {
      toast({
        title: "Workspace Stopped",
        description: "AI workspace has been stopped.",
      });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to stop workspace.",
        variant: "destructive",
      });
    },
  });

  // Restart workspace mutation
  const restartWorkspaceMutation = useMutation({
    mutationFn: () => restartWorkspace(project.id),
    onSuccess: () => {
      toast({
        title: "Workspace Restarted",
        description: "AI workspace is restarting.",
      });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to restart workspace.",
        variant: "destructive",
      });
    },
  });

  // Start all services mutation
  const startAllServicesMutation = useMutation({
    mutationFn: () => startAllServices(project.id),
    onSuccess: (response) => {
      const started = response.data?.started || [];
      toast({
        title: "Services Started",
        description: `Started ${started.length} service(s)`,
      });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to start services.",
        variant: "destructive",
      });
    },
  });

  // Stop all services mutation
  const stopAllServicesMutation = useMutation({
    mutationFn: () => stopAllServices(project.id),
    onSuccess: (response) => {
      const stopped = response.data?.stopped || [];
      toast({
        title: "Services Stopped",
        description: `Stopped ${stopped.length} service(s)`,
      });
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error?.message || "Failed to stop services.",
        variant: "destructive",
      });
    },
  });

  const getStatusColor = (status: ServiceStatus): 'default' | 'secondary' | 'destructive' | 'outline' => {
    switch (status) {
      case 'running':
        return 'secondary';
      case 'stopped':
        return 'outline';
      case 'building':
        return 'secondary';
      case 'error':
        return 'destructive';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status: ServiceStatus) => {
    switch (status) {
      case 'running':
        return <CheckCircle className="h-3 w-3" />;
      case 'stopped':
        return <Pause className="h-3 w-3" />;
      case 'building':
        return <Clock className="h-3 w-3" />;
      case 'error':
        return <AlertCircle className="h-3 w-3" />;
      default:
        return <AlertCircle className="h-3 w-3" />;
    }
  };

  const getStatusText = (status: ServiceStatus): string => {
    switch (status) {
      case 'running':
        return 'Active';
      case 'stopped':
        return 'Inactive';
      case 'building':
        return 'Starting';
      case 'error':
        return 'Error';
      default:
        return 'Unknown';
    }
  };

  const aiWorkspaceStatus = (aiWorkspace?.status || 'unknown') as ServiceStatus;
  const composeServices = services.filter(s => s.service_type !== 'ai-workspace');
  const runningComposeServices = composeServices.filter(s => s.status === 'running');
  const stoppedComposeServices = composeServices.filter(s => s.status === 'stopped');

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      {/* Service Status Display */}
      {showStatusSummary && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {aiWorkspace && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Container className="h-4 w-4" style={{ color: 'var(--pf-v6-global--Color--200)' }} />
              {aiWorkspace.container_name && (
                <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--pf-v6-global--Color--200)', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={aiWorkspace.container_name}>
                  {aiWorkspace.container_name}
                </span>
              )}
              <Badge variant={getStatusColor(aiWorkspaceStatus)}>
                {getStatusIcon(aiWorkspaceStatus)}
                {getStatusText(aiWorkspaceStatus)}
              </Badge>
            </div>
          )}
        </div>
      )}

      {/* Workspace Controls Dropdown */}
      <Dropdown
        onSelect={() => setIsDropdownOpen(false)}
        toggle={(toggleRef) => (
          <MenuToggle
            ref={toggleRef}
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            isExpanded={isDropdownOpen}
          >
            Workspace
          </MenuToggle>
        )}
        isOpen={isDropdownOpen}
        popperProps={{ position: 'end' }}
      >
        <DropdownList>
          {/* AI Workspace Service Header */}
          {aiWorkspace ? (
            <>
              <div style={{ padding: '0.75rem 1rem', fontSize: '0.875rem', borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                  <span style={{ fontWeight: 600 }}>AI Workspace</span>
                  <Badge variant={getStatusColor(aiWorkspaceStatus)} className="text-xs">
                    {getStatusIcon(aiWorkspaceStatus)}
                    {getStatusText(aiWorkspaceStatus)}
                  </Badge>
                </div>
                {aiWorkspace.container_name && (
                  <p style={{ fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--pf-v6-global--Color--200)', margin: '0 0 0.25rem 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={aiWorkspace.container_name}>
                    {aiWorkspace.container_name}
                  </p>
                )}
                {aiWorkspace.image && (
                  <p style={{ fontSize: '0.6875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                    Image: {aiWorkspace.image}
                  </p>
                )}
              </div>

              {/* Start/Stop Controls */}
              {(aiWorkspaceStatus === 'stopped' || aiWorkspaceStatus === 'exited' || aiWorkspaceStatus === 'created') ? (
                <DropdownItem
                  onClick={() => ensureWorkspaceMutation.mutate()}
                  icon={<Play className="h-4 w-4" />}
                >
                  Start Workspace
                </DropdownItem>
              ) : (
                <DropdownItem isDisabled icon={<Play className="h-4 w-4" />}>
                  Start Workspace
                </DropdownItem>
              )}
              {aiWorkspaceStatus === 'running' ? (
                <DropdownItem
                  onClick={() => stopWorkspaceMutation.mutate()}
                  icon={<Pause className="h-4 w-4" />}
                >
                  Stop Workspace
                </DropdownItem>
              ) : (
                <DropdownItem isDisabled icon={<Pause className="h-4 w-4" />}>
                  Stop Workspace
                </DropdownItem>
              )}
              {aiWorkspaceStatus === 'running' ? (
                <DropdownItem
                  onClick={() => restartWorkspaceMutation.mutate()}
                  icon={<RotateCw className="h-4 w-4" />}
                >
                  Restart Workspace
                </DropdownItem>
              ) : (
                <DropdownItem isDisabled icon={<RotateCw className="h-4 w-4" />}>
                  Restart Workspace
                </DropdownItem>
              )}
              
              {/* Bulk Service Operations */}
              {composeServices.length > 0 && (
                <>
                  <div style={{ borderTop: '1px solid var(--pf-v6-global--BorderColor--100)', margin: '0.5rem 0' }} />
                  {stoppedComposeServices.length > 0 && (
                    <DropdownItem
                      onClick={() => startAllServicesMutation.mutate()}
                      icon={<PlayCircle className="h-4 w-4" />}
                    >
                      Start All Services ({stoppedComposeServices.length})
                    </DropdownItem>
                  )}
                  {runningComposeServices.length > 0 && (
                    <DropdownItem
                      onClick={() => stopAllServicesMutation.mutate()}
                      icon={<StopCircle className="h-4 w-4" />}
                    >
                      Stop All Services ({runningComposeServices.length})
                    </DropdownItem>
                  )}
                </>
              )}
            </>
          ) : (
            <>
              <DropdownItem
                onClick={() => ensureWorkspaceMutation.mutate()}
                icon={<Play className="h-4 w-4" />}
              >
                Provision Workspace
              </DropdownItem>
            </>
          )}

          {/* Service Status Summary */}
          <div style={{ padding: '0.75rem 1rem', fontSize: '0.75rem', borderTop: '1px solid var(--pf-v6-global--BorderColor--100)', color: 'var(--pf-v6-global--Color--200)' }}>
            {autoRefresh ? '🔄 Auto-refreshing (5s)' : '⏸️ Auto-refresh paused'}
          </div>
        </DropdownList>
      </Dropdown>
    </div>
  );
};
