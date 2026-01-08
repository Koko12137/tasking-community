"""
File system related data models.

This module provides comprehensive data models for file system operations,
including editing, searching, and result formatting.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class FileType(StrEnum):
    """文件类型枚举"""

    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FOLDER = "folder"
    OTHER = "other"


class EditOperation(BaseModel):
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


class SearchPattern(BaseModel):
    """搜索模式数据模型"""
    pattern: str  # 搜索模式（支持正则表达式）
    is_regex: bool = False  # 是否为正则表达式
    case_sensitive: bool = True  # 是否区分大小写
    invert_match: bool = False  # 是否反转匹配


class FileFilter(BaseModel):
    """文件过滤器数据模型"""
    name_patterns: list[str] | None = None  # 文件名模式列表（glob模式）
    extensions: list[str] | None = None  # 文件扩展名列表（如 ['py', 'js', 'ts']）
    exclude_patterns: list[str] | None = None  # 排除模式列表
    max_depth: int | None = None  # 最大搜索深度


class FileInfo(BaseModel):
    """文件/目录元数据"""

    name: str  # 名称（含文件名，不含路径）
    path: str  # 相对 workspace 的路径
    full_path: str  # 绝对路径
    parent: str  # 相对 workspace 的父路径（根目录为空字符串）
    size: int | None  # 文件大小（字节）；目录为 None
    file_type: FileType  # 文件类型（文本/图片/音频/视频/目录/其他）
    extension: str  # 文件扩展名（含点，例如 .txt），目录为空字符串


class OutputFormat(BaseModel):
    """输出格式配置"""
    context_lines: int = 2  # 上下文行数
    show_line_numbers: bool = True  # 显示行号
    show_filename: bool = True  # 显示文件名
    highlight_matches: bool = False  # 高亮匹配内容
    max_matches_per_file: int | None = None  # 每个文件最大匹配数
    output_format: Literal['text', 'structured'] = 'structured'  # 输出格式


class SearchParams(BaseModel):
    """搜索参数聚合模型"""
    content_pattern: SearchPattern  # 内容搜索模式
    file_filter: FileFilter = Field(default_factory=FileFilter)  # 文件过滤器
    search_paths: list[str] = Field(default_factory=lambda: ['.'])  # 搜索路径列表
    output_format: OutputFormat = Field(default_factory=OutputFormat)  # 输出格式


class MatchInfo(BaseModel):
    """单个匹配信息"""
    file_path: str  # 文件路径
    line_number: int  # 匹配行号
    matched_content: str  # 匹配的内容
    context_before: list[str]  # 前置上下文
    context_after: list[str]  # 后置上下文
    start_column: int  # 匹配开始列号
    end_column: int  # 匹配结束列号


class SearchResult(BaseModel):
    """搜索结果聚合模型"""
    params: SearchParams  # 搜索参数
    total_files_searched: int  # 搜索的文件总数
    files_with_matches: int  # 有匹配的文件数
    total_matches: int  # 总匹配数
    search_time: float  # 总搜索时间（秒）
    file_results: list[MatchInfo]  # 各文件搜索结果
    errors: list[str]  # 错误信息列表
