"""The relay records a route only as the app's router names it: the list is the router's."""

import json
import re
from pathlib import Path

from portalr.analytics.relay import ROUTES

ROUTE_TREE = Path(__file__).parents[1] / "web" / "app" / "src" / "routeTree.gen.ts"


def test_the_relays_routes_are_the_apps_router_s() -> None:
    by_full_path = re.search(
        r"interface FileRoutesByFullPath \{(.*?)\n\}", ROUTE_TREE.read_text(), re.S
    )
    assert by_full_path
    routes = {path.rstrip("/") or "/" for path in re.findall(r"'(/[^']*)'", by_full_path[1])}
    assert routes == ROUTES, "regenerate src/portalr/analytics/routes.json from the router"


def test_the_routes_file_is_sorted_and_whole() -> None:
    listed = json.loads(
        (Path(__file__).parents[1] / "src/portalr/analytics/routes.json").read_text()
    )["routes"]
    assert listed == sorted(set(listed))
