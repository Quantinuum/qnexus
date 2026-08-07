"""Status types for Nexus Jobs."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, NamedTuple

import pandas as pd

from qnexus.models.utils import truncate_to_2dp


class JobStatusEnum(str, Enum):
    """Possible job statuses"""

    COMPLETED = "COMPLETED"
    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    CANCELLING = "CANCELLING"
    RETRYING = "RETRYING"
    TERMINATED = "TERMINATED"
    DEPLETED = "DEPLETED"


class JobStatus(NamedTuple):
    """The status of a job along with an optional description.

    Optionally can also include extra fields such as:
    * Detailed error information.
    * Timestamps for changes in status.
    * Queue position.
    * Cost.
    """

    status: JobStatusEnum
    message: str = ""
    error_detail: str | None = None

    # Timestamp for when a status was last entered.
    completed_time: datetime | None = None
    queued_time: datetime | None = None
    submitted_time: datetime | None = None
    running_time: datetime | None = None
    cancelled_time: datetime | None = None
    error_time: datetime | None = None

    queue_position: int | None = None
    cost: float | None = None

    @classmethod
    def from_dict(cls, dic: Dict[str, Any]) -> "JobStatus":
        """Construct from JSON serializable dictionary."""
        invalid = ValueError(f"Dictionary invalid format for JobStatus: {dic}")
        if "message" not in dic or "status" not in dic:
            raise invalid

        try:
            status = next(s for s in JobStatusEnum if dic["status"] == s.name)
        except StopIteration as err:
            raise invalid from err

        error_detail = dic.get("error_detail", None)

        def read_optional_datetime(key: str) -> datetime | None:
            x = dic.get(key)
            return datetime.fromisoformat(x) if x is not None else None

        completed_time = read_optional_datetime("completed_time")
        queued_time = read_optional_datetime("queued_time")
        submitted_time = read_optional_datetime("submitted_time")
        running_time = read_optional_datetime("running_time")
        cancelled_time = read_optional_datetime("cancelled_time")
        error_time = read_optional_datetime("error_time")

        queue_position = dic.get("queue_position", None)
        cost: float | None = truncate_to_2dp(dic.get("cost", None))

        return cls(
            status,
            dic["message"],
            error_detail,
            completed_time,
            queued_time,
            submitted_time,
            running_time,
            cancelled_time,
            error_time,
            queue_position,
            cost,
        )

    def df(self) -> pd.DataFrame:
        """Present in a pandas DataFrame."""
        return pd.DataFrame.from_dict(
            self._asdict(),
            orient="index",
        ).T


WAITING_STATUS = {
    JobStatusEnum.QUEUED,
    JobStatusEnum.SUBMITTED,
    JobStatusEnum.RUNNING,
    JobStatusEnum.RETRYING,
    JobStatusEnum.CANCELLING,
}
