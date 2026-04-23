import { useNavigate, useOutletContext } from 'react-router-dom';
import { Building2, FolderKanban, ShieldCheck } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { OrganizationHierarchyOutletContext } from '@/pages/Organizations';

const OrganizationsOverview = () => {
  const { organizations, organizationsLoading } = useOutletContext<OrganizationHierarchyOutletContext>();
  const navigate = useNavigate();

  const totalProjects = organizations.reduce((sum, organization) => sum + organization.project_count, 0);
  const delegatedAdminCount = organizations.filter((organization) => organization.user_role === 'admin' || organization.user_role === 'owner').length;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-2xl">
            <Building2 className="h-5 w-5" />
            Organization overview
          </CardTitle>
          <CardDescription>
            The hierarchy is now split into routed detail pages. Pick an organization to drill into projects, environments, and apps.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-background p-4">
            <div className="text-sm text-muted-foreground">Organizations</div>
            <div className="mt-2 text-3xl font-semibold">{organizations.length}</div>
          </div>
          <div className="rounded-lg border border-border bg-background p-4">
            <div className="text-sm text-muted-foreground">Projects across orgs</div>
            <div className="mt-2 text-3xl font-semibold">{totalProjects}</div>
          </div>
          <div className="rounded-lg border border-border bg-background p-4">
            <div className="text-sm text-muted-foreground">Org admin roles</div>
            <div className="mt-2 text-3xl font-semibold">{delegatedAdminCount}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Accessible organizations</CardTitle>
          <CardDescription>Open an organization to see its projects and delegated admins.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {organizationsLoading ? (
            <p className="text-sm text-muted-foreground">Loading organizations...</p>
          ) : organizations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No organizations are available yet.</p>
          ) : (
            organizations.map((organization) => (
              <button
                key={organization.id}
                type="button"
                onClick={() => navigate(`/organizations/${organization.id}`)}
                className="rounded-lg border border-border bg-background p-5 text-left transition hover:border-primary/40 hover:bg-primary/5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold">{organization.name}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{organization.description || 'No organization description yet.'}</div>
                  </div>
                  <Badge variant="secondary">{organization.user_role ?? 'viewer'}</Badge>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <FolderKanban className="h-3.5 w-3.5" />
                    {organization.project_count} projects
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {organization.member_count} members
                  </span>
                </div>
              </button>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default OrganizationsOverview;