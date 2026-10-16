"""OpenTelemetry for applications, in one call.

Two modules, each the one path to its names:

- :mod:`lattice_core.otel.contribution`: the contract a library's contribution follows. It
  needs no extra, so a library's telemetry layer can name it (lattice ADR-0020).
- :mod:`lattice_core.otel.configure`: :func:`~lattice_core.otel.configure.configure_telemetry`
  and its handle, the ``otel`` extra. Each library's ``otel`` module calls it with its own
  contribution, and re-exports the rest, so an application uses the library's.

Nothing here names a library.
"""
