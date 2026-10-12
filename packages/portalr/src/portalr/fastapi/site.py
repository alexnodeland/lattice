"""What the UIs need to know about the application they run in, as ``config.json`` serves it."""

from pydantic import BaseModel, ConfigDict


class Surfaces(BaseModel):
    """Where the application mounts each router, as the UIs' client calls them."""

    model_config = ConfigDict(frozen=True)

    artifactr: str = "/artifactr/v1"
    reflexr: str = "/reflexr/v1"
    grantr: str = ""
    """The origin grantr's router is mounted at: its paths carry ``/grantr/v1`` themselves."""
    portalr: str = "/portalr/v1"


class Site(BaseModel):
    """The application's Supabase project, as the UIs sign in to it, and its surfaces.

    The same built UIs serve every deployment: what differs is here.
    """

    model_config = ConfigDict(frozen=True)

    supabase_url: str
    supabase_key: str
    """The project's publishable key, which the browser sends with every Supabase Auth call."""
    surfaces: Surfaces = Surfaces()
