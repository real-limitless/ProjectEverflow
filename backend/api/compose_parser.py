import re
from typing import Dict, Any, List, Optional, Tuple

import yaml

from .orchestrator import ServiceSpec


COMPOSE_CANDIDATES = [
    "everflow-compose.yml",
    "podman-compose.yml",
    "podman-compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]


class ComposeParseError(RuntimeError):
    pass


def _sanitize_service_name(name: str) -> str:
    # Keep alnum, dash, underscore; lowercased
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", name).lower()
    return cleaned[:200]


def _as_command(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    return str(value)


def _parse_volume_entry(raw: str, project_id: int, workspace_volume: str) -> Optional[Dict[str, Any]]:
    # Supports formats: name:target[:mode] or ./path:target[:mode]
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    source, target = parts[0], parts[1]
    mode = parts[2] if len(parts) > 2 else ""
    readonly = "ro" in mode

    if source.startswith("/"):
        # Absolute binds not allowed for safety
        raise ComposeParseError(f"Absolute bind mounts are not supported: {source}")

    if source.startswith("."):
        # Relative bind -> mount workspace volume to target
        return {"type": "volume", "source": workspace_volume, "target": target, "readonly": readonly}

    # Named volume
    vol_name = f"proj-{project_id}-{source}"
    return {"type": "volume", "source": vol_name, "target": target, "readonly": readonly}


def _extract_limits(service_def: Dict[str, Any], default_cpu: str, default_mem: str) -> Dict[str, Optional[str]]:
    limits = service_def.get("deploy", {}).get("resources", {}).get("limits", {})
    cpu = limits.get("cpus") or default_cpu
    mem = limits.get("memory") or default_mem
    return {"cpu": cpu, "memory": mem}


def _normalize_build_config(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"context": raw}
    if not isinstance(raw, dict):
        return None

    context = raw.get("context", ".")
    dockerfile = raw.get("dockerfile")
    target = raw.get("target")
    args = raw.get("args") or {}

    if isinstance(args, list):
        parsed_args = {}
        for item in args:
            if isinstance(item, str) and "=" in item:
                key, val = item.split("=", 1)
                parsed_args[key] = val
        args = parsed_args
    elif not isinstance(args, dict):
        args = {}

    return {
        "context": context,
        "dockerfile": dockerfile,
        "target": target,
        "args": args,
    }


def build_service_specs(
    compose: Dict[str, Any],
    project_id: int,
    workspace_volume: str,
    network_name: str,
    default_cpu: str,
    default_mem: str,
) -> Tuple[List[ServiceSpec], List[Dict[str, Any]]]:
    services = compose.get("services", {}) or {}
    if not isinstance(services, dict):
        raise ComposeParseError("Invalid compose services section")

    specs: List[ServiceSpec] = []
    build_specs: List[Dict[str, Any]] = []

    for raw_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        name = _sanitize_service_name(raw_name)

        build_cfg = _normalize_build_config(svc.get("build"))
        image = svc.get("image")
        if not image and build_cfg:
            image = f"localhost/proj-{project_id}-{name}:latest"
        if not image:
            continue

        env = svc.get("environment") or {}
        if isinstance(env, list):
            env_dict = {}
            for item in env:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, val = item.split("=", 1)
                env_dict[key] = val
            env = env_dict

        labels = svc.get("labels") or {}
        if isinstance(labels, list):
            label_dict = {}
            for item in labels:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, val = item.split("=", 1)
                label_dict[key] = val
            labels = label_dict

        volumes = []
        raw_vols = svc.get("volumes") or []
        for v in raw_vols:
            if isinstance(v, str):
                parsed = _parse_volume_entry(v, project_id, workspace_volume)
                if parsed:
                    volumes.append(parsed)
            elif isinstance(v, dict):
                vtype = v.get("type", "volume")
                source = v.get("source") or v.get("src")
                target = v.get("target") or v.get("dst") or v.get("destination")
                readonly = v.get("read_only") or v.get("ro") or False
                if not source or not target:
                    continue
                if vtype == "bind":
                    raise ComposeParseError("Bind mounts are not supported; use named volumes")
                vol_name = f"proj-{project_id}-{source}" if not source.startswith(workspace_volume) else source
                volumes.append({"type": "volume", "source": vol_name, "target": target, "readonly": bool(readonly)})

        limits = _extract_limits(svc, default_cpu, default_mem)

        # Parse ports - extract container ports for display (no host binding)
        raw_ports = svc.get("ports") or []
        parsed_ports = []
        for p in raw_ports:
            if isinstance(p, (int, str)):
                # e.g. "8080" or "8080:80" or 8080
                port_str = str(p)
                if ":" in port_str:
                    # Take container port (right side)
                    parts = port_str.split(":")
                    container_port = parts[-1].split("/")[0]  # strip /tcp etc
                    parsed_ports.append(container_port)
                else:
                    parsed_ports.append(port_str.split("/")[0])
            elif isinstance(p, dict):
                target = p.get("target")
                if target:
                    parsed_ports.append(str(target))

        command = _as_command(svc.get("command"))
        entrypoint = _as_command(svc.get("entrypoint"))
        full_command = None
        if entrypoint and command:
            full_command = f"{entrypoint} {command}"
        elif entrypoint:
            full_command = entrypoint
        else:
            full_command = command

        workdir = svc.get("working_dir")
        
        # Read autostart from labels (x-autostart: "true")
        autostart = False
        if isinstance(labels, dict):
            autostart_label = labels.get("x-autostart", "false").lower()
            autostart = autostart_label in ("true", "1", "yes")
        
        # Extract dependencies
        depends_on = svc.get("depends_on", [])
        if isinstance(depends_on, dict):
            # compose v3 format: {service: {condition: ...}}
            depends_on = list(depends_on.keys())
        elif not isinstance(depends_on, list):
            depends_on = []

        specs.append(ServiceSpec(
            name=name,
            service_type=svc.get("service_type", "custom"),
            image=image,
            ports=parsed_ports,  # container ports for display
            environment=env,
            volumes=volumes,
            command=full_command,
            cpu_limit=limits["cpu"],
            memory_limit=limits["memory"],
            network=network_name,
            labels=labels,
            workdir=workdir,
            autostart=autostart,
            depends_on=depends_on,
        ))

        if build_cfg:
            build_specs.append({
                "name": name,
                "image": image,
                "context": build_cfg.get("context", "."),
                "dockerfile": build_cfg.get("dockerfile"),
                "target": build_cfg.get("target"),
                "args": build_cfg.get("args", {}),
            })

    return specs, build_specs


def extract_dependency_order(compose: Dict[str, Any]) -> List[str]:
    services = compose.get("services", {}) or {}
    deps = {name: set(defn.get("depends_on", {}).keys() if isinstance(defn.get("depends_on"), dict) else defn.get("depends_on", []) or []) for name, defn in services.items() if isinstance(defn, dict)}

    # Kahn's algorithm for topo sort
    all_nodes = set(deps.keys())
    for d in deps.values():
        all_nodes.update(d)

    incoming = {n: set() for n in all_nodes}
    for n, ds in deps.items():
        for d in ds:
            incoming[n].add(d)

    ready = [n for n in all_nodes if not incoming[n]]
    order = []
    while ready:
        node = ready.pop()
        order.append(node)
        for n, ds in deps.items():
            if node in ds:
                ds.remove(node)
                incoming[n].discard(node)
                if not incoming[n]:
                    ready.append(n)

    # Append remaining nodes (cycles) at the end
    for n in all_nodes:
        if n not in order:
            order.append(n)
    return order


def load_compose_from_text(text: str) -> Dict[str, Any]:
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ComposeParseError(f"Failed to parse compose file: {exc}") from exc
