"""SQLite记忆存储实现模块"""
import json
from dataclasses import dataclass
from typing import Any

import aiosqlite

from .interface import ISqlDatabase,ISqlDBManager
from ..model import MemoryT, MultimodalContent, TextBlock, ImageBlock, VideoBlock


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
            timeout: 超时时间（秒），默认1800秒，目前 sqlite 不支持
        """
        memory_dict = memory.to_dict()

        # 处理多模态内容，参考 Milvus 的实现
        memory_dict = self._serialize_content(memory_dict)

        columns = ", ".join(memory_dict.keys())
        placeholders = ", ".join("?" for _ in memory_dict.keys())
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
        async with connection.execute(query, values) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return [
            self._process_row(dict(zip(columns, row)))
            for row in rows
        ]

    def _build_search_query(self, params: SearchParams, **kwargs: Any) -> tuple[str, list[Any]]:
        """构建搜索查询SQL语句和参数

        Args:
            params: 搜索参数对象
            **kwargs: 额外的SQL参数，支持: group_by, having, offset

        Returns:
            SQL查询字符串和参数列表的元组
        """
        select_fields = ", ".join(params.fields) if params.fields else "*"

        # 处理where条件列表
        where_conditions = list(params.where) if params.where else []

        # 构建WHERE子句
        where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""

        # 处理参数值列表
        values = []

        # 处理ORDER BY
        order_clause = f"ORDER BY {params.order_by}" if params.order_by else ""

        # 处理GROUP BY
        group_by_clause = f"GROUP BY {kwargs['group_by']}" if kwargs.get('group_by') else ""

        # 处理HAVING
        having_clause = f"HAVING {kwargs['having']}" if kwargs.get('having') else ""

        # 处理LIMIT和OFFSET
        limit_parts = []
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

        return self._memory_cls.from_dict(row_dict)  # type: ignore[misc]

    def _deserialize_content(self, content: Any) -> list[MultimodalContent]:
        """反序列化内容。

        如果 content 是 JSON 字符串且表示列表，解析为列表。
        如果无法解析，返回包含该内容的 TextBlock 列表。

        Args:
            content: 存储的内容

        Returns:
            反序列化后的多模态内容
        """
        if isinstance(content, str):
            # 尝试解析为 JSON（多模态内容）
            if content.startswith("[") and content.endswith("]"):
                try:
                    parsed: list[dict[str, Any]] = json.loads(content)
                    # 将字典列表转换为 MultimodalContent 对象列表
                    multimodal_contents: list[MultimodalContent] = []
                    for item in parsed:
                        if item.get("type") == "text":
                            multimodal_contents.append(TextBlock(text=item.get("text", "")))
                        elif item.get("type") == "image_url":
                            multimodal_contents.append(ImageBlock(
                                image_url=item.get("image_url", ""),
                                image_base64=item.get("image_base64", ""),
                                image_type=item.get("image_type", "jpeg"),
                                detail=item.get("detail", "low")
                            ))
                        elif item.get("type") == "video_url":
                            multimodal_contents.append(VideoBlock(
                                video_url=item.get("video_url", ""),
                                video_base64=item.get("video_base64", ""),
                                video_type=item.get("video_type", "mp4"),
                                fps=item.get("fps", 1)
                            ))
                        return multimodal_contents
                except (json.JSONDecodeError, ValueError):
                    pass
            # 无法解析为 JSON，返回包含原内容的 TextBlock
            return [TextBlock(text=content)]

        # 非字符串类型，转换为字符串并返回 TextBlock
        if content:
            return [TextBlock(text=str(content))]

        # 空内容返回空列表
        return []

    def _serialize_content(self, memory_dict: dict[str, Any]) -> dict[str, Any]:
        """序列化多模态内容为 JSON 字符串。

        如果 content 是列表（多模态），转换为 JSON 字符串以便存储。

        Args:
            memory_dict: 数据库字典

        Returns:
            处理后的数据库字典
        """
        content: list[MultimodalContent] | None = memory_dict.get("content")
        if content is None:
            raise ValueError("Memory dictionary must contain 'content' field.")
        # 将 content 的每一个元素转换为字典表示
        content_list: list[dict[str, Any]] = []
        for item in content:
            content_list.append(item.model_dump())
        memory_dict["content"] = json.dumps(content_list, ensure_ascii=False)
        return memory_dict
