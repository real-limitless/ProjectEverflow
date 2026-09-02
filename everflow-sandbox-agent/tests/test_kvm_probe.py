"""KVM vCPU probe — must never run the ioctl in-process."""

from __future__ import annotations

import subprocess

from app.kvm_probe import kvm_vcpu_usable, reset_kvm_probe_cache


def test_vcpu_usable_false_when_device_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_device_present", lambda: False)
    reset_kvm_probe_cache()
    assert kvm_vcpu_usable(force=True) is False


def test_vcpu_usable_true_on_child_success(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_device_present", lambda: True)

    class _R:
        returncode = 0
        stderr = ""

    monkeypatch.setattr("app.kvm_probe.subprocess.run", lambda *a, **k: _R())
    reset_kvm_probe_cache()
    assert kvm_vcpu_usable(force=True) is True


def test_vcpu_usable_false_on_sigsegv(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_device_present", lambda: True)

    class _R:
        returncode = -11  # SIGSEGV
        stderr = ""

    monkeypatch.setattr("app.kvm_probe.subprocess.run", lambda *a, **k: _R())
    reset_kvm_probe_cache()
    assert kvm_vcpu_usable(force=True) is False


def test_vcpu_usable_false_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr("app.kvm_probe.kvm_device_present", lambda: True)

    def _boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="python", timeout=1)

    monkeypatch.setattr("app.kvm_probe.subprocess.run", _boom)
    reset_kvm_probe_cache()
    assert kvm_vcpu_usable(force=True) is False


def test_probe_source_runs_in_child_not_import() -> None:
    # Importing the module must not open /dev/kvm in this process.
    import app.kvm_probe as probe

    assert "fcntl.ioctl" in probe._PROBE_SOURCE
    assert "KVM_CREATE_VCPU" in probe._PROBE_SOURCE or "0xAE41" in probe._PROBE_SOURCE
