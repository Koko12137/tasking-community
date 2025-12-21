from typing import NamedTuple
from enum import Enum


class Operation(Enum):
    """操作类型（符合GitHub diff风格）"""

    INSERT = "+"
    """插入（新增行）"""
    DELETE = "-"
    """删除（移除行）"""

class DiffItem(NamedTuple):
    """差异项"""

    line: int
    """行号"""
    operation: Operation
    """操作类型"""
    content: str
    """内容"""


def diff_lines(old_lines: list[str], new_lines: list[str]) -> list[DiffItem]:
    """比较两个列表，返回差异（类似GitHub diff风格）。

    Args:
        old_lines: 旧列表。
        new_lines: 新列表。

    Returns:
        list[DiffItem]: 差异列表，每个元素为 DiffItem 对象。
        行号表示在新文件中的行号（对于INSERT）或旧文件中的行号（对于DELETE）。
    """
    # 使用最长公共子序列（LCS）算法计算差异
    def lcs(x: list[str], y: list[str]) -> list[tuple[int, int]]:
        """计算最长公共子序列，返回匹配的索引对列表"""
        m, n = len(x), len(y)
        # dp[i][j] 表示 x[0:i] 和 y[0:j] 的最长公共子序列长度
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        # 填充dp表
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if x[i - 1] == y[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        
        # 回溯找到LCS的索引对
        matches: list[tuple[int, int]] = []
        i, j = m, n
        while i > 0 and j > 0:
            if x[i - 1] == y[j - 1]:
                matches.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
        
        return matches[::-1]  # 反转列表
    
    # 计算LCS匹配
    matches = lcs(old_lines, new_lines)
    
    # 构建差异列表
    diff_items: list[DiffItem] = []
    old_idx = 0
    new_idx = 0
    match_idx = 0
    
    while old_idx < len(old_lines) or new_idx < len(new_lines):
        # 检查是否有匹配
        if match_idx < len(matches):
            match_old, match_new = matches[match_idx]
            
            # 处理旧文件中需要删除的行（在匹配之前）
            while old_idx < match_old:
                diff_items.append(DiffItem(
                    line=old_idx + 1,  # 旧文件中的行号（从1开始）
                    operation=Operation.DELETE,
                    content=old_lines[old_idx].rstrip('\n\r')
                ))
                old_idx += 1
            
            # 处理新文件中需要插入的行（在匹配之前）
            while new_idx < match_new:
                diff_items.append(DiffItem(
                    line=new_idx + 1,  # 新文件中的行号（从1开始）
                    operation=Operation.INSERT,
                    content=new_lines[new_idx].rstrip('\n\r')
                ))
                new_idx += 1
            
            # 跳过匹配的行（相同行不添加到diff中）
            old_idx = match_old + 1
            new_idx = match_new + 1
            match_idx += 1
        else:
            # 没有更多匹配，处理剩余的行
            # 删除旧文件中剩余的行
            while old_idx < len(old_lines):
                diff_items.append(DiffItem(
                    line=old_idx + 1,
                    operation=Operation.DELETE,
                    content=old_lines[old_idx].rstrip('\n\r')
                ))
                old_idx += 1
            
            # 插入新文件中剩余的行
            while new_idx < len(new_lines):
                diff_items.append(DiffItem(
                    line=new_idx + 1,
                    operation=Operation.INSERT,
                    content=new_lines[new_idx].rstrip('\n\r')
                ))
                new_idx += 1
    
    return diff_items


def _get_context_lines(
    diff_items: list[DiffItem],
    old_lines: list[str],
    new_lines: list[str],
    k: int
) -> list[tuple[int, int, Operation, str, bool]]:
    """获取需要显示的行（包括变化行和上下文行）。
    
    Args:
        diff_items: 差异列表。
        old_lines: 旧文件行列表。
        new_lines: 新文件行列表。
        k: 保留变化内容的上下 k 行内容。当设置为 -1 时，保留所有内容。
    
    Returns:
        list[tuple[int, int, Operation, str, bool]]: (旧文件行号, 新文件行号, 操作类型, 内容, 是否为上下文行)
    """
    if k == -1:
        # 保留所有内容，只显示变化行
        result: list[tuple[int, int, Operation, str, bool]] = []
        for item in diff_items:
            if item.operation == Operation.DELETE:
                result.append((item.line, 0, item.operation, item.content, False))
            else:  # INSERT
                result.append((0, item.line, item.operation, item.content, False))
        return result
    
    # 重新计算LCS以找到匹配的行
    def lcs(x: list[str], y: list[str]) -> list[tuple[int, int]]:
        """计算最长公共子序列，返回匹配的索引对列表"""
        m, n = len(x), len(y)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if x[i - 1] == y[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        
        matches: list[tuple[int, int]] = []
        i, j = m, n
        while i > 0 and j > 0:
            if x[i - 1] == y[j - 1]:
                matches.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
        
        return matches[::-1]
    
    matches = lcs(old_lines, new_lines)
    
    # 收集所有变化行的位置
    changed_old_lines: set[int] = set()
    changed_new_lines: set[int] = set()
    for item in diff_items:
        if item.operation == Operation.DELETE:
            changed_old_lines.add(item.line - 1)  # 转换为0-based索引
        else:  # INSERT
            changed_new_lines.add(item.line - 1)  # 转换为0-based索引
    
    # 确定需要显示的行范围
    if not changed_old_lines and not changed_new_lines:
        return []
    
    all_changed_old = changed_old_lines if changed_old_lines else {0}
    all_changed_new = changed_new_lines if changed_new_lines else {0}
    
    min_old_idx = min(all_changed_old) if all_changed_old else 0
    max_old_idx = max(all_changed_old) if all_changed_old else len(old_lines) - 1
    min_new_idx = min(all_changed_new) if all_changed_new else 0
    max_new_idx = max(all_changed_new) if all_changed_new else len(new_lines) - 1
    
    # 扩展范围以包含上下文
    start_old = max(0, min_old_idx - k)
    end_old = min(len(old_lines), max_old_idx + k + 1)
    start_new = max(0, min_new_idx - k)
    end_new = min(len(new_lines), max_new_idx + k + 1)
    
    # 构建匹配映射
    match_map_old_to_new: dict[int, int] = {old_idx: new_idx for old_idx, new_idx in matches}
    match_map_new_to_old: dict[int, int] = {new_idx: old_idx for old_idx, new_idx in matches}
    
    result_lines: list[tuple[int, int, Operation, str, bool]] = []
    seen: set[tuple[int, int]] = set()
    
    # 处理旧文件中的行
    for old_idx in range(start_old, end_old):
        if old_idx in match_map_old_to_new:
            new_idx = match_map_old_to_new[old_idx]
            if old_idx in changed_old_lines:
                # 这是删除的行
                content = old_lines[old_idx].rstrip('\n\r')
                result_lines.append((old_idx + 1, 0, Operation.DELETE, content, False))
                seen.add((old_idx, -1))
            elif new_idx >= start_new and new_idx < end_new:
                # 这是上下文行（相同的行）
                content = old_lines[old_idx].rstrip('\n\r')
                if (old_idx, new_idx) not in seen:
                    result_lines.append((old_idx + 1, new_idx + 1, Operation.DELETE, content, True))
                    seen.add((old_idx, new_idx))
        elif old_idx in changed_old_lines:
            # 删除的行，但不在匹配中
            content = old_lines[old_idx].rstrip('\n\r')
            result_lines.append((old_idx + 1, 0, Operation.DELETE, content, False))
            seen.add((old_idx, -1))
    
    # 处理新文件中的行
    for new_idx in range(start_new, end_new):
        if new_idx in match_map_new_to_old:
            old_idx = match_map_new_to_old[new_idx]
            if new_idx in changed_new_lines and (old_idx, new_idx) not in seen:
                # 这是插入的行
                content = new_lines[new_idx].rstrip('\n\r')
                result_lines.append((0, new_idx + 1, Operation.INSERT, content, False))
                seen.add((-1, new_idx))
        elif new_idx in changed_new_lines:
            # 插入的行，但不在匹配中
            content = new_lines[new_idx].rstrip('\n\r')
            result_lines.append((0, new_idx + 1, Operation.INSERT, content, False))
            seen.add((-1, new_idx))
    
    # 按旧文件行号排序，如果旧文件行号为0则按新文件行号排序
    result_lines.sort(key=lambda x: (x[0] if x[0] > 0 else x[1], x[1]))
    return result_lines


def diff_to_html(
    diff_items: list[DiffItem],
    old_lines: list[str] | None = None,
    new_lines: list[str] | None = None,
    k: int = 3
) -> str:
    """将差异列表转换为 HTML 格式（类似GitHub风格）。

    Args:
        diff_items: 差异列表。
        old_lines: 旧文件行列表（用于获取上下文）。如果为None，则不显示上下文。
        new_lines: 新文件行列表（用于获取上下文）。如果为None，则不显示上下文。
        k: 保留变化内容的上下 k 行内容，默认 3 行。当设置为 -1 时，保留所有内容。

    Returns:
        str: HTML 格式的差异显示。
    """
    html = '<table style="border-collapse: collapse; width: 100%; font-family: monospace;">'
    html += '<thead><tr style="background-color: #f6f8fa;">'
    html += '<th style="padding: 8px; text-align: left; border: 1px solid #d0d7de;">行号</th>'
    html += '<th style="padding: 8px; text-align: left; border: 1px solid #d0d7de;">操作</th>'
    html += '<th style="padding: 8px; text-align: left; border: 1px solid #d0d7de;">内容</th>'
    html += '</tr></thead><tbody>'
    
    # 如果提供了原始文件内容，则包含上下文
    if old_lines is not None and new_lines is not None:
        context_lines = _get_context_lines(diff_items, old_lines, new_lines, k)
        for old_line_num, new_line_num, operation, content, is_context in context_lines:
            if is_context:
                # 上下文行使用灰色背景
                bg_color = "#f6f8fa"
                text_color = "#57606a"
                op_symbol = " "
                display_line = old_line_num if old_line_num > 0 else new_line_num
            else:
                # 变化行使用彩色背景
                if operation == Operation.INSERT:
                    bg_color = "#d4edda"
                    text_color = "#155724"
                    op_symbol = operation.value
                    display_line = new_line_num
                else:  # DELETE
                    bg_color = "#f8d7da"
                    text_color = "#721c24"
                    op_symbol = operation.value
                    display_line = old_line_num
            
            # 转义HTML特殊字符
            escaped_content = (content
                             .replace("&", "&amp;")
                             .replace("<", "&lt;")
                             .replace(">", "&gt;")
                             .replace('"', "&quot;")
                             .replace("'", "&#39;"))
            
            html += f'<tr style="background-color: {bg_color};">'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color};">{display_line}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color}; font-weight: bold;">{op_symbol}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color}; white-space: pre-wrap;">{escaped_content}</td>'
            html += '</tr>'
    else:
        # 不包含上下文，只显示变化行
        for item in diff_items:
            # 根据操作类型设置行背景色
            if item.operation == Operation.INSERT:
                bg_color = "#d4edda"  # 浅绿色背景
                text_color = "#155724"  # 深绿色文字
            else:  # DELETE
                bg_color = "#f8d7da"  # 浅红色背景
                text_color = "#721c24"  # 深红色文字
            
            # 转义HTML特殊字符
            content = (item.content
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;")
                      .replace('"', "&quot;")
                      .replace("'", "&#39;"))
            
            html += f'<tr style="background-color: {bg_color};">'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color};">{item.line}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color}; font-weight: bold;">{item.operation.value}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #d0d7de; color: {text_color}; white-space: pre-wrap;">{content}</td>'
            html += '</tr>'
    
    html += '</tbody></table>'
    return html


def diff_to_text(
    diff_items: list[DiffItem],
    old_lines: list[str] | None = None,
    new_lines: list[str] | None = None,
    k: int = 3
) -> str:
    """将差异列表转换为文本格式，保留变化内容的上下 k 行内容。

    Args:
        diff_items: 差异列表。
        old_lines: 旧文件行列表（用于获取上下文）。如果为None，则不显示上下文。
        new_lines: 新文件行列表（用于获取上下文）。如果为None，则不显示上下文。
        k: 保留变化内容的上下 k 行内容，默认 3 行。当设置为 -1 时，保留所有内容。

    Returns:
        str: 文本格式的差异显示（类似git diff格式）。
    """
    result_lines: list[str] = []
    
    # 如果提供了原始文件内容，则包含上下文
    if old_lines is not None and new_lines is not None:
        context_lines = _get_context_lines(diff_items, old_lines, new_lines, k)
        for old_line_num, new_line_num, operation, content, is_context in context_lines:
            if is_context:
                # 上下文行使用空格作为操作符
                display_line = old_line_num if old_line_num > 0 else new_line_num
                result_lines.append(rf" {display_line:4d}  {content}")
            else:
                # 变化行使用+或-作为操作符
                op_symbol = operation.value
                if operation == Operation.INSERT:
                    display_line = new_line_num
                else:  # DELETE
                    display_line = old_line_num
                result_lines.append(rf"{op_symbol}{display_line:4d}  {content}")
    else:
        # 不包含上下文，只显示变化行
        for item in diff_items:
            op_symbol = item.operation.value
            result_lines.append(rf"{op_symbol}{item.line:4d}  {item.content}")
    
    return "\n".join(result_lines)


def diff_files(
    old_file: str,
    new_file: str,
    output_format: str = "html",
    k: int = 3
) -> str:
    """将两个文件进行差异比较。

    Args:
        old_file: 旧文件路径。
        new_file: 新文件路径。
        output_format: 输出格式，"html" 或 "text"，默认为 "html"。
        k: 保留变化内容的上下 k 行内容，默认 3 行。当设置为 -1 时，保留所有内容。

    Returns:
        str: 差异格式（HTML 或文本）。
    """
    with open(old_file, "r", encoding="utf-8") as f:
        old_lines = f.readlines()
    with open(new_file, "r", encoding="utf-8") as f:
        new_lines = f.readlines()
    
    diff_items = diff_lines(old_lines, new_lines)
    
    if output_format == "text":
        return diff_to_text(diff_items, old_lines, new_lines, k)
    else:
        return diff_to_html(diff_items, old_lines, new_lines, k)


if __name__ == "__main__":
    import os
    os.chdir("/home/koko/projects/tasking/")
    old_file = os.path.join("tests", "assets", "ai_intro_v1.txt")
    new_file = os.path.join("tests", "assets", "ai_intro_v2.txt")
    with open(old_file, "r", encoding="utf-8") as f:
        old_lines = f.readlines()
    with open(new_file, "r", encoding="utf-8") as f:
        new_lines = f.readlines()
    diff_items = diff_lines(old_lines, new_lines)
    print(diff_items)
    text = diff_to_text(diff_items)
    print(text)
    html = diff_to_html(diff_items)
    print(html)
    with open("tests/assets/diff.html", "w", encoding="utf-8") as f:
        f.write(html)
