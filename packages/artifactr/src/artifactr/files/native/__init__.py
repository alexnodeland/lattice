"""Native files in workspaces: [`NativeFiles`][artifactr.files.native.NativeFiles].

Uploads, a person's check-out and check-in, an agent's edit by the app's commands, reads of a
revision's bytes, and the collection of bytes nothing names.
"""

from artifactr.files.native.files import ContentUnavailable, FormatChanged, NativeFiles, Part

__all__ = ["ContentUnavailable", "FormatChanged", "NativeFiles", "Part"]
