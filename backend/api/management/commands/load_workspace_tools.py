"""
Management command to load workspace tools for AI-assisted code editing.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.models import Project, ProjectTool

User = get_user_model()


class Command(BaseCommand):
    help = 'Load workspace tools for all projects'

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-id',
            type=int,
            help='Load tools for specific project only',
        )

    def handle(self, *args, **options):
        self.stdout.write('Loading workspace tools...')
        
        # Get or create a system admin user for tool creation
        admin_user, _ = User.objects.get_or_create(
            username='system',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        
        # Define workspace tools
        tools = [
            {
                'name': 'Read File',
                'slug': 'read_file',
                'description': 'Read contents of a file from workspace',
                'entrypoint': 'cat "$FILE_PATH"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'file_path': {
                            'type': 'string',
                            'description': 'Path to file relative to /workspace'
                        }
                    },
                    'required': ['file_path']
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Edit File',
                'slug': 'edit_file',
                'description': 'Write or update a file in workspace',
                'entrypoint': 'mkdir -p "$(dirname "$FILE_PATH")" && echo "$CONTENT" > "$FILE_PATH"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'file_path': {
                            'type': 'string',
                            'description': 'Path to file relative to /workspace'
                        },
                        'content': {
                            'type': 'string',
                            'description': 'File content to write'
                        }
                    },
                    'required': ['file_path', 'content']
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'List Directory',
                'slug': 'list_directory',
                'description': 'List files and directories in workspace path',
                'entrypoint': 'ls -la "$DIR_PATH"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'dir_path': {
                            'type': 'string',
                            'description': 'Directory path relative to /workspace (default: .)',
                            'default': '.'
                        }
                    }
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Run Shell Command',
                'slug': 'run_shell_command',
                'description': 'Execute a shell command in workspace',
                'entrypoint': 'cd /workspace && bash -c "$COMMAND"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'command': {
                            'type': 'string',
                            'description': 'Shell command to execute'
                        }
                    },
                    'required': ['command']
                },
                'timeout_seconds': 300,
            },
            {
                'name': 'Git Status',
                'slug': 'git_status',
                'description': 'Check git repository status',
                'entrypoint': 'cd /workspace && git status',
                'args_schema': {'type': 'object'},
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Commit',
                'slug': 'git_commit',
                'description': 'Stage and commit changes to git',
                'entrypoint': 'cd /workspace && git add . && git commit -m "$MESSAGE"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'message': {
                            'type': 'string',
                            'description': 'Commit message'
                        }
                    },
                    'required': ['message']
                },
                'timeout_seconds': 60,
            },
            {
                'name': 'Git Pull',
                'slug': 'git_pull',
                'description': 'Pull latest changes from remote repository',
                'entrypoint': 'cd /workspace && git pull',
                'args_schema': {'type': 'object'},
                'timeout_seconds': 120,
            },
            {
                'name': 'Git Push',
                'slug': 'git_push',
                'description': 'Push commits to remote repository',
                'entrypoint': 'cd /workspace && git push',
                'args_schema': {'type': 'object'},
                'timeout_seconds': 120,
            },
            {
                'name': 'Git Branch List',
                'slug': 'git_branch_list',
                'description': 'List all git branches',
                'entrypoint': 'cd /workspace && git branch -a',
                'args_schema': {'type': 'object'},
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Branch Create',
                'slug': 'git_branch_create',
                'description': 'Create a new git branch',
                'entrypoint': 'cd /workspace && git checkout -b "$BRANCH_NAME"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'branch_name': {
                            'type': 'string',
                            'description': 'Name of the new branch'
                        }
                    },
                    'required': ['branch_name']
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Branch Switch',
                'slug': 'git_branch_switch',
                'description': 'Switch to a different git branch',
                'entrypoint': 'cd /workspace && git checkout "$BRANCH_NAME"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'branch_name': {
                            'type': 'string',
                            'description': 'Name of the branch to switch to'
                        }
                    },
                    'required': ['branch_name']
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Branch Delete',
                'slug': 'git_branch_delete',
                'description': 'Delete a git branch',
                'entrypoint': 'cd /workspace && git branch -d "$BRANCH_NAME"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'branch_name': {
                            'type': 'string',
                            'description': 'Name of the branch to delete'
                        }
                    },
                    'required': ['branch_name']
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Merge',
                'slug': 'git_merge',
                'description': 'Merge a branch into current branch',
                'entrypoint': 'cd /workspace && git merge "$BRANCH_NAME"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'branch_name': {
                            'type': 'string',
                            'description': 'Name of the branch to merge'
                        }
                    },
                    'required': ['branch_name']
                },
                'timeout_seconds': 60,
            },
            {
                'name': 'Git Log',
                'slug': 'git_log',
                'description': 'View git commit history',
                'entrypoint': 'cd /workspace && git log --oneline -n "$LIMIT"',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'limit': {
                            'type': 'integer',
                            'description': 'Number of commits to show',
                            'default': 10
                        }
                    }
                },
                'timeout_seconds': 30,
            },
            {
                'name': 'Git Diff',
                'slug': 'git_diff',
                'description': 'Show git diff of changes',
                'entrypoint': 'cd /workspace && git diff',
                'args_schema': {'type': 'object'},
                'timeout_seconds': 30,
            },
            {
                'name': 'Install Package',
                'slug': 'install_package',
                'description': 'Install a system package (dnf/yum)',
                'entrypoint': 'if command -v dnf &> /dev/null; then dnf install -y "$PACKAGE"; else yum install -y "$PACKAGE"; fi',
                'args_schema': {
                    'type': 'object',
                    'properties': {
                        'package': {
                            'type': 'string',
                            'description': 'Package name to install'
                        }
                    },
                    'required': ['package']
                },
                'timeout_seconds': 300,
            },
        ]
        
        # Get projects to add tools to
        if options['project_id']:
            projects = Project.objects.filter(id=options['project_id'])
            if not projects.exists():
                self.stdout.write(self.style.ERROR(f'Project {options["project_id"]} not found'))
                return
        else:
            projects = Project.objects.all()
        
        total_created = 0
        total_updated = 0
        
        for project in projects:
            self.stdout.write(f'\nProject: {project.name} (ID: {project.id})')
            
            for tool_data in tools:
                tool, created = ProjectTool.objects.update_or_create(
                    project=project,
                    slug=tool_data['slug'],
                    defaults={
                        'name': tool_data['name'],
                        'description': tool_data['description'],
                        'entrypoint': tool_data['entrypoint'],
                        'runtime_image': '',  # Empty for workspace tools
                        'args_schema': tool_data['args_schema'],
                        'environment': {},
                        'timeout_seconds': tool_data['timeout_seconds'],
                        'is_active': True,
                        'workspace_tool': True,  # Mark as workspace tool
                        'created_by': admin_user,
                    }
                )
                
                if created:
                    total_created += 1
                    self.stdout.write(f'  ✓ Created: {tool.name}')
                else:
                    total_updated += 1
                    self.stdout.write(f'  ↻ Updated: {tool.name}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted: {total_created} created, {total_updated} updated across {projects.count()} project(s)'
        ))
