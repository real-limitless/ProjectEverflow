from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from urllib.parse import quote

import requests


class GitProviderDiscoveryError(Exception):
    pass


def list_connection_repositories(connection, search: Optional[str] = None) -> List[Dict[str, Any]]:
    provider_type = connection.provider_type
    token = _get_connection_token(connection)

    if provider_type == 'github':
        repositories = _list_github_repositories(connection, token)
    elif provider_type == 'gitlab':
        repositories = _list_gitlab_repositories(connection, token)
    elif provider_type == 'gitea':
        repositories = _list_gitea_repositories(connection, token)
    elif provider_type == 'bitbucket':
        raise GitProviderDiscoveryError('Bitbucket repository discovery is not supported yet for this connection type.')
    else:
        raise GitProviderDiscoveryError('Repository discovery is not supported for this provider yet.')

    if search:
        search_term = search.strip().lower()
        repositories = [
            repository
            for repository in repositories
            if search_term in repository.get('name', '').lower()
            or search_term in repository.get('full_name', '').lower()
            or search_term in repository.get('clone_url', '').lower()
        ]

    return repositories


def list_repository_branches(connection, repository_identifier: str) -> Dict[str, Any]:
    if not repository_identifier or not repository_identifier.strip():
        raise GitProviderDiscoveryError('A repository identifier is required to discover branches.')

    provider_type = connection.provider_type
    token = _get_connection_token(connection)
    repository = _resolve_repository(connection, repository_identifier)

    if provider_type == 'github':
        branches = _list_github_branches(connection, token, repository)
    elif provider_type == 'gitlab':
        branches = _list_gitlab_branches(connection, token, repository)
    elif provider_type == 'gitea':
        branches = _list_gitea_branches(connection, token, repository)
    elif provider_type == 'bitbucket':
        raise GitProviderDiscoveryError('Bitbucket branch discovery is not supported yet for this connection type.')
    else:
        raise GitProviderDiscoveryError('Branch discovery is not supported for this provider yet.')

    return {
        'repository': repository,
        'default_branch': repository.get('default_branch'),
        'branches': _sort_branches(branches, repository.get('default_branch')),
    }


def _get_connection_token(connection) -> str:
    if connection.auth_type == 'ssh':
        raise GitProviderDiscoveryError('Repository discovery is not available for SSH-only connections yet.')

    if not connection.credential:
        raise GitProviderDiscoveryError('A credential is required before repository discovery can run.')

    try:
        token = connection.get_credential().strip()
    except ValueError as exc:
        raise GitProviderDiscoveryError(str(exc)) from exc

    if not token:
        raise GitProviderDiscoveryError('The saved credential is empty. Update the connection and try again.')

    return token


def _github_api_root(base_url: Optional[str]) -> str:
    if not base_url:
        return 'https://api.github.com'

    normalized = base_url.rstrip('/')
    if normalized.endswith('/api/v3') or 'api.github.com' in normalized:
        return normalized
    return f'{normalized}/api/v3'


def _gitlab_api_root(base_url: Optional[str]) -> str:
    normalized = (base_url or 'https://gitlab.com').rstrip('/')
    if normalized.endswith('/api/v4'):
        return normalized
    return f'{normalized}/api/v4'


def _gitea_api_root(base_url: Optional[str]) -> str:
    if not base_url:
        raise GitProviderDiscoveryError('A base URL is required for Gitea repository discovery.')

    normalized = base_url.rstrip('/')
    if normalized.endswith('/api/v1'):
        return normalized
    return f'{normalized}/api/v1'


def _request_json(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        detail = ''
        response = getattr(exc, 'response', None)
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

            if isinstance(payload, dict):
                detail = payload.get('message') or payload.get('error') or payload.get('detail') or str(payload)
            elif payload:
                detail = str(payload)

        if detail:
            raise GitProviderDiscoveryError(detail) from exc
        raise GitProviderDiscoveryError('The provider API request failed.') from exc


def _list_github_repositories(connection, token: str) -> List[Dict[str, Any]]:
    url = f"{_github_api_root(connection.base_url)}/user/repos"
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
    }

    repositories: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(
            url,
            headers,
            params={
                'per_page': 100,
                'page': page,
                'sort': 'updated',
                'affiliation': 'owner,collaborator,organization_member',
            },
        )
        items = payload if isinstance(payload, list) else []
        repositories.extend(
            {
                'id': str(item.get('id', '')),
                'name': item.get('name', ''),
                'full_name': item.get('full_name', ''),
                'clone_url': item.get('clone_url') or '',
                'ssh_url': item.get('ssh_url') or '',
                'web_url': item.get('html_url') or '',
                'default_branch': item.get('default_branch') or '',
                'private': bool(item.get('private', False)),
            }
            for item in items
        )
        if len(items) < 100:
            break
        page += 1

    return repositories


def _list_gitlab_repositories(connection, token: str) -> List[Dict[str, Any]]:
    url = f"{_gitlab_api_root(connection.base_url)}/projects"
    headers = {'PRIVATE-TOKEN': token}

    repositories: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(
            url,
            headers,
            params={
                'membership': 'true',
                'simple': 'true',
                'per_page': 100,
                'page': page,
                'order_by': 'last_activity_at',
                'sort': 'desc',
            },
        )
        items = payload if isinstance(payload, list) else []
        repositories.extend(
            {
                'id': str(item.get('id', '')),
                'name': item.get('name', ''),
                'full_name': item.get('path_with_namespace', ''),
                'clone_url': item.get('http_url_to_repo') or '',
                'ssh_url': item.get('ssh_url_to_repo') or '',
                'web_url': item.get('web_url') or '',
                'default_branch': item.get('default_branch') or '',
                'private': item.get('visibility') in {'private', 'internal'},
            }
            for item in items
        )
        if len(items) < 100:
            break
        page += 1

    return repositories


def _list_gitea_repositories(connection, token: str) -> List[Dict[str, Any]]:
    url = f"{_gitea_api_root(connection.base_url)}/user/repos"
    headers = {'Authorization': f'token {token}'}

    repositories: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(url, headers, params={'limit': 100, 'page': page})
        items = payload if isinstance(payload, list) else []
        repositories.extend(
            {
                'id': str(item.get('id', '')),
                'name': item.get('name', ''),
                'full_name': item.get('full_name', ''),
                'clone_url': item.get('clone_url') or '',
                'ssh_url': item.get('ssh_url') or '',
                'web_url': item.get('html_url') or '',
                'default_branch': item.get('default_branch') or '',
                'private': bool(item.get('private', False)),
            }
            for item in items
        )
        if len(items) < 100:
            break
        page += 1

    return repositories


def _list_github_branches(connection, token: str, repository: Dict[str, Any]) -> List[Dict[str, Any]]:
    full_name = repository.get('full_name')
    if not full_name:
        raise GitProviderDiscoveryError('The selected repository is missing its full repository name.')

    url = f"{_github_api_root(connection.base_url)}/repos/{full_name}/branches"
    headers = {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}',
    }

    branches: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(url, headers, params={'per_page': 100, 'page': page})
        items = payload if isinstance(payload, list) else []
        branches.extend(
            {
                'name': item.get('name', ''),
                'is_default': item.get('name') == repository.get('default_branch'),
                'protected': bool(item.get('protected', False)),
            }
            for item in items
            if item.get('name')
        )
        if len(items) < 100:
            break
        page += 1

    return branches


def _list_gitlab_branches(connection, token: str, repository: Dict[str, Any]) -> List[Dict[str, Any]]:
    repository_id = repository.get('id')
    if not repository_id:
        raise GitProviderDiscoveryError('The selected GitLab repository is missing its project identifier.')

    encoded_id = quote(str(repository_id), safe='')
    url = f"{_gitlab_api_root(connection.base_url)}/projects/{encoded_id}/repository/branches"
    headers = {'PRIVATE-TOKEN': token}

    branches: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(url, headers, params={'per_page': 100, 'page': page})
        items = payload if isinstance(payload, list) else []
        branches.extend(
            {
                'name': item.get('name', ''),
                'is_default': bool(item.get('default', False)),
                'protected': bool(item.get('protected', False)),
            }
            for item in items
            if item.get('name')
        )
        if len(items) < 100:
            break
        page += 1

    return branches


def _list_gitea_branches(connection, token: str, repository: Dict[str, Any]) -> List[Dict[str, Any]]:
    full_name = repository.get('full_name')
    if not full_name:
        raise GitProviderDiscoveryError('The selected Gitea repository is missing its full repository name.')

    url = f"{_gitea_api_root(connection.base_url)}/repos/{full_name}/branches"
    headers = {'Authorization': f'token {token}'}

    branches: List[Dict[str, Any]] = []
    page = 1
    while True:
        payload = _request_json(url, headers, params={'limit': 100, 'page': page})
        items = payload if isinstance(payload, list) else []
        branches.extend(
            {
                'name': item.get('name', ''),
                'is_default': item.get('name') == repository.get('default_branch'),
                'protected': bool(item.get('protected', False)),
            }
            for item in items
            if item.get('name')
        )
        if len(items) < 100:
            break
        page += 1

    return branches


def _resolve_repository(connection, repository_identifier: str) -> Dict[str, Any]:
    candidate = repository_identifier.strip()
    repositories = connection.repository_cache or []
    if not repositories:
        repositories = list_connection_repositories(connection)

    for repository in repositories:
        if _repository_matches(repository, candidate):
            return repository

    raise GitProviderDiscoveryError('The requested repository is not available through the selected connection.')


def _repository_matches(repository: Dict[str, Any], candidate: str) -> bool:
    normalized_candidate = _normalize_repository_value(candidate)
    values: Iterable[str] = (
        repository.get('id', ''),
        repository.get('name', ''),
        repository.get('full_name', ''),
        repository.get('clone_url', ''),
        repository.get('ssh_url', ''),
        repository.get('web_url', ''),
    )

    return any(_normalize_repository_value(value) == normalized_candidate for value in values if value)


def _normalize_repository_value(value: str) -> str:
    normalized = value.strip().rstrip('/')
    if normalized.endswith('.git'):
        normalized = normalized[:-4]
    return normalized.lower()


def _sort_branches(branches: List[Dict[str, Any]], default_branch: Optional[str]) -> List[Dict[str, Any]]:
    default_name = (default_branch or '').strip().lower()
    unique: Dict[str, Dict[str, Any]] = {}
    for branch in branches:
        name = branch.get('name')
        if not name:
            continue
        unique[name] = {
            **branch,
            'is_default': bool(branch.get('is_default')) or name.lower() == default_name,
        }

    return sorted(
        unique.values(),
        key=lambda branch: (not branch.get('is_default', False), branch.get('name', '').lower()),
    )