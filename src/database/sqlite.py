"""SQLite记忆存储实现模块"""
from typing import Any

import aiosqlite

from .interface import ISqlDatabase
from ..model import MemoryT


class SqliteDatabase(ISqlDatabase[MemoryT]):
    """SQLite数据库实现类，基于SQLite数据库进行记忆存储和检索"""
    _connection: aiosqlite.Connection
    _table_name: str
    _memory_cls: type[MemoryT]

    def __init__(
        self,
        connection: aiosqlite.Connection,
        table_name: str,
        memory_cls: type[MemoryT],
    ) -> None:
        """初始化SQLite记忆实例

        Args:
            connection: SQLite异步连接实例
            table_name: 数据表名称
            memory_cls: 记忆对象类型
        """
        self._connection = connection
        self._table_name = table_name
        self._memory_cls = memory_cls

    async def add(self, memory: MemoryT) -> None:
        """添加记忆到SQLite数据库"""
        memory_dict = memory.to_dict()
        columns = ", ".join(memory_dict.keys())
        placeholders = ", ".join("?" for _ in memory_dict)
        values = list(memory_dict.values())

        query = f"INSERT INTO {self._table_name} ({columns}) VALUES ({placeholders})"
        await self._connection.execute(query, values)
        await self._connection.commit()

    async def delete(self, memory_id: str) -> None:
        """从SQLite数据库中删除记忆"""
        query = f"DELETE FROM {self._table_name} WHERE id = ?"
        await self._connection.execute(query, (memory_id,))
        await self._connection.commit()

    async def update(self, memory: MemoryT) -> None:
        """更新SQLite数据库中的记忆"""
        memory_dict = memory.to_dict()
        memory_id = memory_dict.pop("id")
        set_clause = ", ".join(f"{key} = ?" for key in memory_dict.keys())
        values = list(memory_dict.values()) + [memory_id]

        query = f"UPDATE {self._table_name} SET {set_clause} WHERE id = ?"
        await self._connection.execute(query, values)
        await self._connection.commit()

    async def close(self) -> None:
        """关闭SQLite连接，释放资源"""
        await self._connection.close()

    async def search(
        self,
        fields: list[str] | None = None,
        where: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        **kwargs: Any
    ) -> list[MemoryT]:
        """在SQLite数据库中搜索记忆条目

        Args:
            fields: 要查询的字段列表，如果为None则查询所有字段(*)
            where: WHERE过滤条件列表，每个条件为完整的SQL表达式，如 ["status = 'active'", "created_at > '2024-01-01'"]
            order_by: 排序字段，支持ASC/DESC，如 "id DESC"
            limit: 返回的最大条目数量
            **kwargs: 其他过滤条件（兼容性保留）

        Returns:
            符合条件的记忆条目列表
        """
        select_fields = ", ".join(fields) if fields else "*"

        # 处理where条件列表
        where_conditions = list(where) if where else []

        # 兼容旧的kwargs格式，转换为简单的等值条件
        for key in kwargs:
            where_conditions.append(f"{key} = ?")

        # 构建WHERE子句
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # 处理参数值（只处理kwargs中的值，where列表中的值已经是字面量）
        values: list[Any] = list(kwargs.values())

        # 处理LIMIT
        if limit is not None:
            values.append(limit)
            limit_clause = "LIMIT ?"
        else:
            limit_clause = ""

        # 处理ORDER BY
        order_clause = f"ORDER BY {order_by}" if order_by else ""

        # 组装查询
        query_parts = [
            f"SELECT {select_fields}",
            f"FROM {self._table_name}",
            where_clause,
            order_clause,
            limit_clause
        ]
        query = " ".join(filter(None, query_parts))

        async with self._connection.execute(query, values) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return [
            self._memory_cls.from_dict(dict(zip(columns, row)))  # type: ignore[misc]
            for row in rows
        ]
