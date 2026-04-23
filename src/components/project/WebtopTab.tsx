import { useState, useEffect } from 'react';
import { Card, CardBody, Button, Spinner, Alert, AlertVariant, Progress, Modal, ModalVariant } from '@patternfly/react-core';
import { Play, Square, RotateCw, XCircle, Loader2, Trash2, RefreshCw, AlertTriangle, CheckCircle2, Activity } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  ensureWebtop, 
  getProjectServices, 
  startService,
  stopService,
  restartService,
  killService,
  deleteService,
  getWebtopProxyUrl,
  getServiceStats,
  checkServiceSync,
  recreateOrphanedContainer,
  resolveDatabaseInconsistency,
  Project,
  ProjectService,
  ContainerStats,
  SyncCheckResponse
} from '@/lib/api';
import { toast } from '@/hooks/use-toast';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

interface WebtopTabProps {
  project: Project;
}

export const WebtopTab: React.FC<WebtopTabProps> = ({ project }) => {
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const queryClient = useQueryClient();

  // Fetch services for this project
  const { data: servicesResponse, isLoading: servicesLoading, refetch: refetchServices } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: () => getProjectServices(project.id),
    refetchInterval: 5000, // Poll every 5 seconds for status updates
  });

  const services = servicesResponse?.data || [];
  const webtopService = services.find(s => s.name === 'webtop' || s.service_type === 'ai-workspace');

  // Fetch container stats for webtop service
  const { data: statsResponse, refetch: refetchStats } = useQuery({
    queryKey: ['service-stats', webtopService?.id],
    queryFn: () => webtopService ? getServiceStats(webtopService.id) : null,
    enabled: !!webtopService && webtopService.status === 'running',
    refetchInterval: 10000, // Poll every 10 seconds
  });

  // Transform stats response to expected format
  const statsData = statsResponse?.data;
  const stats: ContainerStats | undefined = statsData ? {
    cpu_percent: parseFloat(String(statsData.cpu_percent || '0')),
    memory_percent: parseFloat(String(statsData.memory_percent || '0')),
    disk_percent: undefined,
    timestamp: new Date().toISOString(),
    uptime_seconds: undefined,
  } : undefined;

  // Fetch sync status
  const { data: syncResponse, refetch: refetchSync } = useQuery({
    queryKey: ['service-sync', project.id],
    queryFn: () => checkServiceSync(project.id),
    refetchInterval: 30000, // Poll every 30 seconds
  });

  // Transform sync response to expected format with issues array
  const rawSyncData = syncResponse?.data as SyncCheckResponse | undefined;
  const syncData = rawSyncData ? {
    ...rawSyncData,
    is_synced: rawSyncData.orphaned_count === 0,
    issues: rawSyncData.orphaned?.map(item => ({
      type: 'orphaned_db_record' as const,
      service_id: item.id,
      service_name: item.name,
      container_name: item.container_name,
      details: `Database record exists but container "${item.container_name}" not found`,
    })) || [],
  } : undefined;
  const hasSyncIssues = syncData && !syncData.is_synced && syncData.issues.length > 0;

  // Provision webtop mutation
  const provisionMutation = useMutation({
    mutationFn: () => ensureWebtop(project.id),
    onSuccess: async () => {
      toast({
        title: 'Webtop Provisioned',
        description: 'Your development workspace is ready.',
      });
      // Small delay to ensure database transaction is committed
      await new Promise(resolve => setTimeout(resolve, 500));
      // Explicitly refetch services to ensure UI updates immediately
      await refetchServices();
      setIsProvisioning(false);
    },
    onError: (error: any) => {
      toast({
        title: 'Provisioning Failed',
        description: error.message || 'Failed to provision webtop.',
        variant: 'destructive',
      });
      setIsProvisioning(false);
    },
  });

  // Lifecycle mutations
  const startMutation = useMutation({
    mutationFn: (serviceId: number) => startService(project.id, serviceId),
    onSuccess: () => {
      toast({ title: 'Service Started' });
      refetchServices();
    },
    onError: () => {
      toast({ title: 'Failed to start service', variant: 'destructive' });
    },
  });

  const stopMutation = useMutation({
    mutationFn: (serviceId: number) => stopService(serviceId),
    onSuccess: () => {
      toast({ title: 'Service Stopped' });
      refetchServices();
    },
    onError: () => {
      toast({ title: 'Failed to stop service', variant: 'destructive' });
    },
  });

  const restartMutation = useMutation({
    mutationFn: (serviceId: number) => restartService(serviceId),
    onSuccess: () => {
      toast({ title: 'Service Restarted' });
      refetchServices();
    },
    onError: () => {
      toast({ title: 'Failed to restart service', variant: 'destructive' });
    },
  });

  const killMutation = useMutation({
    mutationFn: (serviceId: number) => killService(serviceId),
    onSuccess: () => {
      toast({ title: 'Service Killed' });
      refetchServices();
    },
    onError: () => {
      toast({ title: 'Failed to kill service', variant: 'destructive' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (serviceId: number) => deleteService(serviceId),
    onSuccess: () => {
      toast({ title: 'Service Deleted' });
      refetchServices();
      setIsDeleteDialogOpen(false);
    },
    onError: () => {
      toast({ title: 'Failed to delete service', variant: 'destructive' });
      setIsDeleteDialogOpen(false);
    },
  });

  // Recovery mutations
  const recreateMutation = useMutation({
    mutationFn: (serviceId: number) => recreateOrphanedContainer(serviceId),
    onSuccess: () => {
      toast({ title: 'Container recreated successfully' });
      refetchServices();
      refetchSync();
      setShowSyncModal(false);
    },
    onError: (error: any) => {
      toast({ 
        title: 'Failed to recreate container', 
        description: error?.message,
        variant: 'destructive' 
      });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: () => resolveDatabaseInconsistency(project.id),
    onSuccess: () => {
      toast({ title: 'Sync issues resolved' });
      refetchServices();
      refetchSync();
      setShowSyncModal(false);
    },
    onError: (error: any) => {
      toast({ 
        title: 'Failed to resolve sync issues', 
        description: error?.message,
        variant: 'destructive' 
      });
    },
  });

  const handleProvision = () => {
    setIsProvisioning(true);
    provisionMutation.mutate();
  };

  const isActionPending = 
    startMutation.isPending || 
    stopMutation.isPending || 
    restartMutation.isPending || 
    killMutation.isPending ||
    deleteMutation.isPending ||
    recreateMutation.isPending ||
    resolveMutation.isPending;

  if (servicesLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="xl" />
        <span className="ml-3">Loading workspace...</span>
      </div>
    );
  }

  if (!webtopService) {
    return (
      <Card>
        <CardBody>
          <div className="text-center py-12">
            <h3 className="text-xl font-semibold mb-4">Webtop Workspace</h3>
            <p className="text-muted-foreground mb-6">
              No webtop workspace has been provisioned for this project yet.
            </p>
            <p className="text-sm text-muted-foreground mb-6">
              Provision a full Fedora KDE desktop environment with all development tools.
            </p>
            <Button
              variant="primary"
              onClick={handleProvision}
              isDisabled={isProvisioning}
            >
              {isProvisioning ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Provisioning...
                </>
              ) : (
                'Provision Webtop Workspace'
              )}
            </Button>
          </div>
        </CardBody>
      </Card>
    );
  }

  const isRunning = webtopService.status === 'running';
  const isStopped = webtopService.status === 'stopped' || webtopService.status === 'exited';
  const proxyUrl = getWebtopProxyUrl(project.id);

  // Helper to render stat gauge
  const renderStatGauge = (label: string, value: number, max: number = 100) => (
    <div className="flex-1">
      <div className="text-sm font-medium text-foreground mb-2">{label}</div>
      <div className="w-full bg-gray-200 rounded-full h-2 mb-1">
        <div
          className={`h-2 rounded-full transition-all ${
            value > 80 ? 'bg-red-500' : value > 60 ? 'bg-yellow-500' : 'bg-green-500'
          }`}
          style={{ width: `${(value / max) * 100}%` }}
        />
      </div>
      <div className="text-xs text-muted-foreground">{value.toFixed(1)}%</div>
    </div>
  );

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Sync Status Alert */}
      {hasSyncIssues && (
        <Card className="border-yellow-300 bg-yellow-50">
          <CardBody>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-yellow-600" />
                <div>
                  <p className="font-semibold text-yellow-900">Sync Issues Detected</p>
                  <p className="text-sm text-yellow-800">
                    {syncData?.issues.length} issue(s) found. Database and containers are out of sync.
                  </p>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowSyncModal(true)}
              >
                View & Fix
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Container Metrics */}
      {isRunning && stats && (
        <Card>
          <CardBody>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-blue-500" />
                <h3 className="font-semibold">Container Metrics</h3>
              </div>
              <Button
                variant="link"
                size="sm"
                onClick={() => refetchStats()}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-4">
              {renderStatGauge('CPU', stats.cpu_percent)}
              {renderStatGauge('Memory', stats.memory_percent)}
              {stats.disk_percent !== undefined && renderStatGauge('Disk', stats.disk_percent)}
            </div>
            <div className="mt-4 text-xs text-muted-foreground">
              Updated: {new Date(stats.timestamp).toLocaleTimeString()}
              {stats.uptime_seconds && ` • Uptime: ${Math.floor(stats.uptime_seconds / 3600)}h ${Math.floor((stats.uptime_seconds % 3600) / 60)}m`}
            </div>
          </CardBody>
        </Card>
      )}
      {/* Control Bar */}
      <Card isCompact className="mb-4">
        <CardBody>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <div
                  className={`h-3 w-3 rounded-full ${
                    isRunning ? 'bg-green-500' : isStopped ? 'bg-gray-400' : 'bg-yellow-500'
                  }`}
                />
                <span className="font-medium">Status:</span>
                <span className="capitalize">{webtopService.status}</span>
              </div>
              {webtopService.last_started_at && (
                <div className="text-sm text-muted-foreground">
                  Started: {new Date(webtopService.last_started_at).toLocaleString()}
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                variant="secondary"
                icon={<Play size={16} />}
                onClick={() => startMutation.mutate(webtopService.id)}
                isDisabled={isRunning || isActionPending}
              >
                Start
              </Button>
              <Button
                variant="secondary"
                icon={<Square size={16} />}
                onClick={() => stopMutation.mutate(webtopService.id)}
                isDisabled={isStopped || isActionPending}
              >
                Stop
              </Button>
              <Button
                variant="secondary"
                icon={<RotateCw size={16} />}
                onClick={() => restartMutation.mutate(webtopService.id)}
                isDisabled={isActionPending}
              >
                Restart
              </Button>
              <Button
                variant="danger"
                icon={<XCircle size={16} />}
                onClick={() => killMutation.mutate(webtopService.id)}
                isDisabled={isStopped || isActionPending}
              >
                Kill
              </Button>
              <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="danger"
                    icon={<Trash2 size={16} />}
                    isDisabled={isActionPending}
                  >
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Webtop Container</AlertDialogTitle>
                    <AlertDialogDescription>
                      Are you sure you want to delete the webtop container? This action cannot be undone and will remove all unsaved data in the workspace.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => deleteMutation.mutate(webtopService.id)}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Webtop Iframe */}
      {isRunning ? (
        <Card className="flex-1">
          <CardBody style={{ padding: 0, height: '100%' }}>
            <iframe
              src={proxyUrl}
              className="w-full h-full border-0"
              title="Webtop Workspace"
              style={{ minHeight: '600px' }}
              allow="screen-wake-lock; fullscreen; clipboard-read; clipboard-write"
            />
          </CardBody>
        </Card>
      ) : (
        <Card className="flex-1">
          <CardBody>
            <div className="flex items-center justify-center h-full">
              <Alert
                variant={AlertVariant.info}
                title="Workspace Not Running"
              >
                <p>The webtop workspace is currently stopped. Click "Start" to launch it.</p>
              </Alert>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Sync Issues Modal */}
      <Modal
        isOpen={showSyncModal}
        onClose={() => setShowSyncModal(false)}
        title="Database Sync Issues"
        variant={ModalVariant.medium}
      >
        <div className="space-y-4">
          {syncData?.issues && syncData.issues.length > 0 ? (
            <>
              <p className="text-sm text-muted-foreground">
                The following inconsistencies were detected between the database and actual containers:
              </p>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {syncData.issues.map((issue, idx) => (
                  <div key={idx} className="p-3 border border-red-200 bg-red-50 rounded-md">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="font-medium text-red-900">
                          {issue.type === 'orphaned_db_record' && 'Orphaned Database Record'}
                          {issue.type === 'missing_db_record' && 'Missing Database Record'}
                          {issue.type === 'status_mismatch' && 'Status Mismatch'}
                        </p>
                        <p className="text-sm text-red-800">{issue.details}</p>
                        {issue.service_name && (
                          <p className="text-xs text-red-700 mt-1">
                            Service: <code>{issue.service_name}</code> ({issue.container_name})
                          </p>
                        )}
                        {issue.type === 'orphaned_db_record' && (
                          <Button
                            variant="secondary"
                            size="sm"
                            className="mt-2"
                            isDisabled={recreateMutation.isPending}
                            onClick={() => issue.service_id && recreateMutation.mutate(issue.service_id)}
                          >
                            {recreateMutation.isPending ? (
                              <>
                                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                                Recreating...
                              </>
                            ) : (
                              'Recreate Container'
                            )}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 justify-end pt-4">
                <Button
                  variant="secondary"
                  onClick={() => setShowSyncModal(false)}
                  isDisabled={resolveMutation.isPending}
                >
                  Close
                </Button>
                <Button
                  variant="primary"
                  onClick={() => resolveMutation.mutate()}
                  isDisabled={resolveMutation.isPending}
                >
                  {resolveMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Resolving...
                    </>
                  ) : (
                    'Resolve All Issues'
                  )}
                </Button>
              </div>
            </>
          ) : (
            <div className="text-center py-6">
              <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto mb-2" />
              <p className="font-semibold text-green-900">All Systems Synced</p>
              <p className="text-sm text-muted-foreground">No sync issues detected.</p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};
