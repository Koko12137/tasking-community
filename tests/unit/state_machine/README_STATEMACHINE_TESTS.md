# 状态机测试套件

这是一个完整的状态机测试套件，包含基础功能测试和Corner Cases测试，确保状态机系统的稳定性和可靠性。

## 📋 测试概览

### 测试文件结构

**test_state_machine.py** - 基础功能测试 (20个测试)
**test_corner_cases.py** - 边界条件和异常测试 (20个测试)

**总计**: 40个测试，覆盖率73%

### 1. 基础功能测试 (test_state_machine.py)

#### 核心功能测试
- **TestBaseStateMachine**: 核心状态机功能测试
- **TestBaseTask**: 任务状态机扩展功能测试
- **TestBaseTreeTaskNode**: 树形任务节点管理测试
- **TestStateMachineBuilder**: 工厂模式构建器测试
- **TestIntegration**: 集成测试样例

#### 核心设计模式展示
- **工厂模式**: 状态机实例创建的工厂方法
- **Protocol接口**: 状态机接口的正确使用
- **模拟模式**: Mock对象的创建和使用
- **生命周期管理**: setUp/tearDown的最佳实践
- **泛型类型安全**: 严格的类型检查和泛型约束

### 2. Corner Cases测试 (test_corner_cases.py)

#### 边界条件和异常测试
- **TestTreeCircularReference**: 循环引用检测测试
- **TestTreeDepthBoundaries**: 深度边界测试
- **TestTypeSafety**: 类型安全测试
- **TestErrorRecovery**: 错误恢复测试
- **TestBoundaryConditions**: 边界条件测试

#### 测试重点
- **循环引用检测**: 防止无限递归和内存泄漏
- **深度边界验证**: 确保树结构逻辑正确
- **类型安全保证**: 验证泛型系统正确工作
- **错误恢复机制**: 确保异常情况下系统稳定
- **边界条件处理**: 处理极值和特殊情况

### 3. 测试脚本设计

#### 双重脚本支持
- **run_state_machine_tests.sh**: Shell版本（Linux/Mac/WSL）
- **run_state_machine_tests.py**: Python版本（跨平台）

#### 设计特色
- **智能环境检测**: uv/python环境自动选择
- **用户体验优化**: 彩色输出、详细帮助信息
- **错误处理机制**: 完善的异常处理和用户提示
- **模块化设计**: 功能分类、参数化支持

## 使用指南

### 运行测试

```bash
# 运行所有测试 (40个测试)
./tests/state_machine/run_state_machine_tests.sh all
# 或
python tests/state_machine/run_state_machine_tests.py all

# 运行基础功能测试 (20个测试)
./tests/state_machine/run_state_machine_tests.sh basic
# 或
python tests/state_machine/run_state_machine_tests.py basic

# 运行Corner Cases测试 (20个测试)
./tests/state_machine/run_state_machine_tests.sh corner
# 或
python tests/state_machine/run_state_machine_tests.py corner

# 生成覆盖率报告
./tests/state_machine/run_state_machine_tests.sh coverage

# 直接使用pytest
pytest tests/state_machine/ -v
```

### 查看帮助信息

```bash
# 查看Shell脚本帮助
./tests/state_machine/run_state_machine_tests.sh help

# 查看Python脚本帮助
python tests/state_machine/run_state_machine_tests.py --help
```

## 测试命令参考

### Shell脚本命令
```bash
# 基本测试运行
./run_state_machine_tests.sh all              # 运行所有测试 (40个测试)
./run_state_machine_tests.sh basic            # 运行基础功能测试 (20个测试)
./run_state_machine_tests.sh corner           # 运行Corner Cases测试 (20个测试)
./run_state_machine_tests.sh corners          # 运行Corner Cases测试 (20个测试)
./run_state_machine_tests.sh coverage         # 生成覆盖率报告
./run_state_machine_tests.sh install          # 安装测试依赖

# 详细选项
./run_state_machine_tests.sh help             # 显示帮助信息
./run_state_machine_tests.sh single TestName  # 运行单个测试
./run_state_machine_tests.sh verbose          # 详细模式
./run_state_machine_tests.sh clean            # 清理测试文件

# 类别测试
./run_state_machine_tests.sh base             # 基础状态机测试
./run_state_machine_tests.sh task             # 任务状态机测试
./run_state_machine_tests.sh tree             # 树形节点测试
./run_state_machine_tests.sh builder          # 构建器测试
./run_state_machine_tests.sh integration      # 集成测试
```

### Python脚本命令
```bash
# 基本测试运行
python run_state_machine_tests.py all              # 运行所有测试 (40个测试)
python run_state_machine_tests.py basic            # 运行基础功能测试 (20个测试)
python run_state_machine_tests.py corner           # 运行Corner Cases测试 (20个测试)
python run_state_machine_tests.py corners          # 运行Corner Cases测试 (20个测试)
python run_state_machine_tests.py coverage         # 生成覆盖率报告
python run_state_machine_tests.py install          # 安装测试依赖

# 详细选项
python run_state_machine_tests.py help             # 显示帮助信息
python run_state_machine_tests.py single TestName  # 运行单个测试
python run_state_machine_tests.py verbose          # 详细模式
python run_state_machine_tests.py clean            # 清理测试文件

# 类别测试
python run_state_machine_tests.py base             # 基础状态机测试
python run_state_machine_tests.py task             # 任务状态机测试
python run_state_machine_tests.py tree             # 树形节点测试
python run_state_machine_tests.py builder          # 构建器测试
python run_state_machine_tests.py integration      # 集成测试
```

## 测试覆盖范围

### 基础功能测试 (test_state_machine.py)
- ✅ 状态机核心功能 (初始化、编译、转换、事件处理)
- ✅ 任务系统功能 (属性管理、输入输出、错误处理)
- ✅ 树形结构功能 (层级关系、父子节点、深度计算)
- ✅ 构建器功能 (工厂模式、配置验证、自动编译)
- ✅ 集成测试 (完整生命周期、复杂转换、多节点协作)

### Corner Cases测试 (test_corner_cases.py)
- ✅ 循环引用检测 (简单循环、自引用、深层循环)
- ✅ 深度边界测试 (最大深度、一致性验证、移除重置)
- ✅ 类型安全测试 (泛型一致性、接口安全、None处理)
- ✅ 错误恢复测试 (编译失败恢复、状态一致性、部分初始化)
- ✅ 边界条件测试 (单状态、空转换、重复操作、空值处理)

## 覆盖率统计

### 当前覆盖率: 73%

#### 模块覆盖率详情:
- **tasking/state_machine/base.py**: 81% (核心状态机功能)
- **tasking/state_machine/task.py**: 93% (任务和树形节点)
- **tasking/state_machine/const.py**: 100% (常量定义)
- **tasking/state_machine/interface.py**: 69% (接口定义)
- **tasking/state_machine/builder.py**: 29% (构建器工厂)

## 设计特色

### 1. 智能环境检测
- **uv环境优先**: 自动检测并使用uv环境
- **Python回退**: uv不可用时自动使用系统python
- **依赖管理**: 自动安装和验证测试依赖

### 2. 用户体验优化
- **彩色输出**: 状态信息、成功、警告、错误分类显示
- **详细帮助**: 完整的命令说明和使用示例
- **错误诊断**: 包含具体的解决建议

### 3. 跨平台兼容
- **Shell脚本**: 针对Linux/Mac/WSL用户优化
- **Python脚本**: 提供跨平台兼容性
- **统一接口**: 两种脚本提供相同的功能

## 技术栈

### 测试框架
- **pytest**: 现代Python测试框架
- **unittest**: Python标准测试库
- **mock**: 对象模拟和测试隔离

### 类型系统
- **TypeVar**: 泛型类型变量
- **Protocol**: 结构化类型系统
- **Generic**: 泛型类约束

### 工具链
- **uv**: Python包管理器
- **pytest-cov**: 覆盖率测试
- **pytest-mock**: Mock对象支持
- **pytest-asyncio**: 异步测试支持

## 最佳实践

### 测试设计原则
1. **测试隔离**: 每个测试方法独立运行
2. **清理资源**: 在tearDown中清理资源
3. **错误处理**: 完善的异常处理机制
4. **类型安全**: 严格的类型检查和泛型约束

### 代码质量保证
1. **全量覆盖**: 基础功能和边界条件全覆盖
2. **错误场景**: 异常情况和恢复机制测试
3. **类型验证**: 泛型系统和接口兼容性
4. **文档完善**: 清晰的测试说明和注释

---

**状态机测试套件**: 确保状态机系统的稳定性、可靠性和类型安全。