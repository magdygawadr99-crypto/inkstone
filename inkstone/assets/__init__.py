"""The asset pipeline: minify, bundle and fingerprint static files."""

from __future__ import annotations

from .bundle import Bundle
from .css import inline_imports, minify_css, rewrite_urls
from .datauri import data_uri
from .errors import AssetError
from .fingerprint import content_hash, fingerprint_name, sri_hash
from .html import minify_html
from .images import ImageInfo, image_info
from .js import minify_js
from .manifest import Manifest
from .pipeline import AssetPipeline, BuildReport

__all__ = [
    "AssetError",
    "AssetPipeline",
    "BuildReport",
    "Bundle",
    "ImageInfo",
    "Manifest",
    "content_hash",
    "data_uri",
    "fingerprint_name",
    "image_info",
    "inline_imports",
    "minify_css",
    "minify_html",
    "minify_js",
    "rewrite_urls",
    "sri_hash",
]
