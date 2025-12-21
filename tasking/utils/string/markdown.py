"""Markdown 标题提取工具模块，提供从 Markdown 文件中按照标题提取对应内容的功能。"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class MarkdownHeader:
    """Markdown 标题数据类"""
    level: int  # 标题级别 (1-6)
    title: str  # 标题文本
    line_number: int  # 行号
    content_start: int  # 内容在文件中的起始位置
    content_end: int  # 内容在文件中的结束位置


@dataclass
class MarkdownSection:
    """Markdown 章节数据类"""
    header: MarkdownHeader  # 章节标题
    content: str  # 章节内容（包含子章节）
    subsections: List['MarkdownSection']  # 子章节列表


def extract_all_headers(content: str) -> List[MarkdownHeader]:
    """提取 Markdown 文件中的所有标题。

    Args:
        content (str): Markdown 文件内容

    Returns:
        List[MarkdownHeader]: 标题列表，按出现顺序排列
    """
    headers: List[MarkdownHeader] = []
    lines = content.split('\n')

    # Markdown 标题正则表达式，支持 ATX 风格 (# ## ###) 和 Setext 风格 (=== ---)
    atx_pattern = r'^(#{1,6})\s+(.+)$'
    setext_pattern = r'^(=+|-+)\s*$'

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 检查 ATX 风格标题
        atx_match = re.match(atx_pattern, line)
        if atx_match:
            level = len(atx_match.group(1))
            title = atx_match.group(2).strip()

            # 计算内容起始位置
            content_start = len('\n'.join(lines[:i+1])) + 1

            headers.append(MarkdownHeader(
                level=level,
                title=title,
                line_number=i + 1,
                content_start=content_start,
                content_end=0  # 稍后计算
            ))

        # 检查 Setext 风格标题（下划线）
        elif i > 0 and re.match(setext_pattern, line):
            prev_line = lines[i-1].strip()
            if prev_line and not re.match(r'^[#\s]', prev_line):
                underline_chars = line[0]
                level = 1 if underline_chars == '=' else 2

                # 计算内容起始位置
                content_start = len('\n'.join(lines[:i+1])) + 1

                headers.append(MarkdownHeader(
                    level=level,
                    title=prev_line,
                    line_number=i,  # 标题实际在上一行
                    content_start=content_start,
                    content_end=0  # 稍后计算
                ))

        i += 1

    # 计算每个标题的内容结束位置
    for i, header in enumerate(headers):
        if i < len(headers) - 1:
            # 下一个标题的开始位置就是当前标题的结束位置
            header.content_end = headers[i + 1].content_start - 1
        else:
            # 最后一个标题的内容到文件结尾
            header.content_end = len(content)

    return headers


def find_header_by_title(headers: List[MarkdownHeader], title: str,
                       case_sensitive: bool = False) -> Optional[MarkdownHeader]:
    """根据标题文本查找匹配的标题。

    Args:
        headers (List[MarkdownHeader]): 标题列表
        title (str): 要查找的标题文本
        case_sensitive (bool): 是否区分大小写，默认为 False

    Returns:
        Optional[MarkdownHeader]: 匹配的标题，如果没找到则返回 None
    """
    for header in headers:
        if case_sensitive:
            if header.title == title:
                return header
        else:
            if header.title.lower() == title.lower():
                return header
    return None


def find_headers_by_level(headers: List[MarkdownHeader], level: int) -> List[MarkdownHeader]:
    """根据标题级别查找所有匹配的标题。

    Args:
        headers (List[MarkdownHeader]): 标题列表
        level (int): 标题级别 (1-6)

    Returns:
        List[MarkdownHeader]: 匹配的标题列表
    """
    return [header for header in headers if header.level == level]


def extract_content_by_header(content: str, header: MarkdownHeader) -> str:
    """根据标题提取对应的内容。

    Args:
        content (str): Markdown 文件的完整内容
        header (MarkdownHeader): 要提取内容的标题

    Returns:
        str: 标题对应的内容（包含所有子章节内容）
    """
    if header.content_end == 0:
        return ""

    # 提取标题对应的内容范围
    extracted_content = content[header.content_start:header.content_end]

    return extracted_content.strip()


def extract_section_with_subsections(content: str, target_header: MarkdownHeader,
                                   all_headers: List[MarkdownHeader]) -> MarkdownSection:
    """提取指定标题及其所有子章节的内容。

    Args:
        content (str): Markdown 文件的完整内容
        target_header (MarkdownHeader): 目标标题
        all_headers (List[MarkdownHeader]): 文件中的所有标题

    Returns:
        MarkdownSection: 包含目标标题及其子章节的章节对象
    """
    # 提取目标标题的内容
    main_content = extract_content_by_header(content, target_header)

    # 查找所有子章节
    subsections: List[MarkdownSection] = []
    target_index = all_headers.index(target_header)

    # 找到目标标题后的所有同级或更深层级的标题，直到遇到同级或更高级的标题
    i = target_index + 1
    while i < len(all_headers):
        current_header = all_headers[i]

        # 如果当前标题是目标标题的子章节（级别更大）
        if current_header.level > target_header.level:
            # 递归提取子章节
            subsection = extract_section_with_subsections(content, current_header, all_headers)
            subsections.append(subsection)
        else:
            # 遇到同级或更高级标题，停止查找子章节
            break

        i += 1

    return MarkdownSection(
        header=target_header,
        content=main_content,
        subsections=subsections
    )


def extract_by_header_title(content: str, title: str,
                          include_subsections: bool = True,
                          case_sensitive: bool = False) -> Optional[str]:
    """根据标题文本提取对应的内容。

    Args:
        content (str): Markdown 文件内容
        title (str): 标题文本
        include_subsections (bool): 是否包含子章节内容，默认为 True
        case_sensitive (bool): 是否区分大小写，默认为 False

    Returns:
        Optional[str]: 提取的内容，如果没找到标题则返回 None
    """
    headers = extract_all_headers(content)
    target_header = find_header_by_title(headers, title, case_sensitive)

    if not target_header:
        return None

    if include_subsections:
        # 包含子章节内容
        section = extract_section_with_subsections(content, target_header, headers)

        # 构建包含子章节的完整内容
        result_parts = [section.content]

        for subsection in section.subsections:
            # 添加子章节标题和内容
            subsection_title = '#' * subsection.header.level + ' ' + subsection.header.title
            result_parts.append(f"\n{subsection_title}\n{subsection.content}")

        return '\n'.join(result_parts)

    # 只提取直接内容，不包含子章节
    return extract_content_by_header(content, target_header)


def extract_by_header_level(content: str, level: int) -> Dict[str, str]:
    """根据标题级别提取所有对应级别的内容。

    Args:
        content (str): Markdown 文件内容
        level (int): 标题级别 (1-6)

    Returns:
        Dict[str, str]: 标题到内容的映射字典
    """
    headers = extract_all_headers(content)
    target_headers = find_headers_by_level(headers, level)

    result = {}
    for header in target_headers:
        section = extract_section_with_subsections(content, header, headers)

        # 构建包含子章节的完整内容
        result_parts = [section.content]

        for subsection in section.subsections:
            subsection_title = '#' * subsection.header.level + ' ' + subsection.header.title
            result_parts.append(f"\n{subsection_title}\n{subsection.content}")

        result[header.title] = '\n'.join(result_parts)

    return result


def get_header_hierarchy(headers: List[MarkdownHeader]) -> Dict[str, List[str]]:
    """获取标题的层级结构。

    Args:
        headers (List[MarkdownHeader]): 标题列表

    Returns:
        Dict[str, List[str]]: 标题层级结构，key 为父标题，value 为子标题列表
    """
    hierarchy: Dict[str, List[str]] = {}

    for i, header in enumerate(headers):
        # 查找父标题
        parent_title = None
        for j in range(i - 1, -1, -1):
            if headers[j].level < header.level:
                parent_title = headers[j].title
                break

        if parent_title:
            if parent_title not in hierarchy:
                hierarchy[parent_title] = []
            hierarchy[parent_title].append(header.title)
        else:
            # 顶级标题
            if "__root__" not in hierarchy:
                hierarchy["__root__"] = []
            hierarchy["__root__"].append(header.title)

    return hierarchy
