"""Unit tests for Traefik route rendering and dry-run deploy_remote."""

from app.services.deploy_remote import (
    DeployRoute,
    execute_compose_up,
    render_traefik_routes_yml,
)


def test_render_traefik_routes_yml_host_rule():
    yml = render_traefik_routes_yml(
        [
            DeployRoute(name="web", domain="app.example.com", service="web", port=8080),
            DeployRoute(
                name="api",
                domain="api.example.com",
                service="api",
                port=3000,
                url="http://127.0.0.1:3000",
            ),
        ]
    )
    assert 'rule: "Host(`app.example.com`)"' in yml
    assert 'rule: "Host(`api.example.com`)"' in yml
    assert 'url: "http://web:8080"' in yml
    assert 'url: "http://127.0.0.1:3000"' in yml
    assert "service: web" in yml


def test_execute_compose_up_dry_run():
    result = execute_compose_up(
        host="edge.example.com",
        user="everflow",
        port=22,
        private_key="-----BEGIN OPENSSH PRIVATE KEY-----\nTEST\n-----END OPENSSH PRIVATE KEY-----",
        local_workspace_hint=None,
        compose_rel_path="docker-compose.yml",
        routes=[{"name": "web", "domain": "app.example.com", "service": "web", "port": 8080}],
        remote_dir="/opt/everflow/apps/demo",
        dry_run=True,
    )
    assert result.ok is True
    assert result.error is None
    assert any("dry-run" in line for line in result.log_lines)
    assert 'Host(`app.example.com`)' in "\n".join(result.log_lines)
