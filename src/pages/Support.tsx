import { useState } from 'react';
import { Page, PageSection, Card, CardBody, CardTitle, Grid, GridItem } from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { LifeBuoy } from 'lucide-react';
import supportData from '@/data/supportData.json';
import PageHeader from '@/components/ui/PageHeader';

const Support = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <PageHeader
          title="Support"
          description="Get help with the platform, find documentation, and contact support teams."
          icon={<LifeBuoy size={32} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
        />
        <Grid hasGutter>
          {supportData.supportOptions.map((option) => (
            <GridItem key={option.id} span={12} md={6}>
              <Card isClickable>
                <CardTitle>{option.title}</CardTitle>
                <CardBody>{option.description}</CardBody>
              </Card>
            </GridItem>
          ))}
        </Grid>
      </PageSection>
    </Page>
  );
};

export default Support;
