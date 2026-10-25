"""Tests unitaires — AD/runner.py::_run_proc / _describe_rc

Avant ce correctif, seul subprocess.TimeoutExpired était intercepté : toute
autre erreur de lancement (interpréteur introuvable, cwd invalide,
permissions...) remontait en exception non gérée et faisait planter tout le
run_domain() (tous les devices/domaines restants), au lieu d'être journalisée
et traitée comme un échec isolé pour ce device. Le code retour était en plus
un simple -1 indifférencié entre "timeout" et "process lancé mais en échec".
"""
import subprocess
from pathlib import Path

import runner as runner_module
from runner import _EXIT_SUBPROCESS_ERROR, _EXIT_TIMEOUT, _describe_rc, _run_proc


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


class TestRunProcSuccess:
    def test_returns_zero_on_success(self, monkeypatch):
        monkeypatch.setattr(
            runner_module.subprocess, "run",
            lambda *a, **kw: _FakeCompletedProcess(0),
        )
        rc = _run_proc(["echo", "hi"], cwd=Path("."), label="test", timeout=10)
        assert rc == 0

    def test_passes_through_nonzero_exit_code(self, monkeypatch):
        monkeypatch.setattr(
            runner_module.subprocess, "run",
            lambda *a, **kw: _FakeCompletedProcess(3, stderr="boom"),
        )
        rc = _run_proc(["python", "bad.py"], cwd=Path("."), label="test", timeout=10)
        assert rc == 3


class TestRunProcTimeout:
    def test_timeout_returns_sentinel_not_exception(self, monkeypatch):
        def _raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="x", timeout=10)

        monkeypatch.setattr(runner_module.subprocess, "run", _raise_timeout)
        rc = _run_proc(["python", "slow.py"], cwd=Path("."), label="test", timeout=10)

        assert rc == _EXIT_TIMEOUT


class TestRunProcLaunchFailure:
    def test_os_error_returns_sentinel_not_exception(self, monkeypatch):
        """Regression: an OSError (missing interpreter, bad cwd, permissions)
        must be caught here — not propagate and abort the whole domain run."""
        def _raise_os_error(*a, **kw):
            raise FileNotFoundError("no such file or directory: 'python'")

        monkeypatch.setattr(runner_module.subprocess, "run", _raise_os_error)
        rc = _run_proc(["python", "x.py"], cwd=Path("."), label="test", timeout=10)

        assert rc == _EXIT_SUBPROCESS_ERROR

    def test_timeout_and_launch_failure_are_distinguishable(self):
        assert _EXIT_TIMEOUT != _EXIT_SUBPROCESS_ERROR


class TestDescribeRc:
    def test_describes_timeout(self):
        assert _describe_rc(_EXIT_TIMEOUT) == "timeout"

    def test_describes_launch_failure(self):
        assert "lancement" in _describe_rc(_EXIT_SUBPROCESS_ERROR)

    def test_describes_real_exit_code(self):
        assert _describe_rc(3) == "exit=3"

    def test_describes_zero(self):
        assert _describe_rc(0) == "exit=0"
