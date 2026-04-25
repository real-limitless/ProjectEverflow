import { useState } from 'react';
import { Page, PageSection, Card, CardBody, Button, Label } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useParams, Link, useNavigate } from 'react-router-dom';
import collaborationData from '@/data/collaborationData.json';
import { MessageSquare } from 'lucide-react';
import NotFound from '@/pages/NotFound';
import { CompactPageHeader } from '@/components/ui/compact-page-header';

const ViewDiscussion = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { id } = useParams();
  const navigate = useNavigate();
  const discussion = collaborationData.discussions.find(d => d.id === parseInt(id, 10));

  if (!discussion) {
    return <NotFound />;
  }

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <CompactPageHeader
          title={discussion.title}
          subtitle={`Discussion by ${discussion.author}`}
          backLink={{
            label: 'Back to Collaboration Hub',
            onClick: () => navigate('/collaboration-hub'),
          }}
        />

        <Card>
          <CardBody>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem', color: 'var(--pf-v6-global--Color--200)', marginBottom: '1rem' }}>
              <span>By <strong>{discussion.author}</strong></span>
              <span>•</span>
              <span>{discussion.replies} replies</span>
              <span>•</span>
              <span>{discussion.views} views</span>
              <span>•</span>
              <span>{discussion.lastActivity}</span>
              <Label color="blue">{discussion.category}</Label>
            </div>
            <div style={{ borderTop: '1px solid var(--pf-v6-global--BorderColor--100)', paddingTop: '1rem' }}>
                <p>{discussion.content || "No content available for this discussion."}</p>
            </div>
          </CardBody>
        </Card>

        <div style={{ marginTop: '2rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem' }}>Replies</h2>
            {/* Placeholder for replies. In a real app, you would map over replies data */}
            <Card>
                <CardBody>
                    <p>Reply functionality would be implemented here.</p>
                </CardBody>
            </Card>
        </div>
      </PageSection>
    </Page>
  );
};

export default ViewDiscussion;
