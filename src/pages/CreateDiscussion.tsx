import { useState } from 'react';
import { Page, PageSection, Card, CardBody, Button, TextInput, TextArea, Form, FormGroup, ActionGroup } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { useNavigate } from 'react-router-dom';
import { MessageSquarePlus } from 'lucide-react';

const CreateDiscussion = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [newDiscussionTitle, setNewDiscussionTitle] = useState('');
  const [newDiscussionContent, setNewDiscussionContent] = useState('');
  const navigate = useNavigate();

  const handleCreateDiscussion = () => {
    // In a real app, this would send data to the backend
    console.log('Creating discussion:', { title: newDiscussionTitle, content: newDiscussionContent });
    // Here you would typically add the new discussion to your data source
    // and then navigate back to the collaboration hub
    navigate('/collaboration-hub');
  };

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <h1 style={{ fontSize: '2rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
          <MessageSquarePlus size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />
          Create New Discussion
        </h1>
        <Card>
          <CardBody>
            <Form>
              <FormGroup label="Discussion Title" isRequired fieldId="discussion-title">
                <TextInput
                  isRequired
                  type="text"
                  id="discussion-title"
                  name="discussion-title"
                  value={newDiscussionTitle}
                  onChange={(_event, value) => setNewDiscussionTitle(value)}
                />
              </FormGroup>
              <FormGroup label="Initial Post Content" isRequired fieldId="discussion-content">
                <TextArea
                  isRequired
                  id="discussion-content"
                  name="discussion-content"
                  value={newDiscussionContent}
                  onChange={(_event, value) => setNewDiscussionContent(value)}
                  rows={10}
                />
              </FormGroup>
              <ActionGroup>
                <Button variant="primary" onClick={handleCreateDiscussion}>Create Discussion</Button>
                <Button variant="link" onClick={() => navigate('/collaboration-hub')}>Cancel</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
    </Page>
  );
};

export default CreateDiscussion;
