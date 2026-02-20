"""Test basic functionality relating to the gpu_decoder_config."""

from typing import Callable, ContextManager

import pandas as pd

import qnexus as qnx
from qnexus.models.job_status import JobStatusEnum
from qnexus.models.references import GpuDecoderConfigRef, Ref


def test_gpu_decoder_config_download(
    test_case_name: str,
    create_gpu_decoder_config_in_project: Callable[
        [str, str, str], ContextManager[GpuDecoderConfigRef]
    ],
    qa_gpu_decoder_config: str,
    test_ref_serialisation: Callable[[str, Ref], None],
) -> None:
    """Test that valid GPU decoder config can be extracted from an uploaded GPU decoder config."""

    project_name = f"project for {test_case_name}"
    gpu_decoder_config_name = f"gpu decoder config for {test_case_name}"

    with create_gpu_decoder_config_in_project(
        project_name,
        gpu_decoder_config_name,
        qa_gpu_decoder_config,
    ) as gpu_decoder_config_ref:
        assert isinstance(gpu_decoder_config_ref, GpuDecoderConfigRef)
        downloaded_gpu_decoder_config = (
            gpu_decoder_config_ref.download_gpu_decoder_config_contents()
        )

        assert downloaded_gpu_decoder_config == qa_gpu_decoder_config

        gpu_decoder_config_ref_by_id = qnx.gpu_decoder_configs.get(
            id=gpu_decoder_config_ref.id
        )
        test_ref_serialisation("gpu_decoder_config", gpu_decoder_config_ref_by_id)


def test_gpu_decoder_config_flow(
    test_case_name: str,
    create_gpu_decoder_config_in_project: Callable[
        [str, str, str], ContextManager[GpuDecoderConfigRef]
    ],
    qa_gpu_decoder_config: str,
    qa_qir_bitcode: bytes,
) -> None:
    """Test the flow for executing a program on an OG device with a GPU decoder config."""

    project_name = f"project for {test_case_name}"
    gpu_decoder_config_name = f"gpu decoder config for {test_case_name}"
    qir_name = f"qir for {test_case_name}"

    with (
        create_gpu_decoder_config_in_project(
            project_name,
            gpu_decoder_config_name,
            qa_gpu_decoder_config,
        ) as gpu_decoder_config_ref,
    ):
        proj_ref = qnx.projects.get(name=project_name)

        my_gpu_decoder_config_db_matches = qnx.gpu_decoder_configs.get_all()
        assert isinstance(my_gpu_decoder_config_db_matches.summarize(), pd.DataFrame)
        assert isinstance(next(my_gpu_decoder_config_db_matches), GpuDecoderConfigRef)

        gpu_decoder_config_ref = qnx.gpu_decoder_configs.get(
            name=gpu_decoder_config_name
        )
        assert isinstance(gpu_decoder_config_ref, GpuDecoderConfigRef)

        gpu_decoder_config_ref_2 = qnx.gpu_decoder_configs.get(
            id=gpu_decoder_config_ref.id
        )
        assert gpu_decoder_config_ref == gpu_decoder_config_ref_2

        qir_program_ref = qnx.qir.upload(
            qir=qa_qir_bitcode, name=qir_name, project=proj_ref
        )

        execute_job_ref = qnx.start_execute_job(
            programs=[qir_program_ref],
            name=f"qir gpu decoder config execute job for {test_case_name}",
            n_shots=[100],
            max_cost=[10.0],
            backend_config=qnx.QuantinuumConfig(
                device_name="H1-1E",
            ),
            gpu_decoder_config=gpu_decoder_config_ref,
            project=proj_ref,
        )

        # Don't fully submit the job (July 2025)
        qnx.jobs.wait_for(execute_job_ref, wait_for_status=JobStatusEnum.SUBMITTED)
        qnx.jobs.cancel(execute_job_ref)
        qnx.jobs.wait_for(execute_job_ref, wait_for_status=JobStatusEnum.CANCELLED)
