import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Spinner } from '@patternfly/react-core';

import { getApps, getEnvironments, getProjects } from '@/lib/api';
import { buildAppWorkspacePath, buildEnvironmentPath, buildProjectPath } from '@/lib/organizationPaths';

interface LegacyHierarchyRouteRedirectProps {
  projectIdentifier?: string;
  message?: string;
}

export const LegacyHierarchyRouteRedirect = ({
  projectIdentifier,
  message = 'Redirecting to the hierarchy workspace...',
}: LegacyHierarchyRouteRedirectProps) => {
  const navigate = useNavigate();

  const { data: projectsResponse, isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  });

  const project = useMemo(() => {
    const projects = projectsResponse?.data ?? [];
    if (!projectIdentifier) {
      return null;
    }

    const parsedId = Number(projectIdentifier);
    if (Number.isFinite(parsedId)) {
      return projects.find((candidate) => candidate.id === parsedId) ?? null;
    }

    return projects.find((candidate) => candidate.name === projectIdentifier) ?? null;
  }, [projectIdentifier, projectsResponse?.data]);

  const { data: environmentsResponse, isLoading: environmentsLoading } = useQuery({
    queryKey: ['legacyHierarchyRedirectEnvironments', project?.id],
    queryFn: () => getEnvironments(project!.id),
    enabled: !!project?.id,
  });

  const environments = environmentsResponse?.data ?? [];
  const singleEnvironment = environments.length === 1 ? environments[0] : null;

  const { data: appsResponse, isLoading: appsLoading } = useQuery({
    queryKey: ['legacyHierarchyRedirectApps', singleEnvironment?.id],
    queryFn: () => getApps(singleEnvironment!.id),
    enabled: singleEnvironment !== null,
  });

  const apps = appsResponse?.data ?? [];

  useEffect(() => {
    if (projectsLoading) {
      return;
    }

    if (!project || !project.organization) {
      navigate('/organizations', { replace: true });
      return;
    }

    if (environmentsLoading) {
      return;
    }

    const projectPath = buildProjectPath(project.organization.id, project.id);

    if (environments.length !== 1) {
      navigate(projectPath, { replace: true });
      return;
    }

    const environment = environments[0];
    const environmentPath = buildEnvironmentPath(project.organization.id, project.id, environment.id);

    if (appsLoading || appsResponse === undefined) {
      return;
    }

    if (apps.length !== 1) {
      navigate(environmentPath, { replace: true });
      return;
    }

    navigate(buildAppWorkspacePath(project.organization.id, project.id, environment.id, apps[0].id), { replace: true });
  }, [apps, appsLoading, appsResponse, environments, environmentsLoading, navigate, project, projectsLoading]);

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 text-sm text-muted-foreground">
      <Spinner size="lg" />
      <p>{message}</p>
    </div>
  );
};