import { useState } from 'react';
import {
  Page,
  PageSection,
  Card,
  CardBody,
  CardTitle,
  Grid,
  GridItem,
} from '@patternfly/react-core';
import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { MetricsCards } from '@/components/dashboard/MetricsCards';
import { DataTable } from '@/components/dashboard/DataTable';
import { AnalyticsChart } from '@/components/dashboard/AnalyticsChart';
import { Home } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';

const Dashboard = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <Page 
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />} 
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
    >
      <PageSection variant="default">
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          <PageHeader
            title="Welcome to Everflow AI Platform!"
            description="Everflow serves as the central hub where employees can build, showcase, and share applications leveraging artificial intelligence. Each application goes through a structured approval process managed by leadership to ensure quality, alignment with Everflows's mission, and adherence to our Code of Conduct."
            icon={<Home size={36} style={{ color: 'var(--pf-v6-global--primary-color--100)' }} />}
          />

          <Grid hasGutter>
            <GridItem span={12}>
              <Card>
                <CardTitle style={{ fontSize: '1.5rem' }}>What is Everflow?</CardTitle>
                <CardBody>
                  <p style={{ lineHeight: '1.6' }}>
                    Everflow serves as the central hub where teams can build, showcase, and share applications leveraging artificial intelligence. 
                    Each application goes through a structured approval process managed by leadership to ensure quality, alignment with Everflow's mission, 
                    and adherence to our Code of Conduct.
                  </p>
                </CardBody>
              </Card>
            </GridItem>

            <GridItem span={12}>
              <Card>
                <CardTitle style={{ fontSize: '1.5rem' }}>Key Features:</CardTitle>
                <CardBody>
                  <div style={{ lineHeight: '1.8' }}>
                    <div style={{ marginBottom: '1rem' }}>
                      <strong style={{ fontSize: '1.1rem' }}>• Centralized Innovation Hub:</strong>
                      <p style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                        Create and publish AI-powered applications that drive innovation within Everflow.
                      </p>
                    </div>
                    <div style={{ marginBottom: '1rem' }}>
                      <strong style={{ fontSize: '1.1rem' }}>• Comprehensive Approval Process:</strong>
                      <p style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                        Every application undergoes manager-level review, ensuring adherence to quality, security, and strategic alignment.
                      </p>
                    </div>
                    <div style={{ marginBottom: '1rem' }}>
                      <strong style={{ fontSize: '1.1rem' }}>• AI-Driven Standardization:</strong>
                      <p style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                        Everflow leverages advanced AI tools and standards, ensuring consistency, efficiency, and compliance across all projects.
                      </p>
                    </div>
                    <div>
                      <strong style={{ fontSize: '1.1rem' }}>• Project Collaboration & Forking:</strong>
                      <p style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                        Employees can easily fork existing projects, promoting collaboration, iteration, and continuous improvement.
                      </p>
                    </div>
                  </div>
                </CardBody>
              </Card>
            </GridItem>

            <GridItem span={12}>
              <Card>
                <CardTitle style={{ fontSize: '1.5rem' }}>Empowering Our Teams</CardTitle>
                <CardBody>
                  <p style={{ lineHeight: '1.6', fontSize: '1.05rem' }}>
                    Everflow is more than a platform—it&apos;s a catalyst for innovation, designed to accelerate the pace at which groundbreaking 
                    ideas are transformed into impactful solutions. Join Everflow and be at the forefront of AI innovation at Everflow.
                  </p>
                </CardBody>
              </Card>
            </GridItem>
          </Grid>
        </div>
      </PageSection>
    </Page>
  );
};

export default Dashboard;
