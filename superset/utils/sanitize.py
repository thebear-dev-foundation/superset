# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""HTML/SVG/URL sanitization utilities extracted from superset.utils.core."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import markdown as md
import nh3
from markupsafe import Markup

logger = logging.getLogger(__name__)

# Characters that browsers remove from URLs during parsing per the WHATWG
# URL spec (TAB, LF, CR). Both literal and percent-encoded forms must be
# stripped before any structural check, otherwise a path like
# ``/%09//host`` slips past a leading-``//`` guard because the percent-
# encoded TAB only disappears after the browser parses the URL.
_URL_STRIPPED_CONTROL_CHARS = re.compile(r"[\t\n\r]|%09|%0[ADad]")

# Browsers normalize backslashes to forward slashes per the WHATWG URL spec,
# so mixed leading sequences such as ``/\``, ``\/`` and ``/\/`` (and their
# percent-encoded ``%5C`` forms) are all parsed as ``//host``.
_URL_BACKSLASHES = re.compile(r"\\|%5[Cc]")


def strip_url_control_chars(url: str) -> str:
    """Remove TAB/LF/CR (and percent-encoded forms) that browsers strip."""
    return _URL_STRIPPED_CONTROL_CHARS.sub("", url)


def normalize_url_backslashes(url: str) -> str:
    """Normalize backslashes (and ``%5C``) to forward slashes."""
    return _URL_BACKSLASHES.sub("/", url)


def markdown(raw: str, markup_wrap: bool | None = False) -> str:
    """Render Markdown to sanitized HTML."""
    safe_markdown_tags = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "b",
        "i",
        "strong",
        "em",
        "tt",
        "p",
        "br",
        "span",
        "div",
        "blockquote",
        "code",
        "hr",
        "ul",
        "ol",
        "li",
        "dd",
        "dt",
        "img",
        "a",
    }
    safe_markdown_attrs = {
        "img": {"src", "alt", "title"},
        "a": {"href", "alt", "title", "target"},
    }
    safe = md.markdown(
        raw or "",
        extensions=[
            "markdown.extensions.tables",
            "markdown.extensions.fenced_code",
            "markdown.extensions.codehilite",
        ],
    )
    # pylint: disable=no-member
    # nh3 preserves supported link attributes and enforces a safe rel value.
    # Explicit URL-scheme allowlist so the sanitizer does not rely on
    # library defaults for security-sensitive filtering.
    safe_markdown_schemes: set[str] = {"http", "https", "mailto"}
    safe = nh3.clean(
        safe,
        tags=safe_markdown_tags,
        attributes=safe_markdown_attrs,
        url_schemes=safe_markdown_schemes,
    )
    if markup_wrap:
        safe = Markup(safe)  # noqa: S704
    return safe


def sanitize_svg_content(svg_content: str) -> str:
    """Sanitize SVG content using nh3 with an SVG-appropriate allowlist.

    Uses nh3 (a Rust-based HTML sanitizer) to parse and filter SVG content,
    which is robust against entity-encoding bypasses, ``<foreignObject>``
    injection, and other attacks that defeat regex-based sanitization.

    Args:
        svg_content: Raw SVG content string

    Returns:
        str: Sanitized SVG content with only safe elements and attributes
    """
    if not svg_content or not svg_content.strip():
        return ""

    safe_svg_tags: set[str] = {
        "svg",
        "g",
        "defs",
        "symbol",
        "use",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "path",
        "text",
        "tspan",
        "textPath",
        "clipPath",
        "mask",
        "image",
        "linearGradient",
        "radialGradient",
        "stop",
        "pattern",
        "filter",
        "feGaussianBlur",
        "feOffset",
        "feBlend",
        "feMerge",
        "feMergeNode",
        "feFlood",
        "feComposite",
        "feColorMatrix",
        "title",
        "desc",
        "marker",
    }

    safe_svg_attrs: dict[str, set[str]] = {
        "*": {
            "id",
            "class",
            "style",
            "fill",
            "stroke",
            "stroke-width",
            "stroke-linecap",
            "stroke-linejoin",
            "stroke-dasharray",
            "stroke-dashoffset",
            "stroke-opacity",
            "fill-opacity",
            "fill-rule",
            "clip-rule",
            "opacity",
            "transform",
            "d",
            "x",
            "y",
            "x1",
            "y1",
            "x2",
            "y2",
            "cx",
            "cy",
            "r",
            "rx",
            "ry",
            "width",
            "height",
            "viewBox",
            "xmlns",
            "preserveAspectRatio",
            "points",
            "offset",
            "stop-color",
            "stop-opacity",
            "gradientUnits",
            "gradientTransform",
            "patternUnits",
            "patternTransform",
            "clip-path",
            "font-family",
            "font-size",
            "font-weight",
            "text-anchor",
            "dominant-baseline",
            "dx",
            "dy",
            "startOffset",
            "markerWidth",
            "markerHeight",
            "refX",
            "refY",
            "orient",
            "stdDeviation",
            "in",
            "in2",
            "result",
            "mode",
            "type",
            "values",
            "flood-color",
            "flood-opacity",
            "color",
        },
        "image": {"href", "width", "height", "x", "y", "preserveAspectRatio"},
        "use": {"href", "x", "y", "width", "height"},
    }

    return nh3.clean(
        svg_content,
        tags=safe_svg_tags,
        attributes=safe_svg_attrs,
        url_schemes={"http", "https"},
    )


def sanitize_url(url: str) -> str:
    """Sanitize URL using urllib.parse to block dangerous schemes.

    Simple validation using standard library. Allows relative URLs and
    safe absolute URLs while blocking javascript: and other dangerous schemes.

    Args:
        url: Raw URL string

    Returns:
        str: Sanitized URL or empty string if dangerous
    """
    if not url or not url.strip():
        return ""

    # Normalize the URL the same way a browser will before parsing (mirroring
    # ``link_redirect.is_safe_redirect_url``): drop the TAB/LF/CR characters
    # the WHATWG URL parser removes (plus their percent-encoded forms) and
    # normalize backslashes to forward slashes. Otherwise payloads such as
    # ``/\evil.com`` or ``/%5Cevil.com`` slip past the leading-``//`` guard
    # yet are still fetched by the browser as ``//evil.com``.
    stripped = strip_url_control_chars(url.strip())
    normalized = normalize_url_backslashes(stripped)

    # Block protocol-relative URLs (//host/...) which bypass scheme checks
    if normalized.startswith("//"):
        return ""

    # Relative URLs are safe
    if normalized.startswith("/"):
        return stripped

    try:
        parsed = urlparse(stripped)

        # Allow safe schemes only
        if parsed.scheme.lower() in {"http", "https"}:
            return stripped

        # Block everything else (javascript:, data:, etc.)
        return ""

    except ValueError:
        logger.debug("Failed to parse URL: %s", url)
        return ""
