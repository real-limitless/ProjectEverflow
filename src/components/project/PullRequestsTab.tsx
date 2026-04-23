import { useState } from 'react';
import { Card, CardBody, Button } from '@patternfly/react-core';
import { GitPullRequest, FileCode, CheckCircle2, AlertTriangle, MessageSquare, Eye, XCircle, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Search } from 'lucide-react';
import { toast } from '@/hooks/use-toast';

type ChangeRequestStatus = 'Pending Review' | 'Changes Requested' | 'Approved' | 'Rejected';
type ChangeType = 'Feature' | 'Bug Fix' | 'Enhancement' | 'Documentation';

interface PullRequest {
  id: string;
  title: string;
  description: string;
  projectName: string;
  type: ChangeType;
  status: ChangeRequestStatus;
  branch: string;
  targetBranch: string;
  requestedBy: {
    name: string;
    initials: string;
  };
  submittedDate: string;
  filesChanged: number;
  linesAdded: number;
  linesRemoved: number;
  currentApprovals: Array<{ name: string; initials: string }>;
  requiredApprovals: number;
  reviewComments?: Array<{ reviewerName: string; comment: string }>;
}

interface PullRequestsTabProps {
  projectId?: string;
  projectName?: string;
}

export const PullRequestsTab = ({ projectId, projectName }: PullRequestsTabProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [createPROpen, setCreatePROpen] = useState(false);
  const [newPR, setNewPR] = useState({
    title: '',
    description: '',
    branch: '',
    targetBranch: 'main',
    type: 'Feature' as ChangeType,
  });

  // Mock data - replace with actual API call filtered by projectId
  const pullRequests: PullRequest[] = [
    {
      id: '1',
      title: 'Add user authentication feature',
      description: 'Implements JWT-based authentication with refresh tokens',
      projectName: projectName || 'Current Project',
      type: 'Feature',
      status: 'Pending Review',
      branch: 'feature/auth',
      targetBranch: 'main',
      requestedBy: { name: 'John Doe', initials: 'JD' },
      submittedDate: '2024-01-15',
      filesChanged: 12,
      linesAdded: 456,
      linesRemoved: 89,
      currentApprovals: [{ name: 'Jane Smith', initials: 'JS' }],
      requiredApprovals: 3,
    },
    {
      id: '2',
      title: 'Fix memory leak in data processing',
      description: 'Resolves issue #42 by properly disposing of event listeners',
      projectName: projectName || 'Current Project',
      type: 'Bug Fix',
      status: 'Approved',
      branch: 'bugfix/memory-leak',
      targetBranch: 'main',
      requestedBy: { name: 'Alice Johnson', initials: 'AJ' },
      submittedDate: '2024-01-14',
      filesChanged: 5,
      linesAdded: 78,
      linesRemoved: 123,
      currentApprovals: [
        { name: 'Bob Wilson', initials: 'BW' },
        { name: 'Carol Davis', initials: 'CD' },
        { name: 'David Lee', initials: 'DL' }
      ],
      requiredApprovals: 3,
    },
  ];

  const getStatusColor = (status: ChangeRequestStatus) => {
    switch (status) {
      case 'Pending Review': return 'info';
      case 'Changes Requested': return 'warning';
      case 'Approved': return 'success';
      case 'Rejected': return 'destructive';
      default: return 'secondary';
    }
  };

  const getTypeColor = (type: ChangeType) => {
    switch (type) {
      case 'Feature': return 'info';
      case 'Bug Fix': return 'destructive';
      case 'Enhancement': return 'success';
      case 'Documentation': return 'secondary';
      default: return 'secondary';
    }
  };

  const filteredRequests = pullRequests.filter(request => {
    const matchesSearch = request.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         request.requestedBy.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === 'all' || request.type === typeFilter;
    const matchesStatus = statusFilter === 'all' || request.status === statusFilter;
    return matchesSearch && matchesType && matchesStatus;
  });

  const handleApprove = (id: string, title: string) => {
    toast({
      title: "Pull Request Approved",
      description: `You have approved: ${title}`,
    });
  };

  const handleRequestChanges = (id: string, title: string) => {
    toast({
      title: "Changes Requested",
      description: `Requested changes for: ${title}`,
    });
  };

  const handleReject = (id: string, title: string) => {
    toast({
      title: "Pull Request Rejected",
      description: `You have rejected: ${title}`,
      variant: "destructive",
    });
  };

  const handleViewDiff = (id: string) => {
    toast({
      title: "View Diff",
      description: "Opening detailed code diff view...",
    });
  };

  const handleCreatePR = () => {
    if (!newPR.title.trim()) {
      toast({
        title: "Error",
        description: "Please enter a title for the pull request.",
        variant: "destructive",
      });
      return;
    }

    if (!newPR.branch.trim()) {
      toast({
        title: "Error",
        description: "Please specify a source branch.",
        variant: "destructive",
      });
      return;
    }

    toast({
      title: "Pull Request Created",
      description: `Successfully created PR: ${newPR.title}`,
    });
    
    setCreatePROpen(false);
    setNewPR({
      title: '',
      description: '',
      branch: '',
      targetBranch: 'main',
      type: 'Feature',
    });
  };

  return (
    <div className="space-y-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0 }}>Pull Requests</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
            Review and approve code changes for {projectName || 'this project'}. Requires <strong>3 contributor approvals</strong> before merging.
          </p>
        </div>
        
        <Dialog open={createPROpen} onOpenChange={setCreatePROpen}>
          <DialogTrigger asChild>
            <Button variant="primary">
              <Plus className="mr-2 h-4 w-4" />
              Create Pull Request
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create Pull Request</DialogTitle>
              <DialogDescription>
                Submit your code changes for review by the project team
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label htmlFor="pr-title">Title *</Label>
                <Input
                  id="pr-title"
                  placeholder="Brief description of changes"
                  value={newPR.title}
                  onChange={(e) => setNewPR({ ...newPR, title: e.target.value })}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label htmlFor="pr-description">Description</Label>
                <Textarea
                  id="pr-description"
                  placeholder="Detailed description of changes, testing notes, etc."
                  value={newPR.description}
                  onChange={(e) => setNewPR({ ...newPR, description: e.target.value })}
                  rows={6}
                  className="mt-2"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="pr-source-branch">Source Branch *</Label>
                  <Input
                    id="pr-source-branch"
                    placeholder="feature/my-feature"
                    value={newPR.branch}
                    onChange={(e) => setNewPR({ ...newPR, branch: e.target.value })}
                    className="mt-2"
                  />
                </div>

                <div>
                  <Label htmlFor="pr-target-branch">Target Branch</Label>
                  <Select value={newPR.targetBranch} onValueChange={(value) => setNewPR({ ...newPR, targetBranch: value })}>
                    <SelectTrigger id="pr-target-branch" className="mt-2">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="main">main</SelectItem>
                      <SelectItem value="develop">develop</SelectItem>
                      <SelectItem value="staging">staging</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label htmlFor="pr-type">Change Type</Label>
                <Select value={newPR.type} onValueChange={(value: ChangeType) => setNewPR({ ...newPR, type: value })}>
                  <SelectTrigger id="pr-type" className="mt-2">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Feature">Feature</SelectItem>
                    <SelectItem value="Bug Fix">Bug Fix</SelectItem>
                    <SelectItem value="Enhancement">Enhancement</SelectItem>
                    <SelectItem value="Documentation">Documentation</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex justify-end gap-2 mt-6">
                <Button variant="secondary" onClick={() => {
                  setCreatePROpen(false);
                  setNewPR({ title: '', description: '', branch: '', targetBranch: 'main', type: 'Feature' });
                }}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleCreatePR}>
                  Create Pull Request
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filter Controls */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ flex: '1 1 300px', position: 'relative' }}>
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search pull requests..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Change type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="Feature">Feature</SelectItem>
            <SelectItem value="Bug Fix">Bug Fix</SelectItem>
            <SelectItem value="Enhancement">Enhancement</SelectItem>
            <SelectItem value="Documentation">Documentation</SelectItem>
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="Pending Review">Pending Review</SelectItem>
            <SelectItem value="Changes Requested">Changes Requested</SelectItem>
            <SelectItem value="Approved">Approved</SelectItem>
            <SelectItem value="Rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>

        <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
          {filteredRequests.length} pull request{filteredRequests.length !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Pull Request Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {filteredRequests.length === 0 ? (
          <Card>
            <CardBody style={{ textAlign: 'center', padding: '3rem' }}>
              <GitPullRequest size={48} style={{ margin: '0 auto 1rem', color: 'var(--pf-v6-global--Color--200)' }} />
              <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No pull requests found</h3>
              <p style={{ color: 'var(--pf-v6-global--Color--200)' }}>
                {searchQuery || typeFilter !== 'all' || statusFilter !== 'all'
                  ? 'Try adjusting your filters'
                  : 'All pull requests have been reviewed'}
              </p>
            </CardBody>
          </Card>
        ) : (
          filteredRequests.map((request) => {
            const approvalProgress = (request.currentApprovals.length / request.requiredApprovals) * 100;
            
            return (
              <Card key={request.id}>
                <CardBody>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                        <h3 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>
                          {request.title}
                        </h3>
                        <Badge variant={getTypeColor(request.type)}>
                          {request.type}
                        </Badge>
                        <Badge variant={getStatusColor(request.status)}>
                          {request.status}
                        </Badge>
                      </div>
                      <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', margin: 0 }}>
                        {request.branch} → {request.targetBranch}
                      </p>
                    </div>
                  </div>

                  {/* Description */}
                  <p style={{ fontSize: '0.9375rem', marginBottom: '1rem', lineHeight: '1.5' }}>
                    {request.description}
                  </p>

                  {/* Metadata */}
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
                    gap: '1rem',
                    marginBottom: '1rem',
                    padding: '1rem',
                    backgroundColor: 'var(--pf-v6-global--BackgroundColor--200)',
                    borderRadius: '8px'
                  }}>
                    <div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '0.25rem' }}>
                        Requested by
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Avatar className="h-6 w-6">
                          <AvatarFallback className="bg-primary text-primary-foreground text-xs">
                            {request.requestedBy.initials}
                          </AvatarFallback>
                        </Avatar>
                        <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>{request.requestedBy.name}</span>
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '0.25rem' }}>
                        Submitted
                      </div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                        {new Date(request.submittedDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </div>
                    </div>

                    <div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '0.25rem' }}>
                        Changes
                      </div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                        <FileCode size={14} style={{ display: 'inline-block', marginRight: '0.25rem' }} />
                        {request.filesChanged} files • <span style={{ color: '#10b981' }}>+{request.linesAdded}</span> <span style={{ color: '#ef4444' }}>-{request.linesRemoved}</span>
                      </div>
                    </div>
                  </div>

                  {/* Approval Progress */}
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                        Approval Progress: {request.currentApprovals.length} / {request.requiredApprovals}
                      </span>
                      {request.status === 'Approved' && (
                        <CheckCircle2 size={16} style={{ color: '#10b981' }} />
                      )}
                    </div>
                    <Progress value={approvalProgress} className="h-2 mb-2" />
                    
                    {request.currentApprovals.length > 0 && (
                      <div style={{ fontSize: '0.8125rem', color: 'var(--pf-v6-global--Color--200)' }}>
                        Approved by: {request.currentApprovals.map(a => a.name).join(', ')}
                      </div>
                    )}
                  </div>

                  {/* Review Comments */}
                  {request.reviewComments && request.reviewComments.length > 0 && (
                    <div style={{ 
                      marginBottom: '1rem',
                      padding: '0.75rem',
                      backgroundColor: '#fef3c7',
                      borderRadius: '8px',
                      border: '1px solid #fbbf24'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <MessageSquare size={16} style={{ color: '#f59e0b' }} />
                        <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Review Comments</span>
                      </div>
                      {request.reviewComments.map((comment, idx) => (
                        <div key={idx} style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>
                          <strong>{comment.reviewerName}:</strong> {comment.comment}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                    <Button 
                      variant="primary"
                      onClick={() => handleApprove(request.id, request.title)}
                      isDisabled={request.status === 'Approved' || request.status === 'Rejected'}
                      icon={<CheckCircle2 size={16} />}
                    >
                      Approve
                    </Button>
                    <Button 
                      variant="secondary"
                      onClick={() => handleRequestChanges(request.id, request.title)}
                      isDisabled={request.status === 'Approved' || request.status === 'Rejected'}
                      icon={<AlertTriangle size={16} />}
                    >
                      Request Changes
                    </Button>
                    <Button 
                      variant="danger"
                      onClick={() => handleReject(request.id, request.title)}
                      isDisabled={request.status === 'Approved' || request.status === 'Rejected'}
                      icon={<XCircle size={16} />}
                    >
                      Reject
                    </Button>
                    <Button 
                      variant="link"
                      onClick={() => handleViewDiff(request.id)}
                      icon={<Eye size={16} />}
                    >
                      View Full Diff
                    </Button>
                  </div>
                </CardBody>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
};