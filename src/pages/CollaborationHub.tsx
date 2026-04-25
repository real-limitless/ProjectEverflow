import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Grid, GridItem, Button, Label, Gallery, GalleryItem, Avatar, Tooltip } from '@patternfly/react-core';
import { Table, Thead, Tbody, Tr, Th, Td } from '@patternfly/react-table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Users, Flame, ThumbsUp, Bookmark, MessageSquare, Eye, Clock, Loader2 } from 'lucide-react';
import { SearchInput } from '@patternfly/react-core';
import { Link } from 'react-router-dom';
import { PlusCircleIcon } from '@patternfly/react-icons';
import { useQuery } from '@tanstack/react-query';
import { getDiscussions, getProjects, Discussion, Project } from '@/lib/api';
import { toast } from '@/hooks/use-toast';

const CollaborationHub = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [votes, setVotes] = useState<Record<number, number>>({});
  const [bookmarks, setBookmarks] = useState<Record<number, boolean>>({});
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [activeSortIndex, setActiveSortIndex] = useState<number | null>(null);
  const [activeSortDirection, setActiveSortDirection] = useState<'asc' | 'desc'>('asc');

  // Fetch discussions from API
  const { data: discussionsResponse, isLoading: discussionsLoading, error: discussionsError } = useQuery({
    queryKey: ['discussions'],
    queryFn: getDiscussions,
  });

  // Fetch projects for forked projects section
  const { data: projectsResponse, isLoading: projectsLoading, error: projectsError } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  const discussions = discussionsResponse?.data || [];
  const projects = projectsResponse?.data || [];

  // Get unique categories from discussions
  const categories = ['All', ...new Set(discussions.map(d => d.category))];

  // Filter discussions based on search term and category
  const filteredDiscussions = discussions.filter((discussion: Discussion) => {
    const matchesSearch = discussion.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      discussion.author.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      discussion.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      discussion.content.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'All' || discussion.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  // Sort discussions
  const sortedDiscussions = [...filteredDiscussions].sort((a: Discussion, b: Discussion) => {
    if (activeSortIndex === null) return 0;
    const direction = activeSortDirection === 'asc' ? 1 : -1;
    switch (activeSortIndex) {
      case 0: // Title
        return a.title.localeCompare(b.title) * direction;
      case 1: // Author
        return a.author.username.localeCompare(b.author.username) * direction;
      case 2: // Replies
        return (a.replies - b.replies) * direction;
      case 3: // Views
        return (a.views - b.views) * direction;
      case 4: // Last Activity
        return (new Date(a.last_activity).getTime() - new Date(b.last_activity).getTime()) * direction;
      default:
        return 0;
    }
  });

  // Get trending discussions (based on replies + views)
  const trendingDiscussions = discussions
    .map((d: Discussion) => ({ ...d, score: d.replies * 2 + d.views }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  // Get forked projects (projects that have contributors besides the owner)
  const forkedProjects = projects.filter((project: Project) =>
    project.contributors && project.contributors.length > 0
  );

  const handleVote = (id: number) => {
    setVotes(prev => ({ ...prev, [id]: (prev[id] || 0) + 1 }));
    toast({
      title: "Vote Recorded",
      description: "Thank you for your vote!",
    });
  };

  const handleBookmark = (id: number) => {
    setBookmarks(prev => ({ ...prev, [id]: !prev[id] }));
    toast({
      title: bookmarks[id] ? "Bookmark Removed" : "Bookmarked",
      description: bookmarks[id] ? "Discussion removed from bookmarks" : "Discussion added to bookmarks",
    });
  };

  const handleViewDiscussion = (id: number) => {
    // TODO: Navigate to discussion detail page
    toast({
      title: "View Discussion",
      description: "Opening discussion details...",
    });
  };

  const handleCreateDiscussion = () => {
    // TODO: Navigate to create discussion page
    toast({
      title: "Create Discussion",
      description: "Opening discussion creation form...",
    });
  };

  const getCategoryColor = (category: string): 'blue' | 'green' | 'red' | 'grey' => {
    const colors: Record<string, 'blue' | 'green' | 'red' | 'grey'> = { 
      'General': 'blue', 
      'AI Ethics': 'green', 
      'Bug Reports': 'red' 
    };
    return colors[category] || 'grey';
  };

  const handleSort = (index: number) => {
    if (activeSortIndex === index) {
      setActiveSortDirection(activeSortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setActiveSortIndex(index);
      setActiveSortDirection('asc');
    }
  };

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.75rem', margin: 0 }}>
              <Users size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />
              Collaboration Hub
            </h1>
            <p style={{ fontSize: '1rem', margin: '0.25rem 0 0 0', color: 'var(--pf-v6-global--Color--200)' }}>
              Connect with colleagues, share ideas, and collaborate on AI projects
            </p>
          </div>
          <Button 
            variant="primary" 
            icon={<PlusCircleIcon />}
            component={Link} 
            to="/create-discussion"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            Create Discussion
          </Button>
        </div>

        {/* Trending Discussions */}
        <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center' }}>
          <Flame size={20} style={{ marginRight: '0.5rem' }} /> Trending Discussions
        </h2>
        <Grid hasGutter style={{ marginBottom: '2rem' }}>
          {trendingDiscussions.map((discussion) => (
            <GridItem key={discussion.id} span={12} md={6} lg={4}>
              <Card isCompact>
                <CardTitle>
                  <Link 
                    to={`/view-discussion/${discussion.id}`}
                    style={{ 
                      textDecoration: 'none', 
                      color: 'var(--pf-v6-global--Color--100)',
                      fontWeight: 500,
                      fontSize: '1rem'
                    }}
                  >
                    {discussion.title}
                  </Link>
                </CardTitle>
                <CardBody>
                  <div style={{ 
                    display: 'flex', 
                    gap: '0.5rem', 
                    fontSize: '0.875rem',
                    color: 'var(--pf-v6-global--Color--200)'
                  }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <MessageSquare size={14} />
                      {discussion.replies} replies
                    </span>
                    <span>•</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Eye size={14} />
                      {discussion.views} views
                    </span>
                  </div>
                  <div style={{ marginTop: '0.75rem' }}>
                    <Button 
                      variant="link" 
                      component={Link} 
                      to={`/view-discussion/${discussion.id}`}
                      style={{ padding: 0, fontSize: '0.875rem' }}
                    >
                      View
                    </Button>
                  </div>
                </CardBody>
              </Card>
            </GridItem>
          ))}
        </Grid>

        {/* Forum-style Thread Browser */}
        <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem', marginTop: '2rem' }}>Browse Threads</h2>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
          <SearchInput
            placeholder="Search threads by title, author, or category..."
            value={searchTerm}
            onChange={(_event, value) => setSearchTerm(value)}
            onClear={() => setSearchTerm('')}
            style={{ flex: 1 }}
          />
          <Select value={selectedCategory} onValueChange={setSelectedCategory}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by category" />
            </SelectTrigger>
            <SelectContent>
              {categories.map(cat => (
                <SelectItem key={cat} value={cat}>
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Table aria-label="Forum threads" variant="compact">
          <Thead>
            <Tr>
              <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(0)}>
                Thread Title {activeSortIndex === 0 && (activeSortDirection === 'asc' ? '↑' : '↓')}
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
              <Th style={{ cursor: 'pointer' }} onClick={() => handleSort(4)}>
                Last Activity {activeSortIndex === 4 && (activeSortDirection === 'asc' ? '↑' : '↓')}
              </Th>
              <Th>Actions</Th>
            </Tr>
          </Thead>
          <Tbody>
            {discussionsLoading ? (
              <Tr>
                <Td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                  <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
                  <span>Loading discussions...</span>
                </Td>
              </Tr>
            ) : discussionsError ? (
              <Tr>
                <Td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--pf-v6-global--danger-color--100)' }}>
                  Error loading discussions: {discussionsError.message}
                </Td>
              </Tr>
            ) : sortedDiscussions.length === 0 ? (
              <Tr>
                <Td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--pf-v6-global--Color--200)' }}>
                  No discussions found matching your criteria.
                </Td>
              </Tr>
            ) : (
              sortedDiscussions.map((discussion: Discussion) => (
                <Tr key={discussion.id}>
                  <Td>
                    <div>
                      <div style={{ marginBottom: '0.25rem' }}>
                        <Link
                          to={`/view-discussion/${discussion.id}`}
                          style={{ fontWeight: 600, textDecoration: 'none', color: 'var(--pf-v6-global--link--Color)' }}
                        >
                          {discussion.title}
                        </Link>
                        {discussion.is_pinned && (
                          <span style={{ marginLeft: '0.5rem', color: 'var(--pf-v6-global--warning-color--100)' }}>📌</span>
                        )}
                        {discussion.is_locked && (
                          <span style={{ marginLeft: '0.25rem', color: 'var(--pf-v6-global--Color--200)' }}>🔒</span>
                        )}
                      </div>
                      <Label color={getCategoryColor(discussion.category)} isCompact>
                        {discussion.category}
                      </Label>
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Tooltip content={`Role: ${discussion.author.role || 'Contributor'}`}>
                        <Avatar
                          src={discussion.author.avatar || '/default-avatar.png'}
                          alt={`${discussion.author.first_name} ${discussion.author.last_name}`}
                          size="sm"
                        />
                      </Tooltip>
                      <span>{discussion.author.first_name} {discussion.author.last_name}</span>
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <MessageSquare size={14} />
                      {discussion.replies}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Eye size={14} />
                      {discussion.views}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      <Clock size={14} />
                      {new Date(discussion.last_activity).toLocaleDateString()}
                    </div>
                  </Td>
                  <Td>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <Tooltip content="Upvote">
                        <Button variant="plain" onClick={() => handleVote(discussion.id)}>
                          <ThumbsUp size={16} />
                          <span style={{ marginLeft: '0.25rem' }}>{votes[discussion.id] || 0}</span>
                        </Button>
                      </Tooltip>
                      <Tooltip content={bookmarks[discussion.id] ? "Remove bookmark" : "Bookmark thread"}>
                        <Button variant="plain" onClick={() => handleBookmark(discussion.id)}>
                          <Bookmark size={16} fill={bookmarks[discussion.id] ? 'currentColor' : 'none'} />
                        </Button>
                      </Tooltip>
                    </div>
                  </Td>
                </Tr>
              ))
            )}
          </Tbody>
        </Table>

        {/* Collaborative Projects */}
        <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem', marginTop: '2rem' }}>Collaborative Projects</h2>
        {projectsLoading ? (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
            <span>Loading projects...</span>
          </div>
        ) : projectsError ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--pf-v6-global--danger-color--100)' }}>
            Error loading projects: {projectsError.message}
          </div>
        ) : forkedProjects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--pf-v6-global--Color--200)' }}>
            No collaborative projects found.
          </div>
        ) : (
          <Grid hasGutter>
            {forkedProjects.slice(0, 6).map((project: Project) => (
              <GridItem key={project.id} span={12} md={6}>
                <Card>
                  <CardTitle>{project.name}</CardTitle>
                  <CardBody>
                    <div style={{ marginBottom: '0.75rem' }}>
                      <strong>Description:</strong> {project.description || 'No description available'}
                    </div>
                    <div style={{ marginBottom: '0.5rem' }}>
                      <strong>Owner:</strong> {project.owner.first_name} {project.owner.last_name}
                    </div>
                    <div style={{ marginBottom: '0.5rem' }}>
                      <strong>Contributors:</strong> {project.contributors.length}
                    </div>
                    <div style={{ marginBottom: '0.5rem' }}>
                      <strong>Status:</strong> {project.status.replace('_', ' ')}
                    </div>
                    <div style={{ marginTop: '0.75rem' }}>
                      <Label
                        color={
                          project.status === 'published' ? 'green' :
                          project.status === 'in_development' ? 'blue' :
                          project.status === 'awaiting_approval' ? 'orange' : 'grey'
                        }
                        isCompact
                      >
                        {project.status.replace('_', ' ')}
                      </Label>
                    </div>
                    <div style={{ marginTop: '1rem' }}>
                      <Button
                        variant="link"
                        style={{ padding: 0 }}
                        component={Link}
                        to={project.organization ? `/organizations/${project.organization.id}/projects/${project.id}` : '/organizations'}
                      >
                        Open Project
                      </Button>
                    </div>
                  </CardBody>
                </Card>
              </GridItem>
            ))}
          </Grid>
        )}
      </PageSection>
    </Page>
  );
};

export default CollaborationHub;
