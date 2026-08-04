import json
from collections.abc import Callable
from urllib.request import Request, urlopen


JsonTransport = Callable[[str, float, dict[str, str]], dict[str, object]]
JsonPostTransport = Callable[
    [str, dict[str, object], float, dict[str, str]], dict[str, object]
]


def get_json(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - provider URLs are configured, not user supplied
        return json.load(response)


def post_json(
    url: str, payload: dict[str, object], timeout: float, headers: dict[str, str]
) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured Azure endpoint
        return json.load(response)
