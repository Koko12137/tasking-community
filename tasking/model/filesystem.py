"""
File system related data models.

This module provides comprehensive data models for file system operations,
including editing, searching, and result formatting.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class EditOperation:
    """文本编辑操作数据模型，表示单个行级编辑操作。

    注意：
    1. 操作将严格按照传入的顺序执行
    2. 支持三种操作类型：insert(插入)/delete(删除)/modify(修改)

    核心字段：
    - line: 操作行号（从1开始，insert支持0=开头、-1=末尾）
    - op: 操作类型（'insert'/'delete'/'modify'）
    - content: 操作内容（delete操作可为空，insert/modify支持内容，保留原始换行符）
    """
    line: int
    op: Literal['insert', 'delete', 'modify']
    content: str


@dataclass
class SearchPattern:
    """搜索模式数据模型"""
    pattern: str  # 搜索模式（支持正则表达式）
    is_regex: bool = False  # 是否为正则表达式
    case_sensitive: bool = True  # 是否区分大小写
    invert_match: bool = False  # 是否反转匹配


@dataclass
class FileFilter:
    """文件过滤器数据模型"""
    name_patterns: list[str] | None = None  # 文件名模式列表（glob模式）
    extensions: list[str] | None = None  # 文件扩展名列表（如 ['py', 'js', 'ts']）
    exclude_patterns: list[str] | None = None  # 排除模式列表
    max_depth: int | None = None  # 最大搜索深度


@dataclass
class OutputFormat:
    """输出格式配置"""
    context_lines: int = 2  # 上下文行数
    show_line_numbers: bool = True  # 显示行号
    show_filename: bool = True  # 显示文件名
    highlight_matches: bool = False  # 高亮匹配内容
    max_matches_per_file: int | None = None  # 每个文件最大匹配数
    output_format: Literal['text', 'structured'] = 'structured'  # 输出格式


@dataclass
class SearchParams:
    """搜索参数聚合模型"""
    content_pattern: SearchPattern  # 内容搜索模式
    file_filter: FileFilter = field(default_factory=FileFilter)  # 文件过滤器
    search_paths: list[str] = field(default_factory=lambda: ['.'])  # 搜索路径列表
    output_format: OutputFormat = field(default_factory=OutputFormat)  # 输出格式


@dataclass
class MatchInfo:
    """单个匹配信息"""
    file_path: str  # 文件路径
    line_number: int  # 匹配行号
    matched_content: str  # 匹配的内容
    context_before: list[str]  # 前置上下文
    context_after: list[str]  # 后置上下文
    start_column: int  # 匹配开始列号
    end_column: int  # 匹配结束列号


@dataclass
class SearchResult:
    """搜索结果聚合模型"""
    params: SearchParams  # 搜索参数
    total_files_searched: int  # 搜索的文件总数
    files_with_matches: int  # 有匹配的文件数
    total_matches: int  # 总匹配数
    search_time: float  # 总搜索时间（秒）
    file_results: list[MatchInfo]  # 各文件搜索结果
    errors: list[str]  # 错误信息列表