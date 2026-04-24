from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import App, AppSourceSettings, Deployment, Environment, Organization, OrganizationGitConnection, OrganizationMembership, PersonalGitConnection, Project, ProjectService


User = get_user_model()


class OrganizationApiTests(APITestCase):
	def setUp(self):
		self.global_admin = User.objects.create_user(
			username='global-admin',
			password='test-pass',
			role='admin',
			is_staff=True,
		)
		self.regular_user = User.objects.create_user(
			username='regular-user',
			password='test-pass',
		)

	def test_global_admin_can_create_organization(self):
		self.client.force_authenticate(self.global_admin)

		response = self.client.post(
			'/api/organizations/',
			{
				'name': 'Everflow Systems',
				'description': 'Primary customer organization',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		organization = Organization.objects.get(id=response.data['id'])
		membership = OrganizationMembership.objects.get(organization=organization, user=self.global_admin)

		self.assertEqual(organization.owner, self.global_admin)
		self.assertEqual(membership.role, 'owner')

	def test_non_admin_cannot_create_organization(self):
		self.client.force_authenticate(self.regular_user)

		response = self.client.post(
			'/api/organizations/',
			{
				'name': 'Blocked Org',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class HierarchyApiTests(APITestCase):
	def setUp(self):
		self.global_admin = User.objects.create_user(
			username='platform-admin',
			password='test-pass',
			role='admin',
			is_staff=True,
		)
		self.org_admin = User.objects.create_user(
			username='org-admin',
			password='test-pass',
		)
		self.org_member = User.objects.create_user(
			username='org-member',
			password='test-pass',
		)

		self.organization = Organization.objects.create(
			name='Acme Organization',
			owner=self.global_admin,
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.global_admin,
			role='owner',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_admin,
			role='admin',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_member,
			role='member',
		)

		self.project = Project.objects.create(
			name='Project Everflow',
			owner=self.org_admin,
			organization=self.organization,
		)

	def test_org_admin_can_create_environment_app_and_deployment(self):
		self.client.force_authenticate(self.org_admin)

		environment_response = self.client.post(
			'/api/environments/',
			{
				'project_id': self.project.id,
				'name': 'Production',
				'environment_type': 'production',
				'workspace_image': 'fedora:43',
				'workspace_size': 'standard',
				'workspace_mode': 'shared',
			},
			format='json',
		)
		self.assertEqual(environment_response.status_code, status.HTTP_201_CREATED)

		app_response = self.client.post(
			'/api/apps/',
			{
				'environment_id': environment_response.data['id'],
				'name': 'Website',
				'source_type': 'compose',
				'compose_path': './container-compose.dev.yml',
			},
			format='json',
		)
		self.assertEqual(app_response.status_code, status.HTTP_201_CREATED)

		deployment_response = self.client.post(
			'/api/deployments/',
			{
				'app_id': app_response.data['id'],
				'version': '2026.04.22.1',
				'status': 'pending',
				'source_ref': 'main',
			},
			format='json',
		)
		self.assertEqual(deployment_response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(deployment_response.data['environment'], environment_response.data['id'])

		rollback_response = self.client.post(
			f"/api/deployments/{deployment_response.data['id']}/rollback/",
			{'notes': 'Rollback smoke test'},
			format='json',
		)
		self.assertEqual(rollback_response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(rollback_response.data['rollback_of'], deployment_response.data['id'])

	def test_org_member_has_read_access_but_not_environment_management(self):
		environment = Environment.objects.create(
			project=self.project,
			name='Staging',
			environment_type='staging',
			created_by=self.org_admin,
		)
		app = App.objects.create(
			environment=environment,
			name='Docs',
			source_type='compose',
			created_by=self.org_admin,
		)
		Deployment.objects.create(
			environment=environment,
			app=app,
			version='2026.04.22.2',
			deployed_by=self.org_admin,
			status='succeeded',
		)

		self.client.force_authenticate(self.org_member)

		list_response = self.client.get(f'/api/environments/?project={self.project.id}')
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)

		create_response = self.client.post(
			'/api/environments/',
			{
				'project_id': self.project.id,
				'name': 'Demo',
				'environment_type': 'demo',
				'workspace_image': 'fedora:43',
				'workspace_size': 'standard',
				'workspace_mode': 'shared',
			},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)


	def test_org_admin_can_create_update_and_delete_app_scoped_service(self):
		self.client.force_authenticate(self.org_admin)

		environment = Environment.objects.create(
			project=self.project,
			name='Development',
			environment_type='development',
			created_by=self.org_admin,
		)
		app = App.objects.create(
			environment=environment,
			name='API',
			source_type='repository',
			created_by=self.org_admin,
		)

		create_response = self.client.post(
			'/api/project-services/',
			{
				'app': app.id,
				'name': 'api-service',
				'service_type': 'backend',
				'image': 'python:3.12',
				'ports': ['8000:8000'],
				'environment': {'PORT': '8000'},
				'autostart': True,
			},
			format='json',
		)

		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		service = ProjectService.objects.get(id=create_response.data['id'])
		self.assertEqual(service.app_id, app.id)
		self.assertEqual(service.pod.project_id, self.project.id)

		update_response = self.client.patch(
			f"/api/project-services/{service.id}/",
			{
				'image': 'python:3.13',
				'memory_limit': '1G',
			},
			format='json',
		)

		self.assertEqual(update_response.status_code, status.HTTP_200_OK)
		service.refresh_from_db()
		self.assertEqual(service.image, 'python:3.13')
		self.assertEqual(service.memory_limit, '1G')

		delete_response = self.client.delete(f"/api/project-services/{service.id}/")
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(ProjectService.objects.filter(id=service.id).exists())

	def test_org_member_cannot_create_service(self):
		environment = Environment.objects.create(
			project=self.project,
			name='Development',
			environment_type='development',
			created_by=self.org_admin,
		)
		app = App.objects.create(
			environment=environment,
			name='API',
			source_type='repository',
			created_by=self.org_admin,
		)

		self.client.force_authenticate(self.org_member)

		create_response = self.client.post(
			'/api/project-services/',
			{
				'app': app.id,
				'name': 'api-service',
				'service_type': 'backend',
				'image': 'python:3.12',
			},
			format='json',
		)

		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectPublicGitInputApiTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='project-clone-user',
			password='test-pass',
		)

	@mock.patch('api.views.initialize_project_workspace')
	@mock.patch('api.views.PodmanOrchestrator.ensure_workspace_service')
	def test_clone_project_normalizes_provider_slug_to_public_https_url(self, mock_ensure_workspace_service, mock_initialize):
		self.client.force_authenticate(self.user)

		response = self.client.post(
			'/api/projects/',
			{
				'name': 'Portal Workspace',
				'description': 'Clone from public slug',
				'owner': self.user.id,
				'creation_method': 'clone',
				'git_repo_url': 'acme/portal',
				'git_provider_hint': 'github',
				'branch': 'main',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		project = Project.objects.get(id=response.data['id'])
		self.assertEqual(project.git_repo_url, 'https://github.com/acme/portal')
		self.assertEqual(project.provisioning_status, 'completed')
		mock_ensure_workspace_service.assert_called_once()
		mock_initialize.assert_called_once_with(project)

	@mock.patch('api.views.initialize_project_workspace')
	@mock.patch('api.views.PodmanOrchestrator.ensure_workspace_service')
	def test_clone_project_normalizes_public_ssh_url_to_https(self, mock_ensure_workspace_service, mock_initialize):
		self.client.force_authenticate(self.user)

		response = self.client.post(
			'/api/projects/',
			{
				'name': 'SSH Workspace',
				'description': 'Clone from public ssh input',
				'owner': self.user.id,
				'creation_method': 'clone',
				'git_repo_url': 'git@github.com:acme/portal.git',
				'branch': 'main',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		project = Project.objects.get(id=response.data['id'])
		self.assertEqual(project.git_repo_url, 'https://github.com/acme/portal')
		self.assertEqual(project.provisioning_status, 'completed')
		mock_ensure_workspace_service.assert_called_once()
		mock_initialize.assert_called_once_with(project)

	def test_clone_project_rejects_slug_without_supported_provider_hint(self):
		self.client.force_authenticate(self.user)

		response = self.client.post(
			'/api/projects/',
			{
				'name': 'Unsupported Slug Workspace',
				'description': 'Clone from unsupported slug input',
				'owner': self.user.id,
				'creation_method': 'clone',
				'git_repo_url': 'acme/portal',
				'git_provider_hint': 'other',
				'branch': 'main',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('git_repo_url', response.data)


class OrganizationGitConnectionApiTests(APITestCase):
	def setUp(self):
		self.global_admin = User.objects.create_user(
			username='platform-owner',
			password='test-pass',
			role='admin',
			is_staff=True,
		)
		self.org_admin = User.objects.create_user(
			username='git-admin',
			password='test-pass',
		)
		self.org_member = User.objects.create_user(
			username='git-member',
			password='test-pass',
		)

		self.organization = Organization.objects.create(
			name='Repo Enabled Org',
			owner=self.global_admin,
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.global_admin,
			role='owner',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_admin,
			role='admin',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_member,
			role='member',
		)

	def test_org_admin_can_create_and_test_connection(self):
		self.client.force_authenticate(self.org_admin)

		create_response = self.client.post(
			'/api/organization-git-connections/',
			{
				'organization_id': self.organization.id,
				'name': 'Engineering GitHub',
				'provider_type': 'github',
				'auth_type': 'pat',
				'base_url': 'https://github.com',
				'notes': 'Shared deployment repositories',
				'credential_plain': 'ghp_example_secret_1234',
			},
			format='json',
		)

		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(create_response.data['has_credentials'])
		self.assertEqual(create_response.data['repository_count'], 0)

		connection = OrganizationGitConnection.objects.get(id=create_response.data['id'])
		self.assertEqual(connection.created_by, self.org_admin)
		self.assertNotEqual(connection.credential, '')

		list_response = self.client.get(f'/api/organization-git-connections/?organization={self.organization.id}')
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)

		test_response = self.client.post(f"/api/organization-git-connections/{connection.id}/test_connection/", {}, format='json')
		self.assertEqual(test_response.status_code, status.HTTP_200_OK)
		self.assertEqual(test_response.data['status'], 'succeeded')

		connection.refresh_from_db()
		self.assertEqual(connection.last_test_status, 'succeeded')
		self.assertIsNotNone(connection.last_tested_at)

	def test_org_member_can_list_but_cannot_manage_connections(self):
		connection = OrganizationGitConnection.objects.create(
			organization=self.organization,
			name='Shared GitLab',
			provider_type='gitlab',
			auth_type='oauth',
			created_by=self.org_admin,
		)

		self.client.force_authenticate(self.org_member)

		list_response = self.client.get(f'/api/organization-git-connections/?organization={self.organization.id}')
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)

		create_response = self.client.post(
			'/api/organization-git-connections/',
			{
				'organization_id': self.organization.id,
				'name': 'Blocked Connection',
				'provider_type': 'github',
				'auth_type': 'pat',
			},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

		delete_response = self.client.delete(f'/api/organization-git-connections/{connection.id}/')
		self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

	@mock.patch('api.git_connection_discovery._get_connection_token', return_value='ghp_repo_discovery_token')
	@mock.patch('api.git_connection_discovery.requests.get')
	def test_org_member_can_discover_shared_repositories(self, mock_get, _mock_token):
		connection = OrganizationGitConnection.objects.create(
			organization=self.organization,
			name='Shared GitHub',
			provider_type='github',
			auth_type='pat',
			created_by=self.org_admin,
		)

		response_payload = mock.Mock()
		response_payload.raise_for_status.return_value = None
		response_payload.json.return_value = [
			{
				'id': 101,
				'name': 'portal',
				'full_name': 'acme/portal',
				'clone_url': 'https://github.com/acme/portal.git',
				'ssh_url': 'git@github.com:acme/portal.git',
				'html_url': 'https://github.com/acme/portal',
				'default_branch': 'main',
				'private': True,
			},
		]
		mock_get.return_value = response_payload

		self.client.force_authenticate(self.org_member)

		response = self.client.get(f'/api/organization-git-connections/{connection.id}/repositories/')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['repositories'][0]['full_name'], 'acme/portal')

		connection.refresh_from_db()
		self.assertEqual(connection.repository_cache[0]['clone_url'], 'https://github.com/acme/portal.git')

	@mock.patch('api.git_connection_discovery._get_connection_token', return_value='bb_repo_discovery_token')
	@mock.patch('api.git_connection_discovery.requests.get')
	def test_org_member_can_discover_shared_bitbucket_repositories(self, mock_get, _mock_token):
		connection = OrganizationGitConnection.objects.create(
			organization=self.organization,
			name='Shared Bitbucket',
			provider_type='bitbucket',
			auth_type='pat',
			created_by=self.org_admin,
		)

		first_page = mock.Mock()
		first_page.raise_for_status.return_value = None
		first_page.json.return_value = {
			'values': [
				{
					'uuid': '{repo-1}',
					'name': 'portal',
					'slug': 'portal',
					'full_name': 'acme/portal',
					'is_private': True,
					'mainbranch': {'name': 'main'},
					'links': {
						'html': {'href': 'https://bitbucket.org/acme/portal'},
						'clone': [
							{'name': 'https', 'href': 'https://bitbucket.org/acme/portal.git'},
							{'name': 'ssh', 'href': 'git@bitbucket.org:acme/portal.git'},
						],
					},
				},
			],
			'next': 'https://api.bitbucket.org/2.0/repositories?page=2',
		}

		second_page = mock.Mock()
		second_page.raise_for_status.return_value = None
		second_page.json.return_value = {
			'values': [
				{
					'uuid': '{repo-2}',
					'name': 'docs',
					'slug': 'docs',
					'full_name': 'acme/docs',
					'is_private': False,
					'mainbranch': {'name': 'develop'},
					'links': {
						'html': {'href': 'https://bitbucket.org/acme/docs'},
						'clone': [
							{'name': 'https', 'href': 'https://bitbucket.org/acme/docs.git'},
							{'name': 'ssh', 'href': 'git@bitbucket.org:acme/docs.git'},
						],
					},
				},
			],
		}

		mock_get.side_effect = [first_page, second_page]

		self.client.force_authenticate(self.org_member)

		response = self.client.get(f'/api/organization-git-connections/{connection.id}/repositories/')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 2)
		self.assertEqual(response.data['repositories'][0]['full_name'], 'acme/portal')
		self.assertEqual(response.data['repositories'][1]['default_branch'], 'develop')

		connection.refresh_from_db()
		self.assertEqual(connection.repository_cache[0]['ssh_url'], 'git@bitbucket.org:acme/portal.git')


class PersonalGitConnectionApiTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='personal-owner',
			password='test-pass',
		)
		self.other_user = User.objects.create_user(
			username='personal-other',
			password='test-pass',
		)

	def test_user_can_create_list_and_test_personal_connection(self):
		self.client.force_authenticate(self.user)

		create_response = self.client.post(
			'/api/personal-git-connections/',
			{
				'name': 'My GitHub',
				'provider_type': 'github',
				'auth_type': 'pat',
				'base_url': 'https://github.com',
				'credential_plain': 'ghp_personal_secret_1234',
			},
			format='json',
		)

		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(create_response.data['has_credentials'])

		connection = PersonalGitConnection.objects.get(id=create_response.data['id'])
		self.assertEqual(connection.user, self.user)
		self.assertNotEqual(connection.credential, '')

		list_response = self.client.get('/api/personal-git-connections/')
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 1)

		test_response = self.client.post(f"/api/personal-git-connections/{connection.id}/test_connection/", {}, format='json')
		self.assertEqual(test_response.status_code, status.HTTP_200_OK)
		self.assertEqual(test_response.data['status'], 'succeeded')

		connection.refresh_from_db()
		self.assertEqual(connection.last_test_status, 'succeeded')

	def test_user_cannot_access_someone_elses_personal_connection(self):
		connection = PersonalGitConnection.objects.create(
			user=self.other_user,
			name='Private GitLab',
			provider_type='gitlab',
			auth_type='oauth',
		)

		self.client.force_authenticate(self.user)

		list_response = self.client.get('/api/personal-git-connections/')
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data), 0)

		detail_response = self.client.get(f'/api/personal-git-connections/{connection.id}/')
		self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)

		delete_response = self.client.delete(f'/api/personal-git-connections/{connection.id}/')
		self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)

	@mock.patch('api.git_connection_discovery._get_connection_token', return_value='ghp_branch_discovery_token')
	@mock.patch('api.git_connection_discovery.requests.get')
	def test_user_can_discover_personal_repository_branches(self, mock_get, _mock_token):
		connection = PersonalGitConnection.objects.create(
			user=self.user,
			name='My GitHub',
			provider_type='github',
			auth_type='pat',
		)

		repositories_response = mock.Mock()
		repositories_response.raise_for_status.return_value = None
		repositories_response.json.return_value = [
			{
				'id': 22,
				'name': 'everflow-ui',
				'full_name': 'acme/everflow-ui',
				'clone_url': 'https://github.com/acme/everflow-ui.git',
				'ssh_url': 'git@github.com:acme/everflow-ui.git',
				'html_url': 'https://github.com/acme/everflow-ui',
				'default_branch': 'main',
				'private': False,
			},
		]

		branches_response = mock.Mock()
		branches_response.raise_for_status.return_value = None
		branches_response.json.return_value = [
			{'name': 'main', 'protected': True},
			{'name': 'feature/ai-commit-back', 'protected': False},
		]

		mock_get.side_effect = [repositories_response, branches_response]

		self.client.force_authenticate(self.user)

		response = self.client.get(
			f'/api/personal-git-connections/{connection.id}/branches/',
			{'repository': 'https://github.com/acme/everflow-ui.git'},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['default_branch'], 'main')
		self.assertEqual(response.data['count'], 2)
		self.assertEqual(response.data['branches'][0]['name'], 'main')
		self.assertTrue(response.data['branches'][0]['is_default'])

	@mock.patch('api.git_connection_discovery._get_connection_token', return_value='bb_branch_discovery_token')
	@mock.patch('api.git_connection_discovery.requests.get')
	def test_user_can_discover_personal_bitbucket_repository_branches(self, mock_get, _mock_token):
		connection = PersonalGitConnection.objects.create(
			user=self.user,
			name='My Bitbucket',
			provider_type='bitbucket',
			auth_type='pat',
		)

		repositories_response = mock.Mock()
		repositories_response.raise_for_status.return_value = None
		repositories_response.json.return_value = {
			'values': [
				{
					'uuid': '{repo-1}',
					'name': 'portal',
					'slug': 'portal',
					'full_name': 'acme/portal',
					'is_private': True,
					'mainbranch': {'name': 'main'},
					'links': {
						'html': {'href': 'https://bitbucket.org/acme/portal'},
						'clone': [
							{'name': 'https', 'href': 'https://bitbucket.org/acme/portal.git'},
							{'name': 'ssh', 'href': 'git@bitbucket.org:acme/portal.git'},
						],
					},
				},
			],
		}

		branches_response = mock.Mock()
		branches_response.raise_for_status.return_value = None
		branches_response.json.return_value = {
			'values': [
				{'name': 'release/2026.04'},
				{'name': 'main'},
			],
		}

		mock_get.side_effect = [repositories_response, branches_response]

		self.client.force_authenticate(self.user)

		response = self.client.get(
			f'/api/personal-git-connections/{connection.id}/branches/',
			{'repository': 'acme/portal'},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['default_branch'], 'main')
		self.assertEqual(response.data['count'], 2)
		self.assertEqual(response.data['branches'][0]['name'], 'main')
		self.assertTrue(response.data['branches'][0]['is_default'])


class AppSourceSettingsApiTests(APITestCase):
	def setUp(self):
		self.global_admin = User.objects.create_user(
			username='settings-owner',
			password='test-pass',
			role='admin',
			is_staff=True,
		)
		self.org_admin = User.objects.create_user(
			username='app-source-admin',
			password='test-pass',
		)
		self.org_member = User.objects.create_user(
			username='app-source-member',
			password='test-pass',
		)

		self.organization = Organization.objects.create(
			name='App Source Org',
			owner=self.global_admin,
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.global_admin,
			role='owner',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_admin,
			role='admin',
		)
		OrganizationMembership.objects.create(
			organization=self.organization,
			user=self.org_member,
			role='member',
		)

		self.project = Project.objects.create(
			name='App Source Project',
			owner=self.org_admin,
			organization=self.organization,
		)
		self.environment = Environment.objects.create(
			project=self.project,
			name='Development',
			environment_type='development',
			created_by=self.org_admin,
		)
		self.app = App.objects.create(
			environment=self.environment,
			name='Portal',
			source_type='repository',
			repository_url='https://github.com/acme/portal',
			compose_path='./docker-compose.yml',
			config={
				'deploymentSettings': {
					'providerType': 'github',
					'sourceRef': 'main',
					'watchPaths': 'src/**\ncompose/**',
					'triggerType': 'push',
					'autoDeployEnabled': True,
					'submodulesEnabled': True,
					'schedule': '0 */6 * * *',
				},
			},
			created_by=self.org_admin,
		)
		self.organization_connection = OrganizationGitConnection.objects.create(
			organization=self.organization,
			name='Engineering GitHub',
			provider_type='github',
			auth_type='pat',
			created_by=self.org_admin,
		)
		self.personal_connection = PersonalGitConnection.objects.create(
			user=self.org_admin,
			name='Personal GitHub',
			provider_type='github',
			auth_type='pat',
		)
		self.member_personal_connection = PersonalGitConnection.objects.create(
			user=self.org_member,
			name='Member GitHub',
			provider_type='github',
			auth_type='pat',
		)

	def test_get_source_settings_bootstraps_from_existing_app_config(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.get(f'/api/apps/{self.app.id}/source_settings/')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['source_provider'], 'github')
		self.assertEqual(response.data['source_kind'], 'git-repository')
		self.assertEqual(response.data['source_location'], self.app.repository_url)
		self.assertEqual(response.data['source_ref'], 'main')
		self.assertEqual(response.data['trigger_type'], 'push')
		self.assertEqual(response.data['watch_paths'], ['src/**', 'compose/**'])
		self.assertEqual(response.data['repository_url'], self.app.repository_url)
		self.assertEqual(response.data['compose_path'], self.app.compose_path)

		self.assertTrue(AppSourceSettings.objects.filter(app=self.app).exists())

	def test_can_set_shared_or_personal_source_connection(self):
		self.client.force_authenticate(self.org_admin)

		shared_response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': 'organization',
				'organization_connection_id': self.organization_connection.id,
				'personal_connection_id': None,
				'source_provider': 'github',
				'source_kind': 'git-repository',
				'source_location': 'https://github.com/acme/portal',
				'source_ref': 'release',
				'watch_paths': ['src/**'],
				'trigger_type': 'manual',
				'auto_deploy_enabled': False,
			},
			format='json',
		)

		self.assertEqual(shared_response.status_code, status.HTTP_200_OK)
		self.assertEqual(shared_response.data['connection_scope'], 'organization')
		self.assertEqual(shared_response.data['organization_connection_name'], 'Engineering GitHub')

		personal_response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': 'personal',
				'organization_connection_id': None,
				'personal_connection_id': self.personal_connection.id,
				'source_provider': 'github',
				'source_kind': 'git-repository',
				'source_location': 'https://github.com/acme/portal',
				'source_ref': 'feature/ai-updates',
				'watch_paths': ['src/**', 'tests/**'],
				'trigger_type': 'push',
				'auto_deploy_enabled': True,
			},
			format='json',
		)

		self.assertEqual(personal_response.status_code, status.HTTP_200_OK)
		self.assertEqual(personal_response.data['connection_scope'], 'personal')
		self.assertEqual(personal_response.data['personal_connection_name'], 'Personal GitHub')

		settings = AppSourceSettings.objects.get(app=self.app)
		self.assertEqual(settings.personal_connection_id, self.personal_connection.id)
		self.assertEqual(settings.source_ref, 'feature/ai-updates')
		self.assertEqual(settings.watch_paths, ['src/**', 'tests/**'])

	def test_public_git_source_without_connection_normalizes_hosted_inputs(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': '',
				'organization_connection_id': None,
				'personal_connection_id': None,
				'source_provider': 'github',
				'source_kind': 'git-repository',
				'source_location': 'acme/public-portal',
				'source_ref': 'main',
				'watch_paths': ['src/**'],
				'trigger_type': 'manual',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['connection_scope'], '')
		self.assertEqual(response.data['source_location'], 'https://github.com/acme/public-portal')

		ssh_response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': '',
				'organization_connection_id': None,
				'personal_connection_id': None,
				'source_provider': 'github',
				'source_kind': 'git-repository',
				'source_location': 'git@github.com:acme/public-portal.git',
				'source_ref': 'main',
				'watch_paths': ['src/**'],
				'trigger_type': 'manual',
			},
			format='json',
		)

		self.assertEqual(ssh_response.status_code, status.HTTP_200_OK)
		self.assertEqual(ssh_response.data['source_location'], 'https://github.com/acme/public-portal')

	def test_generic_git_without_connection_requires_full_repository_url(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': '',
				'organization_connection_id': None,
				'personal_connection_id': None,
				'source_provider': 'generic-git',
				'source_kind': 'git-repository',
				'source_location': 'acme/public-portal',
				'source_ref': 'main',
				'watch_paths': ['src/**'],
				'trigger_type': 'manual',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('source_location', response.data)

	def test_user_cannot_attach_another_users_personal_connection(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'connection_scope': 'personal',
				'personal_connection_id': self.member_personal_connection.id,
				'source_provider': 'github',
				'source_kind': 'git-repository',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_raw_compose_and_dockerfile_sources_require_explicit_non_git_fields(self):
		self.client.force_authenticate(self.org_admin)

		compose_response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'source_provider': 'raw-compose',
				'source_kind': 'raw-compose',
				'source_location': 'https://example.com/compose/docker-compose.yml',
				'trigger_type': 'manual',
				'watch_paths': ['ignored/**'],
				'submodules_enabled': True,
			},
			format='json',
		)

		self.assertEqual(compose_response.status_code, status.HTTP_200_OK)
		self.assertEqual(compose_response.data['source_kind'], 'raw-compose')
		self.assertEqual(compose_response.data['source_location'], 'https://example.com/compose/docker-compose.yml')
		self.assertEqual(compose_response.data['watch_paths'], [])
		self.assertFalse(compose_response.data['submodules_enabled'])
		self.assertEqual(compose_response.data['source_ref'], '')

		dockerfile_response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'source_provider': 'raw-compose',
				'source_kind': 'raw-dockerfile',
				'source_location': 'https://example.com/build/Dockerfile',
				'build_context_path': './build',
				'trigger_type': 'manual',
			},
			format='json',
		)

		self.assertEqual(dockerfile_response.status_code, status.HTTP_200_OK)
		self.assertEqual(dockerfile_response.data['source_kind'], 'raw-dockerfile')
		self.assertEqual(dockerfile_response.data['build_context_path'], './build')

	def test_docker_registry_source_defaults_tag_to_latest(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'source_provider': 'docker-registry',
				'source_kind': 'container-image',
				'source_location': 'library/nginx',
				'source_ref': '',
				'trigger_type': 'manual',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['source_kind'], 'container-image')
		self.assertEqual(response.data['source_ref'], 'latest')

	def test_non_git_source_kinds_reject_push_trigger(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.patch(
			f'/api/apps/{self.app.id}/source_settings/',
			{
				'source_provider': 'raw-compose',
				'source_kind': 'raw-compose',
				'source_location': 'https://example.com/compose/docker-compose.yml',
				'trigger_type': 'push',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('trigger_type', response.data)

	def test_source_discovery_returns_manual_only_response_for_generic_git(self):
		self.client.force_authenticate(self.org_admin)

		response = self.client.get(
			f'/api/apps/{self.app.id}/source_discovery/',
			{'provider': 'generic-git', 'source_kind': 'git-repository'},
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertFalse(response.data['capabilities']['repository_browser'])
		self.assertEqual(response.data['repositories'], [])
		self.assertIn('Generic Git', response.data['manual_guidance'])

	@mock.patch('api.source_discovery.requests.get')
	def test_source_discovery_returns_docker_registry_results_and_tags(self, mock_get):
		search_response = mock.Mock()
		search_response.raise_for_status.return_value = None
		search_response.json.return_value = {
			'results': [
				{
					'repo_name': 'library/nginx',
					'name': 'nginx',
					'namespace': 'library',
					'short_description': 'Official build of NGINX.',
					'star_count': 100,
					'pull_count': 500,
					'is_official': True,
				},
			],
		}

		tags_response = mock.Mock()
		tags_response.raise_for_status.return_value = None
		tags_response.json.return_value = {
			'results': [
				{
					'name': 'latest',
					'last_updated': '2026-04-24T00:00:00Z',
					'images': [{'digest': 'sha256:deadbeef'}],
				},
			],
		}

		mock_get.side_effect = [search_response, tags_response]

		self.client.force_authenticate(self.org_admin)

		search_result = self.client.get(
			f'/api/apps/{self.app.id}/source_discovery/',
			{'provider': 'docker-registry', 'source_kind': 'container-image', 'search': 'nginx'},
		)

		self.assertEqual(search_result.status_code, status.HTTP_200_OK)
		self.assertTrue(search_result.data['capabilities']['registry_search'])
		self.assertEqual(search_result.data['repositories'][0]['full_name'], 'library/nginx')

		tags_result = self.client.get(
			f'/api/apps/{self.app.id}/source_discovery/',
			{'provider': 'docker-registry', 'source_kind': 'container-image', 'repository': 'nginx'},
		)

		self.assertEqual(tags_result.status_code, status.HTTP_200_OK)
		self.assertEqual(tags_result.data['selected_repository'], 'library/nginx')
		self.assertEqual(tags_result.data['tags'][0]['name'], 'latest')