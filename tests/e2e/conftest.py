"""Acceptance runs must fail when integration coverage is skipped."""
from __future__ import annotations

import os

import pytest

skipped = 0


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global skipped
    if report.skipped:
        skipped += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if os.getenv("VTT_ACCEPTANCE_REQUIRED") == "1" and skipped:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
