# Database 类测试驱动文档

# 1. 文档概述

## 1.1 文档目的

本文档为 `Database` 模块（数据库存储系统）的测试驱动规范，明确"需测试的功能范围、测试用例设计逻辑、执行标准及交付要求"，确保测试覆盖所有核心功能与接口契约，验证 Database 系统符合设计预期（如接口实现、查询构建、内容序列化、向量搜索等）。

## 1.2 测试对象

测试对象包括基于数据库抽象接口实现的数据库系统，核心组件包括：

- **数据库接口层**：定义数据库操作的抽象契约（IDatabase、IVectorDatabase、ISqlDatabase、IKVDatabase）；
- **SQLite 实现**：基于 aiosqlite 的关系型数据库实现，支持复杂查询和多模态内容存储；
- **Milvus 实现**：基于 pymilvus 的向量数据库实现，支持混合搜索和多嵌入模型；
- **数据管理组件**：SearchParams、EmbeddingInfo 等辅助数据结构。

## 1.3 测试依据

- 数据库抽象接口定义的抽象方法契约；
- SQLite 和 Milvus 具体实现的设计注释和核心逻辑；
- 多模态内容序列化/反序列化规范；
- SQL 查询构建和向量搜索算法实现。

# 2. 测试目标

1. **接口合规性**：验证所有数据库接口的完整性和正确性，确保抽象方法被正确实现；
2. **组件隔离性**：验证每个数据库实现类的内部逻辑正确，通过 Mock 隔离外部依赖；
3. **数据处理正确性**：验证多模态内容序列化、SQL 查询构建、向量搜索等核心功能；
4. **边缘情况处理**：验证异常输入、错误处理、资源管理等边界条件；
5. **类型安全性**：验证泛型类型约束和类型注解的正确使用。

# 3. 测试范围

基于 Database 模块的核心能力，测试范围分为"接口测试模块""SQLite实现模块""Milvus实现模块""数据组件模块"四大类，具体测试项如下：

## 3.1 接口测试模块

|测试子项|测试内容说明|测试类型|
|---|---|---|
|接口抽象性验证|1. 验证所有数据库接口是抽象基类；2. 验证抽象方法定义；3. 验证接口文档完整性|接口测试|
|方法签名检查|1. 验证所有必需方法的存在和签名；2. 验证泛型类型参数的正确使用；3. 验证返回类型和参数类型|接口测试|
|接口实现验证|1. 验证 SQLite 和 Milvus 实现正确实现对应接口；2. 验证具体实现符合接口契约；3. 验证继承关系|接口测试|

## 3.2 SQLite实现模块

|测试子项|测试内容说明|测试类型|
|---|---|---|
|SearchParams 数据类|1. 参数初始化和默认值；2. None 值处理；3. 参数验证和约束|功能测试|
|内容序列化/反序列化|1. 多模态内容 JSON 序列化；2. TextBlock/ImageBlock/VideoBlock 处理；3. 错误恢复和异常处理|功能测试|
|SQL 查询构建|1. _build_search_query 方法测试；2. 复杂 WHERE 子句处理；3. ORDER BY、LIMIT/OFFSET、GROUP BY、HAVING|功能测试|
|结果行处理|1. _process_row 方法测试；2. 内容反序列化；3. 类型转换和内存对象重建|功能测试|
|CRUD 操作|1. add、delete、update、search 方法测试；2. 错误处理和异常场景；3. 资源管理和连接清理|功能测试|

## 3.3 Milvus实现模块

|测试子项|测试内容说明|测试类型|
|---|---|---|
|EmbeddingInfo 数据结构|1. NamedTuple 类型安全；2. 维度验证；3. 搜索参数配置|功能测试|
|多模态内容标准化|1. _ensure_multimodal_content 方法；2. 字符串到 TextBlock 转换；3. 列表处理和验证|功能测试|
|向量嵌入生成|1. 多嵌入模型支持；2. 向量维度验证；3. 嵌入生成错误处理|功能测试|
|混合搜索功能|1. 多嵌入向量搜索；2. AnnSearchRequest 创建；3. RRFRanker 使用和结果合并|功能测试|
|搜索结果处理|1. _process_search_results 方法；2. _extract_hit_data 方法；3. 距离过滤和内容重建|功能测试|
|向量 CRUD 操作|1. 向量数据添加、删除、更新；2. 相似性搜索和查询；3. 集合管理操作|功能测试|

## 3.4 数据组件模块

|测试子项|测试内容说明|测试类型|
|---|---|---|
|SearchParams 类|1. 数据类初始化；2. 字段默认值；3. 参数边界值测试|功能测试|
|EmbeddingInfo 类|1. NamedTuple 创建；2. 类型约束；3. 不可变性验证|功能测试|
|多模态内容转换|1. 不同内容类型转换；2. 错误输入处理；3. 数据完整性验证|功能测试|

测试用例需遵循"正向验证+异常处理"原则，即既要验证合法操作正常执行，也要验证异常情况被正确处理。以下为关键测试用例模板：

## 4.1 接口测试用例模板（以"SQLite 接口实现验证"为例）

|用例ID|测试项|前置条件|测试步骤|预期结果|优先级|
|---|---|---|---|---|---|
|IFACE-SQLITE-001|SqliteDatabase 接口实现验证|1. Python 3.12+ 环境；2. 已导入相关接口和实现|1. 验证 SqliteDatabase 继承 ISqlDatabase；2. 验证所有抽象方法被实现；3. 验证方法签名匹配|1. 继承关系正确；2. 所有抽象方法有实现；3. 方法签名与接口一致|高|

## 4.2 SQLite 功能测试用例模板

|用例ID|测试项|前置条件|测试步骤|预期结果|优先级|
|---|---|---|---|---|---|
|SQLITE-PARAMS-001|SearchParams 默认值测试|1. 导入 SearchParams 类|1. 创建无参数的 SearchParams 实例；2. 验证所有字段默认值为 None|1. 实例创建成功；2. 所有字段为 None|高|
|SQLITE-SERIAL-001|TextBlock 内容序列化|1. 创建包含 TextBlock 的记忆对象；2. 准备序列化方法|1. 调用 _serialize_content 方法；2. 验证 JSON 输出格式；3. 验证内容完整性|1. 序列化成功；2. JSON 格式正确；3. 内容数据完整|高|
|SQLITE-QUERY-001|基础 SQL 查询构建|1. 创建 SearchParams 实例；2. 设置基础查询参数|1. 调用 _build_search_query 方法；2. 验证 SQL 语句结构；3. 验证参数列表|1. SQL 语句正确；2. 参数列表正确；3. 无语法错误|高|
|SQLITE-QUERY-002|复杂 WHERE 子句构建|1. 创建包含多个条件的 SearchParams；2. 设置复杂 where 条件|1. 构建查询语句；2. 验证 WHERE 子句逻辑；3. 验证 AND 连接|1. WHERE 子句正确；2. 条件逻辑正确；3. AND 连接正确|中|

## 4.3 Milvus 功能测试用例模板

|用例ID|测试项|前置条件|测试步骤|预期结果|优先级|
|---|---|---|---|---|---|
|MILVUS-EMBED-001|EmbeddingInfo 创建验证|1. 准备嵌入模型实例；2. 设置维度和搜索参数|1. 创建 EmbeddingInfo 实例；2. 验证字段值；3. 验证类型约束|1. 实例创建成功；2. 字段值正确；3. 类型符合预期|高|
|MILVUS-MULTI-001|字符串内容标准化|1. 准备纯字符串内容；2. 调用标准化方法|1. 调用 _ensure_multimodal_content；2. 验证返回类型；3. 验证 TextBlock 内容|1. 返回 list 类型；2. 包含一个 TextBlock；3. 文本内容正确|高|
|MILVUS-HYBRID-001|双嵌入向量搜索|1. 准备两个嵌入模型；2. 设置搜索参数|1. 创建 AnnSearchRequest；2. 设置 RRFRanker；3. 执行混合搜索|1. 请求创建成功；2. 排名器配置正确；3. 搜索结果合并正确|中|

# 5. 测试环境要求

## 5.1 硬件环境

- CPU：≥2核（支持数据处理和并发测试）
- 内存：≥4GB（支持大量数据测试和向量计算）
- 存储：≥5GB（测试数据和临时文件存储）

## 5.2 软件环境

|环境类型|具体要求|说明|
|---|---|---|
|操作系统|Linux（Ubuntu 20.04+/CentOS 7+）、macOS（12+）、Windows（WSL2）|支持跨平台测试|
|依赖工具|Python 3.12+、pytest 7.0+、pytest-asyncio 0.21.0+、aiosqlite、pymilvus|通过 `uv pip install` 安装|
|基础组件|uv（推荐）或 python3|用于环境管理和依赖安装|

## 5.3 静态检查要求

所有测试代码编辑完成后，必须执行以下静态检查流程：

### 必需检查

1. **pyright 检查**：确保类型正确性和现代 Python 特性的正确使用

   ```bash
   uv run pyright tasking/database/
   uv run pyright tests/unit/database/
   ```

2. **pylint 检查**：确保代码风格、结构和最佳实践

   ```bash
   uv run pylint tasking/database/
   uv run pylint tests/unit/database/
   ```

### 检查标准

- **pyright**：必须零错误，警告应评估并修复
- **pylint**：评分 ≥ 8.0/10，关键错误必须修复

### 集成到开发流程

- 每次编辑代码后必须执行上述检查
- 提交前必须确保所有检查通过
- 测试脚本应集成静态检查功能

### 测试脚本集成

使用统一的测试脚本 `tests/unit/database/run_tests.sh` 执行数据库模块测试：

```bash
# 运行数据库模块单元测试
./tests/unit/database/run_tests.sh all

# 运行 SQLite 特定测试
./tests/unit/database/run_tests.sh sqlite

# 运行 Milvus 特定测试
./tests/unit/database/run_tests.sh milvus

# 运行质量检查
./tests/unit/database/run_tests.sh quality

# 运行覆盖率报告
./tests/unit/database/run_tests.sh coverage
```

# 6. 测试执行策略

## 6.1 执行顺序

1. **接口测试**：先验证所有数据库接口定义和契约正确，再进行实现测试
2. **数据组件测试**：验证 SearchParams、EmbeddingInfo 等基础数据结构
3. **SQLite 实现测试**：验证 SQLite 查询构建、内容序列化等核心功能
4. **Milvus 实现测试**：验证向量搜索、混合搜索等向量数据库功能
5. **集成场景测试**：最后执行端到端集成测试

## 6.2 优先级与阻塞规则

- 优先级划分：接口测试（最高）> 数据组件测试（高）> SQLite 实现（高）> Milvus 实现（中）> 集成场景（中）
- 阻塞规则：若接口测试或数据组件测试失败，直接阻塞后续所有测试，需优先修复

## 6.3 缺陷管理

- **严重缺陷（P0）**：接口实现错误、核心功能失效、数据丢失/损坏；需立即修复，修复后重新执行全量测试
- **一般缺陷（P1）**：查询构建错误、序列化异常、搜索结果不正确；需在迭代内修复，修复后执行相关模块测试
- **轻微缺陷（P2）**：边缘情况处理不完善、性能问题、非核心方法注释缺失；可延后修复，不阻塞测试通过

# 7. Mock 策略

## 7.1 组件隔离原则

- **完全隔离**：所有单元测试必须通过 Mock 隔离外部数据库连接
- **可控输入**：使用预定义的测试数据和 Mock 返回值
- **状态验证**：验证方法调用次数、参数传递和返回值处理

## 7.2 SQLite Mock 配置

```python
# Mock aiosqlite 连接和游标
MockAsyncConnection = AsyncMock(spec=aiosqlite.Connection)
MockAsyncCursor = AsyncMock(spec=aiosqlite.Cursor)
MockSqliteManager = AsyncMock(spec=ISqlDBManager[aiosqlite.Connection])

# 配置 Mock 返回值
mock_cursor.fetchall.return_value = test_rows
mock_cursor.description = [(col, None) for col in test_columns]
mock_connection.execute.return_value.__aenter__.return_value = mock_cursor
```

## 7.3 Milvus Mock 配置

```python
# Mock pymilvus 客户端和组件
MockMilvusClient = AsyncMock(spec=AsyncMilvusClient)
MockEmbedModel = AsyncMock(spec=IEmbedModel)
MockVectorManager = AsyncMock(spec=IVectorDBManager[AsyncMilvusClient])

# 配置向量嵌入 Mock
mock_embed_model.embed.return_value = [0.1, 0.2, 0.3]  # 模拟向量
```

## 7.4 共享 Mock 组件

```python
# Mock 内存实现
MockMemory = create_autospec(MemoryProtocol, instance=True)
MockMultimodalContent = create_autospec(MultimodalContent, instance=True)
```

# 8. 测试交付物

1. **测试用例集**：含完整测试用例的测试文件（`test_search_params.py`、`test_embedding_info.py`、`test_sqlite_*.py`、`test_milvus_*.py` 等，可直接执行）
2. **测试报告**：含测试覆盖率（≥80%）、用例执行结果（通过率）、缺陷清单及修复情况
3. **问题记录**：未修复缺陷的跟踪表（含用例ID、复现步骤、影响范围）
4. **环境配置说明**：测试环境的详细部署步骤（用于回归测试）

# 9. 附则

本文档需随 Database 模块的迭代同步更新：若新增数据库实现（如 Redis KV 数据库）或修改接口定义（如新增抽象方法），需补充对应的测试范围、用例及执行标准。

## 9.1 测试设计原则

- **功能验证优先**：专注核心功能测试，不进行性能测试或负载测试
- **独立性**：每个测试方法独立运行，不依赖其他测试的执行顺序
- **可重复性**：使用固定的测试数据，确保测试结果的一致性
- **清晰性**：测试意图明确，易于理解和维护

## 9.2 测试隔离机制

- **环境隔离**：每个测试使用独立的测试环境，不依赖真实数据库
- **数据隔离**：测试数据不相互污染，使用 Mock 对象隔离外部依赖
- **状态隔离**：测试状态在测试间完全重置，使用 setUp/tearDown 清理
- **Mock 使用**：使用 Mock 对象验证交互行为而非具体实现

## 9.3 错误排查指南

**常见问题**:

1. **导入错误**: 确保使用正确的模块路径（如 `tasking.database.sqlite`）
2. **Mock 配置错误**: 检查 Mock 对象的 spec 配置和返回值设置
3. **异步测试错误**: 确保使用 `unittest.IsolatedAsyncioTestCase` 或 `@pytest.mark.asyncio`
4. **数据类型错误**: 检查 SearchParams 和 EmbeddingInfo 的类型约束
5. **序列化错误**: 验证多模态内容的 JSON 序列化格式
6. **路径问题**: 确保在项目根目录执行测试，使用正确的 Python 路径

**调试技巧**:

- 使用 `print()` 或 `logging` 输出中间结果
- 检查 Mock 对象的调用记录和参数
- 验证异步方法的 await 调用
- 使用调试器逐步执行测试逻辑