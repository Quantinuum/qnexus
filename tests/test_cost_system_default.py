"""Tests for default costing system name selection based on domain.

Can be deleted once the automatic system selection is removed.
"""

import uuid
import warnings
from datetime import datetime
from unittest import mock

import pytest

from qnexus.models.annotations import Annotations
from qnexus.models.references import HUGRRef, ProjectRef, QIRRef


def _make_project() -> ProjectRef:
    """Create a mock ProjectRef for testing."""
    return ProjectRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        contents_modified=datetime.now(),
    )


def _make_hugr_ref(project: ProjectRef) -> HUGRRef:
    """Create a mock HUGRRef for testing."""
    return HUGRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=project,
    )


def _make_qir_ref(project: ProjectRef) -> QIRRef:
    """Create a mock QIRRef for testing."""
    return QIRRef(
        id=uuid.uuid4(),
        annotations=Annotations(),
        project=project,
    )


class TestHugrCostConfidenceDefaultSystem:
    """Tests for hugr.cost_confidence default system_name selection."""

    @pytest.mark.parametrize(
        "domain, target_region, expected_system",
        [
            # Domain-based defaults (no target_region)
            ("nexus.quantinuum.com", None, "Helios-1SC"),
            ("nexus.quantinuum.sg", None, "Helios-2SC"),
            # target_region overrides domain
            ("nexus.quantinuum.sg", "us", "Helios-1SC"),
            ("nexus.quantinuum.com", "sg", "Helios-2SC"),
        ],
    )
    def test_system_name_selection(
        self, domain: str, target_region: str | None, expected_system: str
    ) -> None:
        """Verify correct Helios system is selected based on domain and target_region."""
        import qnexus.client.hugr as hugr_module

        project = _make_project()
        hugr_ref = _make_hugr_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = domain
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                kwargs = {
                    "programs": hugr_ref,
                    "n_shots": 100,
                    "project": project,
                }
                if target_region is not None:
                    kwargs["target_region"] = target_region
                hugr_module.cost_confidence(**kwargs)  # type: ignore[arg-type]

            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == expected_system


class TestQirCostConfidenceDefaultSystem:
    """Tests for qir.cost_confidence default system_name selection."""

    @pytest.mark.parametrize(
        "domain, target_region, expected_system",
        [
            # Domain-based defaults (no target_region)
            ("nexus.quantinuum.com", None, "Helios-1SC"),
            ("nexus.quantinuum.sg", None, "Helios-2SC"),
            # target_region overrides domain
            ("nexus.quantinuum.sg", "us", "Helios-1SC"),
            ("nexus.quantinuum.com", "sg", "Helios-2SC"),
        ],
    )
    def test_system_name_selection(
        self, domain: str, target_region: str | None, expected_system: str
    ) -> None:
        """Verify correct Helios system is selected based on domain and target_region."""
        import qnexus.client.qir as qir_module

        project = _make_project()
        qir_ref = _make_qir_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = domain
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                kwargs = {
                    "programs": qir_ref,
                    "n_shots": 100,
                    "project": project,
                }
                if target_region is not None:
                    kwargs["target_region"] = target_region
                qir_module.cost_confidence(**kwargs)  # type: ignore[arg-type]

            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == expected_system
