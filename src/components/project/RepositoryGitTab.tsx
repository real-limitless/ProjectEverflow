import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardBody, Button } from '@patternfly/react-core';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { Sparkles, GitCommit, GitPullRequest, FileSearch, MessageSquare, Zap, GitBranch, Plus, Trash2, Merge, RotateCcw, ArrowUp, ArrowDown, RefreshCw } from 'lucide-react';
import { toast } from '@/hooks/use-toast';
import {
  getGitBranches,
  getGitCommits,
  getGitRemoteStatus,
  gitPull,
  gitPush,
  gitFetch,
  gitCheckout,
  gitCommit,
  type GitBranch as IGitBranch,
  type GitCommit as IGitCommit,
  type GitRemoteStatus,
} from '@/lib/api';

interface RepositoryGitTabProps {
  projectName: string;
  projectId: number;
}

export const RepositoryGitTab: React.FC<RepositoryGitTabProps> = ({ projectName, projectId }) => {
  const queryClient = useQueryClient();

  // Query states
  const { data: branchesData, isLoading: branchesLoading } = useQuery({
    queryKey: ['git-branches', projectId],
    queryFn: () => getGitBranches(projectId),
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  const { data: commitsData, isLoading: commitsLoading } = useQuery({
    queryKey: ['git-commits', projectId],
    queryFn: () => getGitCommits(projectId, { limit: 20 }),
    refetchInterval: 30000,
  });

  const { data: remoteStatusData, isLoading: remoteStatusLoading } = useQuery({
    queryKey: ['git-remote-status', projectId],
    queryFn: () => getGitRemoteStatus(projectId),
    refetchInterval: 30000,
  });

  // UI states
  const [commitMessage, setCommitMessage] = useState('');
  const [aiCommitSuggestion, setAiCommitSuggestion] = useState('');
  const [codeReviewOpen, setCodeReviewOpen] = useState(false);
  const [prDescriptionOpen, setPrDescriptionOpen] = useState(false);
  const [issueAnalysisOpen, setIssueAnalysisOpen] = useState(false);
  const [refactorSuggestionsOpen, setRefactorSuggestionsOpen] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  // Branch management states
  const [newBranchName, setNewBranchName] = useState('');
  const [selectedBranchToSwitch, setSelectedBranchToSwitch] = useState('');
  const [selectedBranchToDelete, setSelectedBranchToDelete] = useState('');
  const [mergeBranchSource, setMergeBranchSource] = useState('');
  const [createBranchOpen, setCreateBranchOpen] = useState(false);
  const [switchBranchOpen, setSwitchBranchOpen] = useState(false);
  const [deleteBranchOpen, setDeleteBranchOpen] = useState(false);
  const [mergeBranchOpen, setMergeBranchOpen] = useState(false);
  const [commitDialogOpen, setCommitDialogOpen] = useState(false);

  // Mutations
  const pullMutation = useMutation({
    mutationFn: () => gitPull(projectId),
    onSuccess: (data) => {
      if (data.data?.success) {
        toast({
          title: 'Pull Successful',
          description: 'Latest changes from remote have been pulled',
        });
        queryClient.invalidateQueries({ queryKey: ['git-commits', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-remote-status', projectId] });
      } else {
        toast({
          title: 'Pull Failed',
          description: data.data?.error || 'An error occurred',
          variant: 'destructive',
        });
      }
    },
    onError: () => {
      toast({
        title: 'Pull Failed',
        description: 'Failed to pull changes',
        variant: 'destructive',
      });
    },
  });

  const pushMutation = useMutation({
    mutationFn: () => gitPush(projectId),
    onSuccess: (data) => {
      if (data.data?.success) {
        toast({
          title: 'Push Successful',
          description: 'Your commits have been pushed to remote',
        });
        queryClient.invalidateQueries({ queryKey: ['git-commits', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-remote-status', projectId] });
      } else {
        toast({
          title: 'Push Failed',
          description: data.data?.error || 'An error occurred',
          variant: 'destructive',
        });
      }
    },
    onError: () => {
      toast({
        title: 'Push Failed',
        description: 'Failed to push changes',
        variant: 'destructive',
      });
    },
  });

  const fetchMutation = useMutation({
    mutationFn: () => gitFetch(projectId),
    onSuccess: (data) => {
      if (data.data?.success) {
        toast({
          title: 'Fetch Successful',
          description: 'Repository updated with latest remote changes',
        });
        queryClient.invalidateQueries({ queryKey: ['git-branches', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-remote-status', projectId] });
      } else {
        toast({
          title: 'Fetch Failed',
          description: data.data?.error || 'An error occurred',
          variant: 'destructive',
        });
      }
    },
    onError: () => {
      toast({
        title: 'Fetch Failed',
        description: 'Failed to fetch from remote',
        variant: 'destructive',
      });
    },
  });

  const checkoutMutation = useMutation({
    mutationFn: (branch: string) => gitCheckout(projectId, branch),
    onSuccess: (data) => {
      if (data.data?.success) {
        toast({
          title: 'Branch Switched',
          description: `Switched to branch successfully`,
        });
        queryClient.invalidateQueries({ queryKey: ['git-branches', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-commits', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-remote-status', projectId] });
        setSelectedBranchToSwitch('');
        setSwitchBranchOpen(false);
      } else {
        toast({
          title: 'Switch Failed',
          description: data.data?.error || 'An error occurred',
          variant: 'destructive',
        });
      }
    },
  });

  const commitMutation = useMutation({
    mutationFn: (message: string) => gitCommit(projectId, message, { all: true }),
    onSuccess: (data) => {
      if (data.data?.success) {
        toast({
          title: 'Commit Created',
          description: 'Changes have been committed',
        });
        queryClient.invalidateQueries({ queryKey: ['git-commits', projectId] });
        queryClient.invalidateQueries({ queryKey: ['git-remote-status', projectId] });
        setCommitMessage('');
        setCommitDialogOpen(false);
      } else {
        toast({
          title: 'Commit Failed',
          description: data.data?.error || 'An error occurred',
          variant: 'destructive',
        });
      }
    },
  });

  const handleCreateBranch = () => {
    if (!newBranchName.trim()) {
      toast({
        title: 'Error',
        description: 'Branch name cannot be empty',
        variant: 'destructive',
      });
      return;
    }
    // In a real implementation, this would call an API
    toast({
      title: 'Feature Coming Soon',
      description: 'Create branch feature will be available soon',
    });
  };

  const handleSwitchBranch = () => {
    if (!selectedBranchToSwitch) return;
    checkoutMutation.mutate(selectedBranchToSwitch);
  };

  const handleDeleteBranch = () => {
    if (!selectedBranchToDelete || selectedBranchToDelete === 'main') {
      toast({
        title: 'Error',
        description: 'Cannot delete main branch',
        variant: 'destructive',
      });
      return;
    }
    // In a real implementation, this would call an API
    toast({
      title: 'Feature Coming Soon',
      description: 'Delete branch feature will be available soon',
    });
  };

  const handleMergeBranch = () => {
    if (!mergeBranchSource) {
      toast({
        title: 'Error',
        description: 'Please select a branch to merge',
        variant: 'destructive',
      });
      return;
    }
    // In a real implementation, this would call an API
    toast({
      title: 'Feature Coming Soon',
      description: 'Merge branch feature will be available soon',
    });
  };

  const generateCommitMessage = () => {
    setIsGenerating(true);
    // Simulate AI generation
    setTimeout(() => {
      setAiCommitSuggestion('feat: Add user authentication with JWT tokens\n\n- Implement JWT-based authentication\n- Add refresh token mechanism\n- Update user model with auth fields\n- Add login/logout endpoints');
      setIsGenerating(false);
      toast({
        title: 'Commit Message Generated',
        description: 'AI has generated a commit message based on your changes',
      });
    }, 1500);
  };

  const handleAICodeReview = () => {
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setCodeReviewOpen(true);
    }, 1500);
  };

  const currentBranch = branchesData?.data?.currentBranch || 'main';
  const branches = branchesData?.data?.branches || [];
  const commits = commitsData?.data?.commits || [];
  const remoteStatus = remoteStatusData?.data;

  return (
    <div className="space-y-4">
      {/* Top bar: Branch selector + Sync status + Quick actions */}
      <Card>
        <CardBody>
          <div className="flex items-center justify-between flex-wrap gap-3">
            {/* Current Branch & Selector */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-primary" />
                <span className="font-mono font-semibold text-base">{currentBranch}</span>
              </div>
              
              {/* Branch Quick Actions */}
              <div className="flex gap-1.5">
                <Dialog open={switchBranchOpen} onOpenChange={setSwitchBranchOpen}>
                  <DialogTrigger asChild>
                    <Button variant="secondary" size="sm" className="gap-1" style={{ display: 'inline-flex', alignItems: 'center', minWidth: 'auto' }}>
                      <GitBranch className="h-3.5 w-3.5" /> Switch
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-md">
                    <DialogHeader>
                      <DialogTitle>Switch Branch</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                      <div>
                        <Label htmlFor="switch-branch">Select Branch</Label>
                        <Select value={selectedBranchToSwitch} onValueChange={setSelectedBranchToSwitch}>
                          <SelectTrigger className="mt-2">
                            <SelectValue placeholder="Choose a branch..." />
                          </SelectTrigger>
                          <SelectContent>
                            {branches
                              .filter(b => !b.isCurrent)
                              .map((branch) => (
                                <SelectItem key={branch.fullName} value={branch.fullName}>
                                  {branch.isRemote ? '📡 ' : ''}{branch.name}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button 
                        onClick={handleSwitchBranch}
                        disabled={!selectedBranchToSwitch || checkoutMutation.isPending}
                        className="w-full"
                      >
                        {checkoutMutation.isPending ? 'Switching...' : 'Switch Branch'}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>

                <Dialog open={createBranchOpen} onOpenChange={setCreateBranchOpen}>
                  <DialogTrigger asChild>
                    <Button variant="secondary" size="sm" className="gap-1" style={{ display: 'inline-flex', alignItems: 'center', minWidth: 'auto' }}>
                      <Plus className="h-3.5 w-3.5" /> New
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-md">
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <GitBranch className="h-4 w-4" />
                        Create New Branch
                      </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                      <div>
                        <Label htmlFor="branch-name">Branch Name</Label>
                        <Input
                          id="branch-name"
                          placeholder="e.g., feature/new-feature"
                          value={newBranchName}
                          onChange={(e) => setNewBranchName(e.target.value)}
                          className="mt-2"
                        />
                      </div>
                      <Button onClick={handleCreateBranch} className="w-full">Create Branch</Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </div>

            {/* Sync Status & Actions */}
            <div className="flex items-center gap-2">
              {remoteStatus?.needsPull && (
                <Button
                  onClick={() => pullMutation.mutate()}
                  disabled={pullMutation.isPending}
                  size="sm"
                  className="gap-1.5"
                  style={{ display: 'inline-flex', alignItems: 'center' }}
                >
                  <ArrowDown className="h-3.5 w-3.5" />
                  Pull ({remoteStatus.behindCount})
                </Button>
              )}
              {remoteStatus?.needsPush && (
                <Button
                  onClick={() => pushMutation.mutate()}
                  disabled={pushMutation.isPending}
                  size="sm"
                  className="gap-1.5"
                  style={{ display: 'inline-flex', alignItems: 'center' }}
                >
                  <ArrowUp className="h-3.5 w-3.5" />
                  Push ({remoteStatus.aheadCount})
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                onClick={() => fetchMutation.mutate()}
                disabled={fetchMutation.isPending}
                className="gap-1.5"
                style={{ display: 'inline-flex', alignItems: 'center', minWidth: 'auto' }}
              >
                <RefreshCw className={`h-3.5 w-3.5 ${fetchMutation.isPending ? 'animate-spin' : ''}`} />
                Fetch
              </Button>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Two-column: Branches + Commits */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Branches List - Compact */}
        <Card>
          <CardBody>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Branches ({branches.length})</h3>
              <div className="flex gap-1">
                <Dialog open={deleteBranchOpen} onOpenChange={setDeleteBranchOpen}>
                  <DialogTrigger asChild>
                    <button className="p-1 rounded hover:bg-muted" title="Delete branch">
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-md">
                    <DialogHeader><DialogTitle>Delete Branch</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                      <Select value={selectedBranchToDelete} onValueChange={setSelectedBranchToDelete}>
                        <SelectTrigger><SelectValue placeholder="Select branch..." /></SelectTrigger>
                        <SelectContent>
                          {branches.filter(b => b.name !== 'main' && !b.isCurrent).map(b => (
                            <SelectItem key={b.fullName} value={b.fullName}>{b.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button onClick={handleDeleteBranch} disabled={!selectedBranchToDelete} variant="destructive" className="w-full">Delete</Button>
                    </div>
                  </DialogContent>
                </Dialog>
                <Dialog open={mergeBranchOpen} onOpenChange={setMergeBranchOpen}>
                  <DialogTrigger asChild>
                    <button className="p-1 rounded hover:bg-muted" title="Merge branch">
                      <Merge className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-md">
                    <DialogHeader>
                      <DialogTitle>Merge into {currentBranch}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                      <Select value={mergeBranchSource} onValueChange={setMergeBranchSource}>
                        <SelectTrigger><SelectValue placeholder="Select branch to merge..." /></SelectTrigger>
                        <SelectContent>
                          {branches.filter(b => !b.isCurrent).map(b => (
                            <SelectItem key={b.fullName} value={b.fullName}>{b.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button onClick={handleMergeBranch} disabled={!mergeBranchSource} className="w-full">Merge</Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
            {branchesLoading ? (
              <div className="text-center text-muted-foreground py-4 text-sm">Loading...</div>
            ) : (
              <div className="space-y-1 max-h-[400px] overflow-y-auto">
                {/* Local branches first, then remote */}
                {branches.filter(b => !b.isRemote).map(branch => (
                  <div
                    key={branch.fullName}
                    className={`px-2.5 py-1.5 rounded text-sm font-mono cursor-pointer transition-colors flex items-center justify-between ${
                      branch.isCurrent
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-foreground'
                    }`}
                    onClick={() => {
                      if (!branch.isCurrent) {
                        setSelectedBranchToSwitch(branch.fullName);
                        checkoutMutation.mutate(branch.fullName);
                      }
                    }}
                  >
                    <span className="truncate">{branch.name}</span>
                    {branch.isCurrent && <span className="text-xs ml-1">●</span>}
                  </div>
                ))}
                {branches.filter(b => b.isRemote).length > 0 && (
                  <>
                    <div className="text-xs text-muted-foreground font-semibold uppercase mt-3 mb-1 px-2">Remote</div>
                    {branches.filter(b => b.isRemote).map(branch => (
                      <div
                        key={branch.fullName}
                        className="px-2.5 py-1.5 rounded text-sm font-mono hover:bg-muted text-muted-foreground cursor-pointer transition-colors truncate"
                        onClick={() => {
                          setSelectedBranchToSwitch(branch.fullName);
                          checkoutMutation.mutate(branch.fullName);
                        }}
                      >
                        {branch.name}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Recent Commits */}
        <Card className="lg:col-span-2">
          <CardBody>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold">Recent Commits</h3>
              <Dialog open={commitDialogOpen} onOpenChange={setCommitDialogOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5" style={{ display: 'inline-flex', alignItems: 'center', minWidth: 'auto' }}>
                    <GitCommit className="h-3.5 w-3.5" /> New Commit
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <GitCommit className="h-5 w-5" />
                      Create Commit
                    </DialogTitle>
                    <DialogDescription>
                      Commit your staged changes to the repository
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 mt-4">
                    <div>
                      <Label>Commit Message</Label>
                      <Textarea
                        placeholder="Describe your changes..."
                        value={commitMessage}
                        onChange={(e) => setCommitMessage(e.target.value)}
                        rows={4}
                        className="mt-2"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button 
                        onClick={() => commitMutation.mutate(commitMessage)}
                        disabled={!commitMessage.trim() || commitMutation.isPending}
                        className="flex-1"
                      >
                        {commitMutation.isPending ? 'Creating...' : 'Create Commit'}
                      </Button>
                      <Button 
                        onClick={generateCommitMessage}
                        disabled={isGenerating}
                        variant="outline"
                        className="gap-1.5"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        AI Suggest
                      </Button>
                    </div>
                    {aiCommitSuggestion && (
                      <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <pre className="text-sm whitespace-pre-wrap font-mono">{aiCommitSuggestion}</pre>
                        <Button 
                          size="sm" variant="secondary" className="mt-2"
                          onClick={() => setCommitMessage(aiCommitSuggestion)}
                        >Use This</Button>
                      </div>
                    )}
                  </div>
                </DialogContent>
              </Dialog>
            </div>
            
            {commitsLoading ? (
              <div className="text-center text-muted-foreground py-4 text-sm">Loading commits...</div>
            ) : commits.length === 0 ? (
              <div className="text-center text-muted-foreground py-4 text-sm">No commits found</div>
            ) : (
              <div className="space-y-2 max-h-[400px] overflow-y-auto">
                {commits.map((commit, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-muted/50 transition-colors">
                    <div className="mt-0.5">
                      <GitCommit className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{commit.message}</p>
                      <div className="flex gap-2 items-center mt-0.5">
                        <code className="text-xs text-muted-foreground bg-muted px-1 rounded">{commit.shortHash}</code>
                        <span className="text-xs text-muted-foreground">{commit.author}</span>
                        <span className="text-xs text-muted-foreground ml-auto">{commit.date}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* AI Git Features - Compact grid */}
      <Card>
        <CardBody>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">AI-Powered Git Tools</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {/* AI Code Review */}
            <Dialog open={codeReviewOpen} onOpenChange={setCodeReviewOpen}>
              <DialogTrigger asChild>
                <button className="flex flex-col items-start p-3 rounded-lg border border-border hover:border-primary hover:shadow-md transition-all bg-card text-left">
                  <FileSearch className="h-4 w-4 text-primary mb-1" />
                  <span className="text-sm font-medium">Code Review</span>
                  <span className="text-xs text-muted-foreground">AI analysis of changes</span>
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <FileSearch className="h-5 w-5" />
                    AI Code Review
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 mt-4">
                  <div className="p-3 border border-green-500 bg-green-50 dark:bg-green-950 rounded-lg">
                    <h4 className="font-semibold text-green-700 dark:text-green-300 text-sm mb-1">✓ Strengths</h4>
                    <ul className="text-xs space-y-1 text-green-700 dark:text-green-300">
                      <li>• Good TypeScript types for type safety</li>
                      <li>• Proper error handling with try-catch</li>
                      <li>• Clean separation of concerns</li>
                    </ul>
                  </div>
                  <div className="p-3 border border-yellow-500 bg-yellow-50 dark:bg-yellow-950 rounded-lg">
                    <h4 className="font-semibold text-yellow-700 dark:text-yellow-300 text-sm mb-1">⚠ Suggestions</h4>
                    <ul className="text-xs space-y-1 text-yellow-700 dark:text-yellow-300">
                      <li>• Add input validation in auth.ts</li>
                      <li>• Optimize database query in user.service.ts</li>
                    </ul>
                  </div>
                  <div className="p-3 border border-red-500 bg-red-50 dark:bg-red-950 rounded-lg">
                    <h4 className="font-semibold text-red-700 dark:text-red-300 text-sm mb-1">⚡ Security</h4>
                    <ul className="text-xs space-y-1 text-red-700 dark:text-red-300">
                      <li>• Potential SQL injection — use parameterized queries</li>
                      <li>• Hardcoded API key — use env variables</li>
                    </ul>
                  </div>
                </div>
              </DialogContent>
            </Dialog>

            {/* AI PR Description */}
            <Dialog open={prDescriptionOpen} onOpenChange={setPrDescriptionOpen}>
              <DialogTrigger asChild>
                <button className="flex flex-col items-start p-3 rounded-lg border border-border hover:border-primary hover:shadow-md transition-all bg-card text-left">
                  <GitPullRequest className="h-4 w-4 text-primary mb-1" />
                  <span className="text-sm font-medium">PR Description</span>
                  <span className="text-xs text-muted-foreground">Auto-generate PR text</span>
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <GitPullRequest className="h-5 w-5" />
                    Generate PR Description
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-4 mt-4">
                  <Button onClick={() => {
                    toast({ title: "Generating Description", description: "Analyzing changes..." });
                  }}>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Generate
                  </Button>
                  <div>
                    <Label>Generated Description</Label>
                    <Textarea
                      defaultValue={`## Overview\nImplements user authentication with JWT tokens.\n\n## Changes\n- JWT auth middleware\n- Login/logout endpoints\n- Refresh token mechanism\n\n## Testing\n- ✓ Unit tests for auth service\n- ✓ Integration tests for login flow`}
                      rows={10}
                      className="mt-2 font-mono text-sm"
                    />
                  </div>
                </div>
              </DialogContent>
            </Dialog>

            {/* AI Issue Analysis */}
            <Dialog open={issueAnalysisOpen} onOpenChange={setIssueAnalysisOpen}>
              <DialogTrigger asChild>
                <button className="flex flex-col items-start p-3 rounded-lg border border-border hover:border-primary hover:shadow-md transition-all bg-card text-left">
                  <MessageSquare className="h-4 w-4 text-primary mb-1" />
                  <span className="text-sm font-medium">Issue Analysis</span>
                  <span className="text-xs text-muted-foreground">AI bug & feature insights</span>
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <MessageSquare className="h-5 w-5" />
                    AI Issue Analysis
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-2 mt-4">
                  {[
                    { id: '#45', title: 'Login page crashes on mobile', priority: 'High' },
                    { id: '#44', title: 'Add dark mode support', priority: 'Medium' },
                    { id: '#43', title: 'Performance issues on dashboard', priority: 'High' },
                  ].map((issue) => (
                    <div key={issue.id} className="p-3 border rounded-lg hover:bg-muted cursor-pointer flex justify-between items-center">
                      <div>
                        <span className="font-mono text-xs text-muted-foreground">{issue.id}</span>
                        <p className="text-sm font-medium">{issue.title}</p>
                      </div>
                      <Badge variant={issue.priority === 'High' ? 'destructive' : 'secondary'}>{issue.priority}</Badge>
                    </div>
                  ))}
                </div>
              </DialogContent>
            </Dialog>

            {/* AI Refactor Suggestions */}
            <Dialog open={refactorSuggestionsOpen} onOpenChange={setRefactorSuggestionsOpen}>
              <DialogTrigger asChild>
                <button className="flex flex-col items-start p-3 rounded-lg border border-border hover:border-primary hover:shadow-md transition-all bg-card text-left">
                  <Zap className="h-4 w-4 text-primary mb-1" />
                  <span className="text-sm font-medium">Refactor</span>
                  <span className="text-xs text-muted-foreground">Code improvement tips</span>
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <Zap className="h-5 w-5" />
                    AI Refactoring Suggestions
                  </DialogTitle>
                </DialogHeader>
                <div className="space-y-3 mt-4">
                  <div className="p-3 border rounded-lg">
                    <h4 className="font-semibold text-sm mb-1">🔄 Extract Reusable Components</h4>
                    <p className="text-xs text-muted-foreground">3 instances of similar code can be shared</p>
                    <Button size="sm" variant="secondary" className="mt-2">Apply</Button>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <h4 className="font-semibold text-sm mb-1">⚡ Performance Optimization</h4>
                    <p className="text-xs text-muted-foreground">Use React.memo() to prevent re-renders</p>
                    <Button size="sm" variant="secondary" className="mt-2">Apply</Button>
                  </div>
                  <div className="p-3 border rounded-lg">
                    <h4 className="font-semibold text-sm mb-1">📦 Simplify State</h4>
                    <p className="text-xs text-muted-foreground">Combine useState calls into useReducer</p>
                    <Button size="sm" variant="secondary" className="mt-2">Apply</Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </CardBody>
      </Card>
    </div>
  );
};
