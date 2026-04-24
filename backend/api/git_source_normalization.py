from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


KNOWN_PROVIDER_HOSTS = {
    'github': 'github.com',
    'gitlab': 'gitlab.com',
    'bitbucket': 'bitbucket.org',
}
KNOWN_PUBLIC_HOSTS = set(KNOWN_PROVIDER_HOSTS.values())

SSH_REPOSITORY_PATTERN = re.compile(r'^(?P<user>[^@/\s]+)@(?P<host>[^:/\s]+):(?P<path>.+)$')
REPOSITORY_SLUG_PATTERN = re.compile(r'^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+$')


class GitRepositoryNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedGitRepository:
    clone_url: str
    input_kind: str
    host: Optional[str] = None


def normalize_public_git_repository_input(
    raw_input: str,
    provider_hint: Optional[str] = None,
) -> NormalizedGitRepository:
    candidate = (raw_input or '').strip()
    if not candidate:
        raise GitRepositoryNormalizationError('Enter a repository URL or supported owner/repo slug.')

    ssh_match = SSH_REPOSITORY_PATTERN.match(candidate)
    if ssh_match:
        host = ssh_match.group('host').strip().lower()
        repository_path = _normalize_repository_path(ssh_match.group('path'), strip_dot_git=True)
        return NormalizedGitRepository(
            clone_url=f'https://{host}/{repository_path}',
            input_kind='ssh',
            host=host,
        )

    parsed = urlsplit(candidate)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme in {'http', 'https'}:
            hostname = (parsed.hostname or '').lower()
            strip_dot_git = hostname in KNOWN_PUBLIC_HOSTS
            repository_path = _normalize_repository_path(parsed.path, strip_dot_git=strip_dot_git)
            scheme = 'https' if hostname in KNOWN_PUBLIC_HOSTS else parsed.scheme
            netloc = parsed.netloc.strip().lower() if hostname in KNOWN_PUBLIC_HOSTS else parsed.netloc.strip()
            return NormalizedGitRepository(
                clone_url=urlunsplit((scheme, netloc, f'/{repository_path}', '', '')),
                input_kind='url',
                host=hostname or None,
            )

        if parsed.scheme in {'ssh', 'git+ssh'} and parsed.hostname:
            host = parsed.hostname.lower()
            repository_path = _normalize_repository_path(parsed.path, strip_dot_git=True)
            return NormalizedGitRepository(
                clone_url=f'https://{host}/{repository_path}',
                input_kind='ssh-url',
                host=host,
            )

        raise GitRepositoryNormalizationError(
            'Enter a public HTTPS repository URL, an SSH clone URL, or a supported owner/repo slug.'
        )

    if REPOSITORY_SLUG_PATTERN.match(candidate):
        host = KNOWN_PROVIDER_HOSTS.get((provider_hint or '').strip())
        if not host:
            raise GitRepositoryNormalizationError(
                'Enter a full repository URL, or choose GitHub, GitLab, or Bitbucket when using an owner/repo slug.'
            )

        repository_path = _normalize_repository_path(candidate, strip_dot_git=True)
        return NormalizedGitRepository(
            clone_url=f'https://{host}/{repository_path}',
            input_kind='slug',
            host=host,
        )

    raise GitRepositoryNormalizationError(
        'Enter a public HTTPS repository URL, an SSH clone URL, or a supported owner/repo slug.'
    )


def _normalize_repository_path(raw_path: str, *, strip_dot_git: bool) -> str:
    repository_path = (raw_path or '').strip().strip('/')
    if strip_dot_git and repository_path.lower().endswith('.git'):
        repository_path = repository_path[:-4]

    if not repository_path or '/' not in repository_path:
        raise GitRepositoryNormalizationError('Enter both the repository owner and repository name.')

    return repository_path