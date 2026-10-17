"""Native files in workspaces: [`NativeFiles`][artifactr_files.files.NativeFiles].

Uploads, a person's check-out and check-in, an agent's edit by the app's commands, reads of a
revision's bytes, and the collection of bytes nothing names.
"""

from artifactr_files.files.native import ContentUnavailable, NativeFiles, Part

__all__ = ["ContentUnavailable", "NativeFiles", "Part"]
