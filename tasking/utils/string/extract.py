import re
from typing import Tuple


def extract_by_label(content: str, *labels: str) -> str:
    """Extract the content by the label.

    Args:
        content (str):
            The content to extract.
        *labels (str):
            The labels to extract.

    Returns:
        str:
            The extracted content. If the content is not found, return an empty string.
    """
    content = fix_incomplete_labels(content)

    # Traverse all the labels
    for label in labels:

        # Try with closing tag
        result = re.search(f"<{label}>\\s*\\n(.*)\\n\\s*</{label}>", content, re.DOTALL)
        if result:
            return result.group(1)
        else:
            # Try without closing tag
            result = re.search(f"<{label}>\\s*\\n(.*)\\n\\s*", content, re.DOTALL)
            if result:
                return result.group(1)

    # All the labels are not found
    return ""


def fix_incomplete_labels(content: str) -> str:
    """修复不完整的尖括号标签，使用括号合法性的栈算法来匹配任意标签。

    Args:
        content (str): 包含尖括号标签的内容

    Returns:
        str: 修复后的内容
    """

    def parse_tags(text: str) -> list[Tuple[str, str, int, bool]]:
        """解析文本中的所有标签，返回(标签名, 完整标签, 位置, 是否为结束标签)的列表"""
        tags: list[Tuple[str, str, int, bool]] = []
        # 匹配开始标签和结束标签，支持任意标签名和属性
        tag_pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9_-]*)(?:\s[^>]*)?>'

        for match in re.finditer(tag_pattern, text):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2)
            full_tag = match.group(0)
            position = match.start()

            tags.append((tag_name, full_tag, position, is_closing))

        return tags

    def fix_tags_with_stack(text: str) -> str:
        """使用栈算法修复标签匹配问题"""
        tags = parse_tags(text)
        stack: list[Tuple[str, int, str]] = []  # 存储(标签名, 位置, 完整标签)的元组
        fixed_text = text
        offset = 0  # 由于插入/删除标签导致的偏移量

        for tag_name, full_tag, position, is_closing in tags:
            adjusted_position = position + offset

            if is_closing:
                # 结束标签
                if stack and stack[-1][0] == tag_name:
                    # 匹配成功，弹出栈
                    stack.pop()
                else:
                    # 多余的结束标签，需要移除
                    fixed_text = fixed_text[:adjusted_position] + fixed_text[adjusted_position + len(full_tag):]
                    offset -= len(full_tag)
            else:
                # 开始标签，压入栈
                stack.append((tag_name, adjusted_position, full_tag))

        # 为未闭合的开始标签添加结束标签
        for tag_name, _, _ in reversed(stack):
            closing_tag = f'</{tag_name}>'
            fixed_text += closing_tag
            offset += len(closing_tag)

        return fixed_text

    def fix_orphaned_closing_tags(text: str) -> str:
        """修复孤立的结束标签（没有对应的开始标签）"""
        tags = parse_tags(text)
        opening_tags: set[str] = set()
        closing_tags: list[Tuple[str, str, int]] = []

        # 收集所有开始标签和结束标签
        for tag_name, full_tag, position, is_closing in tags:
            if is_closing:
                closing_tags.append((tag_name, full_tag, position))
            else:
                opening_tags.add(tag_name)

        # 找出没有对应开始标签的结束标签
        orphaned_closings: list[Tuple[str, str, int]] = []
        for tag_name, full_tag, position in closing_tags:
            if tag_name not in opening_tags:
                orphaned_closings.append((tag_name, full_tag, position))

        # 为孤立的结束标签添加开始标签
        fixed_text = text
        offset = 0
        for tag_name, full_tag, position in orphaned_closings:
            adjusted_position = position + offset
            opening_tag = f'<{tag_name}>'
            fixed_text = fixed_text[:adjusted_position] + opening_tag + fixed_text[adjusted_position:]
            offset += len(opening_tag)

        return fixed_text

    def clean_empty_tags(text: str) -> str:
        """清理空的标签对"""
        # 移除空的标签对，如 <tag></tag>
        text = re.sub(r'<([a-zA-Z][a-zA-Z0-9_-]*)(?:\s[^>]*)?>\s*</\1>', '', text)
        return text

    # 执行修复步骤
    fixed_content = content

    # 1. 使用栈算法修复标签匹配
    fixed_content = fix_tags_with_stack(fixed_content)

    # 2. 修复孤立的结束标签
    fixed_content = fix_orphaned_closing_tags(fixed_content)

    # 3. 清理空标签对
    fixed_content = clean_empty_tags(fixed_content)

    # 4. 清理空白行和格式
    fixed_content = re.sub(r'\n\s*\n', '\n', fixed_content)
    fixed_content = fixed_content.strip()

    return fixed_content
