"""What `inkstone new` writes: a starter site, posts and pages."""

from __future__ import annotations

from .content import new_page, new_post, post_filename
from .site import SKELETON, create_site, render, skeleton_files

__all__ = [
    "SKELETON",
    "create_site",
    "new_page",
    "new_post",
    "post_filename",
    "render",
    "skeleton_files",
]
