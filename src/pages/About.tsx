import { useState } from 'react';
import { Page, PageSection, Card, CardBody } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { Info } from 'lucide-react';
import aboutData from '@/data/aboutData.json';
import PageHeader from '@/components/ui/PageHeader';

const About = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="About"
          description="Learn more about the Everflow AI Platform and its features."
          icon={<Info size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />
        <Card>
          <CardBody>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '1rem' }}>{aboutData.about.title}</h2>
            <p style={{ marginBottom: '1rem' }}>
              Version {aboutData.about.version}
            </p>
            <p style={{ marginBottom: '1rem' }}>
              {aboutData.about.description}
            </p>
            <p>
              {aboutData.about.additionalInfo}
            </p>
          </CardBody>
        </Card>
      </PageSection>
    </Page>
  );
};

export default About;
