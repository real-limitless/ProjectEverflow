import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Page, PageSection, Spinner } from '@patternfly/react-core';

import { DashboardHeader } from '@/components/dashboard/DashboardHeader';
import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useOrganizationHierarchyData } from '@/hooks/useOrganizationHierarchyData';
import {
  buildAppOverviewPath,
  buildEnvironmentPath,
  buildOrganizationPath,
  buildProjectPath,
} from '@/lib/organizationPaths';
import { ApplicationWorkspace } from '@/pages/EditApplication';

const AppWorkspacePage = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const navigate = useNavigate();
  const {
    appsLoading,
    environmentsLoading,
    organizationsLoading,
    projectsLoading,
    selectedApp,
    selectedAppId,
    selectedEnvironment,
    selectedEnvironmentId,
    selectedOrgId,
    selectedOrganization,
    selectedProject,
    selectedProjectId,
  } = useOrganizationHierarchyData();

  const isLoadingSelection =
    organizationsLoading ||
    (selectedOrgId !== null && projectsLoading) ||
    (selectedProjectId !== null && environmentsLoading) ||
    (selectedEnvironmentId !== null && appsLoading);

  const overviewPath =
    selectedOrgId !== null &&
    selectedProjectId !== null &&
    selectedEnvironmentId !== null &&
    selectedAppId !== null
      ? buildAppOverviewPath(selectedOrgId, selectedProjectId, selectedEnvironmentId, selectedAppId)
      : '/organizations';

  return (
    <Page
      masthead={<DashboardHeader onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)} />}
      sidebar={<DashboardSidebar isOpen={isSidebarOpen} />}
      mainAriaLabel="Application workspace"
      isContentFilled
    >
      <PageSection variant="default" style={{ paddingBottom: 0 }}>
        <Breadcrumb aria-label="Application workspace breadcrumb">
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/organizations">Organizations</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            {selectedOrganization ? (
              <>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <Link to={buildOrganizationPath(selectedOrganization.id)}>{selectedOrganization.name}</Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </>
            ) : null}
            {selectedProject ? (
              <>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <Link to={buildProjectPath(selectedOrganization!.id, selectedProject.id)}>{selectedProject.name}</Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </>
            ) : null}
            {selectedEnvironment ? (
              <>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <Link to={buildEnvironmentPath(selectedOrganization!.id, selectedProject!.id, selectedEnvironment.id)}>
                      {selectedEnvironment.name}
                    </Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </>
            ) : null}
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{selectedApp?.name || 'Application workspace'}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </PageSection>

      {isLoadingSelection ? (
        <PageSection variant="default">
          <div className="flex min-h-[40vh] items-center justify-center gap-3 text-sm text-muted-foreground">
            <Spinner size="lg" />
            Loading workspace...
          </div>
        </PageSection>
      ) : !selectedOrganization || !selectedProject || !selectedEnvironment || !selectedApp ? (
        <PageSection variant="default">
          <Card>
            <CardHeader>
              <CardTitle>Application workspace unavailable</CardTitle>
              <CardDescription>
                The selected organization, project, environment, or application could not be resolved from this URL.
              </CardDescription>
            </CardHeader>
          </Card>
        </PageSection>
      ) : (
        <ApplicationWorkspace
          project={selectedProject}
          app={selectedApp}
          environment={selectedEnvironment}
          applicationName={selectedApp.name}
          serviceAppId={selectedApp.id}
          headerTitle={selectedApp.name}
          subtitle={undefined}
          headerMeta={
            <Badge variant="outline" className="border-red-200 bg-red-500/10 text-red-700">
              {selectedEnvironment.name}
            </Badge>
          }
          layoutMode="full-page"
          backLink={{
            label: 'Back to application overview',
            onClick: () => navigate(overviewPath),
          }}
        />
      )}
    </Page>
  );
};

export default AppWorkspacePage;