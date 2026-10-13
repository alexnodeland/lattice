"""OpenTelemetry for applications, in one call: the ``otel`` extra.

Each library's ``otel`` module calls :func:`~lattice_core.otel.configure.configure_telemetry` with
its own contribution, and re-exports the rest, so an application uses the library's. Each name is
imported from :mod:`lattice_core.otel.configure`, which defines it; nothing here names a library.
"""
