import { useState } from 'react';
import { Page, PageSection, Card, CardBody } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import notificationsData from '@/data/notifications.json';
import { Bell } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';

const Notifications = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const notifications = notificationsData.notifications;

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="Notifications"
          description="Stay updated with the latest activity, approvals, and messages from your projects."
          icon={<Bell size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />
        {notifications.map((notif) => (
          <Card key={notif.id} style={{ marginBottom: '1rem' }}>
            <CardBody>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>{notif.message}</div>
                <div style={{ fontSize: '0.875rem', color: 'var(--pf-v6-global--Color--200)' }}>
                  {notif.time}
                </div>
              </div>
            </CardBody>
          </Card>
        ))}
      </PageSection>
    </Page>
  );
};

export default Notifications;
