"""Client API for quotas in Nexus."""

from typing import Literal

from qnexus.client import get_nexus_client
from qnexus.client.users import get_self
from qnexus.exceptions import ResourceFetchFailed
from qnexus.models import Quota
from qnexus.models.references import DataframableList

QuotaName = Literal["compilation", "simulation", "jupyterhub", "database_usage"]

_quota_map = {
    "compilation": "total_time_taken",
    "simulation": "total_time_taken",
    "jupyterhub": "total_time_taken",
    "database_usage": "megabytes_used",
}

NO_QUOTA_SET = "No quota set for user"


def get_all() -> DataframableList[Quota]:
    """Get all quotas, including usage."""
    user = get_self()

    res = get_nexus_client().get(
        "/api/quotas/v1beta",
        params={
            "entity_type": "user",
            "entity_id": str(user.id),
            "include_usage": True,
        },
    )

    if res.status_code != 200:
        raise ResourceFetchFailed(message=res.text, status_code=res.status_code)

    quota_list: DataframableList[Quota] = DataframableList([])
    for quota in res.json():
        try:
            quota_key = _quota_map[quota["quota"]["name"]]
        except KeyError:
            # If the quota name is not in the map, skip it
            continue
        quota_value = quota["quota"]["details"].get(quota_key, None)
        quota_list.append(
            Quota(
                name=quota["quota"]["name"],
                description=quota["quota"]["details"]["description"],
                usage=quota["quota"]["usage"].get(quota_key, 0),
                quota=quota_value if quota_value else NO_QUOTA_SET,
            )
        )

    return quota_list


def get(name: QuotaName) -> Quota:
    """Get specific quota details by name."""
    user = get_self()

    res = get_nexus_client().get(
        "/api/quotas/v1beta3",
        params={
            "entity_type": "user",
            "entity_id": str(user.id),
            "name": name,
            "include_usage": True,
        },  # needs user id
    )

    if res.status_code != 200:
        raise ResourceFetchFailed(message=res.text, status_code=res.status_code)

    quota = res.json()[0]

    quota_key = _quota_map[quota["quota"]["name"]]
    quota_value = quota["quota"]["details"].get(quota_key, None)

    return Quota(
        name=quota["quota"]["name"],
        description=quota["quota"]["details"]["description"],
        usage=quota["quota"]["usage"].get(quota_key, 0),
        quota=quota_value if quota_value else NO_QUOTA_SET,
    )


def check_quota(name: QuotaName) -> bool:
    """Check that the current user has available quota."""
    user = get_self()
    res = get_nexus_client().get(
        "/api/quotas/v1beta3/guard", params={"name": name, "user_id": str(user.id)}
    )

    if res.status_code != 200:
        return False
    return True
