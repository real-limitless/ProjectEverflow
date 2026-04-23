import { useState, useEffect } from 'react';
import { Page, PageSection } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import PageHeader from '@/components/ui/PageHeader';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  BarChart,
  Activity,
  DollarSign,
  Download,
  TrendingUp,
  MessageSquare,
  Loader2,
} from 'lucide-react';
import {
  LLMProviderScope,
  UsageStats,
  DailyTrend,
  getScopeUsageStats,
  getDailyUsageTrends,
  getTeams,
  getProjects,
  Team,
  Project,
  getCurrentUser,
  User,
} from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

const LLMUsageReport = () => {
  const { toast } = useToast();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(false);

  // Filters
  const [scope, setScope] = useState<LLMProviderScope>('system');
  const [teams, setTeams] = useState<Team[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedTeam, setSelectedTeam] = useState<number | undefined>();
  const [selectedProject, setSelectedProject] = useState<number | undefined>();
  const [dateRange, setDateRange] = useState<number>(30);

  // Data
  const [usageStats, setUsageStats] = useState<UsageStats | null>(null);
  const [dailyTrends, setDailyTrends] = useState<DailyTrend[]>([]);

  useEffect(() => {
    fetchInitialData();
  }, []);

  useEffect(() => {
    if (currentUser) {
      fetchUsageData();
    }
  }, [scope, selectedTeam, selectedProject, dateRange, currentUser]);

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      const [userResult, teamsResult, projectsResult] = await Promise.all([
        getCurrentUser(),
        getTeams(),
        getProjects(),
      ]);

      if (userResult.data) setCurrentUser(userResult.data);
      if (teamsResult.data) setTeams(teamsResult.data);
      if (projectsResult.data) setProjects(projectsResult.data);
    } catch (error) {
      toast({
        title: 'Failed to Load Data',
        description: 'Unable to fetch initial data',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchUsageData = async () => {
    setStatsLoading(true);
    try {
      let scopeId: number | undefined;
      if (scope === 'team' && selectedTeam) scopeId = selectedTeam;
      if (scope === 'project' && selectedProject) scopeId = selectedProject;

      const [statsResult, trendsResult] = await Promise.all([
        getScopeUsageStats(scope, scopeId),
        getDailyUsageTrends(dateRange),
      ]);

      if (statsResult.data) setUsageStats(statsResult.data);
      if (trendsResult.data) setDailyTrends(trendsResult.data);
    } catch (error) {
      toast({
        title: 'Failed to Load Usage Data',
        description: 'Unable to fetch usage statistics',
        variant: 'destructive',
      });
    } finally {
      setStatsLoading(false);
    }
  };

  const handleScopeChange = (newScope: LLMProviderScope) => {
    setScope(newScope);
    setSelectedTeam(undefined);
    setSelectedProject(undefined);
  };

  const handleExportCSV = () => {
    if (!usageStats) return;

    const csvData = [
      ['Provider', 'Messages', 'Prompt Tokens', 'Completion Tokens', 'Total Cost (USD)'],
      ...usageStats.by_provider.map((p) => [
        p.provider_name,
        p.messages.toString(),
        p.prompt_tokens.toString(),
        p.completion_tokens.toString(),
        p.cost,
      ]),
      [''],
      ['Total', usageStats.total_messages.toString(), usageStats.total_prompt_tokens.toString(), usageStats.total_completion_tokens.toString(), usageStats.total_cost],
    ];

    const csvContent = csvData.map((row) => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `llm-usage-report-${scope}-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    toast({
      title: 'Report Exported',
      description: 'Usage report downloaded as CSV',
    });
  };

  const formatCost = (cost: string) => {
    return `$${parseFloat(cost).toFixed(4)}`;
  };

  const formatNumber = (num: number) => {
    return num.toLocaleString();
  };

  if (loading) {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </PageSection>
      </Page>
    );
  }

  if (!currentUser || currentUser.role !== 'admin') {
    return (
      <Page
        masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
        sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      >
        <PageSection variant="default">
          <div className="text-center py-12">
            <h2 className="text-2xl font-bold mb-2">Access Denied</h2>
            <p className="text-muted-foreground">
              This page is only accessible to administrators.
            </p>
          </div>
        </PageSection>
      </Page>
    );
  }

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="LLM Usage Report"
          description="Monitor AI model usage, costs, and trends across your organization"
          icon={<BarChart size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />

        {/* Filters */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Filters</CardTitle>
            <CardDescription>Customize your usage report view</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Scope Selection */}
              <div className="space-y-2">
                <Label>Scope</Label>
                <Select value={scope} onValueChange={(v) => handleScopeChange(v as LLMProviderScope)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="system">System-Wide</SelectItem>
                    <SelectItem value="team">Team</SelectItem>
                    <SelectItem value="project">Project</SelectItem>
                    <SelectItem value="user">User</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Team Selection */}
              {scope === 'team' && (
                <div className="space-y-2">
                  <Label>Team</Label>
                  <Select
                    value={selectedTeam?.toString()}
                    onValueChange={(v) => setSelectedTeam(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select team" />
                    </SelectTrigger>
                    <SelectContent>
                      {teams.map((team) => (
                        <SelectItem key={team.id} value={team.id.toString()}>
                          {team.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Project Selection */}
              {scope === 'project' && (
                <div className="space-y-2">
                  <Label>Project</Label>
                  <Select
                    value={selectedProject?.toString()}
                    onValueChange={(v) => setSelectedProject(parseInt(v))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select project" />
                    </SelectTrigger>
                    <SelectContent>
                      {projects.map((project) => (
                        <SelectItem key={project.id} value={project.id.toString()}>
                          {project.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Date Range */}
              <div className="space-y-2">
                <Label>Date Range</Label>
                <Select value={dateRange.toString()} onValueChange={(v) => setDateRange(parseInt(v))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7">Last 7 Days</SelectItem>
                    <SelectItem value="30">Last 30 Days</SelectItem>
                    <SelectItem value="90">Last 90 Days</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Export Button */}
              <div className="flex items-end">
                <Button onClick={handleExportCSV} disabled={!usageStats || statsLoading} className="w-full">
                  <Download className="mr-2 h-4 w-4" />
                  Export CSV
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {statsLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            {/* Metrics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {usageStats ? formatNumber(usageStats.total_messages) : '0'}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    AI interactions in {dateRange} days
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Prompt Tokens</CardTitle>
                  <Activity className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {usageStats ? formatNumber(usageStats.total_prompt_tokens) : '0'}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Input tokens consumed
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Completion Tokens</CardTitle>
                  <TrendingUp className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {usageStats ? formatNumber(usageStats.total_completion_tokens) : '0'}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Output tokens generated
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                  <DollarSign className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {usageStats ? formatCost(usageStats.total_cost) : '$0.00'}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Estimated spend (USD)
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Daily Trend Chart */}
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>Daily Cost Trend</CardTitle>
                <CardDescription>
                  LLM usage costs over the last {dateRange} days
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dailyTrends.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={dailyTrends}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      />
                      <YAxis tickFormatter={(value) => `$${value.toFixed(2)}`} />
                      <Tooltip
                        formatter={(value: any) => [`$${parseFloat(value).toFixed(4)}`, 'Cost']}
                        labelFormatter={(label) => new Date(label).toLocaleDateString()}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="cost"
                        stroke="hsl(var(--primary))"
                        strokeWidth={2}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                        name="Cost (USD)"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-64 text-muted-foreground">
                    No usage data available for the selected period
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Provider Breakdown Table */}
            <Card>
              <CardHeader>
                <CardTitle>Provider Breakdown</CardTitle>
                <CardDescription>
                  Usage statistics by LLM provider
                </CardDescription>
              </CardHeader>
              <CardContent>
                {usageStats && usageStats.by_provider.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Provider</TableHead>
                        <TableHead className="text-right">Messages</TableHead>
                        <TableHead className="text-right">Prompt Tokens</TableHead>
                        <TableHead className="text-right">Completion Tokens</TableHead>
                        <TableHead className="text-right">Cost</TableHead>
                        <TableHead className="text-right">% of Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {usageStats.by_provider.map((provider) => {
                        const percentage = usageStats.total_cost !== '0'
                          ? ((parseFloat(provider.cost) / parseFloat(usageStats.total_cost)) * 100).toFixed(1)
                          : '0';
                        return (
                          <TableRow key={provider.provider_id}>
                            <TableCell className="font-medium">
                              {provider.provider_name}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(provider.messages)}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(provider.prompt_tokens)}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatNumber(provider.completion_tokens)}
                            </TableCell>
                            <TableCell className="text-right">
                              {formatCost(provider.cost)}
                            </TableCell>
                            <TableCell className="text-right">
                              <Badge variant="outline">{percentage}%</Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                      <TableRow className="font-bold bg-muted/50">
                        <TableCell>Total</TableCell>
                        <TableCell className="text-right">
                          {formatNumber(usageStats.total_messages)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(usageStats.total_prompt_tokens)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(usageStats.total_completion_tokens)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCost(usageStats.total_cost)}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge>100%</Badge>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                ) : (
                  <div className="text-center py-12 text-muted-foreground">
                    No provider usage data available
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </PageSection>
    </Page>
  );
};

export default LLMUsageReport;
