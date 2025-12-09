"""
数据库接口模块测试套件

测试 src.database.interface 模块中的接口定义
"""

import unittest
from abc import ABC
from typing import Any, Generic, TypeVar

from tasking.database.interface import (
    IDatabase,
    IDBResourceManager,
    IVectorDatabase,
    IVectorDBManager,
    ISqlDatabase,
    ISqlDBManager,
    IKVDatabase,
    IKVDBManager,
    ClientT,
)
from tasking.model.memory import MemoryProtocol, MemoryT


class MockMemory(MemoryProtocol):
    """模拟记忆对象"""

    def __init__(self, id: str, content: str) -> None:
        self.id = id
        self.content = content

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "content": self.content}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MockMemory":
        return cls(data["id"], data["content"])


class TestDatabaseInterfaces(unittest.TestCase):
    """数据库接口定义测试"""

    def test_idatabase_interface(self) -> None:
        """测试 IDatabase 接口定义"""
        # 验证 IDatabase 是抽象基类
        self.assertTrue(issubclass(IDatabase, ABC))
        self.assertTrue(hasattr(IDatabase, '__abstractmethods__'))

        # 验证必需的抽象方法
        abstract_methods = IDatabase.__abstractmethods__
        expected_methods = {'add', 'delete', 'update'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_idb_resource_manager_interface(self) -> None:
        """测试 IDBResourceManager 接口定义"""
        # 验证 IDBResourceManager 是抽象基类
        self.assertTrue(issubclass(IDBResourceManager, ABC))

        # 验证必需的抽象方法
        abstract_methods = IDBResourceManager.__abstractmethods__
        expected_methods = {'close'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_ivector_database_interface(self) -> None:
        """测试 IVectorDatabase 接口定义"""
        # 验证 IVectorDatabase 继承自 IDatabase
        self.assertTrue(issubclass(IVectorDatabase, IDatabase))

        # 验证必需的抽象方法
        abstract_methods = IVectorDatabase.__abstractmethods__
        expected_methods = {
            'get_embedding_llm', 'search', 'query',  # IVectorDatabase 特有方法
            'add', 'delete', 'update'  # IDatabase 继承的方法
        }
        self.assertEqual(abstract_methods, expected_methods)

    def test_ivector_db_manager_interface(self) -> None:
        """测试 IVectorDBManager 接口定义"""
        # 验证 IVectorDBManager 继承自 IDBResourceManager
        self.assertTrue(issubclass(IVectorDBManager, IDBResourceManager))

        # 验证必需的抽象方法
        abstract_methods = IVectorDBManager.__abstractmethods__
        expected_methods = {'get_vector_database', 'close'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_isql_database_interface(self) -> None:
        """测试 ISqlDatabase 接口定义"""
        # 验证 ISqlDatabase 继承自 IDatabase
        self.assertTrue(issubclass(ISqlDatabase, IDatabase))

        # 验证必需的抽象方法
        abstract_methods = ISqlDatabase.__abstractmethods__
        expected_methods = {
            'search',  # ISqlDatabase 特有方法
            'add', 'delete', 'update'  # IDatabase 继承的方法
        }
        self.assertEqual(abstract_methods, expected_methods)

    def test_isql_db_manager_interface(self) -> None:
        """测试 ISqlDBManager 接口定义"""
        # 验证 ISqlDBManager 继承自 IDBResourceManager
        self.assertTrue(issubclass(ISqlDBManager, IDBResourceManager))

        # 验证必需的抽象方法
        abstract_methods = ISqlDBManager.__abstractmethods__
        expected_methods = {'get_sql_database', 'close'}
        self.assertEqual(abstract_methods, expected_methods)

    def test_ikv_database_interface(self) -> None:
        """测试 IKVDatabase 接口定义"""
        # 验证 IKVDatabase 是抽象基类
        self.assertTrue(issubclass(IKVDatabase, ABC))

        # 验证必需的抽象方法
        abstract_methods = IKVDatabase.__abstractmethods__
        expected_methods = {
            'add', 'batch_add', 'delete', 'batch_delete',
            'update', 'batch_update', 'search', 'batch_search'
        }
        self.assertEqual(abstract_methods, expected_methods)

    def test_ikv_db_manager_interface(self) -> None:
        """测试 IKVDBManager 接口定义"""
        # 验证 IKVDBManager 继承自 IDBResourceManager
        self.assertTrue(issubclass(IKVDBManager, IDBResourceManager))

        # 验证必需的抽象方法
        abstract_methods = IKVDBManager.__abstractmethods__
        expected_methods = {'get_kv_database', 'close'}
        self.assertEqual(abstract_methods, expected_methods)


class TestInterfaceTypeParameters(unittest.TestCase):
    """接口类型参数测试"""

    def test_client_type_variable(self) -> None:
        """测试 ClientT 类型变量"""
        self.assertEqual(ClientT.__name__, 'ClientT')
        self.assertTrue(hasattr(ClientT, '__constraints__'))

    def test_generic_type_usage(self) -> None:
        """测试泛型类型使用"""
        # 验证接口类是泛型的
        self.assertTrue(hasattr(IDatabase, '__orig_bases__'))
        self.assertTrue(hasattr(IDBResourceManager, '__orig_bases__'))
        self.assertTrue(hasattr(IVectorDatabase, '__orig_bases__'))
        self.assertTrue(hasattr(ISqlDatabase, '__orig_bases__'))
        self.assertTrue(hasattr(IKVDatabase, '__orig_bases__'))

    def test_memory_type_parameter(self) -> None:
        """测试 MemoryT 类型参数"""
        # 验证 MemoryT 类型参数在接口中使用
        # 这确保了接口可以正确处理不同类型的记忆对象
        class TestDatabase(IDatabase[MockMemory]):
            async def add(self, context: dict[str, Any], memory: MockMemory) -> None:
                pass

            async def delete(self, context: dict[str, Any], memory_id: str) -> None:
                pass

            async def update(self, context: dict[str, Any], memory: MockMemory) -> None:
                pass

        # 验证类型参数正确传递
        db = TestDatabase()
        self.assertIsInstance(db, IDatabase)
        # 验证泛型类型参数（不能直接使用 isinstance 检查泛型类型）
        self.assertEqual(db.__orig_bases__[0].__args__[0], MockMemory)


class TestInterfaceMethodSignatures(unittest.TestCase):
    """接口方法签名测试"""

    def test_idatabase_method_signatures(self) -> None:
        """测试 IDatabase 方法签名"""
        import inspect

        # 检查 add 方法签名
        add_sig = inspect.signature(IDatabase.add)
        params = list(add_sig.parameters.keys())
        expected_params = ['self', 'context', 'memory']
        self.assertEqual(params, expected_params)

        # 检查 delete 方法签名
        delete_sig = inspect.signature(IDatabase.delete)
        params = list(delete_sig.parameters.keys())
        expected_params = ['self', 'context', 'memory_id']
        self.assertEqual(params, expected_params)

        # 检查 update 方法签名
        update_sig = inspect.signature(IDatabase.update)
        params = list(update_sig.parameters.keys())
        expected_params = ['self', 'context', 'memory']
        self.assertEqual(params, expected_params)

    def test_ivector_database_method_signatures(self) -> None:
        """测试 IVectorDatabase 方法签名"""
        import inspect

        # 检查 get_embedding_llm 方法签名
        get_embedding_sig = inspect.signature(IVectorDatabase.get_embedding_llm)
        params = list(get_embedding_sig.parameters.keys())
        expected_params = ['self', 'model_name']
        self.assertEqual(params, expected_params)

        # 检查 search 方法签名
        search_sig = inspect.signature(IVectorDatabase.search)
        params = list(search_sig.parameters.keys())
        expected_params = ['self', 'context', 'query', 'top_k', 'threshold', 'filter_expr']
        self.assertEqual(params, expected_params)

        # 检查 query 方法签名
        query_sig = inspect.signature(IVectorDatabase.query)
        params = list(query_sig.parameters.keys())
        expected_params = ['self', 'context', 'filter_expr', 'output_fields', 'limit']
        self.assertEqual(params, expected_params)

    def test_isql_database_method_signatures(self) -> None:
        """测试 ISqlDatabase 方法签名"""
        import inspect

        # 检查 search 方法签名
        search_sig = inspect.signature(ISqlDatabase.search)
        params = list(search_sig.parameters.keys())
        expected_params = ['self', 'context', 'fields', 'where', 'order_by', 'limit']
        self.assertEqual(params[:6], expected_params)

        # 验证 kwargs 参数
        self.assertTrue(search_sig.parameters['limit'].default is None)
        # 验证签名有类型注解
        self.assertTrue(search_sig.return_annotation is not None)


if __name__ == "__main__":
    unittest.main()