"""Native files as artifacts: artifactr's `files` extra.

A file in a native format, such as a Word document, is an artifact whose data is a small
manifest naming the file's bytes, by their SHA-256, in a blob store. Agents edit it through the
file's own app, by batches of its commands, and people check it out, edit it in the app and check
it in. Every revision is ordinary JSON Patch that first tests the digest it was made from, and one
writer at a time holds a lease on the artifact (lattice RFC-0003).

The layers: [`artifactr.files.manifest`][artifactr.files.manifest], the types and the revision;
[`artifactr.files.blobs`][artifactr.files.blobs], the blob store;
[`artifactr.files.checkouts`][artifactr.files.checkouts], the check-out record;
[`artifactr.files.app`][artifactr.files.app], the app port and its fake;
[`artifactr.files.wordcraft`][artifactr.files.wordcraft], WordCraft's adapter, and each
crafting app's beside it, such as [`artifactr.files.cadcraft`][artifactr.files.cadcraft];
[`artifactr.files.native`][artifactr.files.native], native files in a workspace;
[`artifactr.files.tools`][artifactr.files.tools], the agent's tools; and
[`artifactr.files.sql`][artifactr.files.sql], the stores in SQL, with the `sql` extra. Its
documentation is at <https://lattice.alexnodeland.com/artifactr/files/>.
"""

from artifactr.files.app import App, AppCommand, AppFailed, FakeApp
from artifactr.files.blobs import Blobs, InMemoryBlobs, TooLarge
from artifactr.files.checkouts import Checkout, Checkouts, InMemoryCheckouts
from artifactr.files.manifest import (
    DOCX,
    Blob,
    Design,
    Drawing,
    LayeredImage,
    NativeFile,
    PageLayout,
    Provenance,
    VectorImage,
    WordDocument,
)
from artifactr.files.native import ContentUnavailable, NativeFiles

__all__ = [
    "DOCX",
    "App",
    "AppCommand",
    "AppFailed",
    "Blob",
    "Blobs",
    "Checkout",
    "Checkouts",
    "ContentUnavailable",
    "Design",
    "Drawing",
    "FakeApp",
    "InMemoryBlobs",
    "InMemoryCheckouts",
    "LayeredImage",
    "NativeFile",
    "NativeFiles",
    "PageLayout",
    "Provenance",
    "TooLarge",
    "VectorImage",
    "WordDocument",
]
