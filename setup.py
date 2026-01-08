from setuptools import setup, find_packages

# 步骤1：扫描 tasking 下所有子包（得到 ["core", "core.agent", "llm", "memory", ...]）
src_sub_packages = find_packages(where="tasking")

# 步骤2：给每个子包名添加 "tasking." 前缀（变成 ["tasking.core", "tasking.core.agent", ...]）
tasking_sub_packages = [f"tasking.{pkg}" for pkg in src_sub_packages]

setup(
    # 步骤3：打包列表 = 主包 "tasking" + 带前缀的子包
    packages=["tasking"] + tasking_sub_packages,
    # 关键映射：所有 "tasking.*" 包的源码都在 tasking 目录下（自动对应子目录）
    # 例：tasking.core → tasking/core，tasking.llm → tasking/llm
    package_dir={"tasking": "tasking"},
    # 打包资源文件
    package_data={
        "": ["*.md", "*.xml"],
        "tasking": ["*", "py.typed"],
        "tasking.core": ["*"],
    },
    # 资源文件（prompt 目录）- 按子路径组织
    data_files=[
        ("share/tasking/prompt/tool", [
            "prompt/tool/human_interfere.md",
        ]),
        ("share/tasking/prompt/memory", [
            "prompt/memory/episode_search.md",
            "prompt/memory/episode_compress.md",
            "prompt/memory/state_compress.md",
        ]),
        ("share/tasking/prompt/task", [
            "prompt/task/default.md",
        ]),
        ("share/tasking/prompt/workflow/orchestrate", [
            "prompt/workflow/orchestrate/orchestrating.md",
            "prompt/workflow/orchestrate/thinking.md",
        ]),
        ("share/tasking/prompt/workflow/react", [
            "prompt/workflow/react/processing.md",
        ]),
        ("share/tasking/prompt/workflow/reflect", [
            "prompt/workflow/reflect/reasoning.md",
            "prompt/workflow/reflect/reflecting.md",
        ]),
    ],
)