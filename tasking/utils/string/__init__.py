"""String manipulation utilities"""

from .markdown import (
    extract_all_headers,
    find_header_by_title,
    find_headers_by_level,
    extract_content_by_header,
    extract_section_with_subsections,
    extract_by_header_title,
    extract_by_header_level,
    get_header_hierarchy,
    MarkdownHeader,
    MarkdownSection,
)
from .message import (
    extract_text_from_message,
    extract_text_from_content,
    create_text_message,
    is_text_message,
    is_multimodal_message,
)
from .xml import extract_by_label, fix_incomplete_labels

__all__ = [
    # Markdown functions
    "extract_all_headers",
    "find_header_by_title",
    "find_headers_by_level",
    "extract_content_by_header",
    "extract_section_with_subsections",
    "extract_by_header_title",
    "extract_by_header_level",
    "get_header_hierarchy",
    # Markdown classes
    "MarkdownHeader",
    "MarkdownSection",
    # Message functions
    "extract_text_from_message",
    "extract_text_from_content",
    "create_text_message",
    "is_text_message",
    "is_multimodal_message",
    # XML functions
    "extract_by_label",
    "fix_incomplete_labels",
]
