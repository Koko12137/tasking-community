"""IO utility functions for reading files from different sources."""

from pathlib import Path
from typing import Union
import sys


def get_prompt_file_path(prompt_rel_path: str) -> Path:
    """动态获取 prompt 文件绝对路径（兼容开发/安装环境）"""
    # 1. 开发环境：项目根目录下的 prompt
    project_root = Path(__file__).parent.parent.parent  # src/utils/io.py -> 项目根目录
    dev_prompt_path = project_root / "prompt" / prompt_rel_path
    if dev_prompt_path.exists():
        return dev_prompt_path

    # 检查当前 Python 路径中是否有包含 prompts 目录的项目根目录
    for path_entry in sys.path:
        potential_root = Path(path_entry)
        # 检查是否包含 prompts 目录和该文件（src 项目结构）
        potential_file = potential_root / "prompts" / prompt_rel_path
        if potential_file.exists():
            return potential_file
        # 也检查上级目录（项目根目录）
        potential_file = potential_root.parent / "prompts" / prompt_rel_path
        if potential_file.exists():
            return potential_file

    # 2. 安装环境：share/tasking/prompt 目录（多种路径方案）

    # 方案A: 通过 sys.prefix 构造路径（通用且可靠）
    # 标准环境：/usr/local -> /usr/local/share/tasking/prompt
    # venv环境：/path/to/.venv -> /path/to/.venv/share/tasking/prompt
    # conda环境：/path/to/envs/name -> /path/to/envs/name/share/tasking/prompt
    candidate_paths = [
        Path(sys.prefix) / "share" / "tasking" / "prompt" / prompt_rel_path,
        # 方案B: lib64 环境（WSL等）
        Path(sys.prefix).parent / "share" / "tasking" / "prompt" / prompt_rel_path,
        # 方案C: 通过包位置推导（兼容性方案）
        Path(__file__).resolve().parent.parent.parent / "share" \
        / "tasking" / "prompt" / prompt_rel_path,
    ]

    for candidate in candidate_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        f"Prompt 文件不存在：{prompt_rel_path}\n"
        f"已搜索路径：\n"
        f"  - tasking包开发环境: {dev_prompt_path}\n"
        f"  - 外部项目prompts目录（自动检测）\n"
        f"  - 安装环境: {candidate_paths[0]}\n"
        f"请确保文件存在且路径正确。"
    )


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
    # 获取文件绝对路径
    path = get_prompt_file_path(str(path))
    # 读取文件内容
    p = Path(path)
    return p.read_text(encoding=encoding)


# 为了兼容历史代码，保留 read_markdown 名称作为 alias（会根据扩展自动处理）
def read_markdown(path: Union[str, Path], encoding: str = "utf-8") -> str:
    """兼容接口：默认按纯文本读取 Markdown 文件。"""
    return read_document(path, encoding)
