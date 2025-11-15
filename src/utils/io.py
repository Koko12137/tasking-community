from pathlib import Path
from typing import Union


def read_document(
    path: Union[str, Path],
    encoding: str = "utf-8",
) -> str:
    """
    读取文件并根据文件类型返回文本内容。

    支持的类型：Markdown (.md, .markdown)、XML (.xml)、纯文本（其它扩展或无扩展）。

    参数:
    - path: 文件路径（str 或 Path）
    - encoding: 文件编码，默认 'utf-8'

    返回: 文本字符串
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"不是文件: {p}")

    return p.read_text(encoding=encoding)


# 为了兼容历史代码，保留 read_markdown 名称作为 alias（会根据扩展自动处理）
def read_markdown(path: Union[str, Path], encoding: str = "utf-8") -> str:
    """兼容接口：默认按纯文本读取 Markdown 文件。"""
    return read_document(path, encoding)
