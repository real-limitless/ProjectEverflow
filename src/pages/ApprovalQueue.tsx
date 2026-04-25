import { useState } from 'react';
import { Page, PageSection, Card, CardBody, Button, Label } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { GitPullRequest, FileCode, CheckCircle2, Clock, AlertTriangle, MessageSquare, Eye, XCircle, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import { useQuery } from '@tanstack/react-query';
import { getChangeRequests, approveChangeRequest, requestChangesChangeRequest, ChangeRequest } from '@/lib/api';
import PageHeader from '@/components/ui/PageHeader';

type ChangeRequestStatus = 'Pending Review' | 'Changes Requested' | 'Approved' | 'Rejected';
type ChangeType = 'Feature' | 'Bug Fix' | 'Enhancement' | 'Documentation';

const ApprovalQueue = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [projectFilter, setProjectFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [approvingRequest, setApprovingRequest] = useState<number | null>(null);
  const [requestingChanges, setRequestingChanges] = useState<number | null>(null);
  const [rejectingRequest, setRejectingRequest] = useState<number | null>(null);

  // Fetch change requests
  const { data: changeRequestsResponse, isLoading, error, refetch } = useQuery({
    queryKey: ['changeRequests'],
    queryFn: getChangeRequests,
  });

  const changeRequests = changeRequestsResponse?.data || [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'info';
      case 'changes_requested': return 'warning';
      case 'approved': return 'success';
      case 'rejected': return 'destructive';
      default: return 'secondary';
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'feature': return 'info';
      case 'bug_fix': return 'destructive';
      case 'enhancement': return 'success';
      case 'documentation': return 'secondary';
      default: return 'secondary';
    }
  };

  const filteredRequests = changeRequests.filter((request: ChangeRequest) => {
    const matchesSearch = request.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         request.project.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         request.author.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         request.author.first_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         request.author.last_name.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesProject = projectFilter === 'all' || request.project.name === projectFilter;
    const matchesType = typeFilter === 'all' || request.change_type === typeFilter;
    const matchesStatus = statusFilter === 'all' || request.status === statusFilter;

    return matchesSearch && matchesProject && matchesType && matchesStatus;
  });

  const uniqueProjects = Array.from(new Set(changeRequests.map((r: ChangeRequest) => r.project.name)));

  const handleApprove = async (id: number) => {
    setApprovingRequest(id);
    try {
      await approveChangeRequest(id);
      toast({
        title: "Change Request Approved",
        description: "You have successfully approved the change request",
      });
      refetch(); // Refresh the data
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to approve change request",
        variant: "destructive",
      });
    } finally {
      setApprovingRequest(null);
    }
  };

  const handleRequestChanges = async (id: number) => {
    setRequestingChanges(id);
    try {
      await requestChangesChangeRequest(id);
      toast({
        title: "Changes Requested",
        description: "You have requested changes for this pull request",
      });
      refetch(); // Refresh the data
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to request changes",
        variant: "destructive",
      });
    } finally {
      setRequestingChanges(null);
    }
  };

  const handleReject = async (id: number) => {
    setRejectingRequest(id);
    try {
      toast({
        title: "Change Request Rejected",
        description: "You have rejected the change request",
      });
      // TODO: Implement reject functionality with API call
    } finally {
      setRejectingRequest(null);
    }
  };

  const handleViewDiff = (id: number) => {
    toast({
      title: "View Diff",
      description: "Opening detailed code diff view...",
    });
  };

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="Approval Queue"
          description="Review and approve code changes and pull requests for projects you own or contribute to. Requires 3 contributor approvals before merging to main."
          icon={<GitPullRequest size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        {/* Filter Controls */}
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ flex: '1 1 300px', position: 'relative' }}>
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by title, project, or contributor..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          
          <Select value={projectFilter} onValueChange={setProjectFilter}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Filter by project" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Projects</SelectItem>
              {uniqueProjects.map(project => (
                <SelectItem key={project} value={project}>{project}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Change type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="feature">Feature</SelectItem>
              <SelectItem value="bug_fix">Bug Fix</SelectItem>
              <SelectItem value="enhancement">Enhancement</SelectItem>
              <SelectItem value="documentation">Documentation</SelectItem>
              <SelectItem value="refactor">Refactor</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>

          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="pending">Pending Review</SelectItem>
              <SelectItem value="changes_requested">Changes Requested</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>

          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
            Showing {filteredRequests.length} of {changeRequests.length} requests
          </p>
        </div>

        {/* Loading and Error States */}
        {isLoading && (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading change requests...</span>
          </div>
        )}

        {error && (
          <div className="text-center py-12">
            <p className="text-destructive">Error loading change requests: {error.message}</p>
          </div>
        )}

        {/* Change Request Cards */}
        {!isLoading && !error && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {filteredRequests.length === 0 ? (
              <Card>
                <CardBody style={{ textAlign: 'center', padding: '3rem' }}>
                  <GitPullRequest size={48} style={{ margin: '0 auto 1rem', color: 'var(--pf-v6-global--Color--200)' }} />
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No change requests found</h3>
                  <p style={{ color: 'var(--pf-v6-global--Color--200)' }}>
                    {searchQuery || projectFilter !== 'all' || typeFilter !== 'all' || statusFilter !== 'all'
                      ? 'Try adjusting your filters'
                      : 'All change requests have been reviewed'}
                  </p>
                </CardBody>
              </Card>
            ) : (
              filteredRequests.map((request: ChangeRequest) => {
                const approvalProgress = (request.approval_count / request.approvals_required) * 100;

                return (
                  <Card key={request.id}>
                    <CardBody>
                      {/* Header Section */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>
                              {request.title}
                            </h3>
                            <Badge variant={getTypeColor(request.change_type)}>
                              {request.change_type.replace('_', ' ')}
                            </Badge>
                            <Badge variant={getStatusColor(request.status)}>
                              {request.status.replace('_', ' ')}
                            </Badge>
                          </div>
                          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                            <strong>{request.project.name}</strong> • main → {request.target_branch}
                          </p>
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                          by {request.author.username} • {new Date(request.created_at).toLocaleDateString()}
                        </div>
                      </div>

                      {/* Description */}
                      <div style={{ marginBottom: '1rem' }}>
                        <p style={{ fontSize: '0.875rem', margin: 0 }}>
                          {request.description || 'No description provided'}
                        </p>
                      </div>

                      {/* Diff Summary */}
                      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', fontSize: '0.875rem' }}>
                        <span style={{ color: 'var(--pf-v6-global--success-color--100)' }}>
                          +{request.lines_added} additions
                        </span>
                        <span style={{ color: 'var(--pf-v6-global--danger-color--100)' }}>
                          -{request.lines_removed} deletions
                        </span>
                        <span style={{ color: 'var(--pf-v6-global--Color--200)' }}>
                          {request.files_changed} files changed
                        </span>
                      </div>

                      {/* Approval Progress */}
                      <div style={{ marginBottom: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>
                            Approval Progress
                          </span>
                          <span style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                            {request.approval_count} of {request.approvals_required} approvals
                          </span>
                        </div>
                        <Progress value={approvalProgress} size={ProgressSize.sm} />
                      </div>

                      {/* Action Buttons */}
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {request.status === 'pending_review' && (
                          <>
                            <Button
                              variant={ButtonVariant.primary}
                              size="sm"
                              onClick={() => handleApprove(request.id)}
                              isLoading={approvingRequest === request.id}
                              isDisabled={approvingRequest === request.id}
                            >
                              <Check size={16} style={{ marginRight: '0.25rem' }} />
                              Approve
                            </Button>
                            <Button
                              variant={ButtonVariant.secondary}
                              size="sm"
                              onClick={() => handleRequestChanges(request.id)}
                              isLoading={requestingChanges === request.id}
                              isDisabled={requestingChanges === request.id}
                            >
                              <MessageSquare size={16} style={{ marginRight: '0.25rem' }} />
                              Request Changes
                            </Button>
                            <Button
                              variant={ButtonVariant.danger}
                              size="sm"
                              onClick={() => handleReject(request.id)}
                              isLoading={rejectingRequest === request.id}
                              isDisabled={rejectingRequest === request.id}
                            >
                              <X size={16} style={{ marginRight: '0.25rem' }} />
                              Reject
                            </Button>
                          </>
                        )}
                        <Button
                          variant={ButtonVariant.link}
                          size="sm"
                          onClick={() => handleViewDiff(request.id)}
                        >
                          <GitDiff size={16} style={{ marginRight: '0.25rem' }} />
                          View Diff
                        </Button>
                        <Button
                          variant={ButtonVariant.link}
                          size="sm"
                          onClick={() => handleViewProject(request.project.id)}
                        >
                          <FolderOpen size={16} style={{ marginRight: '0.25rem' }} />
                          View Project
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                );
              })
            )}
          </div>
        )}
      </PageSection>
    </Page>
  );
};

export default ApprovalQueue;
