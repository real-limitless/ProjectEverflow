import { useState, useEffect } from 'react';
import {
  Card,
  CardBody,
  CardTitle,
  Button,
  Select,
  SelectOption,
  MenuToggle,
  Spinner,
  TextInput,
} from '@patternfly/react-core';
import { SyncAltIcon, DownloadIcon } from '@patternfly/react-icons';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useQuery } from '@tanstack/react-query';
import { getProjectServices, getServiceLogs, Project, ProjectService } from '@/lib/api';
import { toast } from '@/hooks/use-toast';

interface ContainerLogsTabProps {
  project: Project;
}

export const ContainerLogsTab: React.FC<ContainerLogsTabProps> = ({ project }) => {
  const [selectedServiceId, setSelectedServiceId] = useState<number | null>(null);
  const [isServiceSelectOpen, setIsServiceSelectOpen] = useState(false);
  const [tail, setTail] = useState('1000');
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Fetch services
  const { data: servicesResponse, isLoading: servicesLoading } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: () => getProjectServices(project.id),
  });

  const services = servicesResponse?.data || [];

  // Auto-select first service
  useEffect(() => {
    if (services.length > 0 && !selectedServiceId) {
      setSelectedServiceId(services[0].id);
    }
  }, [services, selectedServiceId]);

  // Fetch logs for selected service
  const {
    data: logsResponse,
    isLoading: logsLoading,
    refetch: refetchLogs,
  } = useQuery({
    queryKey: ['service-logs', selectedServiceId, tail],
    queryFn: () => getServiceLogs(selectedServiceId!, { tail: parseInt(tail) || 1000 }),
    enabled: !!selectedServiceId,
    refetchInterval: autoRefresh ? 3000 : false, // Auto-refresh every 3 seconds if enabled
  });

  const logs = logsResponse?.data?.logs || '';
  const truncated = logsResponse?.data?.truncated || false;

  const selectedService = services.find(s => s.id === selectedServiceId);

  const handleDownloadLogs = () => {
    if (!logs) return;

    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedService?.name || 'service'}-logs-${new Date().toISOString()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast({
      title: 'Logs Downloaded',
      description: 'Log file has been downloaded.',
    });
  };

  if (servicesLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="xl" />
        <span className="ml-3">Loading services...</span>
      </div>
    );
  }

  if (services.length === 0) {
    return (
      <Card>
        <CardBody>
          <div className="text-center py-12">
            <p className="text-muted-foreground">No services found for this project.</p>
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Controls */}
      <Card isCompact>
        <CardBody>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Service:</label>
              <Select
                isOpen={isServiceSelectOpen}
                selected={selectedServiceId?.toString()}
                onSelect={(_, value) => {
                  setSelectedServiceId(parseInt(value as string));
                  setIsServiceSelectOpen(false);
                }}
                onOpenChange={setIsServiceSelectOpen}
                toggle={toggleRef => (
                  <MenuToggle
                    ref={toggleRef}
                    onClick={() => setIsServiceSelectOpen(prev => !prev)}
                    isExpanded={isServiceSelectOpen}
                  >
                    {selectedService?.name || 'Select service'}
                  </MenuToggle>
                )}
              >
                {services.map(service => (
                  <SelectOption key={service.id} value={service.id.toString()}>
                    {service.name} ({service.service_type})
                  </SelectOption>
                ))}
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Tail:</label>
              <TextInput
                type="number"
                value={tail}
                onChange={(_, value) => setTail(value)}
                style={{ width: '100px' }}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto-refresh"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
                className="h-4 w-4"
              />
              <label htmlFor="auto-refresh" className="text-sm font-medium cursor-pointer">
                Auto-refresh
              </label>
            </div>

            <div className="ml-auto flex gap-2">
              <Button
                variant="secondary"
                icon={<SyncAltIcon />}
                onClick={() => refetchLogs()}
                isDisabled={logsLoading}
              >
                Refresh
              </Button>
              <Button
                variant="secondary"
                icon={<DownloadIcon />}
                onClick={handleDownloadLogs}
                isDisabled={!logs}
              >
                Download
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Logs Display */}
      <Card className="flex-1">
        <CardBody>
          <CardTitle>Container Logs</CardTitle>
          {truncated && (
            <div className="mb-2 text-sm text-yellow-600">
              ⚠️ Logs truncated. Showing last {tail} lines.
            </div>
          )}
          {logsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner size="lg" />
              <span className="ml-3">Loading logs...</span>
            </div>
          ) : (
            <ScrollArea className="h-[600px] w-full">
              <pre className="text-xs font-mono bg-black text-green-400 p-4 rounded whitespace-pre-wrap break-words">
                {logs || 'No logs available'}
              </pre>
            </ScrollArea>
          )}
        </CardBody>
      </Card>
    </div>
  );
};
