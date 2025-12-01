from pathlib import Path
from typing import Union


def get_prompt_file_path(prompt_rel_path: str) -> Path:
    """动态获取 prompt 文件绝对路径（兼容开发/安装环境）"""
    # 1. 开发环境：项目根目录下的 prompt
    project_root = Path(__file__).parent.parent.parent.parent.parent  # 适配你的目录层级
    dev_prompt_path = project_root / "prompt" / prompt_rel_path
    if dev_prompt_path.exists():
        return dev_prompt_path

    # 2. 安装环境：share/tasking/prompt 目录
    try:
        from pkg_resources import resource_filename, Requirement
        install_prompt_dir = Path(resource_filename(Requirement.parse("tasking"), "share/tasking/prompt"))
    except ImportError:
        import importlib.util
        spec = importlib.util.find_spec("tasking")
        if spec and spec.submodule_search_locations:
            pkg_dir = Path(spec.submodule_search_locations[0])
        else:
            pkg_dir = Path(__file__).resolve().parent.parent
        install_prompt_dir = pkg_dir.parent.parent / "share" / "tasking" / "prompt"

    install_prompt_path = install_prompt_dir / prompt_rel_path
    if install_prompt_path.exists():
        return install_prompt_path

    raise FileNotFoundError(f"Prompt 文件不存在：{prompt_rel_path}")


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
