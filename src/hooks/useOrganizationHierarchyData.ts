import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';

import {
  getApps,
  getCurrentUser,
  getDeployments,
  getEnvironments,
  normalizeApiList,
  getOrganizationProjects,
  getOrganizations,
} from '@/lib/api';

function parseRouteId(value?: string): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function useOrganizationHierarchyData() {
  const params = useParams();

  const selectedOrgId = parseRouteId(params.orgId);
  const selectedProjectId = parseRouteId(params.projectId);
  const selectedEnvironmentId = parseRouteId(params.environmentId);
  const selectedAppId = parseRouteId(params.appId);

  const { data: organizationsResponse, isLoading: organizationsLoading } = useQuery({
    queryKey: ['organizations'],
    queryFn: getOrganizations,
  });
  const { data: currentUserResponse } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });
  const { data: projectsResponse, isLoading: projectsLoading } = useQuery({
    queryKey: ['organizationProjects', selectedOrgId],
    queryFn: () => getOrganizationProjects(selectedOrgId as number),
    enabled: selectedOrgId !== null,
  });
  const { data: environmentsResponse, isLoading: environmentsLoading } = useQuery({
    queryKey: ['environments', selectedProjectId],
    queryFn: () => getEnvironments(selectedProjectId as number),
    enabled: selectedProjectId !== null,
  });
  const { data: appsResponse, isLoading: appsLoading } = useQuery({
    queryKey: ['apps', selectedEnvironmentId],
    queryFn: () => getApps(selectedEnvironmentId as number),
    enabled: selectedEnvironmentId !== null,
  });
  const { data: deployments = [], isLoading: deploymentsLoading } = useQuery({
    queryKey: ['deployments', selectedAppId],
    queryFn: async () => {
      const response = await getDeployments({ appId: selectedAppId as number });
      return response.data ?? [];
    },
    select: (value) => normalizeApiList(value),
    enabled: selectedAppId !== null,
  });

  const organizations = organizationsResponse?.data ?? [];
  const projects = projectsResponse?.data ?? [];
  const environments = environmentsResponse?.data ?? [];
  const apps = appsResponse?.data ?? [];
  const currentUser = currentUserResponse?.data;
  const canCreateOrganization = currentUser?.is_staff || currentUser?.role === 'admin';

  const selectedOrganization = organizations.find((organization) => organization.id === selectedOrgId) ?? null;
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedEnvironment = environments.find((environment) => environment.id === selectedEnvironmentId) ?? null;
  const selectedApp = apps.find((app) => app.id === selectedAppId) ?? null;

  return {
    apps,
    appsLoading,
    canCreateOrganization,
    currentUser,
    deployments,
    deploymentsLoading,
    environments,
    environmentsLoading,
    organizations,
    organizationsLoading,
    projects,
    projectsLoading,
    selectedApp,
    selectedAppId,
    selectedEnvironment,
    selectedEnvironmentId,
    selectedOrgId,
    selectedOrganization,
    selectedProject,
    selectedProjectId,
  };
}