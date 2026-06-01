"""Client API for teams in Nexus."""

import qnexus.exceptions as qnx_exc
from qnexus.client import get_nexus_client
from qnexus.context import merge_scope_from_context
from qnexus.models.references import DataframableList, TeamRef
from qnexus.models.scope import ScopeFilterEnum


@merge_scope_from_context
def get_all(scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> DataframableList[TeamRef]:
    """Get all teams.

    Examples:
        >>> import qnexus as qnx
        >>> all_teams = qnx.teams.get_all()
        >>> all_teams.df()
    """
    res = get_nexus_client().get(
        "/api/teams/v1beta2",
        params={"scope": scope.value},
    )

    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    return DataframableList(
        [
            TeamRef(
                id=team["id"],
                name=team["attributes"]["name"],
                description=team["attributes"]["description"],
            )
            for team in res.json()["data"]
        ]
    )


@merge_scope_from_context
def get(name: str, scope: ScopeFilterEnum = ScopeFilterEnum.USER) -> TeamRef:
    """
    Get a single team using filters. Throws an exception if the filters do not
    match exactly one object.

    Examples:
        >>> import qnexus as qnx
        >>> team_ref = qnx.teams.get(name="my-team")
    """
    res = get_nexus_client().get(
        "/api/teams/v1beta2",
        params={
            "filter[team][name]": name,
            "scope": scope.value,
        },
    )

    if res.status_code == 404 or res.json()["data"] == []:
        raise qnx_exc.ZeroMatches

    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    teams_list = [
        TeamRef(
            id=team["id"],
            name=team["attributes"]["name"],
            description=team["attributes"]["description"],
        )
        for team in res.json()["data"]
    ]

    if len(teams_list) > 1:
        print(teams_list)
        raise qnx_exc.NoUniqueMatch

    return teams_list[0]


@merge_scope_from_context
def _fetch_by_id(
    team_id: str, scope: ScopeFilterEnum = ScopeFilterEnum.USER
) -> TeamRef:
    """
    Get a single team by id.
    """
    res = get_nexus_client().get(
        f"/api/teams/v1beta2/{team_id}",
        params={"scope": scope.value},
    )

    if res.status_code == 404:
        raise qnx_exc.ZeroMatches

    if res.status_code != 200:
        raise qnx_exc.ResourceFetchFailed(message=res.text, status_code=res.status_code)

    team_dict = res.json()["data"]

    return TeamRef(
        id=team_dict["id"],
        name=team_dict["attributes"]["name"],
        description=team_dict["attributes"]["description"],
    )


def create(name: str, description: str | None = None) -> TeamRef:
    """Create a team in Nexus.

    Examples:
        >>> import qnexus as qnx
        >>> team_ref = qnx.teams.create(name="team-unobtainium", description="Team studying novel materials")
    """

    resp = get_nexus_client().post(
        "/api/teams/v1beta2",
        json={
            "data": {
                "attributes": {
                    "name": name,
                    "description": description,
                    "display_name": name,
                },
                "relationships": {},
                "type": "team",
            },
        },
    )

    if resp.status_code != 201:
        raise qnx_exc.ResourceCreateFailed(
            message=resp.text, status_code=resp.status_code
        )

    team_dict = resp.json()["data"]
    return TeamRef(
        id=team_dict["id"],
        name=team_dict["attributes"]["name"],
        description=team_dict["attributes"]["description"],
    )
