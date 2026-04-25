"""
Background deployment runner.

Runs in a daemon thread spawned by DeploymentViewSet.create().
Performs: git clone → compose service provisioning → status update.
Progress is streamed to the frontend via the existing
`provisioning-logs` WebSocket (ProjectProvisioningConsumer).
"""

import logging
import os

from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


def run_deployment(deployment_id: int) -> None:
    """
    Execute a deployment in the background thread.

    Steps:
    1. Acquire a fresh DB connection (required for threads).
    2. Set deployment status to in_progress.
    3. Resolve git credentials from AppSourceSettings.
    4. Clone the source repository into the project workspace volume.
    5. Provision compose services from the cloned compose file.
    6. Mark deployment succeeded or failed.
    """
    # --- thread-safe DB setup ---
    close_old_connections()

    # Lazy imports to avoid circular dependencies at module load time.
    from .models import Deployment, AppSourceSettings, OrganizationGitConnection, PersonalGitConnection
    from .workspace_initializer import WorkspaceInitializer
    from .git_source_normalization import normalize_public_git_repository_input, GitRepositoryNormalizationError

    try:
        deployment = Deployment.objects.select_related(
            'app__environment__project'
        ).get(pk=deployment_id)
    except Deployment.DoesNotExist:
        logger.error(f"[deployment_runner] Deployment {deployment_id} not found")
        return

    app = deployment.app
    project = app.environment.project
    volume_name = f"proj-{project.id}-workspace"

    # Mark in progress
    deployment.status = 'in_progress'
    deployment.started_at = timezone.now()
    deployment.save(update_fields=['status', 'started_at'])

    initializer = WorkspaceInitializer(volume_name, project_id=project.id)

    try:
        initializer._log(
            'info', 'deployment_start',
            f"Starting deployment for app '{app.name}' (deployment #{deployment.id})",
            metadata={'deployment_id': deployment.id, 'app_id': app.id, 'project_id': project.id},
        )

        # --- resolve source settings ---
        try:
            source_settings = AppSourceSettings.objects.get(app=app)
        except AppSourceSettings.DoesNotExist:
            source_settings = None

        git_url = None
        branch = None
        clone_credential = None

        if source_settings and source_settings.source_location:
            raw_url = source_settings.source_location.strip()
            branch = (deployment.source_ref or source_settings.source_ref or 'main').strip() or 'main'

            # Normalize URL if possible
            try:
                normalized = normalize_public_git_repository_input(raw_url)
                git_url = normalized.clone_url
            except GitRepositoryNormalizationError:
                git_url = raw_url  # use as-is (private / self-hosted)

            # Resolve PAT credential
            connection_scope = source_settings.connection_scope
            org_conn = source_settings.organization_connection
            personal_conn = source_settings.personal_connection

            try:
                if connection_scope == 'organization' and org_conn:
                    clone_credential = org_conn.get_credential()
                elif connection_scope == 'personal' and personal_conn:
                    clone_credential = personal_conn.get_credential()
            except Exception as cred_exc:  # noqa: BLE001
                logger.warning(
                    f"[deployment_runner] Could not resolve credential for deployment {deployment_id}: {cred_exc}"
                )
                clone_credential = None

        # --- clone step ---
        if git_url:
            initializer._log(
                'info', 'clone_repo',
                f"Cloning {git_url} (branch: {branch}) into workspace volume...",
                metadata={'git_url': git_url, 'branch': branch},
            )

            podman_bin = os.getenv('PODMAN_BIN', 'podman')

            # Ensure volume exists
            initializer._ensure_volume_exists()

            # Clear existing workspace content so the clone lands cleanly
            clear_cmd = 'find /workspace -mindepth 1 -delete 2>/dev/null || true'
            try:
                initializer._run_command([
                    podman_bin, 'run', '--rm',
                    '-v', f'{volume_name}:/workspace',
                    '--entrypoint', '/bin/sh',
                    'alpine:latest',
                    '-c', clear_cmd,
                ])
            except Exception as clear_exc:
                logger.warning(f"[deployment_runner] Could not clear workspace before clone: {clear_exc}")

            initializer.init_from_clone(git_url, branch, credential=clone_credential)

            initializer._log(
                'info', 'clone_repo',
                "Repository cloned successfully.",
            )
        else:
            initializer._log(
                'info', 'clone_repo',
                "No git source URL configured — skipping clone step.",
            )

        # --- provision compose services ---
        initializer._log(
            'info', 'provision_services',
            "Checking workspace for compose file to provision services...",
        )
        initializer.provision_compose_services(project)

        # --- success ---
        deployment.status = 'succeeded'
        deployment.completed_at = timezone.now()
        deployment.save(update_fields=['status', 'completed_at'])

        initializer._log(
            'info', 'init_complete',
            f"Deployment #{deployment.id} completed successfully.",
            metadata={'deployment_id': deployment.id, 'status': 'succeeded'},
        )

    except Exception as exc:
        logger.error(
            f"[deployment_runner] Deployment {deployment_id} failed: {exc}",
            exc_info=True,
        )

        try:
            deployment.status = 'failed'
            deployment.completed_at = timezone.now()
            deployment.save(update_fields=['status', 'completed_at'])

            initializer._log(
                'error', 'init_complete',
                f"Deployment #{deployment.id} failed: {exc}",
                metadata={'deployment_id': deployment.id, 'status': 'failed', 'error': str(exc)},
            )
        except Exception as save_exc:
            logger.error(f"[deployment_runner] Could not persist failure for deployment {deployment_id}: {save_exc}")
    finally:
        close_old_connections()
