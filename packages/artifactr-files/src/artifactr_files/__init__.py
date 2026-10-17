"""artifactr-files: native files as artifactr artifacts.

A file in a native format, such as a Word document, is an artifact whose data is a small
manifest naming the file's bytes, by their SHA-256, in a blob store. Agents edit it through the
file's own app, by batches of its commands, and people check it out, edit it in the app and check
it in. Every revision is ordinary JSON Patch that first tests the digest it was made from, and one
writer at a time holds a lease on the artifact (lattice RFC-0003).

The layers: [`artifactr_files.manifest`][artifactr_files.manifest], the types and the revision;
[`artifactr_files.blobs`][artifactr_files.blobs], the blob store;
[`artifactr_files.checkouts`][artifactr_files.checkouts], the check-out record;
[`artifactr_files.app`][artifactr_files.app], the app port and its fake;
[`artifactr_files.files`][artifactr_files.files], native files in a workspace; and
[`artifactr_files.sql`][artifactr_files.sql], the stores in SQL. Its documentation is at
<https://lattice.alexnodeland.com/artifactr-files/>.
"""

from importlib.metadata import version

from artifactr_files.app import App, AppCommand, AppFailed, FakeApp
from artifactr_files.blobs import Blobs, InMemoryBlobs, TooLarge
from artifactr_files.checkouts import Checkout, Checkouts, InMemoryCheckouts
from artifactr_files.files import ContentUnavailable, NativeFiles
from artifactr_files.manifest import DOCX, Blob, NativeFile, Provenance, WordDocument

__version__ = version("artifactr-files-ai")

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
    "FakeApp",
    "InMemoryBlobs",
    "InMemoryCheckouts",
    "NativeFile",
    "NativeFiles",
    "Provenance",
    "TooLarge",
    "WordDocument",
    "__version__",
]
