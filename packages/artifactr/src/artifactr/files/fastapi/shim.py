"""The editor's shim: lattice's own page, beside an app's unmodified build, on the editor's origin.

An app's host surface hears only a page of its own origin: the `?host=parent` bridge answers
only a same-origin parent window, and a JavaScript API is a global of the build's own page. So
the portal frames the shim, the shim frames the build on the shim's own origin, and the shim
relays between them by `postMessage`, checking every message's window and origin (native files
ADR-0010). The build is served unchanged; the shim is ours.

A deployment reached at several addresses has several portal origins (portalr ADR-0084): the
shim is told them all, and learns which one frames it from `?host=`, the framing page's own
origin, which the portal's frame adds. Told one portal, it needs no `?host=`; told several, it
answers only a `?host=` among them, and does nothing without one, so no message goes to an
origin the portal's frame never named.

The portal speaks one protocol to the shim, whatever the app's surface:

- `lattice:open` (portal to shim): `{ name, bytes }`, the checked-out file, as an `ArrayBuffer`,
  once the shim said `lattice:ready`: one sent before is lost.
- `lattice:ready` (shim to portal): `{ version }`, the build is listening.
- `lattice:save` (shim to portal): `{ name, bytes }`, each file the build would download,
  whatever its format: the portal checks it in, and the check-in refuses another format.
- `lattice:dirty` (shim to portal): `{ dirty }`, whether the build has unsaved changes.
- `lattice:failed` (shim to portal): `{ error }`, the build couldn't start.
- `lattice:call` (portal to shim): `{ id, method, args }`, for a JavaScript API: one of the
  methods the deployment allows, called on the build's global; `lattice:reply` (shim to
  portal) is `{ id, result }` or `{ id, error }`.
"""

import base64
import hashlib
import html
import re
from collections.abc import Sequence
from typing import Final

from artifactr.files.craft import Craft
from lattice_core.origins import web_origins

PATH: Final = "/.lattice/shim.html"
"""Where the shim is served, beside the build, where no build has a file."""

METHOD: Final = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
"""A JavaScript API's method, by its name."""

SCRIPT: Final = """
(() => {
  const root = document.documentElement;
  const app = root.dataset.app;
  const portals = (root.dataset.portals || "").split(" ").filter(Boolean);
  const asked = new URLSearchParams(location.search).get("host");
  const portal = portals.includes(asked) ? asked : portals.length === 1 ? portals[0] : null;
  if (!portal) return;
  const methods = (root.dataset.methods || "").split(" ").filter(Boolean);
  const frame = document.querySelector("iframe");
  const own = location.origin;
  const tell = (message, transfer) => parent.postMessage(message, portal, transfer || []);
  const reply = (id, answer) => {
    try {
      tell({ type: "lattice:reply", id, ...answer });
    } catch (error) {
      tell({ type: "lattice:reply", id, error: String(error) });
    }
  };
  const buffer = (bytes) =>
    bytes instanceof ArrayBuffer
      ? bytes
      : ArrayBuffer.isView(bytes)
        ? new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength).slice().buffer
        : null;
  const fromPortal = (data) => {
    const bytes = buffer(data.bytes);
    if (data.type === "lattice:open" && typeof data.name === "string" && bytes) {
      frame.contentWindow.postMessage({ type: `${app}:open`, name: data.name, bytes }, own, [
        bytes,
      ]);
    } else if (data.type === "lattice:call") {
      // The method called is the allowed name itself, found in the list, never the message's.
      const method = methods.find((name) => name === data.method);
      if (method === undefined) return;
      const args = Array.isArray(data.args) ? data.args : [];
      Promise.resolve()
        .then(() => frame.contentWindow[app][method](...args))
        .then(
          (result) => reply(data.id, { result }),
          (error) => reply(data.id, { error: String(error) }),
        );
    }
  };
  const fromBuild = (data) => {
    const bytes = buffer(data.bytes);
    if (data.type === `${app}:ready`) {
      tell({ type: "lattice:ready", version: String(data.version || "") });
    } else if (data.type === `${app}:dirty`) {
      tell({ type: "lattice:dirty", dirty: data.dirty === true });
    } else if (data.type === `${app}:failed`) {
      tell({ type: "lattice:failed", error: String(data.error || "") });
    } else if (data.type === `${app}:save` && typeof data.name === "string" && bytes) {
      tell({ type: "lattice:save", name: data.name, bytes }, [bytes]);
    }
  };
  addEventListener("message", (event) => {
    const data = event.data;
    if (typeof data !== "object" || data === null || typeof data.type !== "string") return;
    if (event.source === parent && event.origin === portal) fromPortal(data);
    else if (event.source === frame.contentWindow && event.origin === own) fromBuild(data);
  });
  if (root.dataset.surface === "global") {
    const started = Date.now();
    const ready = setInterval(() => {
      const api = frame.contentWindow?.[app];
      if (api || Date.now() - started > 60000) {
        clearInterval(ready);
        const failed = { type: "lattice:failed", error: `the build has no ${app} API` };
        tell(api ? { type: "lattice:ready", version: "" } : failed);
      }
    }, 100);
  }
  frame.src = root.dataset.surface === "parent" ? "/?host=parent" : "/";
})();
"""

STYLE: Final = "html, body, iframe { margin: 0; border: 0; width: 100%; height: 100%; }"


def _hash(text: str) -> str:
    return f"'sha256-{base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()}'"


def shim_page(craft: Craft, portal: str | Sequence[str], methods: Sequence[str] = ()) -> str:
    """The shim's page, for an app's build framed by the portal at `portal`.

    Args:
        craft: The app, whose build's host surface the shim relays to.
        portal: The portal's origin, or its origins where it is reached at several addresses:
            the only ones the shim hears or answers, and, given several, only the one the
            frame's `?host=` names.
        methods: For a JavaScript API, the methods of it the portal may call.

    Raises:
        ValueError: If the app's build has no host surface, the portal isn't an origin, or
            methods are given for a surface that has none, or aren't names.
    """
    if craft.bridge is None:
        raise ValueError(f"{craft.title}'s build has no host surface for a shim to reach")
    origins = web_origins(portal, what="the portal")
    if methods and craft.bridge != "global":
        raise ValueError(f"{craft.title}'s build has no JavaScript API to call methods of")
    if not all(METHOD.fullmatch(method) for method in methods):
        raise ValueError(f"a method is named as JavaScript names one, not {list(methods)}")
    data = {
        "app": craft.name,
        "portals": " ".join(origins),
        "surface": craft.bridge,
        "methods": " ".join(methods),
    }
    attributes = " ".join(f'data-{key}="{html.escape(value)}"' for key, value in data.items())
    return (
        f'<!DOCTYPE html><html lang="en" {attributes}><head><meta charset="utf-8">'
        f"<title>{html.escape(craft.title)}</title><style>{STYLE}</style></head>"
        f'<body><iframe title="{html.escape(craft.title)}"></iframe>'
        f"<script>{SCRIPT}</script></body></html>"
    )


def shim_policy(portal: str | Sequence[str]) -> str:
    """The shim's Content-Security-Policy: its own script and style, and only the portal above it.

    It runs its script and style by their hashes, frames only its own origin, and is framed only
    by the portal, at each of its origins.
    """
    return "; ".join(
        [
            "default-src 'none'",
            f"script-src {_hash(SCRIPT)}",
            f"style-src {_hash(STYLE)}",
            "frame-src 'self'",
            f"frame-ancestors {' '.join(web_origins(portal, what='the portal'))}",
            "base-uri 'none'",
            "form-action 'none'",
        ]
    )
