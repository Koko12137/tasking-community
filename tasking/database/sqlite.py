"""SQLite记忆存储实现模块"""
import asyncio
import json
from dataclasses import dataclass
from typing import Any, cast

import aiosqlite

from .interface import ISqlDatabase, ISqlDBManager
from ..model import MemoryT, TextBlock


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

    async def add(self, context: dict[str, Any], memory: MemoryT, timeout: float = 1800.0) -> None:
        """添加记忆到SQLite数据库

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒
        """
        memory_dict = memory.to_dict()

        # 处理多模态内容，参考 Milvus 的实现
        self._serialize_content(memory_dict)

        columns = ", ".join(memory_dict.keys())
        placeholders = ", ".join("?" for _ in memory_dict.keys())
        values = list(memory_dict.values())

        query = f"INSERT INTO {self._table_name} ({columns}) VALUES ({placeholders})"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        
        # 创建一个任务来执行插入操作
        async def insert_task() -> None:
            await connection.execute(query, values)
            await connection.commit()
        await asyncio.wait_for(insert_task(), timeout=timeout)

    async def delete(self, context: dict[str, Any], memory_id: str, timeout: float = 1800.0) -> None:
        """从SQLite数据库中删除记忆

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory_id: 记忆的唯一标识符
            timeout: 超时时间（秒），默认1800秒
        """
        query = f"DELETE FROM {self._table_name} WHERE id = ?"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        
        # 创建一个任务来执行删除操作
        async def delete_task() -> None:
            await connection.execute(query, (memory_id,))
            await connection.commit()
        await asyncio.wait_for(delete_task(), timeout=timeout)

    async def update(self, context: dict[str, Any], memory: MemoryT, timeout: float = 1800.0) -> None:
        """更新SQLite数据库中的记忆
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒
        """
        memory_dict = memory.to_dict()
        memory_id = memory_dict.pop("id")
        set_clause = ", ".join(f"{key} = ?" for key in memory_dict.keys())
        values = list(memory_dict.values()) + [memory_id]

        query = f"UPDATE {self._table_name} SET {set_clause} WHERE id = ?"
        # 获取SQLite连接
        connection = await self._manager.get_sql_database(context)
        
        # 创建一个任务来执行更新操作
        async def update_task() -> None:
            await connection.execute(query, values)
            await connection.commit()
        await asyncio.wait_for(update_task(), timeout=timeout)

    async def search(
        self,
        context: dict[str, Any],
        fields: list[str] | None = None,
        where: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        timeout: float = 1800.0,
        **kwargs: Any
    ) -> list[MemoryT]:
        """在SQLite数据库中搜索记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            fields: 要查询的字段列表，如果为None则查询所有字段(*)
            where: WHERE过滤条件列表，每个条件为完整的SQL表达式，如 ["status = 'active'", "created_at > '2024-01-01'"]
            order_by: 排序字段，支持ASC/DESC，如 "id DESC"
            limit: 返回的最大条目数量
            timeout: 超时时间（秒），默认1800秒
            **kwargs: 其他SQL参数，SQLite实现支持: group_by, having, offset

        Returns:
            符合条件的记忆条目列表
        """
        # 检查不支持的参数
        supported_kwargs = {"group_by", "having", "offset"}
        unsupported_kwargs = set(kwargs.keys()) - supported_kwargs
        if unsupported_kwargs:
            raise ValueError(
                f"SQLite implementation does not support the following parameters: "
                f"{', '.join(unsupported_kwargs)}. Supported parameters: {', '.join(supported_kwargs)}"
            )

        # 封装搜索参数
        params = SearchParams(
            fields=fields,
            where=where,
            order_by=order_by,
            limit=limit,
            filters=None  # 不再使用kwargs作为filters
        )

        # 构建查询和参数
        query, values = self._build_search_query(params, **kwargs)

        # 获取SQLite连接并执行查询
        connection = await self._manager.get_sql_database(context)
        
        # 创建一个任务来执行搜索操作
        async def search_task() -> list[MemoryT]:
            async with connection.execute(query, values) as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

            res = [
                self._process_row(dict(zip(columns, row)))
                for row in rows
            ]
            return res
        return await asyncio.wait_for(search_task(), timeout=timeout)

    def _build_search_query(self, params: SearchParams, **kwargs: Any) -> tuple[str, list[Any]]:
        """构建搜索查询SQL语句和参数

        Args:
            params: 搜索参数对象
            **kwargs: 额外的SQL参数，支持: group_by, having, offset

        Returns:
            SQL查询字符串和参数列表的元组
        """
        select_fields = ", ".join(params.fields) if params.fields else "*"

        # 处理where条件列表和filters字典
        where_conditions = list(params.where) if params.where else []
        values: list[Any] = []

        # 处理filters字典并转换为SQL条件
        if params.filters:
            for field, value in params.filters.items():
                where_conditions.append(f"{field} = ?")
                values.append(value)

        # 构建WHERE子句
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # 处理ORDER BY
        order_clause = f"ORDER BY {params.order_by}" if params.order_by else ""

        # 处理GROUP BY
        group_by_clause = f"GROUP BY {kwargs['group_by']}" if kwargs.get('group_by') else ""

        # 处理HAVING
        having_clause = f"HAVING {kwargs['having']}" if kwargs.get('having') else ""

        # 处理LIMIT和OFFSET
        limit_parts: list[str] = []
        if params.limit is not None:
            limit_parts.append(str(params.limit))
        if kwargs.get('offset') is not None:
            limit_parts.append(str(kwargs['offset']))

        limit_clause = f"LIMIT {', '.join(limit_parts)}" if limit_parts else ""

        # 组装查询
        query_parts = [
            f"SELECT {select_fields}",
            f"FROM {self._table_name}",
            where_clause,
            group_by_clause,
            having_clause,
            order_clause,
            limit_clause
        ]
        query = " ".join(filter(None, query_parts))

        return query, values

    def _process_row(self, row_dict: dict[str, Any]) -> MemoryT:
        """处理查询结果行，反序列化 content 字段。

        Args:
            row_dict: 数据库查询返回的行字典

        Returns:
            处理后的记忆对象
        """
        # 反序列化 content
        if "content" in row_dict:
            row_dict["content"] = self._deserialize_content(row_dict["content"])

        return cast(MemoryT, self._memory_cls.from_dict(row_dict))

    def _deserialize_content(self, content: Any) -> list[TextBlock]:
        """反序列化内容。

        如果 content 是 JSON 字符串且表示列表，解析为 TextBlock 列表。
        如果无法解析，返回包含该内容的 TextBlock 列表。

        Args:
            content: 存储的内容

        Returns:
            反序列化后的 TextBlock 列表
        """
        if isinstance(content, str):
            # 尝试解析为 JSON
            if content.startswith("[") and content.endswith("]"):
                try:
                    parsed: list[dict[str, Any]] = json.loads(content)
                    # 将字典列表转换为 TextBlock 对象列表
                    text_contents: list[TextBlock] = []
                    for item in parsed:
                        if item.get("type") == "text":
                            text_contents.append(TextBlock(text=item.get("text", "")))
                        else:
                            # 忽略非文本内容
                            continue
                    return text_contents
                except (json.JSONDecodeError, ValueError):
                    pass
            # 无法解析为 JSON
            if content:  # 非空字符串返回包含原内容的 TextBlock
                return [TextBlock(text=content)]
            return []  # 空字符串返回空列表

        # 非字符串类型，转换为字符串并返回 TextBlock
        if content:
            return [TextBlock(text=str(content))]

        # 空内容返回空列表
        return []

    def _serialize_content(self, memory_dict: dict[str, Any]) -> None:
        """序列化文本内容为 JSON 字符串。

        如果 content 是字符串，转换为单个 TextBlock；如果是列表，确保只包含 TextBlock。
        最终将转换为 JSON 字符串以便存储。

        Args:
            memory_dict: 数据库字典
        """
        content: list[TextBlock] | str | None = memory_dict.get("content")
        if content is None:
            raise ValueError("Memory dictionary must contain 'content' field.")

        # 确保只包含 TextBlock
        text_only_content: list[TextBlock] = []

        # 如果是字符串，直接转换为 TextBlock
        if isinstance(content, str):
            text_only_content.append(TextBlock(text=content))
        else:
            # 如果是列表，确保所有元素都是 TextBlock
            for item in content:
                if not isinstance(item, TextBlock): # pyright: ignore[reportUnnecessaryIsInstance]
                    raise ValueError("Only TextBlock content is supported")
                text_only_content.append(item)

        # 序列化为 JSON 字符串
        content_list: list[dict[str, Any]] = [block.model_dump() for block in text_only_content]
        memory_dict["content"] = json.dumps(content_list, ensure_ascii=False)
