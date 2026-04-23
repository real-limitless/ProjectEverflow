import { useState, useRef, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Page, PageSection, Card, CardBody, CardTitle, Button, Tabs, Tab, TabTitleText, Grid, GridItem } from '@patternfly/react-core';
import { ArrowLeftIcon, CompressIcon, ExpandIcon } from '@patternfly/react-icons';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { toast } from '@/hooks/use-toast';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Checkbox } from '@/components/ui/checkbox';
import complianceData from '@/data/complianceChecks.json';

import { Settings, Plus, Trash2 } from 'lucide-react';
import { Tabs as UITabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import editApplicationData from '@/data/editApplicationData.json';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { FileTree } from '@/components/editor/FileTree';
import { CodeEditor } from '@/components/editor/CodeEditor';
import { GitDiffViewer } from '@/components/editor/GitDiffViewer';
import { ScrollArea } from '@/components/ui/scroll-area';
import { CompactPageHeader } from '@/components/ui/compact-page-header';
import { IssuesTab } from '@/components/project/IssuesTab';
import { PullRequestsTab } from '@/components/project/PullRequestsTab';
import { WorkflowTab } from '@/components/project/WorkflowTab';
import { AIEditorTab } from '@/components/project/AIEditorTab';
import { ProjectDetailsTab } from '@/components/project/ProjectDetailsTab';
import { FileManagerTab } from '@/components/project/FileManagerTab';
import { RepositoryGitTab } from '@/components/project/RepositoryGitTab';
import { SafetyComplianceTab } from '@/components/project/SafetyComplianceTab';
import { WebtopTab } from '@/components/project/WebtopTab';
import { ContainerLogsTab } from '@/components/project/ContainerLogsTab';
import { BranchChatPanel } from '@/components/project/BranchChatPanel';
import { WorkspaceOrchestration } from '@/components/project/WorkspaceOrchestration';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getProjects, Project, getProjectServices, ProjectService, startService, stopService, restartService, killService, startAllServices, stopAllServices } from '@/lib/api';
import { CheckCircle, AlertTriangle, XCircle, FileText, Layers, ListChecks, Target, Shield, Play, Square, ChevronDown, Terminal, RefreshCcw, ExternalLink, RotateCcw, Loader2, MessageSquare } from 'lucide-react';


interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ServicesTabProps {
  project: Project;
}

const ServicesTab: React.FC<ServicesTabProps> = ({ project }) => {
  const storageKey = `livePreviewEnabled:${project.id}`;
  const queryClient = useQueryClient();
  const { data: services = [], isLoading, isError } = useQuery({
    queryKey: ['project-services', project.id],
    queryFn: () => getProjectServices(project.id),
    select: (response) => response?.data || [],
    refetchInterval: 5000,
  });

  const [enabledIds, setEnabledIds] = useState<number[] | null>(null);
  const [expandedService, setExpandedService] = useState<number | null>(null);

  // Service action mutations
  const startServiceMutation = useMutation({
    mutationFn: (serviceId: number) => startService(project.id, serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Service Starting', description: 'Service is being started...' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to start service', variant: 'destructive' }),
  });

  const stopServiceMutation = useMutation({
    mutationFn: (serviceId: number) => stopService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Service Stopped', description: 'Service has been stopped.' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to stop service', variant: 'destructive' }),
  });

  const restartServiceMutation = useMutation({
    mutationFn: (serviceId: number) => restartService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Service Restarting', description: 'Service is being restarted...' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to restart service', variant: 'destructive' }),
  });

  const killServiceMutation = useMutation({
    mutationFn: (serviceId: number) => killService(serviceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
      toast({ title: 'Service Killed', description: 'Service has been forcefully stopped.' });
    },
    onError: () => toast({ title: 'Error', description: 'Failed to kill service', variant: 'destructive' }),
  });

  useEffect(() => {
    if (!services.length) return;
    const raw = localStorage.getItem(storageKey);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setEnabledIds(parsed);
          return;
        }
      } catch (err) {
        console.warn('Failed to parse live preview selection', err);
      }
    }
    const allIds = services.map((s: ProjectService) => s.id);
    setEnabledIds(allIds);
    localStorage.setItem(storageKey, JSON.stringify(allIds));
  }, [services, storageKey]);

  const toggleService = (id: number) => {
    const current = enabledIds ?? services.map((s: ProjectService) => s.id);
    const exists = current.includes(id);
    const next = exists ? current.filter((s) => s !== id) : [...current, id];
    setEnabledIds(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-green-500';
      case 'stopped': return 'text-red-500';
      case 'paused': return 'text-yellow-500';
      default: return 'text-muted-foreground';
    }
  };

  const renderStatus = (status: string) => {
    const variant = status === 'running' ? 'success' : status === 'stopped' ? 'secondary' : 'outline';
    return (
      <Badge variant={variant} className="flex items-center gap-1">
        <span className={`inline-block w-2 h-2 rounded-full ${status === 'running' ? 'bg-green-500 animate-pulse' : status === 'stopped' ? 'bg-red-400' : 'bg-yellow-400'}`} />
        {status}
      </Badge>
    );
  };

  const renderList = useMemo(() => {
    if (isLoading) {
      return <div className="flex items-center justify-center py-8"><Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading services...</div>;
    }
    if (isError) {
      return <div className="text-center py-8 text-destructive">Failed to load services. Ensure workspace is provisioned.</div>;
    }
    if (!services.length) {
      return (
        <div className="text-center py-12 space-y-3">
          <Layers className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="text-muted-foreground">No services found for this project.</p>
          <p className="text-sm text-muted-foreground">Provision your workspace in the AI Editor or Webtop tab to create services.</p>
        </div>
      );
    }

    return (
      <div className="flex flex-col gap-3">
        {services.map((service: ProjectService) => {
          const envCount = service.environment ? Object.keys(service.environment).length : 0;
          const volumesRaw = (service.config && (service.config as any).volumes) || [];
          const volumes = Array.isArray(volumesRaw) ? volumesRaw : Object.keys(volumesRaw || {});
          const dependsOnRaw = (service.config && (service.config as any).depends_on) || [];
          const dependsOn = Array.isArray(dependsOnRaw) ? dependsOnRaw : Object.keys(dependsOnRaw || {});
          const isExpanded = expandedService === service.id;
          const isRunning = service.status === 'running';

          return (
            <div key={service.id} className="border rounded-lg bg-card overflow-hidden">
              {/* Service Header */}
              <div 
                className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => setExpandedService(isExpanded ? null : service.id)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-semibold text-base">{service.name}</span>
                  {renderStatus(service.status)}
                  <Badge variant="outline" className="text-xs">{service.service_type}</Badge>
                </div>
                <div className="flex items-center gap-2">
                  {/* Quick Actions */}
                  {isRunning ? (
                    <>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); restartServiceMutation.mutate(service.id); }}
                        isDisabled={restartServiceMutation.isPending}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <RotateCcw style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Restart
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); stopServiceMutation.mutate(service.id); }}
                        isDisabled={stopServiceMutation.isPending}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                      >
                        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                          <Square style={{ width: '0.875rem', height: '0.875rem' }} />
                        </span>
                        Stop
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); startServiceMutation.mutate(service.id); }}
                      isDisabled={startServiceMutation.isPending}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Play style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Start
                    </Button>
                  )}
                  <span className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                    <ChevronDown style={{ width: '1rem', height: '1rem' }} />
                  </span>
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="border-t border-border p-4 space-y-4">
                  {/* Info Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Image</span>
                      <span className="font-mono text-xs truncate block">{service.image || 'n/a'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">CPU Limit</span>
                      <span className="font-medium">{service.cpu_limit || 'unlimited'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Memory Limit</span>
                      <span className="font-medium">{service.memory_limit || 'unlimited'}</span>
                    </div>
                    <div className="p-2 bg-muted rounded">
                      <span className="text-xs text-muted-foreground block">Autostart</span>
                      <span className="font-medium">{service.autostart ? 'Yes' : 'No'}</span>
                    </div>
                  </div>

                  {/* Ports - clickable links */}
                  {service.ports?.length > 0 && (
                    <div>
                      <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Exposed Ports</span>
                      <div className="flex gap-2 flex-wrap">
                        {service.ports.map((port, i) => {
                          const hostPort = port.split(':')[0];
                          return (
                            <a
                              key={i}
                              href={`http://localhost:${hostPort}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-mono transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink style={{ width: '0.75rem', height: '0.75rem' }} />
                              :{port}
                            </a>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Environment & Dependencies */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {envCount > 0 && (
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Environment Variables ({envCount})</span>
                        <div className="bg-muted p-2 rounded max-h-32 overflow-y-auto text-xs font-mono space-y-0.5">
                          {Object.entries(service.environment).map(([key, val]) => (
                            <div key={key}><span className="text-blue-600">{key}</span>=<span className="text-muted-foreground">{String(val).length > 30 ? '***' : String(val)}</span></div>
                          ))}
                        </div>
                      </div>
                    )}
                    {volumes.length > 0 && (
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Volumes ({volumes.length})</span>
                        <div className="bg-muted p-2 rounded max-h-32 overflow-y-auto text-xs font-mono space-y-0.5">
                          {volumes.map((v: string, i: number) => (
                            <div key={i}>{v}</div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {dependsOn.length > 0 && (
                    <div>
                      <span className="text-xs font-semibold text-muted-foreground uppercase mb-1 block">Dependencies</span>
                      <div className="flex gap-1.5 flex-wrap">
                        {dependsOn.map((dep: string) => (
                          <Badge key={dep} variant="outline" className="text-xs">{dep}</Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Advanced Actions */}
                  <div className="flex gap-2 flex-wrap pt-2 border-t border-border">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toast({ title: 'Terminal', description: `Opening terminal for ${service.name}...` })}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Terminal style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Terminal
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toast({ title: 'Rebuilding', description: `Rebuilding ${service.name}...` })}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <RefreshCcw style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Rebuild
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); killServiceMutation.mutate(service.id); }}
                      isDisabled={killServiceMutation.isPending}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', minWidth: 'auto' }}
                    >
                      <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <XCircle style={{ width: '0.875rem', height: '0.875rem' }} />
                      </span>
                      Force Kill
                    </Button>
                    <div className="ml-auto flex items-center gap-2">
                      <Checkbox
                        id={`live-preview-${service.id}`}
                        checked={enabledIds ? enabledIds.includes(service.id) : true}
                        onCheckedChange={() => toggleService(service.id)}
                      />
                      <Label htmlFor={`live-preview-${service.id}`} className="text-xs">Live Preview</Label>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }, [services, isLoading, isError, enabledIds, expandedService, startServiceMutation, stopServiceMutation, restartServiceMutation, killServiceMutation]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Container Services</h2>
          <p className="text-sm text-muted-foreground">
            Manage your project's containerized services. Start, stop, restart, or access terminals.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              startAllServices(project.id);
              queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
              toast({ title: 'Starting All', description: 'Starting all services...' });
            }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <Play style={{ width: '0.875rem', height: '0.875rem' }} />
            </span>
            Start All
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              stopAllServices(project.id);
              queryClient.invalidateQueries({ queryKey: ['project-services', project.id] });
              toast({ title: 'Stopping All', description: 'Stopping all services...' });
            }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <Square style={{ width: '0.875rem', height: '0.875rem' }} />
            </span>
            Stop All
          </Button>
        </div>
      </div>
      {renderList}
    </div>
  );
};

const applicationFormSchema = z.object({
  name: z.string().trim().min(1, { message: "Project name is required" }).max(100, { message: "Name must be less than 100 characters" }),
  version: z.string().trim().regex(/^\d+\.\d+\.\d+$/, { message: "Version must be in format X.Y.Z (e.g., 1.0.0)" }),
  description: z.string().trim().min(10, { message: "Description must be at least 10 characters" }).max(500, { message: "Description must be less than 500 characters" }),
  category: z.string().min(1, { message: "Please select a category" }),
  aiTechnology: z.string().min(1, { message: "Please select an AI technology" }),
  repositoryUrl: z.string().url({ message: "Must be a valid URL" }).optional().or(z.literal('')),
});

const EditApplication = () => {
  const { appName } = useParams();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isChatCollapsed, setIsChatCollapsed] = useState(false);
  const [isBranchChatOpen, setIsBranchChatOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string | number>(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Hello! I'm your AI assistant for editing "${appName}". How can I help you modify your project today?`
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  
  // AI Settings State
  const [aiModel, setAiModel] = useState(editApplicationData.defaultSettings.aiModel);
  const [temperature, setTemperature] = useState([editApplicationData.defaultSettings.temperature]);
  const [maxTokens, setMaxTokens] = useState([editApplicationData.defaultSettings.maxTokens]);
  const [topP, setTopP] = useState([editApplicationData.defaultSettings.topP]);
  const [frequencyPenalty, setFrequencyPenalty] = useState([editApplicationData.defaultSettings.frequencyPenalty]);
  const [presencePenalty, setPresencePenalty] = useState([editApplicationData.defaultSettings.presencePenalty]);
  const [streamResponse, setStreamResponse] = useState(editApplicationData.defaultSettings.streamResponse);
  
  // MCP Servers State
  const [mcpServers, setMcpServers] = useState<Array<{ id: string; name: string; url: string; enabled: boolean }>>(editApplicationData.defaultMcpServers);

  // File Manager State
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>(editApplicationData.sampleFiles);
  const [originalContents, setOriginalContents] = useState<Record<string, string>>({});
  const [modifiedFiles, setModifiedFiles] = useState<Set<string>>(new Set());
  
  const fileStructure = editApplicationData.sampleFileStructure as any;

  const [chatSummary, setChatSummary] = useState('');
  const [todoOutline, setTodoOutline] = useState<string[]>([]); // New state for todo outline as array of strings

  // Fetch project data
  const { data: projectsResponse, isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  const projects = projectsResponse?.data || [];

  // Find the project
  const project = projects.find(p => p.name === appName || p.id.toString() === appName);

  // Simulated compliance data (replace with actual data source)
  const complianceChecks = [
    { id: '1', name: 'Security Scan', status: 'Pass', remediation: 'No issues found.' },
    { id: '2', name: 'Code Quality Check', status: 'Warning', remediation: 'Fix unused variables in file.js.' },
    { id: '3', name: 'Performance Audit', status: 'Fail', remediation: 'Optimize database queries.' },
  ];

  // Add state for compliance management
  const [assignedTemplates, setAssignedTemplates] = useState<string[]>([]);
  const [assignedChecks, setAssignedChecks] = useState<string[]>([]);
  const [isRunningChecks, setIsRunningChecks] = useState(false);
  const [checkResults, setCheckResults] = useState<Array<{
    checkId: string;
    checkName: string;
    status: 'Pass' | 'Warning' | 'Fail';
    message: string;
    remediation: string;
  }>>([]);
  const [isAssignDialogOpen, setIsAssignDialogOpen] = useState(false);
  const [selectedTemplatesForAssign, setSelectedTemplatesForAssign] = useState<string[]>([]);

  const form = useForm<z.infer<typeof applicationFormSchema>>({
    resolver: zodResolver(applicationFormSchema),
    defaultValues: {
      name: appName || '',
      version: '1.0.0',
      description: '',
      category: '',
      aiTechnology: '',
      repositoryUrl: '',
    },
  });

  const onSubmit = (values: z.infer<typeof applicationFormSchema>) => {
    console.log('Project details updated:', values);
    toast({
      title: "Changes Saved",
      description: "Project details have been updated successfully.",
    });
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Simulate AI response
    setTimeout(() => {
      const assistantMessage: Message = {
        role: 'assistant',
        content: 'I understand you want to make changes. This is a demo interface. To enable full AI editing capabilities, you would need to integrate with an AI service.'
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1000);

    // Simulate updating summary and todo on send
    setChatSummary(prev => prev + ` ${input}`); // Append to summary
    if (input.toLowerCase().includes('large change')) {
      setTodoOutline(['Step 1: Analyze requirements', 'Step 2: Implement core logic', 'Step 3: Test changes']); // Simulate AI-generated todo
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // File Manager Handlers
  const handleFileSelect = (path: string) => {
    setSelectedFile(path);
    if (!originalContents[path] && fileContents[path]) {
      setOriginalContents(prev => ({ ...prev, [path]: fileContents[path] }));
    }
  };

  const handleContentChange = (content: string) => {
    if (!selectedFile) return;
    setFileContents(prev => ({ ...prev, [selectedFile]: content }));
    
    const isModified = originalContents[selectedFile] !== content;
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      if (isModified) {
        newSet.add(selectedFile);
      } else {
        newSet.delete(selectedFile);
      }
      return newSet;
    });
  };

  const handleSaveFile = () => {
    if (!selectedFile) return;
    setOriginalContents(prev => ({ ...prev, [selectedFile]: fileContents[selectedFile] }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(selectedFile);
      return newSet;
    });
    toast({
      title: "File Saved",
      description: `${selectedFile} has been saved successfully.`,
    });
  };

  const handleDiscardFile = () => {
    if (!selectedFile) return;
    setFileContents(prev => ({ ...prev, [selectedFile]: originalContents[selectedFile] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(selectedFile);
      return newSet;
    });
    toast({
      title: "Changes Discarded",
      description: `Changes to ${selectedFile} have been discarded.`,
    });
  };

  const handleStageFile = (path: string) => {
    toast({
      title: "File Staged",
      description: `${path} has been staged for commit.`,
    });
  };

  const handleDiscardGitFile = (path: string) => {
    setFileContents(prev => ({ ...prev, [path]: originalContents[path] || '' }));
    setModifiedFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(path);
      return newSet;
    });
    toast({
      title: "Changes Discarded",
      description: `Changes to ${path} have been discarded.`,
    });
  };

  const handleCommit = () => {
    toast({
      title: "Committing Changes",
      description: "This would open a commit dialog in a full implementation.",
    });
  };

  const getGitDiffs = () => {
    return Array.from(modifiedFiles).map(path => {
      const original = originalContents[path] || '';
      const current = fileContents[path] || '';
      const originalLines = original.split('\n');
      const currentLines = current.split('\n');
      
      let diff = '';
      let additions = 0;
      let deletions = 0;

      const maxLen = Math.max(originalLines.length, currentLines.length);
      for (let i = 0; i < maxLen; i++) {
        if (originalLines[i] !== currentLines[i]) {
          if (originalLines[i]) {
            diff += `- ${originalLines[i]}\n`;
            deletions++;
          }
          if (currentLines[i]) {
            diff += `+ ${currentLines[i]}\n`;
            additions++;
          }
        }
      }

      return { path, additions, deletions, diff };
    });
  };

  // Render tabs for the header
  const renderTabs = () => (
    <Tabs
      activeKey={activeTab}
      onSelect={(event, tabIndex) => setActiveTab(tabIndex)}
      style={{ marginBottom: '1.5rem' }}
    >
      <Tab eventKey={0} title={<TabTitleText>AI Editor</TabTitleText>} />
      <Tab eventKey={1} title={<TabTitleText>Project Details</TabTitleText>} />
      <Tab eventKey={2} title={<TabTitleText>Services</TabTitleText>} />
      <Tab eventKey={3} title={<TabTitleText>File Manager</TabTitleText>} />
      <Tab eventKey={4} title={<TabTitleText>Repository & Git</TabTitleText>} />
      <Tab eventKey={5} title={<TabTitleText>Issues</TabTitleText>} />
      <Tab eventKey={6} title={<TabTitleText>Pull Requests</TabTitleText>} />
      <Tab eventKey={7} title={<TabTitleText>Workflows</TabTitleText>} />
      <Tab eventKey={8} title={<TabTitleText>Safety and Compliance</TabTitleText>} />
      <Tab eventKey={9} title={<TabTitleText>Webtop</TabTitleText>} />
      <Tab eventKey={10} title={<TabTitleText>Container Logs</TabTitleText>} />
    </Tabs>
  );

  const handleAssignTemplates = () => {
    setAssignedTemplates(selectedTemplatesForAssign);
    
    // Also add all checks from selected templates
    const checksFromTemplates = selectedTemplatesForAssign.flatMap(templateId => {
      const template = complianceData.templates.find(t => t.id === templateId);
      return template ? template.checks : [];
    });
    
    setAssignedChecks(prev => [...new Set([...prev, ...checksFromTemplates])]);
    
    toast({
      title: "Templates Assigned",
      description: `${selectedTemplatesForAssign.length} compliance template(s) assigned to this project.`,
    });
    
    setIsAssignDialogOpen(false);
    setSelectedTemplatesForAssign([]);
  };

  const handleToggleCheck = (checkId: string) => {
    setAssignedChecks(prev => 
      prev.includes(checkId) 
        ? prev.filter(id => id !== checkId)
        : [...prev, checkId]
    );
  };

  const handleRunChecks = async () => {
    if (assignedChecks.length === 0) {
      toast({
        title: "No Checks Assigned",
        description: "Please assign templates or checks before running compliance checks.",
        variant: "destructive",
      });
      return;
    }

    setIsRunningChecks(true);
    
    // Simulate running checks
    setTimeout(() => {
      const results = assignedChecks.map(checkId => {
        const check = complianceData.checks.find(c => c.id === checkId);
        if (!check) return null;
        
        // Simulate random results for demo
        const statuses: Array<'Pass' | 'Warning' | 'Fail'> = ['Pass', 'Warning', 'Fail'];
        const randomStatus = statuses[Math.floor(Math.random() * statuses.length)];
        
        return {
          checkId: check.id,
          checkName: check.name,
          status: randomStatus,
          message: randomStatus === 'Pass' 
            ? `${check.name} passed successfully.`
            : randomStatus === 'Warning'
            ? `${check.name} completed with warnings.`
            : `${check.name} failed validation.`,
          remediation: check.aiPrompt,
        };
      }).filter(Boolean) as typeof checkResults;
      
      setCheckResults(results);
      setIsRunningChecks(false);
      
      const passCount = results.filter(r => r.status === 'Pass').length;
      const failCount = results.filter(r => r.status === 'Fail').length;
      const warningCount = results.filter(r => r.status === 'Warning').length;
      
      toast({
        title: "Compliance Checks Complete",
        description: `${passCount} passed, ${warningCount} warnings, ${failCount} failed`,
      });
    }, 2000);
  };

  const getAssignedTemplateNames = () => {
    return assignedTemplates
      .map(id => complianceData.templates.find(t => t.id === id)?.name)
      .filter(Boolean)
      .join(', ');
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      className="edit-app-page"
    >
      <style>{`
        .edit-app-page .pf-v6-c-page__main {
          overflow: hidden !important;
          display: flex !important;
          flex-direction: column !important;
        }
        .edit-app-page .pf-v6-c-page__main-container {
          align-self: stretch !important;
          max-height: 100% !important;
        }
        .edit-app-page .pf-v6-c-page__main-section.pf-m-fill {
          min-height: 0 !important;
          overflow: hidden !important;
        }
        .edit-app-page .pf-v6-c-page__main-section.pf-m-fill > .pf-v6-c-page__main-body {
          display: flex !important;
          flex: 1 !important;
          min-height: 0 !important;
          overflow: hidden !important;
          flex-direction: row !important;
        }
      `}</style>
      <PageSection variant="default" style={{ paddingTop: 0, paddingBottom: 0 }}>
        <div style={{ 
          position: 'sticky', 
          top: 0, 
          zIndex: 100, 
          backgroundColor: 'var(--pf-v6-global--BackgroundColor--100)',
          borderBottom: '1px solid var(--pf-v6-global--BorderColor--100)',
          paddingTop: '1rem'
        }}>
          <CompactPageHeader
            title="Edit Project"
            subtitle={project?.name || appName || ''}
            backLink={{
              label: 'Back to My Projects',
              onClick: () => navigate('/my-applications'),
            }}
            actions={
              <div className="flex items-center gap-2">
                {project && <WorkspaceOrchestration project={project} />}
                <button
                  onClick={() => setIsBranchChatOpen(!isBranchChatOpen)}
                  className={`p-2 rounded-md border transition-colors ${
                    isBranchChatOpen
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-background hover:bg-muted border-border'
                  }`}
                  title="Toggle branch chat"
                >
                  <MessageSquare className="h-4 w-4" />
                </button>
              </div>
            }
            tabs={renderTabs()}
          />
        </div>
      </PageSection>

      <PageSection variant="default" isFilled style={{ paddingTop: '1rem', paddingBottom: 0 }}>
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: activeTab === 0 ? 'hidden' : 'auto' }}>
        {activeTab === 0 && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {project ? <AIEditorTab project={project} /> : <div>Loading AI editor...</div>}
          </div>
        )}

        {activeTab === 1 && (
          project ? <ProjectDetailsTab project={project} /> : <div>Loading project details...</div>
        )}

        {activeTab === 2 && (
          project ? <ServicesTab project={project} /> : <div>Loading services...</div>
        )}

        {activeTab === 3 && (
          project ? <FileManagerTab project={project} /> : <div>Loading file manager...</div>
        )}

        {activeTab === 4 && (
          project ? <RepositoryGitTab projectName={appName} projectId={project.id} /> : <div>Loading repository...</div>
        )}

        {activeTab === 5 && (
          <IssuesTab projectId={appName} projectName={appName} />
        )}

        {activeTab === 6 && (
          <PullRequestsTab projectId={appName} projectName={appName} />
        )}

        {activeTab === 7 && (
          <WorkflowTab projectId={appName} projectName={appName} />
        )}

        {activeTab === 8 && (
          <SafetyComplianceTab projectName={appName} />
        )}

        {activeTab === 9 && (
          project ? <WebtopTab project={project} /> : <div>Loading webtop...</div>
        )}

        {activeTab === 10 && (
          project ? <ContainerLogsTab project={project} /> : <div>Loading logs...</div>
        )}
        </div>

        {project && (
          <BranchChatPanel
            projectId={project.id}
            projectName={project.name}
            isOpen={isBranchChatOpen}
            onClose={() => setIsBranchChatOpen(false)}
          />
        )}
      </PageSection>
    </Page>
  );
};

export default EditApplication;

