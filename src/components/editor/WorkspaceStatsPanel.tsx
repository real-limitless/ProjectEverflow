import { useQuery } from '@tanstack/react-query';
import { Card, CardBody } from '@patternfly/react-core';
import { Loader2, AlertCircle, Cpu, HardDrive, Wifi, Activity, Container, Network } from 'lucide-react';
import { Project, getProjectServices, getServiceStats, getServiceProcesses, ProjectService, ProcessInfo } from '@/lib/api';

interface WorkspaceStatsPanelProps {
  project: Project;
}

interface ContainerStats {
  status: string;
  running: boolean;
  cpu_percent: number;
  memory_percent: number;
  memory_used: string;
  block_input: string;
  block_output: string;
  net_input: string;
  net_output: string;
  pids: number;
  container_name: string;
}

export const WorkspaceStatsPanel: React.FC<WorkspaceStatsPanelProps> = ({ project }) => {
  // First fetch services to get the webtop service ID
  const { data: servicesResponse } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: () => getProjectServices(project.id),
    refetchInterval: 10000,
  });

  const services = servicesResponse?.data || [];
  const webtopService = services.find((s: ProjectService) => s.service_type === 'ai-workspace' || s.name === 'webtop');
  const isRunning = webtopService?.status === 'running';

  // Fetch container stats using the correct API
  const { data: statsResponse, isLoading, error } = useQuery({
    queryKey: ['service-stats', webtopService?.id],
    queryFn: async () => {
      if (!webtopService?.id) return null;
      const response = await getServiceStats(webtopService.id);
      return response.data;
    },
    enabled: !!webtopService?.id,
    refetchInterval: isRunning ? 3000 : 10000,
    retry: 1,
  });

  // Fetch live process list
  const { data: processesResponse } = useQuery({
    queryKey: ['service-processes', webtopService?.id],
    queryFn: async () => {
      if (!webtopService?.id) return null;
      const response = await getServiceProcesses(webtopService.id);
      return response.data;
    },
    enabled: !!webtopService?.id && isRunning,
    refetchInterval: 5000,
    retry: 1,
  });

  const processes: ProcessInfo[] = processesResponse?.processes || [];

  // Transform API response to expected format
  const stats: ContainerStats | null = statsResponse ? {
    status: statsResponse.status || 'unknown',
    running: isRunning || false,
    cpu_percent: parseFloat(String(statsResponse.cpu_percent || '0')),
    memory_percent: parseFloat(String(statsResponse.memory_percent || '0')),
    memory_used: statsResponse.memory_used || '0B',
    block_input: statsResponse.block_input || '0B',
    block_output: statsResponse.block_output || '0B',
    net_input: (statsResponse as any).net_input || '0B',
    net_output: (statsResponse as any).net_output || '0B',
    pids: statsResponse.pids || 0,
    container_name: statsResponse.container_name || webtopService?.container_name || '',
  } : null;

  if (isLoading) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
        flexDirection: 'column',
        gap: '1rem',
      }}>
        <Loader2 size={32} style={{ animation: 'spin 2s linear infinite', opacity: 0.7 }} />
        <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          Loading Stats
        </p>
      </div>
    );
  }

  // No workspace service found
  if (!webtopService) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
        flexDirection: 'column',
        gap: '1rem',
      }}>
        <AlertCircle size={32} style={{ opacity: 0.5 }} />
        <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          No Workspace Found
        </p>
        <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          Provision a workspace to view stats
        </p>
      </div>
    );
  }

  // Workspace not running
  if (!isRunning) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
        flexDirection: 'column',
        gap: '1rem',
      }}>
        <AlertCircle size={32} style={{ opacity: 0.5 }} />
        <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          Workspace Not Running
        </p>
        <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          Start the workspace to view live stats
        </p>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
        flexDirection: 'column',
        gap: '1rem',
      }}>
        <AlertCircle size={32} style={{ opacity: 0.5 }} />
        <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
          Unable to Load Stats
        </p>
      </div>
    );
  }

  const getStatusColor = (percent: number) => {
    if (percent < 50) return '#22c55e'; // green
    if (percent < 80) return '#eab308'; // yellow
    return '#ef4444'; // red
  };

  const statusBgColor = stats.running ? '#dbeafe' : '#fee2e2';
  const statusTextColor = stats.running ? '#0c4a6e' : '#7f1d1d';

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      gap: '0.75rem',
      padding: '0.75rem',
      overflow: 'auto',
      backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
    }}>
      {/* Status Card — Shows container name prominently */}
      <Card>
        <CardBody style={{ padding: '0.75rem' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <Container size={16} style={{ color: 'var(--pf-v6-global--Color--300)', flexShrink: 0 }} />
                <p style={{
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  color: 'var(--pf-v6-global--Color--100)',
                  margin: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {stats.container_name || webtopService?.container_name || 'Unknown'}
                </p>
              </div>
              <p style={{ fontSize: '0.6875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                AI Workspace Container
              </p>
            </div>
            <div style={{
              padding: '0.25rem 0.75rem',
              borderRadius: '999px',
              backgroundColor: statusBgColor,
              color: statusTextColor,
              fontWeight: 600,
              fontSize: '0.75rem',
              flexShrink: 0,
            }}>
              {stats.running ? '● Active' : '● Inactive'}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Stats Grid */}
      {stats.running && (
        <>
          {/* CPU & Memory side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            {/* CPU Usage */}
            <Card>
              <CardBody style={{ padding: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <Cpu size={14} style={{ color: 'var(--pf-v6-global--Color--300)' }} />
                  <p style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                    CPU
                  </p>
                </div>
                <span style={{
                  fontSize: '1.5rem',
                  fontWeight: 700,
                  color: getStatusColor(stats.cpu_percent),
                  display: 'block',
                  marginBottom: '0.5rem',
                }}>
                  {stats.cpu_percent.toFixed(1)}%
                </span>
                <div style={{
                  width: '100%',
                  height: '6px',
                  backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
                  borderRadius: '3px',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(stats.cpu_percent, 100)}%`,
                    backgroundColor: getStatusColor(stats.cpu_percent),
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              </CardBody>
            </Card>

            {/* Memory Usage */}
            <Card>
              <CardBody style={{ padding: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <HardDrive size={14} style={{ color: 'var(--pf-v6-global--Color--300)' }} />
                  <p style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                    Memory
                  </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.25rem', marginBottom: '0.5rem' }}>
                  <span style={{
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    color: getStatusColor(stats.memory_percent),
                  }}>
                    {stats.memory_percent.toFixed(1)}%
                  </span>
                  <span style={{ fontSize: '0.6875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                    ({stats.memory_used})
                  </span>
                </div>
                <div style={{
                  width: '100%',
                  height: '6px',
                  backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
                  borderRadius: '3px',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(stats.memory_percent, 100)}%`,
                    backgroundColor: getStatusColor(stats.memory_percent),
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              </CardBody>
            </Card>
          </div>

          {/* I/O & Network Info */}
          <Card>
            <CardBody style={{ padding: '0.75rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                {/* Disk I/O */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <Activity size={14} style={{ color: 'var(--pf-v6-global--Color--300)' }} />
                    <p style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                      Disk I/O
                    </p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>Read:</span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{stats.block_input}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>Write:</span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{stats.block_output}</span>
                    </div>
                  </div>
                </div>

                {/* Network I/O */}
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <Wifi size={14} style={{ color: 'var(--pf-v6-global--Color--300)' }} />
                    <p style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                      Network
                    </p>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>In:</span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{stats.net_input}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>Out:</span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{stats.net_output}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* PIDs count */}
              <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--pf-v6-global--BorderColor--100)', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>Processes:</span>
                <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{stats.pids}</span>
              </div>
            </CardBody>
          </Card>

          {/* Live Process List (htop-style) */}
          <Card>
            <CardBody style={{ padding: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <Activity size={14} style={{ color: 'var(--pf-v6-global--Color--300)' }} />
                <p style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                  Running Processes
                </p>
                <span style={{ fontSize: '0.625rem', color: 'var(--pf-v6-global--Color--200)', marginLeft: 'auto' }}>
                  Refreshes every 5s
                </span>
              </div>
              {processes.length > 0 ? (
                <div style={{ overflow: 'auto', maxHeight: '250px' }}>
                  <table style={{ width: '100%', fontSize: '0.6875rem', borderCollapse: 'collapse', fontFamily: 'monospace' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)' }}>
                        <th style={{ textAlign: 'left', padding: '0.25rem 0.5rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', position: 'sticky', top: 0, backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>PID</th>
                        <th style={{ textAlign: 'left', padding: '0.25rem 0.5rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', position: 'sticky', top: 0, backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>USER</th>
                        <th style={{ textAlign: 'right', padding: '0.25rem 0.5rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', position: 'sticky', top: 0, backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>CPU%</th>
                        <th style={{ textAlign: 'right', padding: '0.25rem 0.5rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', position: 'sticky', top: 0, backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>MEM%</th>
                        <th style={{ textAlign: 'left', padding: '0.25rem 0.5rem', fontWeight: 600, color: 'var(--pf-v6-global--Color--200)', position: 'sticky', top: 0, backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)' }}>COMMAND</th>
                      </tr>
                    </thead>
                    <tbody>
                      {processes.map((proc, idx) => {
                        const cpuVal = parseFloat(proc.cpu || '0');
                        const memVal = parseFloat(proc.mem || '0');
                        return (
                          <tr
                            key={`${proc.pid}-${idx}`}
                            style={{
                              borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
                              backgroundColor: cpuVal > 10 || memVal > 10 ? 'rgba(239, 68, 68, 0.05)' : 'transparent',
                            }}
                          >
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--pf-v6-global--Color--200)' }}>{proc.pid}</td>
                            <td style={{ padding: '0.2rem 0.5rem' }}>{proc.user}</td>
                            <td style={{ padding: '0.2rem 0.5rem', textAlign: 'right', color: cpuVal > 50 ? '#ef4444' : cpuVal > 10 ? '#eab308' : 'inherit' }}>{proc.cpu}</td>
                            <td style={{ padding: '0.2rem 0.5rem', textAlign: 'right', color: memVal > 50 ? '#ef4444' : memVal > 10 ? '#eab308' : 'inherit' }}>{proc.mem}</td>
                            <td style={{
                              padding: '0.2rem 0.5rem',
                              maxWidth: '200px',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }} title={proc.command}>{proc.command}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p style={{ fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)', textAlign: 'center', padding: '1rem 0' }}>
                  No process data available
                </p>
              )}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
};
