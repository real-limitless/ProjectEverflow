import { useState } from 'react';
import { Page, PageSection } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { EnterpriseChatbotShell } from '@/components/chatbot/EnterpriseChatbotShell';

const EnterpriseChatbot = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <EnterpriseChatbotShell />
      </PageSection>
    </Page>
  );
};

export default EnterpriseChatbot;
