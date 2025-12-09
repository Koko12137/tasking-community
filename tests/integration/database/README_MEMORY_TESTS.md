# 记忆模块测试套件

这是一个完整的记忆模块测试套件，包含 SQLite 和 Milvus 两种记忆实现的测试，确保记忆存储系统的稳定性和可靠性。

## 📋 测试概览

### 测试文件结构

- **test_sqlite_memory.py** - SQLite 记忆实现测试 (10个测试)
- **test_milvus_memory.py** - MilvusVectorMemory 类测试 (12个测试)

**总计**: 22个测试

### 1. SQLite 记忆测试 (test_sqlite_memory.py)

#### 测试类别
- **TestSqliteMemoryAddAndSearch**: 添加和搜索功能测试
- **TestSqliteMemoryUpdate**: 更新功能测试
- **TestSqliteMemoryDelete**: 删除功能测试
- **TestSqliteMemoryClose**: 连接关闭测试
- **TestSqliteMemoryIntegration**: 集成测试

#### 测试特点
- 使用 `aiosqlite.connect(":memory:")` 内存数据库
- 真实数据库交互，无 Mock
- 异步测试支持

### 2. MilvusVectorMemory 类测试 (test_milvus_memory.py)

#### 测试类别
- **TestMilvusVectorMemoryInit**: 初始化测试
- **TestMilvusVectorMemoryAdd**: 添加记忆测试
- **TestMilvusVectorMemoryDelete**: 删除记忆测试
- **TestMilvusVectorMemoryUpdate**: 更新记忆测试
- **TestMilvusVectorMemoryClose**: 关闭连接测试
- **TestMilvusVectorMemorySearch**: 搜索记忆测试
- **TestMilvusVectorMemoryIntegration**: 集成测试

#### 测试特点
- Mock AsyncMilvusClient 和 EmbeddingInfo
- 使用 Mock 嵌入模型
- 测试 MilvusVectorMemory 类的所有接口方法

## 使用指南

### 运行测试

```bash
# 运行所有测试
./tests/memory/run_memory_tests.sh all

# 运行 SQLite 测试
./tests/memory/run_memory_tests.sh sqlite

# 运行 Milvus 测试
./tests/memory/run_memory_tests.sh milvus

# 生成覆盖率报告
./tests/memory/run_memory_tests.sh coverage

# 运行代码质量检查
./tests/memory/run_memory_tests.sh quality

# 查看帮助
./tests/memory/run_memory_tests.sh help
```

### 直接使用 pytest

```bash
# 运行所有记忆测试
PYTHONPATH=. uv run pytest tests/memory/ -v

# 运行单个测试文件
PYTHONPATH=. uv run pytest tests/memory/test_sqlite_memory.py -v
PYTHONPATH=. uv run pytest tests/memory/test_milvus_memory.py -v

# 生成覆盖率报告
PYTHONPATH=. uv run pytest tests/memory/ --cov=src.memory --cov-report=term-missing
```

## 测试覆盖范围

### SQLite 记忆测试
- ✅ 添加记忆 (add_memory)
- ✅ 搜索记忆 (search_memory) - 带过滤、限制、空结果
- ✅ 更新记忆 (update_memory)
- ✅ 删除记忆 (delete_memory) - 包括不存在的记忆
- ✅ 关闭连接 (close)
- ✅ 完整生命周期集成测试
- ✅ 批量操作测试

### MilvusVectorMemory 类测试
- ✅ 初始化 (MilvusVectorMemory.__init__)
- ✅ 获取嵌入模型 (get_embedding_llm)
- ✅ 添加记忆 (add_memory)
- ✅ 删除记忆 (delete_memory)
- ✅ 更新记忆 (update_memory)
- ✅ 关闭连接 (close)
- ✅ 搜索记忆 (search_memory) - 带阈值过滤
- ✅ 完整生命周期集成测试
- ✅ 多记忆处理测试

## 技术栈

### 测试框架
- **pytest**: 现代 Python 测试框架
- **pytest-asyncio**: 异步测试支持

### 数据库
- **aiosqlite**: SQLite 异步客户端 (内存模式)
- **Mock**: AsyncMilvusClient 和 EmbeddingInfo (用于 MilvusVectorMemory 测试)

### 工具链
- **uv**: Python 包管理器
- **pytest-cov**: 覆盖率测试
- **pyright/pylint**: 代码质量检查

## 最佳实践

### 测试设计原则
1. **真实数据库交互**: 使用真实的数据库客户端，而非完全 Mock
2. **测试隔离**: 每个测试使用独立的数据库实例
3. **资源清理**: 测试后自动清理临时文件和连接
4. **类型安全**: 严格的类型检查和泛型约束

### 代码质量保证
1. **全量覆盖**: 基础功能和边界条件全覆盖
2. **集成测试**: 完整生命周期测试
3. **类型验证**: pyright 零错误
4. **代码规范**: pylint 评分 ≥ 8.0/10

---

**记忆模块测试套件**: 确保记忆存储系统的稳定性、可靠性和类型安全。
