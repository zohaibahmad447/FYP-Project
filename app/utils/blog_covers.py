"""
Single source of truth for blog card / hero image URLs (always DB featured_image).

Some legacy articles embed a duplicate hero image in HTML; those slugs still get
inline images stripped on the article view only (see blogs.py).
"""

from __future__ import annotations

from typing import Any, Optional

# Long-form posts where the body historically duplicated the cover image.
STRIP_INLINE_SLUGS = frozenset(
    {
        "chest-pain-in-young-adults-when-it-is-benign-and-when-it-is-urgent",
        "overthinking-before-sleep-psychological-tools-to-reduce-night-time-rumination",
    }
)


def blog_static_image_path(blog: Any) -> Optional[str]:
    """
    Return the static filename (relative to static/) for the blog hero/card image.

    Uses only ``Blog.featured_image`` (uploads/...) so listing, landing, and article
    views match and files that exist on disk are used.
    """
    fi = getattr(blog, "featured_image", None)
    if not fi:
        return None
    fi = str(fi).lstrip("/").replace("\\", "/")
    if fi.startswith("uploads/"):
        return fi
    return f"uploads/{fi}"
