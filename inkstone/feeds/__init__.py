"""Feeds, sitemaps and the other files written for machines rather than people."""

from __future__ import annotations

from .atom import render_atom
from .errors import FeedError
from .jsonfeed import render_json_feed
from .models import Author, Enclosure, FeedEntry, FeedMeta
from .opml import OpmlFeed, render_opml
from .robots import RobotsRule, RobotsTxt, parse_robots, render_robots
from .rss import render_rss
from .sitemap import Sitemap, SitemapUrl, render_sitemap, render_sitemap_index
from .urls import absolutize_html
from .xmlwriter import XmlWriter

__all__ = [
    "Author",
    "Enclosure",
    "FeedEntry",
    "FeedError",
    "FeedMeta",
    "OpmlFeed",
    "RobotsRule",
    "RobotsTxt",
    "Sitemap",
    "SitemapUrl",
    "XmlWriter",
    "absolutize_html",
    "parse_robots",
    "render_atom",
    "render_json_feed",
    "render_opml",
    "render_robots",
    "render_rss",
    "render_sitemap",
    "render_sitemap_index",
]
