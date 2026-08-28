"""Tests for default costing system name selection based on domain.

Can be deleted once the automatic system selection is removed.
"""

import uuid
import warnings
from datetime import datetime
from unittest import mock

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

    def test_us_domain_defaults_to_helios_1(self) -> None:
        """When domain is nexus.quantinuum.com, default system should be Helios-1."""
        import qnexus.client.hugr as hugr_module

        project = _make_project()
        hugr_ref = _make_hugr_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = "nexus.quantinuum.com"
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                hugr_module.cost_confidence(
                    programs=hugr_ref,
                    n_shots=100,
                    project=project,
                )

            # Check that start_execute_job was called with the correct backend_config
            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == "Helios-1SC"

    def test_sg_domain_defaults_to_helios_2(self) -> None:
        """When domain is nexus.quantinuum.sg, default system should be Helios-2."""
        import qnexus.client.hugr as hugr_module

        project = _make_project()
        hugr_ref = _make_hugr_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = "nexus.quantinuum.sg"
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                hugr_module.cost_confidence(
                    programs=hugr_ref,
                    n_shots=100,
                    project=project,
                )

            # Check that start_execute_job was called with the correct backend_config
            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == "Helios-2SC"


class TestQirCostConfidenceDefaultSystem:
    """Tests for qir.cost_confidence default system_name selection."""

    def test_us_domain_defaults_to_helios_1(self) -> None:
        """When domain is nexus.quantinuum.com, default system should be Helios-1."""
        import qnexus.client.qir as qir_module

        project = _make_project()
        qir_ref = _make_qir_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = "nexus.quantinuum.com"
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                qir_module.cost_confidence(
                    programs=qir_ref,
                    n_shots=100,
                    project=project,
                )

            # Check that start_execute_job was called with the correct backend_config
            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == "Helios-1SC"

    def test_sg_domain_defaults_to_helios_2(self) -> None:
        """When domain is nexus.quantinuum.sg, default system should be Helios-2."""
        import qnexus.client.qir as qir_module

        project = _make_project()
        qir_ref = _make_qir_ref(project)

        with (
            mock.patch("qnexus.start_execute_job") as mock_start_execute_job,
            mock.patch("qnexus.jobs.wait_for"),
            mock.patch("qnexus.jobs.cost_confidence", return_value=[(1.0, 0.95)]),
            mock.patch("qnexus.models.region.CONFIG") as mock_config,
        ):
            mock_config.domain = "nexus.quantinuum.sg"
            mock_start_execute_job.return_value = mock.MagicMock()

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                qir_module.cost_confidence(
                    programs=qir_ref,
                    n_shots=100,
                    project=project,
                )

            # Check that start_execute_job was called with the correct backend_config
            call_kwargs = mock_start_execute_job.call_args.kwargs
            backend_config = call_kwargs["backend_config"]
            assert backend_config.system_name == "Helios-2SC"
