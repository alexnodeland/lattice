"""The worker that runs an app on hostile files, and the `App` that sends it every call.

[`worker_app`][artifactr.files.worker.worker_app] is the worker: an app's four calls over HTTP,
one job at a time, each under [`Limits`][artifactr.files.worker.Limits] that its CLI is started
under. [`Worker`][artifactr.files.worker.Worker] is the application's side, an
[`App`][artifactr.files.app.App] that sends each call to it. The container it runs in, its
internal network and its own limits are stackr's (lattice RFC-0003, phase 3).
"""

from artifactr.files.worker.client import Worker
from artifactr.files.worker.limits import Limits
from artifactr.files.worker.service import worker_app

__all__ = ["Limits", "Worker", "worker_app"]
