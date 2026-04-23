## Workflows

### 1. Navigate the Organization Hierarchy
```
1. User navigates to "Organizations" or "My Teamspace"
2. Selects an organization from the hierarchy or directory view
3. Opens a project nested under that organization
4. Drills into environment and app routes
5. Reviews deployment history for the selected app
6. If needed, triggers a rollback deployment from the app detail route
```

### 2. Submit and Approve Change Request Workflow
```
1. Contributor makes code changes locally
2. Submits PR (creates change request)
3. Change request appears in "Approval Queue" for all project members
4. Project members review:
   - View diff summary (files changed, lines added/removed)
   - Read description
   - Review code changes
5. Each approver clicks "Approve" or "Request Changes"
6. System tracks approvals (e.g., 2 of 3 required)
7. Cannot approve own PR
8. Once required approvals met (e.g., 3):
   - Status changes to "Approved"
   - Ready to merge
9. Changes merged into main/target branch
10. All team members notified
```

### 3. Compliance Check Assignment Workflow
```
1. Administrator navigates to "Safety & Compliance"
2. Creates individual checks:
   - Name: "SQL Injection Detection"
   - Category: Security
   - Severity: Critical
   - AI Prompt: "Analyze code for SQL injection..."
3. Groups checks into template:
   - Name: "HIPAA Compliance"
   - Includes: checks for encryption, access control, audit logs
4. Assigns template to projects:
   - Navigate to "Project Assignments" tab
   - Select project
   - Assign "HIPAA Compliance" template
5. Checks run automatically:
   - On every commit
   - On every build
   - On every PR creation
6. View results:
   - Navigate to "Project Assignments"
   - See last run status (Pass/Fail)
   - View violations count
   - Drill down to specific failures
7. Address violations before approving PR
```

---

## User Roles & Permissions

### Project Owner
- Creates the project
- Full control over project
- Can approve PRs
- Can manage contributors
- Sees all PRs for their projects in Approval Queue

### Organization Owner / Organization Admin
- Can create and manage projects inside the organization
- Can create environments and apps under organization projects
- Can create deployment records and rollbacks for managed apps
- Acts as the delegated administrator for organization-scoped resources

### Project Contributor
- Works on project code
- Can submit PRs
- Can approve others' PRs (not own)
- Sees all PRs for projects they contribute to in Approval Queue

### Organization Member
- Can browse organizations and projects they have access to
- Can use "My Projects" to jump to projects they own or contribute to
- Cannot manage organization-scoped resources unless elevated to admin or owner

### Administrator
- Can create organizations
- Has global access across the organization hierarchy
- Can create/edit/delete compliance checks
- Can create/edit/delete compliance templates
- Can assign checks/templates to any project
- Can view all check results across all projects
- Can run checks manually
- Full access to Safety & Compliance page

[Back to Index](./index.md)
