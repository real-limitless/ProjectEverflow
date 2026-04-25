import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Grid, GridItem, Button } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Shield, Search, Plus, Edit, Trash2, Settings, CheckCircle2, AlertTriangle, XCircle, FileText, Layers, Loader2, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from '@/hooks/use-toast';
import { useQuery } from '@tanstack/react-query';
import { getComplianceChecks, getComplianceTemplates, getProjectAssignments, ComplianceCheck, ComplianceTemplate, ProjectAssignment } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';

type CheckCategory = 'Security' | 'Code Quality' | 'Performance' | 'Compliance' | 'Custom';
type CheckSeverity = 'Critical' | 'Warning' | 'Info';
type CheckStatus = 'pass' | 'fail' | 'not_run';

const SafetyCompliance = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [selectedCheckId, setSelectedCheckId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState('library');

  const { data: checks, isLoading: checksLoading, error: checksError } = useQuery({
    queryKey: ['compliance-checks'],
    queryFn: () => getComplianceChecks(),
  });

  const { data: templates, isLoading: templatesLoading, error: templatesError } = useQuery({
    queryKey: ['compliance-templates'],
    queryFn: () => getComplianceTemplates(),
  });

  const { data: projectAssignments, isLoading: assignmentsLoading, error: assignmentsError } = useQuery({
    queryKey: ['project-assignments'],
    queryFn: () => getProjectAssignments(),
  });

  const filteredChecks = ((checks?.data || []) as ComplianceCheck[]).filter(check => {
    const matchesSearch = check.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         check.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = categoryFilter === 'all' || check.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const selectedCheck = selectedCheckId ? (checks || []).find(c => c.id === selectedCheckId) : null;

  const getSeverityColor = (severity: CheckSeverity) => {
    switch (severity) {
      case 'Critical': return 'destructive';
      case 'Warning': return 'warning';
      case 'Info': return 'info';
      default: return 'secondary';
    }
  };

  const getStatusColor = (status: CheckStatus) => {
    switch (status) {
      case 'pass': return 'success';
      case 'fail': return 'destructive';
      case 'not_run': return 'secondary';
      default: return 'secondary';
    }
  };

  const handleCreateCheck = () => {
    toast({
      title: "Create New Check",
      description: "Opening check editor...",
    });
  };

  const handleEditCheck = (checkId: string) => {
    toast({
      title: "Edit Check",
      description: "Opening check editor...",
    });
  };

  const handleDeleteCheck = (checkId: string, checkName: string) => {
    toast({
      title: "Delete Check",
      description: `Are you sure you want to delete ${checkName}?`,
      variant: "destructive",
    });
  };

  const handleCreateTemplate = () => {
    toast({
      title: "Create Template",
      description: "Opening template editor...",
    });
  };

  const handleAssignToProject = (templateId: string) => {
    toast({
      title: "Assign to Projects",
      description: "Opening project assignment dialog...",
    });
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="Safety & Compliance"
          description="Administrator check library for creating, browsing, and assigning compliance checks. Checks run automatically on every commit, build, and PR creation."
          icon={<Shield size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        {(checks?.error || templates?.error || projectAssignments?.error || checksError || templatesError || assignmentsError) ? (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <AlertCircle size={32} style={{ margin: '0 auto 1rem', display: 'block', color: 'var(--pf-v6-global--danger-color--100)' }} />
            <p style={{ color: 'var(--pf-v6-global--danger-color--100)', marginBottom: '1rem' }}>Failed to load compliance data</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
              {checks?.error && `Checks: ${checks.error}`}
              {templates?.error && `Templates: ${templates.error}`}
              {projectAssignments?.error && `Assignments: ${projectAssignments.error}`}
              {checksError && `Checks (query): ${checksError}`}
              {templatesError && `Templates (query): ${templatesError}`}
              {assignmentsError && `Assignments (query): ${assignmentsError}`}
            </p>
          </div>
        ) : (checksLoading || templatesLoading || assignmentsLoading) ? (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <Loader2 className="animate-spin" size={32} style={{ margin: '0 auto 1rem', display: 'block' }} />
            <p style={{ color: 'var(--pf-v6-global--Color--200)' }}>Loading compliance data...</p>
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="library">Check Library</TabsTrigger>
            <TabsTrigger value="templates">Compliance Templates</TabsTrigger>
            <TabsTrigger value="assignments">Project Assignments</TabsTrigger>
          </TabsList>

          {/* Check Library Tab */}
          <TabsContent value="library">
            <Grid hasGutter>
              {/* Left Section: Check Browser */}
              <GridItem span={12} lg={6}>
                <Card style={{ height: '100%' }}>
                  <CardBody>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                      <CardTitle style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>
                        Browse Checks
                      </CardTitle>
                      <Button variant="primary" onClick={handleCreateCheck} size="sm">
                        <Plus size={16} style={{ marginRight: '0.25rem' }} />
                        Create Check
                      </Button>
                    </div>

                    {/* Search and Filter */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
                      <div style={{ position: 'relative' }}>
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search checks..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="pl-10"
                        />
                      </div>
                      
                      <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="Filter by category" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Categories</SelectItem>
                          <SelectItem value="Security">Security</SelectItem>
                          <SelectItem value="Code Quality">Code Quality</SelectItem>
                          <SelectItem value="Performance">Performance</SelectItem>
                          <SelectItem value="Compliance">Compliance</SelectItem>
                          <SelectItem value="Custom">Custom</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
                      Showing {filteredChecks.length} of {((checks?.data || []) as ComplianceCheck[]).length} checks
                    </p>

                    {/* Check List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '600px', overflowY: 'auto' }}>
                      {filteredChecks.map(check => (
                        <div
                          key={check.id}
                          onClick={() => setSelectedCheckId(check.id)}
                          style={{
                            padding: '1rem',
                            border: `2px solid ${selectedCheckId === check.id ? 'var(--pf-v6-global--primary-color--100)' : 'var(--pf-v6-global--BorderColor--100)'}`,
                            borderRadius: '8px',
                            cursor: 'pointer',
                            backgroundColor: selectedCheckId === check.id ? 'var(--pf-v6-global--BackgroundColor--200)' : 'transparent',
                            transition: 'all 0.2s'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.5rem' }}>
                            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, margin: 0 }}>{check.name}</h4>
                            <div style={{ display: 'flex', gap: '0.375rem' }}>
                              <Badge variant={getSeverityColor(check.severity as CheckSeverity)}>
                                {check.severity}
                              </Badge>
                              <Badge variant="secondary">{check.category}</Badge>
                            </div>
                          </div>
                          <p style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '0.5rem' }}>
                            {check.description}
                          </p>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem', color: 'var(--pf-v6-global--Color--200)' }}>
                            <span>Used in {check.usage_count} projects</span>
                            <span>Updated {new Date(check.updated_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardBody>
                </Card>
              </GridItem>

              {/* Right Section: Check Details/Editor */}
              <GridItem span={12} lg={6}>
                <Card style={{ height: '100%' }}>
                  <CardBody>
                    {selectedCheck ? (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center', marginBottom: '1.5rem' }}>
                          <CardTitle style={{ fontSize: '1.25rem', fontWeight: 600, margin: 0 }}>
                            Check Details
                          </CardTitle>
                          <div style={{ display: 'flex', gap: '0.5rem' }}>
                                                        <Button variant="secondary" size="sm" onClick={() => handleEditCheck(selectedCheck.id.toString())}>
                              <Edit className="h-4 w-4 mr-2" />
                              Edit
                            </Button>
                            <Button variant="danger" size="sm" onClick={() => handleDeleteCheck(selectedCheck.id.toString(), selectedCheck.name)}>
                              <Trash2 className="h-4 w-4 mr-2" />
                              Delete
                            </Button>
                          </div>
                        </div>

                        <div style={{ marginBottom: '1.5rem' }}>
                          <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            Check Name
                          </label>
                          <Input value={selectedCheck.name} disabled />
                        </div>

                        <div style={{ marginBottom: '1.5rem' }}>
                          <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            Description
                          </label>
                          <Input value={selectedCheck.description} disabled />
                        </div>

                        <Grid hasGutter style={{ marginBottom: '1.5rem' }}>
                          <GridItem span={6}>
                            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                              Category
                            </label>
                            <Badge variant="secondary">{selectedCheck.category}</Badge>
                          </GridItem>
                          <GridItem span={6}>
                            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                              Severity
                            </label>
                            <Badge variant={getSeverityColor(selectedCheck.severity as CheckSeverity)}>
                              {selectedCheck.severity}
                            </Badge>
                          </GridItem>
                        </Grid>

                        <div style={{ marginBottom: '1.5rem' }}>
                          <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            AI Validation Prompt
                          </label>
                          <div style={{ 
                            padding: '0.75rem', 
                            backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                            borderRadius: '6px',
                            fontSize: '0.8125rem',
                            lineHeight: '1.5',
                            fontFamily: 'monospace'
                          }}>
                            {selectedCheck.ai_prompt}
                          </div>
                        </div>

                        <div style={{ 
                          padding: '1rem',
                          backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                          borderRadius: '8px'
                        }}>
                          <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                            <strong>Status:</strong> {selectedCheck.is_active ? 'Enabled' : 'Disabled'}
                          </div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                            <strong>Used in:</strong> {selectedCheck.usage_count} projects
                          </div>
                          <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.5rem' }}>
                            <strong>Last Updated:</strong> {new Date(selectedCheck.updated_at).toLocaleDateString()}
                          </div>
                        </div>
                      </>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '4rem 1rem', color: 'var(--pf-v6-global--Color--200)' }}>
                        <Settings size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                        <p>Select a check from the list to view details</p>
                      </div>
                    )}
                  </CardBody>
                </Card>
              </GridItem>
            </Grid>
          </TabsContent>

          {/* Templates Tab */}
          <TabsContent value="templates">
            <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <p style={{ fontSize: '0.9375rem', color: 'var(--pf-v6-global--Color--200)' }}>
                Group checks into templates for easy assignment to multiple projects
              </p>
              <Button variant="primary" onClick={handleCreateTemplate}>
                <Plus size={16} style={{ marginRight: '0.25rem' }} />
                Create Template
              </Button>
            </div>

            <Grid hasGutter>
              {((templates?.data || []) as ComplianceTemplate[]).map(template => (
                <GridItem key={template.id} span={12} md={6}>
                  <Card>
                    <CardBody>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                        <div>
                          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                            <Layers size={20} style={{ display: 'inline-block', marginRight: '0.5rem', verticalAlign: 'middle' }} />
                            {template.name}
                          </h3>
                          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                            {template.description}
                          </p>
                        </div>
                      </div>

                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                          Includes {(template.checks || []).length} checks:
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                          {(template.checks || []).map(check => (
                            <Badge key={check.id} variant="secondary">{check.name}</Badge>
                          ))}
                        </div>
                      </div>

                      <div style={{ 
                        padding: '0.75rem',
                        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                        borderRadius: '6px',
                        marginBottom: '1rem',
                        fontSize: '0.875rem'
                      }}>
                        Used in <strong>{template.projects_using_count}</strong> projects
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <Button variant="secondary" size="sm" onClick={() => handleAssignToProject(template.id.toString())}>
                          Assign to Project
                        </Button>
                        <Button variant="link" size="sm">
                          Edit Template
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                </GridItem>
              ))}
            </Grid>
          </TabsContent>

          {/* Project Assignments Tab */}
          <TabsContent value="assignments">
            <p style={{ fontSize: '0.9375rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
              View and manage which checks and templates are assigned to each project
            </p>

            {assignmentsLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '2rem' }}>
                <Loader2 className="animate-spin" size={24} style={{ marginRight: '0.5rem' }} />
                Loading project assignments...
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {((projectAssignments?.data || []) as ProjectAssignment[]).map(assignment => {
                  const assignedTemplates = assignment.template ? [assignment.template] : [];
                  return (
                    <Card key={assignment.id}>
                      <CardBody>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                          <div>
                            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                              <FileText size={20} style={{ display: 'inline-block', marginRight: '0.5rem', verticalAlign: 'middle' }} />
                              {assignment.project.name}
                            </h3>
                          </div>
                          <Badge variant={getStatusColor(assignment.status as CheckStatus)}>
                            {assignment.status === 'pass' && <CheckCircle2 size={14} style={{ marginRight: '0.25rem' }} />}
                            {assignment.status === 'fail' && <XCircle size={14} style={{ marginRight: '0.25rem' }} />}
                            {assignment.status === 'not_run' ? 'Not Run' : assignment.status.charAt(0).toUpperCase() + assignment.status.slice(1)}
                          </Badge>
                        </div>

                      <Grid hasGutter style={{ marginBottom: '1rem' }}>
                        <GridItem span={12} md={6}>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            Assigned Templates:
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                            {(assignedTemplates || []).map(template => 
                              <Badge key={template.id} variant="info">{template.name}</Badge>
                            )}
                            {(assignedTemplates || []).length === 0 && (
                              <span style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>None</span>
                            )}
                          </div>
                        </GridItem>

                        <GridItem span={12} md={6}>
                          <div style={{ fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                            Custom Checks:
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                            {(assignment.custom_checks || []).length > 0 ? (
                              (assignment.custom_checks || []).map(check => (
                                <Badge key={check.id} variant="secondary">{check.name}</Badge>
                              ))
                            ) : (
                              <span style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>None</span>
                            )}
                          </div>
                        </GridItem>
                      </Grid>

                      <div style={{ 
                        display: 'flex', 
                        justifyContent: 'space-between',
                        padding: '0.75rem',
                        backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                        borderRadius: '6px',
                        fontSize: '0.8125rem'
                      }}>
                        <div>
                          <strong>Last Run:</strong> {assignment.last_run ? new Date(assignment.last_run).toLocaleDateString('en-US', { 
                            month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' 
                          }) : 'Never'}
                        </div>
                        <div>
                          <strong>Violations:</strong> <span style={{ color: assignment.violations > 0 ? '#ef4444' : '#10b981' }}>
                            {assignment.violations}
                          </span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                        <Button variant="secondary" size="sm">
                          Edit Assignments
                        </Button>
                        <Button variant="link" size="sm">
                          View Check History
                        </Button>
                        <Button variant="link" size="sm">
                          Run Checks Now
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                );
              })}
              </div>
            )}
          </TabsContent>
        </Tabs>
        )}
      </PageSection>
    </Page>
  );
};

export default SafetyCompliance;
