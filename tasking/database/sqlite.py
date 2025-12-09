"""SQLite记忆存储实现模块"""
from dataclasses import dataclass
from typing import Any

import aiosqlite

from .interface import ISqlDatabase,ISqlDBManager
from ..model import MemoryT


@dataclass
class SearchParams:
    """搜索参数封装类"""
    fields: list[str] | None = None
    where: list[str] | None = None
    order_by: str | None = None
    limit: int | None = None
    filters: dict[str, Any] | None = None


class SqliteDatabase(ISqlDatabase[MemoryT]):
    """SQLite数据库实现类，基于SQLite数据库进行记忆存储和检索"""
    _manager: ISqlDBManager[aiosqlite.Connection]
    _connection: aiosqlite.Connection
    _table_name: str
    _memory_cls: type[MemoryT]

    def __init__(
        self,
        manager: ISqlDBManager[aiosqlite.Connection],
        table_name: str,
        memory_cls: type[MemoryT],
    ) -> None:
        """初始化SQLite记忆实例

        Args:
            connection: SQLite异步连接实例
            table_name: 数据表名称
            memory_cls: 记忆对象类型
        """
        self._manager = manager
        self._table_name = table_name
        self._memory_cls = memory_cls

    async def add(self, context: dict[str, Any], memory: MemoryT) -> None:
        """添加记忆到SQLite数据库

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
        """
        memory_dict = memory.to_dict()
        columns = ", ".join(memory_dict.keys())
        placeholders = ", ".join("?" for _ in memory_dict)
        values = list(memory_dict.values())

        query = f"INSERT INTO {self._table_name} ({columns}) VALUES ({placeholders})"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        await connection.execute(query, values)
        await connection.commit()

    async def delete(self, context: dict[str, Any], memory_id: str) -> None:
        """从SQLite数据库中删除记忆

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory_id: 记忆的唯一标识符
        """
        query = f"DELETE FROM {self._table_name} WHERE id = ?"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        await connection.execute(query, (memory_id,))
        await connection.commit()

    async def update(self, context: dict[str, Any], memory: MemoryT) -> None:
        """更新SQLite数据库中的记忆"""
        memory_dict = memory.to_dict()
        memory_id = memory_dict.pop("id")
        set_clause = ", ".join(f"{key} = ?" for key in memory_dict.keys())
        values = list(memory_dict.values()) + [memory_id]

        query = f"UPDATE {self._table_name} SET {set_clause} WHERE id = ?"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        await connection.execute(query, values)
        await connection.commit()

    async def search(
        self,
        context: dict[str, Any],
        fields: list[str] | None = None,
        where: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        **kwargs: Any
    ) -> list[MemoryT]:
        """在SQLite数据库中搜索记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            fields: 要查询的字段列表，如果为None则查询所有字段(*)
            where: WHERE过滤条件列表，每个条件为完整的SQL表达式，如 ["status = 'active'", "created_at > '2024-01-01'"]
            order_by: 排序字段，支持ASC/DESC，如 "id DESC"
            limit: 返回的最大条目数量
            **kwargs: 其他过滤条件（兼容性保留）

        Returns:
            符合条件的记忆条目列表
        """
        # 封装搜索参数
        params = SearchParams(
            fields=fields,
            where=where,
            order_by=order_by,
            limit=limit,
            filters=kwargs if kwargs else None
        )

        # 构建查询和参数
        query, values = self._build_search_query(params)

        # 获取SQLite连接并执行查询
        connection = await self._manager.get_sql_database(context)
        async with connection.execute(query, values) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return [
            self._memory_cls.from_dict(dict(zip(columns, row)))  # type: ignore[misc]
            for row in rows
        ]

    def _build_search_query(self, params: SearchParams) -> tuple[str, list[Any]]:
        """构建搜索查询SQL语句和参数

        Args:
            params: 搜索参数对象

        Returns:
            SQL查询字符串和参数列表的元组
        """
        select_fields = ", ".join(params.fields) if params.fields else "*"

        # 处理where条件列表
        where_conditions = list(params.where) if params.where else []

        # 兼容旧的kwargs格式，转换为简单的等值条件
        filters = params.filters or {}
        for key in filters:
            where_conditions.append(f"{key} = ?")

        # 构建WHERE子句
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # 处理参数值（只处理filters中的值，where列表中的值已经是字面量）
        values = list(filters.values())

        # 处理LIMIT
        if params.limit is not None:
            values.append(params.limit)
            limit_clause = "LIMIT ?"
        else:
            limit_clause = ""

        # 处理ORDER BY
        order_clause = f"ORDER BY {params.order_by}" if params.order_by else ""

        # 组装查询
        query_parts = [
            f"SELECT {select_fields}",
            f"FROM {self._table_name}",
            where_clause,
            order_clause,
            limit_clause
        ]
        query = " ".join(filter(None, query_parts))

        return query, values
