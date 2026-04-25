"""
Orchestrator abstraction layer for container management.
Supports Podman now, designed for future Kubernetes/OpenShift providers.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ServiceSpec:
    """Specification for a service/container to be deployed."""
    name: str
    service_type: str  # 'backend', 'frontend', 'tooling', 'custom'
    image: str
    ports: List[str] = None  # e.g., ['8080:8080'] for host mappings (empty for internal-only)
    environment: Dict[str, str] = None
    volumes: List[Dict[str, str]] = None  # [{'source': 'vol-name', 'target': '/path', 'type': 'volume'}]
    command: Optional[str] = None
    cpu_limit: Optional[str] = None  # e.g., '1.0', future use
    memory_limit: Optional[str] = None  # e.g., '512Mi', future use
    network: Optional[str] = None
    labels: Dict[str, str] = None
    workdir: Optional[str] = None
    autostart: bool = False
    depends_on: List[str] = None
    
    def __post_init__(self):
        self.ports = self.ports or []
        self.environment = self.environment or {}
        self.volumes = self.volumes or []
        self.labels = self.labels or {}
        self.depends_on = self.depends_on or []


@dataclass
class ServiceStatus:
    """Current status of a service."""
    container_name: str
    status: str  # 'running', 'stopped', 'error', 'creating', 'unknown'
    started_at: Optional[datetime] = None
    internal_address: Optional[str] = None  # e.g., 'container-name:3000'
    error_message: Optional[str] = None


@dataclass
class LogEntry:
    """Container log output."""
    logs: str
    truncated: bool = False


class OrchestratorError(RuntimeError):
    """Base exception for orchestrator operations."""
    pass


class Orchestrator(ABC):
    """Abstract base class for container orchestration providers."""
    
    @abstractmethod
    def ensure_pod(self, project_id: int) -> str:
        """
        Ensure a pod/namespace exists for the project.
        Returns the pod identifier (name or namespace).
        """
        pass
    
    @abstractmethod
    def ensure_service(self, project_id: int, spec: ServiceSpec) -> ServiceStatus:
        """
        Ensure a service is created and running according to spec.
        Idempotent - safe to call multiple times.
        Returns current service status.
        """
        pass
    
    @abstractmethod
    def get_service_status(self, project_id: int, service_name: str) -> ServiceStatus:
        """Get current status of a service."""
        pass
    
    @abstractmethod
    def start_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Start a stopped service."""
        pass
    
    @abstractmethod
    def stop_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Stop a running service."""
        pass
    
    @abstractmethod
    def restart_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Restart a service."""
        pass
    
    @abstractmethod
    def kill_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Forcefully kill a service."""
        pass
    
    @abstractmethod
    def get_service_logs(
        self, 
        project_id: int, 
        service_name: str, 
        tail: int = 1000,
        since: Optional[str] = None
    ) -> LogEntry:
        """
        Retrieve service logs.
        
        Args:
            project_id: Project identifier
            service_name: Service name
            tail: Number of lines from end (default 1000, max enforced by implementation)
            since: Timestamp or duration (e.g., '1h', '2024-01-01T00:00:00Z')
        """
        pass
    
    @abstractmethod
    def resolve_service_address(self, project_id: int, service_name: str, port: int) -> str:
        """
        Resolve internal network address for a service.
        Returns address like 'container-name:port' or 'service.namespace.svc.cluster.local:port'.
        """
        pass
    
    @abstractmethod
    def ensure_volume(self, project_id: int, volume_name: str) -> str:
        """
        Ensure a persistent volume exists for the project.
        Returns volume identifier.
        """
        pass
    
    @abstractmethod
    def list_services(self, project_id: int) -> List[ServiceStatus]:
        """List all services for a project."""
        pass
    
    @abstractmethod
    def delete_pod(self, project_id: int, force: bool = False) -> None:
        """Delete pod and all its services."""
        pass
