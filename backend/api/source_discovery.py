from __future__ import annotations

from typing import Any, Dict, List, Optional

from urllib.parse import quote

import requests


GIT_PROVIDER_TYPES = {'github', 'gitlab', 'bitbucket', 'gitea', 'generic-git'}
HOSTED_GIT_PROVIDER_TYPES = {'github', 'gitlab', 'bitbucket', 'gitea'}
RAW_SOURCE_KINDS = {'raw-compose', 'raw-dockerfile'}


class SourceDiscoveryError(Exception):
    pass


def get_source_discovery_payload(
    provider: str,
    source_kind: str,
    *,
    search: Optional[str] = None,
    repository: Optional[str] = None,
) -> Dict[str, Any]:
    _validate_provider_and_kind(provider, source_kind)

    capabilities = _build_capabilities(provider, source_kind)
    payload: Dict[str, Any] = {
        'provider': provider,
        'source_kind': source_kind,
        'capabilities': capabilities,
        'manual_guidance': _manual_guidance(provider, source_kind),
        'repositories': [],
        'tags': [],
    }

    if provider != 'docker-registry':
        return payload

    try:
        if search and search.strip():
            payload['repositories'] = search_docker_hub_repositories(search.strip())
        if repository and repository.strip():
            normalized_repository = normalize_docker_hub_repository(repository.strip())
            payload['selected_repository'] = normalized_repository
            payload['tags'] = list_docker_hub_tags(normalized_repository)
    except SourceDiscoveryError as exc:
        payload['lookup_error'] = str(exc)

    return payload


def normalize_docker_hub_repository(repository: str) -> str:
    normalized = repository.strip().strip('/')
    if not normalized:
        return normalized
    if '/' not in normalized:
        return f'library/{normalized}'
    return normalized


def search_docker_hub_repositories(search: str) -> List[Dict[str, Any]]:
    payload = _request_json(
        'https://hub.docker.com/v2/search/repositories/',
        params={
            'page_size': 25,
            'page': 1,
            'query': search,
        },
    )
    items = payload.get('results') or []

    repositories: List[Dict[str, Any]] = []
    for item in items:
        full_name = item.get('repo_name') or ''
        namespace = item.get('namespace') or ''
        name = item.get('name') or (full_name.split('/', 1)[1] if '/' in full_name else full_name)
        if not full_name and namespace and name:
            full_name = f'{namespace}/{name}'
        if not full_name:
            continue

        repositories.append(
            {
                'name': name,
                'full_name': full_name,
                'description': item.get('short_description') or item.get('description') or '',
                'star_count': int(item.get('star_count') or 0),
                'pull_count': int(item.get('pull_count') or 0),
                'is_official': bool(item.get('is_official', False)),
            }
        )

    return repositories


def list_docker_hub_tags(repository: str) -> List[Dict[str, Any]]:
    payload = _request_json(
        f'https://hub.docker.com/v2/repositories/{quote(repository, safe="")}/tags/',
        params={
            'page_size': 25,
            'page': 1,
        },
    )
    items = payload.get('results') or []

    tags: List[Dict[str, Any]] = []
    for item in items:
        name = item.get('name') or ''
        if not name:
            continue
        images = item.get('images') or []
        digest = item.get('digest') or (images[0].get('digest') if images else '')
        tags.append(
            {
                'name': name,
                'full_name': f'{repository}:{name}',
                'last_updated': item.get('last_updated') or '',
                'digest': digest or '',
            }
        )

    return tags


def _validate_provider_and_kind(provider: str, source_kind: str) -> None:
    if provider in GIT_PROVIDER_TYPES:
        if source_kind != 'git-repository':
            raise SourceDiscoveryError('Git providers must use the git-repository source kind.')
        return

    if provider == 'raw-compose':
        if source_kind not in RAW_SOURCE_KINDS:
            raise SourceDiscoveryError('Raw compose sources must use the raw-compose or raw-dockerfile source kind.')
        return

    if provider == 'docker-registry':
        if source_kind != 'container-image':
            raise SourceDiscoveryError('Docker registry sources must use the container-image source kind.')
        return

    raise SourceDiscoveryError('Unsupported provider for source discovery.')


def _build_capabilities(provider: str, source_kind: str) -> Dict[str, bool]:
    return {
        'manual_entry': True,
        'connection_selector': provider in GIT_PROVIDER_TYPES,
        'repository_browser': provider in HOSTED_GIT_PROVIDER_TYPES,
        'branch_browser': provider in HOSTED_GIT_PROVIDER_TYPES,
        'registry_search': provider == 'docker-registry' and source_kind == 'container-image',
        'tag_browser': provider == 'docker-registry' and source_kind == 'container-image',
        'build_context_path': source_kind == 'raw-dockerfile',
    }


def _manual_guidance(provider: str, source_kind: str) -> str:
    if provider == 'generic-git':
        return 'Enter a repository URL or slug and source ref manually. Generic Git connections do not expose repository browsing.'
    if provider == 'raw-compose' and source_kind == 'raw-compose':
        return 'Enter the raw compose file URL or location manually. Repository browsing is not available for this source kind.'
    if provider == 'raw-compose' and source_kind == 'raw-dockerfile':
        return 'Enter the raw Dockerfile URL or location manually and set a build context path if needed.'
    if provider == 'docker-registry':
        return 'Search public Docker Hub repositories and tags when available, or enter an image reference manually.'
    return 'Use the saved Git connection browser when available, or enter the source manually.'


def _request_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SourceDiscoveryError('Source discovery lookup failed. Manual entry is still available.') from exc
    except ValueError as exc:
        raise SourceDiscoveryError('Source discovery returned an invalid response. Manual entry is still available.') from exc

    if isinstance(payload, dict):
        return payload

    raise SourceDiscoveryError('Source discovery returned an unexpected response. Manual entry is still available.')