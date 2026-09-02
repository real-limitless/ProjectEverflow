"""Probe whether this kernel can create a KVM vCPU.

``/dev/kvm`` existing is not enough. On some nested Cloud Agent kernels,
``KVM_CREATE_VCPU`` hits ``kvm_spurious_fault`` (kernel BUG in
``alloc_loaded_vmcs``) and the calling process is SIGSEGV'd. The probe
always runs in a child so the agent process survives.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# linux/kvm.h — _IO(KVMIO, n) on x86_64
_KVM_CREATE_VM = 0xAE01
_KVM_CREATE_VCPU = 0xAE41

_PROBE_SOURCE = f"""
import fcntl
import os
import sys

try:
    fd = os.open("/dev/kvm", os.O_RDWR)
except OSError as exc:
    sys.stderr.write(f"open /dev/kvm: {{exc}}\\n")
    sys.exit(2)
try:
    vm = fcntl.ioctl(fd, {_KVM_CREATE_VM}, 0)
    vcpu = fcntl.ioctl(vm, {_KVM_CREATE_VCPU}, 0)
except OSError as exc:
    sys.stderr.write(f"KVM_CREATE_VCPU: {{exc}}\\n")
    sys.exit(3)
except Exception as exc:
    sys.stderr.write(f"kvm probe: {{exc}}\\n")
    sys.exit(4)
os.close(vcpu)
os.close(vm)
os.close(fd)
sys.exit(0)
"""

_cached: bool | None = None


def kvm_device_present() -> bool:
    return Path("/dev/kvm").exists()


def kvm_vcpu_usable(*, timeout: float = 4.0, force: bool = False) -> bool:
    """True when a child process can create a KVM VM + vCPU without dying."""
    global _cached
    if _cached is not None and not force:
        return _cached
    if not kvm_device_present():
        _cached = False
        return False
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_SOURCE],
            check=False,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("KVM vCPU probe timed out (kernel likely hung in ioctl)")
        _cached = False
        return False
    except OSError as exc:
        logger.warning("KVM vCPU probe failed to spawn: %s", exc)
        _cached = False
        return False

    if proc.returncode == 0:
        _cached = True
        return True

    # Negative returncode = killed by signal (SIGSEGV from kvm_spurious_fault).
    if proc.returncode < 0:
        logger.warning(
            "KVM vCPU probe killed by signal %s — nested KVM cannot create vCPUs "
            "on this kernel (alloc_loaded_vmcs / kvm_spurious_fault)",
            -proc.returncode,
        )
    else:
        logger.warning(
            "KVM vCPU probe failed rc=%s stderr=%s",
            proc.returncode,
            (proc.stderr or "").strip()[:300],
        )
    _cached = False
    return False


def reset_kvm_probe_cache() -> None:
    global _cached
    _cached = None
