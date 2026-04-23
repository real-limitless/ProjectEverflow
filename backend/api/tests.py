from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import App, Deployment, Environment, Organization, OrganizationMembership, Project, ProjectService


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