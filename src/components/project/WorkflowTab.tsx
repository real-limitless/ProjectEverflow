import { useState, useCallback, useRef, useEffect } from 'react';
import { Card, CardBody, CardTitle } from '@patternfly/react-core';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from '@/hooks/use-toast';
import { Play, GitBranch, CheckCircle, XCircle, Clock, AlertTriangle, Plus, Save, Upload, Edit, Workflow, Zap, Database, MessageSquare, Code, Globe, Mail } from 'lucide-react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  Node,
  NodeTypes,
  ReactFlowProvider,
  Panel,
  BackgroundVariant,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  getBezierPath,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getWorkflows, createWorkflow, updateWorkflow, executeWorkflow, Workflow as ApiWorkflow } from '@/lib/api';

interface NodeTypeDefinition {
  type: string;
  label: string;
  icon: any;
  color: string;
  description: string;
}

const nodeTypeDefinitions: NodeTypeDefinition[] = [
  { type: 'trigger', label: 'Trigger', icon: Zap, color: '#f59e0b', description: 'Start workflow on event' },
  { type: 'action', label: 'Action', icon: Workflow, color: '#3b82f6', description: 'Perform an action' },
  { type: 'condition', label: 'Condition', icon: GitBranch, color: '#8b5cf6', description: 'Branch logic' },
  { type: 'database', label: 'Database', icon: Database, color: '#10b981', description: 'Database operations' },
  { type: 'ai', label: 'AI Model', icon: MessageSquare, color: '#ec4899', description: 'AI processing' },
  { type: 'code', label: 'Code', icon: Code, color: '#6366f1', description: 'Custom code execution' },
  { type: 'api', label: 'API Call', icon: Globe, color: '#06b6d4', description: 'HTTP API request' },
  { type: 'email', label: 'Email', icon: Mail, color: '#ef4444', description: 'Send email' },
];

// Helper functions for status display
const getStatusColor = (status: string) => {
  switch (status) {
    case 'active':
      return 'default';
    case 'draft':
      return 'secondary';
    case 'paused':
      return 'outline';
    case 'archived':
      return 'destructive';
    default:
      return 'secondary';
  }
};

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'active':
      return <CheckCircle size={12} />;
    case 'draft':
      return <Clock size={12} />;
    case 'paused':
      return <AlertTriangle size={12} />;
    case 'archived':
      return <XCircle size={12} />;
    default:
      return <Clock size={12} />;
  }
};

const workflowTemplates = [
  {
    id: 'template-1',
    name: 'Basic Approval Workflow',
    description: 'Simple workflow for document approvals',
    nodes: 5,
    edges: 4,
  },
  {
    id: 'template-2',
    name: 'Data Processing Pipeline',
    description: 'ETL workflow with AI processing',
    nodes: 8,
    edges: 7,
  },
  {
    id: 'template-3',
    name: 'Notification System',
    description: 'Automated email and alert system',
    nodes: 6,
    edges: 5,
  },
];

// Custom Edge with Delete Button
const CustomEdge = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style = {}, markerEnd, selected, data }: EdgeProps) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const onDelete = data?.onDelete as ((id: string) => void) | undefined;

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      {selected && onDelete && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              fontSize: 12,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
          >
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(id);
              }}
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                background: '#dc3545',
                border: '2px solid white',
                color: 'white',
                fontSize: '14px',
                fontWeight: 'bold',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                padding: 0,
                lineHeight: 1,
              }}
              title="Delete connection"
            >
              ×
            </button>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

// Custom Node Types
const WorkflowNode = ({ data, id }: { data: { label: string; icon?: string; onDelete?: (id: string) => void }; id: string }) => (
  <>
    <Handle 
      type="target" 
      position={Position.Left}
      style={{
        width: '14px',
        height: '14px',
        background: '#0066cc',
        border: '3px solid white',
        boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
        cursor: 'crosshair',
      }}
      isConnectable={true}
    />
    <div style={{
      padding: '10px',
      border: '1px solid #ddd',
      borderRadius: '5px',
      background: '#fff',
      minWidth: '120px',
      textAlign: 'center',
      position: 'relative',
    }}>
      {data.onDelete && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            data.onDelete(id);
          }}
          style={{
            position: 'absolute',
            top: '-8px',
            right: '-8px',
            width: '20px',
            height: '20px',
            borderRadius: '50%',
            background: '#dc3545',
            border: '2px solid white',
            color: 'white',
            fontSize: '12px',
            fontWeight: 'bold',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            padding: 0,
            lineHeight: 1,
          }}
          title="Delete node"
        >
          ×
        </button>
      )}
      {data.icon && <div style={{ fontSize: '20px', marginBottom: '5px' }}>{data.icon}</div>}
      <div>{data.label}</div>
    </div>
    <Handle 
      type="source" 
      position={Position.Right}
      style={{
        width: '14px',
        height: '14px',
        background: '#0066cc',
        border: '3px solid white',
        boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
        cursor: 'crosshair',
      }}
      isConnectable={true}
    />
  </>
);

const nodeTypes: NodeTypes = {
  workflowNode: WorkflowNode,
};

const edgeTypes = {
  custom: CustomEdge,
};

const initialNodes: Node[] = [
  {
    id: '1',
    type: 'workflowNode',
    position: { x: 250, y: 25 },
    data: { label: 'Start', icon: '🚀' },
  },
];

const initialEdges: Edge[] = [];

interface WorkflowTabProps {
  projectId?: string;
  projectName?: string;
}

export const WorkflowTab = ({ projectId, projectName }: WorkflowTabProps) => {
  const [workflows, setWorkflows] = useState<ApiWorkflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDesigner, setShowDesigner] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [newWorkflow, setNewWorkflow] = useState({
    name: '',
    description: '',
    status: 'draft' as 'active' | 'draft' | 'paused' | 'archived',
  });

  // Load workflows on component mount
  useEffect(() => {
    loadWorkflows();
  }, [projectId]);

  const loadWorkflows = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params: any = {};
      if (projectId) {
        params.project = parseInt(projectId);
      }

      const response = await getWorkflows(params);
      if (response.data) {
        setWorkflows(response.data);
      } else if (response.error) {
        setError(response.error);
      }
    } catch (err) {
      setError('Failed to load workflows');
      console.error('Error loading workflows:', err);
    } finally {
      setLoading(false);
    }
  };

  const deleteEdge = useCallback((edgeId: string) => {
    setEdges((eds) => eds.filter((edge) => edge.id !== edgeId));
    toast({
      title: "Connection Deleted",
      description: "Connection has been removed.",
    });
  }, [setEdges]);

  const deleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((node) => node.id !== nodeId));
    setEdges((eds) => eds.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
    toast({
      title: "Node Deleted",
      description: "Node and its connections have been removed.",
    });
  }, [setNodes, setEdges]);

  const onConnect = useCallback(
    (params: Connection | Edge) => {
      const edgeId = `edge-${Date.now()}`;
      const newEdge = {
        ...params,
        id: edgeId,
        type: 'custom',
        animated: true,
        style: { 
          stroke: '#0066cc',
          strokeWidth: 3,
        },
        data: { onDelete: deleteEdge },
      } as Edge;
      
      setEdges((eds) => [...eds, newEdge]);
      toast({
        title: "Connection Created",
        description: "Nodes have been connected successfully",
      });
    },
    [setEdges, deleteEdge]
  );

  const addNode = (nodeTypeDef: NodeTypeDefinition) => {
    const Icon = nodeTypeDef.icon;
    const newNode: Node = {
      id: `node-${Date.now()}`,
      type: 'workflowNode',
      position: { x: Math.random() * 400 + 100, y: Math.random() * 400 + 150 },
      data: { 
        label: nodeTypeDef.label,
        icon: nodeTypeDef.type === 'trigger' ? '⚡' : 
              nodeTypeDef.type === 'action' ? '⚙️' :
              nodeTypeDef.type === 'condition' ? '🔀' :
              nodeTypeDef.type === 'database' ? '💾' :
              nodeTypeDef.type === 'ai' ? '🤖' :
              nodeTypeDef.type === 'code' ? '💻' :
              nodeTypeDef.type === 'api' ? '🌐' :
              nodeTypeDef.type === 'email' ? '📧' : '📦',
        onDelete: deleteNode,
      },
      style: {
        background: 'var(--pf-v6-global--BackgroundColor--100)',
        border: `2px solid ${nodeTypeDef.color}`,
        borderRadius: '8px',
        padding: '10px 15px',
        fontSize: '14px',
        fontWeight: 500,
        minWidth: '150px',
      },
    };
    setNodes((nds) => nds.concat(newNode));
    toast({
      title: "Node Added",
      description: `${nodeTypeDef.label} node has been added. Drag from its edge to connect it to other nodes.`,
    });
  };

  const loadTemplate = (template: any) => {
    toast({
      title: "Loading Template",
      description: `Loading ${template.name} template...`,
    });
  };

  const saveWorkflow = () => {
    if (!selectedWorkflow) return;
    const workflowData = { nodes, edges };
    localStorage.setItem(`workflow-${projectId}-${selectedWorkflow}`, JSON.stringify(workflowData));
    toast({
      title: "Workflow Saved",
      description: "Your workflow design has been saved.",
    });
  };

  const loadWorkflow = (workflowId?: string) => {
    const targetWorkflowId = workflowId || selectedWorkflow;
    if (!targetWorkflowId) return;
    
    const workflow = workflows.find(w => w.id.toString() === targetWorkflowId.toString());
    if (workflow && workflow.nodes && workflow.edges) {
      setNodes(workflow.nodes);
      const loadedEdges = workflow.edges.map((edge: Edge) => ({
        ...edge,
        type: 'custom',
        data: { ...edge.data, onDelete: deleteEdge },
      }));
      setEdges(loadedEdges);
      toast({
        title: "Workflow Loaded",
        description: "Workflow design has been loaded.",
      });
    }
  };

  const handleDesignWorkflow = (workflowId: number) => {
    setSelectedWorkflow(workflowId.toString());
    setShowDesigner(true);
    // Load the workflow design
    loadWorkflow(workflowId.toString());
  };

  const handleRunWorkflow = async (workflowId: number, workflowName: string) => {
    try {
      const response = await executeWorkflow(workflowId);
      if (response.data) {
        toast({
          title: "Workflow Executed",
          description: `${workflowName} has been started.`,
        });
        // Refresh workflows to show updated status
        loadWorkflows();
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to execute workflow.",
        variant: "destructive",
      });
    }
  };

  const handleViewLogs = (workflowId: number) => {
    // TODO: Implement view logs functionality
    toast({
      title: "View Logs",
      description: "Logs viewing not yet implemented.",
    });
  };

  const handleCreateWorkflow = async () => {
    if (!newWorkflow.name.trim()) {
      toast({
        title: "Error",
        description: "Please enter a workflow name.",
        variant: "destructive",
      });
      return;
    }

    try {
      const workflowData: any = {
        name: newWorkflow.name,
        description: newWorkflow.description,
        status: newWorkflow.status,
        nodes: initialNodes,
        edges: initialEdges,
      };

      if (projectId) {
        workflowData.project = parseInt(projectId);
      }

      const response = await createWorkflow(workflowData);
      
      if (response.data) {
        toast({
          title: "Workflow Created",
          description: `${newWorkflow.name} has been created successfully.`,
        });
        setShowCreateForm(false);
        setNewWorkflow({ name: '', description: '', status: 'draft' });
        loadWorkflows(); // Reload workflows
      } else if (response.error) {
        toast({
          title: "Error",
          description: response.error,
          variant: "destructive",
        });
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to create workflow.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardBody>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <div>
              <CardTitle style={{ marginBottom: '0.5rem' }}>
                CI/CD Workflows
              </CardTitle>
              <p style={{ fontSize: '0.9375rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                Automated workflows for testing, building, and deploying your application
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {!showCreateForm && (
                <Button
                  variant="default"
                  onClick={() => setShowCreateForm(true)}
                >
                  <Plus size={16} style={{ marginRight: '0.5rem' }} />
                  Create Workflow
                </Button>
              )}
            </div>
          </div>

          {/* Create Workflow Form */}
          {showCreateForm && (
            <div style={{
              padding: '1.5rem',
              border: '2px solid var(--pf-v6-global--primary-color--100)',
              borderRadius: '8px',
              backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
              marginBottom: '1.5rem',
            }}>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '1rem' }}>
                Create New Workflow
              </h3>
              
              <div className="space-y-4">
                <div>
                  <Label htmlFor="workflow-name">Workflow Name *</Label>
                  <Input
                    id="workflow-name"
                    placeholder="e.g., CI/CD Pipeline, Deploy to Production"
                    value={newWorkflow.name}
                    onChange={(e) => setNewWorkflow({ ...newWorkflow, name: e.target.value })}
                    className="mt-2"
                  />
                </div>

                <div>
                  <Label htmlFor="workflow-description">Description</Label>
                  <Textarea
                    id="workflow-description"
                    placeholder="Describe what this workflow does..."
                    value={newWorkflow.description}
                    onChange={(e) => setNewWorkflow({ ...newWorkflow, description: e.target.value })}
                    rows={3}
                    className="mt-2"
                  />
                </div>

                <div>
                  <Label htmlFor="workflow-status">Initial Status</Label>
                  <Select 
                    value={newWorkflow.status} 
                    onValueChange={(value: 'active' | 'draft' | 'paused' | 'archived') => 
                      setNewWorkflow({ ...newWorkflow, status: value })
                    }
                  >
                    <SelectTrigger id="workflow-status" className="mt-2">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="draft">Draft</SelectItem>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'flex-end', 
                  gap: '0.5rem',
                  paddingTop: '1rem',
                  borderTop: '1px solid var(--pf-v6-global--BorderColor--100)',
                }}>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setShowCreateForm(false);
                      setNewWorkflow({ name: '', description: '', status: 'draft' });
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="default"
                    onClick={handleCreateWorkflow}
                  >
                    Create Workflow
                  </Button>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-4">
            {workflows.map((workflow) => (
              <div
                key={workflow.id}
                style={{
                  padding: '1.25rem',
                  border: '1px solid var(--pf-v6-global--BorderColor--100)',
                  borderRadius: '8px',
                  backgroundColor: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                      <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>
                        {workflow.name}
                      </h3>
                      <Badge variant={getStatusColor(workflow.status)}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          {getStatusIcon(workflow.status)}
                          {workflow.status.charAt(0).toUpperCase() + workflow.status.slice(1)}
                        </span>
                      </Badge>
                    </div>

                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Workflow size={14} />
                        {workflow.run_count} runs
                      </span>
                      <span>•</span>
                      <span>Last run: {workflow.last_run ? new Date(workflow.last_run).toLocaleDateString() : 'Never'}</span>
                      <span>•</span>
                      <span>Created: {new Date(workflow.created_at).toLocaleDateString()}</span>
                    </div>

                    <div style={{
                      marginTop: '0.75rem',
                      padding: '0.75rem',
                      backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                      borderRadius: '6px',
                      fontSize: '0.8125rem',
                    }}>
                      {workflow.description || 'No description provided'}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', marginLeft: '1rem' }}>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleRunWorkflow(workflow.id, workflow.name)}
                      disabled={workflow.status !== 'active'}
                    >
                      <Play size={14} style={{ marginRight: '0.25rem' }} />
                      Run
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDesignWorkflow(workflow.id)}
                    >
                      <Edit size={14} style={{ marginRight: '0.25rem' }} />
                      Design
                    </Button>
                    <Button
                      variant="link"
                      size="sm"
                      onClick={() => handleViewLogs(workflow.id)}
                    >
                      View Logs
                    </Button>
                  </div>
                </div>

                {/* Workflow Steps - Placeholder for future execution tracking */}
                {workflow.status === 'active' && workflow.run_count > 0 && (
                  <div style={{
                    marginTop: '1rem',
                    padding: '1rem',
                    backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                    borderRadius: '6px',
                  }}>
                    <div style={{ fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
                      Recent Activity:
                    </div>
                    <div className="space-y-2">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <CheckCircle size={14} className="text-green-600" />
                        <span style={{ fontSize: '0.8125rem' }}>Workflow executed {workflow.run_count} times</span>
                      </div>
                      {workflow.last_run && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Clock size={14} className="text-blue-600" />
                          <span style={{ fontSize: '0.8125rem' }}>Last run: {new Date(workflow.last_run).toLocaleString()}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
};