## Workflows

### 1. Join a Project Workflow
```
1. User navigates to "My Teamspace"
2. Browses all team projects
3. Finds project they want to join
4. Clicks "Join" button
5. System sends join request to project owner
6. Toast notification: "Join request sent to [Owner Name]"
7. Owner receives notification
8. Owner reviews request and approves/rejects
9. If approved:
   - User becomes contributor
   - User can now see project in "My Projects"
   - User can submit PRs
   - User can approve other PRs
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
- Can approve join requests
- Sees all PRs for their projects in Approval Queue

### Project Contributor
- Works on project code
- Can submit PRs
- Can approve others' PRs (not own)
- Sees all PRs for projects they contribute to in Approval Queue
- Can request to join additional projects

### Team Member (Non-Contributor)
- Can view all team projects in "My Teamspace"
- Can request to join projects
- Cannot see projects in "My Projects" until they join
- Cannot see PRs in Approval Queue

### Administrator
- Can create/edit/delete compliance checks
- Can create/edit/delete compliance templates
- Can assign checks/templates to any project
- Can view all check results across all projects
- Can run checks manually
- Full access to Safety & Compliance page

[Back to Index](./index.md)
