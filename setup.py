from setuptools import setup, find_packages

# 步骤1：扫描 src 下所有子包（得到 ["core", "core.agent", "llm", "memory", ...]）
src_sub_packages = find_packages(where="src")  # 无 prefix 参数！

# 步骤2：给每个子包名添加 "tasking." 前缀（变成 ["tasking.core", "tasking.core.agent", ...]）
tasking_sub_packages = [f"tasking.{pkg}" for pkg in src_sub_packages]

setup(
    # 步骤3：打包列表 = 主包 "tasking" + 带前缀的子包
    packages=["tasking"] + tasking_sub_packages,
    # 关键映射：所有 "tasking.*" 包的源码都在 src 目录下（自动对应子目录）
    # 例：tasking.core → src/core，tasking.llm → src/llm
    package_dir={"tasking": "src"},
    # 打包资源文件
    package_data={
        "": ["*.md", "*.xml"],
        "tasking": ["*"],
        "tasking.core": ["*"],
    },
    # 资源文件（prompt 目录）
    data_files=[
        ("share/tasking/prompt", [
            "prompt/task/default.xml",
            "prompt/task/plan_and_exec.xml",
            "prompt/workflow/orchestrate/orchestrating.md",
            "prompt/workflow/orchestrate/thinking.md",
            "prompt/workflow/react/processing.md",
            "prompt/workflow/reflect/reasoning.md",
            "prompt/workflow/reflect/reflecting.md",
            "prompt/workflow/supervise/system.md",
        ])
    ],
)