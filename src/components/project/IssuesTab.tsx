import { useState, useEffect } from 'react';
import { Card, CardBody, Button, Label } from '@patternfly/react-core';
import { Table, Thead, Tbody, Tr, Th, Td } from '@patternfly/react-table';
import { MessageSquare, Eye, Clock, ThumbsUp, Bookmark } from 'lucide-react';
import { Avatar, Tooltip } from '@patternfly/react-core';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { SearchInput } from '@patternfly/react-core';
import { Link } from 'react-router-dom';
import { PlusCircleIcon } from '@patternfly/react-icons';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { toast } from '@/hooks/use-toast';
import { getIssues, voteIssue, bookmarkIssue, viewIssue, createIssue, Issue as ApiIssue } from '@/lib/api';

interface IssuesTabProps {
  projectId?: string;
  projectName?: string;
}

export const IssuesTab = ({ projectId, projectName }: IssuesTabProps) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [selectedStatus, setSelectedStatus] = useState<string>('All');
  const [activeSortIndex, setActiveSortIndex] = useState<number | null>(null);
  const [activeSortDirection, setActiveSortDirection] = useState<'asc' | 'desc'>('asc');
  const [issues, setIssues] = useState<ApiIssue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newIssue, setNewIssue] = useState({
    title: '',
    description: '',
    category: 'bug',
    status: 'open'
  });

  const categories = ['All', 'bug', 'feature_request', 'question', 'enhancement', 'documentation', 'other'];
  const statuses = ['All', 'open', 'in_progress', 'resolved', 'closed'];

  // Load issues on component mount and when filters change
  useEffect(() => {
    loadIssues();
  }, [projectId, selectedCategory, selectedStatus]);

  const loadIssues = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params: any = {};
      if (projectId) {
        params.project = parseInt(projectId);
      }
      if (selectedCategory !== 'All') {
        params.category = selectedCategory;
      }
      if (selectedStatus !== 'All') {
        params.status = selectedStatus;
      }
      if (searchTerm) {
        params.search = searchTerm;
      }

      const response = await getIssues(params);
      if (response.data) {
        setIssues(response.data);
      } else if (response.error) {
        setError(response.error);
      }
    } catch (err) {
      setError('Failed to load issues');
      console.error('Error loading issues:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleVote = async (issueId: number) => {
    try {
      const response = await voteIssue(issueId);
      if (response.data) {
        setIssues(prev => prev.map(issue => 
          issue.id === issueId 
            ? { ...issue, votes: response.data!.votes }
            : issue
        ));
        toast({
          title: "Vote recorded",
          description: "Your vote has been added to this issue.",
        });
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to vote on issue.",
        variant: "destructive",
      });
    }
  };

  const handleBookmark = async (issueId: number) => {
    try {
      const response = await bookmarkIssue(issueId);
      if (response.data) {
        setIssues(prev => prev.map(issue => 
          issue.id === issueId 
            ? { ...issue, is_bookmarked: response.data!.is_bookmarked }
            : issue
        ));
        toast({
          title: response.data!.is_bookmarked ? "Bookmarked" : "Unbookmarked",
          description: `Issue has been ${response.data!.is_bookmarked ? 'bookmarked' : 'unbookmarked'}.`,
        });
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to bookmark issue.",
        variant: "destructive",
      });
    }
  };

  const handleView = async (issueId: number) => {
    try {
      await viewIssue(issueId);
      // Update local state
      setIssues(prev => prev.map(issue => 
        issue.id === issueId 
          ? { ...issue, views: issue.views + 1 }
          : issue
      ));
    } catch (err) {
      // Silently fail for view tracking
      console.error('Error tracking view:', err);
    }
  };

  const handleCreateIssue = async () => {
    if (!newIssue.title.trim()) {
      toast({
        title: "Error",
        description: "Please enter an issue title.",
        variant: "destructive",
      });
      return;
    }

    if (!newIssue.description.trim()) {
      toast({
        title: "Error",
        description: "Please enter an issue description.",
        variant: "destructive",
      });
      return;
    }

    try {
      const issueData: any = {
        title: newIssue.title,
        description: newIssue.description,
        category: newIssue.category,
        status: newIssue.status,
      };

      if (projectId) {
        issueData.project = parseInt(projectId);
      }

      const response = await createIssue(issueData);
      
      if (response.data) {
        toast({
          title: "Issue Created",
          description: "Your issue has been successfully created.",
        });
        setCreateDialogOpen(false);
        setNewIssue({ title: '', description: '', category: 'bug', status: 'open' });
        loadIssues(); // Reload issues
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
        description: "Failed to create issue.",
        variant: "destructive",
      });
    }
  };

  const filteredIssues = issues.filter(issue => {
    const matchesSearch = searchTerm === '' || 
      issue.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      `${issue.author.first_name} ${issue.author.last_name}`.toLowerCase().includes(searchTerm.toLowerCase()) ||
      issue.author.username.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  });

  const sortedIssues = [...filteredIssues].sort((a, b) => {
    if (activeSortIndex === null) return 0;
    const direction = activeSortDirection === 'asc' ? 1 : -1;
    switch (activeSortIndex) {
      case 0:
        return a.title.localeCompare(b.title) * direction;
      case 1:
        return `${a.author.first_name} ${a.author.last_name}`.localeCompare(`${b.author.first_name} ${b.author.last_name}`) * direction;
      case 2:
        return (a.replies_count - b.replies_count) * direction;
      case 3:
        return (a.views - b.views) * direction;
      default:
        return 0;
    }
  });

  const handleSort = (index: number) => {
    if (activeSortIndex === index) {
      setActiveSortDirection(activeSortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setActiveSortIndex(index);
      setActiveSortDirection('asc');
    }
  };

  const getCategoryColor = (category: string): 'blue' | 'green' | 'red' | 'grey' | 'purple' => {
    const colors: Record<string, 'blue' | 'green' | 'red' | 'grey' | 'purple'> = {
      'bug': 'red',
      'feature_request': 'blue',
      'question': 'purple',
      'enhancement': 'green',
      'documentation': 'grey',
      'other': 'grey'
    };
    return colors[category] || 'grey';
  };

  const getStatusColor = (status: string): 'blue' | 'green' | 'red' | 'grey' | 'orange' => {
    const colors: Record<string, 'blue' | 'green' | 'red' | 'grey' | 'orange'> = {
      'open': 'blue',
      'in_progress': 'orange',
      'resolved': 'green',
      'closed': 'grey'
    };
    return colors[status] || 'grey';
  };

  return (
    <div className="space-y-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0 }}>Issues & Discussions</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)', marginTop: '0.25rem' }}>
            Report issues, ask questions, and discuss features for {projectName || 'this project'}
          </p>
        </div>
        <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button 
              variant="primary" 
              icon={<PlusCircleIcon />}
            >
              New Issue
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Issue</DialogTitle>
              <DialogDescription>
                Report a bug, request a feature, or start a discussion about {projectName || 'this project'}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label htmlFor="issue-title">Title *</Label>
                <Input
                  id="issue-title"
                  placeholder="Brief description of the issue"
                  value={newIssue.title}
                  onChange={(e) => setNewIssue({ ...newIssue, title: e.target.value })}
                  className="mt-2"
                />
              </div>
              
              <div>
                <Label htmlFor="issue-description">Description *</Label>
                <Textarea
                  id="issue-description"
                  placeholder="Provide detailed information about the issue..."
                  value={newIssue.description}
                  onChange={(e) => setNewIssue({ ...newIssue, description: e.target.value })}
                  rows={6}
                  className="mt-2"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="issue-category">Category</Label>
                  <Select value={newIssue.category} onValueChange={(value) => setNewIssue({ ...newIssue, category: value })}>
                    <SelectTrigger id="issue-category" className="mt-2">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bug">Bug</SelectItem>
                      <SelectItem value="feature_request">Feature Request</SelectItem>
                      <SelectItem value="question">Question</SelectItem>
                      <SelectItem value="enhancement">Enhancement</SelectItem>
                      <SelectItem value="documentation">Documentation</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="issue-status">Status</Label>
                  <Select value={newIssue.status} onValueChange={(value) => setNewIssue({ ...newIssue, status: value })}>
                    <SelectTrigger id="issue-status" className="mt-2">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="open">Open</SelectItem>
                      <SelectItem value="in_progress">In Progress</SelectItem>
                      <SelectItem value="resolved">Resolved</SelectItem>
                      <SelectItem value="closed">Closed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-6">
                <Button variant="secondary" onClick={() => {
                  setCreateDialogOpen(false);
                  setNewIssue({ title: '', description: '', category: 'bug', status: 'open' });
                }}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleCreateIssue}>
                  Create Issue
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
        <SearchInput
          placeholder="Search issues..."
          value={searchTerm}
          onChange={(_event, value) => setSearchTerm(value)}
          onClear={() => setSearchTerm('')}
          style={{ flex: '1 1 300px' }}
        />
        <Select value={selectedCategory} onValueChange={setSelectedCategory}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            {categories.map(cat => (
              <SelectItem key={cat} value={cat}>{cat}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={selectedStatus} onValueChange={setSelectedStatus}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {statuses.map(status => (
              <SelectItem key={status} value={status}>{status}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Issues Table */}
      <Card>
        <CardBody style={{ padding: 0 }}>
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center' }}>
              Loading issues...
            </div>
          ) : error ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'red' }}>
              Error: {error}
              <Button onClick={loadIssues} style={{ marginLeft: '1rem' }}>
                Retry
              </Button>
            </div>
          ) : sortedIssues.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center' }}>
              No issues found.
              {projectId && (
                <Button 
                  onClick={() => {/* TODO: Open create issue dialog */}}
                  style={{ marginLeft: '1rem' }}
                >
                  Create First Issue
                </Button>
              )}
            </div>
          ) : (
            <Table aria-label="Issues table" variant="compact">
            <Thead>
              <Tr>
                <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(0)}>
                  Issue {activeSortIndex === 0 && (activeSortDirection === 'asc' ? '↑' : '↓')}
                </Th>
                <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(1)}>
                  Author {activeSortIndex === 1 && (activeSortDirection === 'asc' ? '↑' : '↓')}
                </Th>
                <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(2)}>
                  Replies {activeSortIndex === 2 && (activeSortDirection === 'asc' ? '↑' : '↓')}
                </Th>
                <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(3)}>
                  Views {activeSortIndex === 3 && (activeSortDirection === 'asc' ? '↑' : '↓')}
                </Th>
                <Th>Last Activity</Th>
                <Th>Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {sortedIssues.map((issue) => (
                <Tr key={issue.id}>
                  <Td>
                    <div>
                      <div style={{ marginBottom: '0.25rem' }}>
                        <Link 
                          to={`/view-issue/${issue.id}`}
                          style={{ fontWeight: 600, textDecoration: 'none', color: 'var(--pf-v6-global--link--Color)' }}
                        >
                          {issue.title}
                        </Link>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <Label color={getCategoryColor(issue.category)} isCompact>
                          {issue.category}
                        </Label>
                        <Label color={getStatusColor(issue.status)} isCompact>
                          {issue.status}
                        </Label>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Avatar src={issue.author.avatar || '/default-avatar.png'} alt={`${issue.author.first_name} ${issue.author.last_name}`} size="sm" />
                      <span>{`${issue.author.first_name} ${issue.author.last_name}`}</span>
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <MessageSquare size={14} />
                      {issue.replies_count}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Eye size={14} />
                      {issue.views}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Clock size={14} />
                      {new Date(issue.last_activity).toLocaleDateString()}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <Tooltip content="Upvote">
                        <Button variant="plain" onClick={() => handleVote(issue.id)}>
                          <ThumbsUp size={16} />
                          <span style={{ marginLeft: '0.25rem' }}>{issue.votes}</span>
                        </Button>
                      </Tooltip>
                      <Tooltip content={issue.is_bookmarked ? "Remove bookmark" : "Bookmark"}>
                        <Button variant="plain" onClick={() => handleBookmark(issue.id)}>
                          <Bookmark size={16} fill={issue.is_bookmarked ? 'currentColor' : 'none'} />
                        </Button>
                      </Tooltip>
                      <Tooltip content="View issue">
                        <Button 
                          variant="plain" 
                          onClick={() => handleView(issue.id)}
                          component="a"
                          href={`/issues/${issue.id}`}
                        >
                          <Eye size={16} />
                        </Button>
                      </Tooltip>
                    </div>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
          )}
        </CardBody>
      </Card>
    </div>
  );
};