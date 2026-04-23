export function buildOrganizationPath(organizationId: number) {
  return `/organizations/${organizationId}`;
}

export function buildProjectPath(organizationId: number, projectId: number) {
  return `${buildOrganizationPath(organizationId)}/projects/${projectId}`;
}

export function buildEnvironmentPath(organizationId: number, projectId: number, environmentId: number) {
  return `${buildProjectPath(organizationId, projectId)}/environments/${environmentId}`;
}

export function buildAppOverviewPath(
  organizationId: number,
  projectId: number,
  environmentId: number,
  appId: number,
) {
  return `${buildEnvironmentPath(organizationId, projectId, environmentId)}/apps/${appId}`;
}

export function buildAppWorkspacePath(
  organizationId: number,
  projectId: number,
  environmentId: number,
  appId: number,
) {
  return `${buildAppOverviewPath(organizationId, projectId, environmentId, appId)}/workspace`;
}