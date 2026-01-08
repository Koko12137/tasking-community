from typing import Any

from aiosqlite import Connection, connect
from pymilvus import AsyncMilvusClient, DataType

from ..database.interface import ISqlDBManager, IVectorDBManager


STATE = """
CREATE TABLE IF NOT EXISTS state_memory (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    raw_data TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
)
"""


class BaseStateService(ISqlDBManager[Connection]):
    _connection: Connection
    _is_initialized: bool
    
    def __init__(self, workspace: str) -> None:
        # Initialize the database connection for the given workspace
        self._connection = connect(f"{workspace}/state.sqlite")
        # Set initialization flag
        self._is_initialized = False

    async def get_sql_database(self, context: dict[str, Any]) -> Connection:
        if not self._is_initialized:
            # Check if the table exists, if not create it
            exists = await self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='state_memory';"
            )
            if not await exists.fetchone():
                # Perform any necessary initialization here
                await self._connection.execute(STATE)
                await self._connection.commit()

            # Mark as initialized
            self._is_initialized = True
        return self._connection

    async def close(self, context: dict[str, Any]) -> None:
        # Close the database connection
        await self._connection.close()


class BaseEpisodeService(IVectorDBManager[AsyncMilvusClient]):
    _milvus: AsyncMilvusClient
    _is_initialized: bool
    
    def __init__(self, workspace: str) -> None:
        # Initialize the Milvus client for the given workspace
        self._milvus = AsyncMilvusClient(f"{workspace}/state.milvus")
        # Set initialization flag
        self._is_initialized = False
    
    async def get_vector_database(self, context: dict[str, Any]) -> AsyncMilvusClient:
        if not self._is_initialized:
            # Perform any necessary initialization here
            # For example, check if the collection exists, if not create it
            exists = await self._milvus.has_collection("state_memory")
            
            if not exists:
                # Create a schema
                schema = await self._milvus.create_schema()
                schema.add_field("id", DataType.VARCHAR, is_primary=True)
                schema.add_field("task_id", DataType.VARCHAR)
                schema.add_field("content", DataType.VARCHAR, max_length=65535)
                schema.add_field("timestamp", DataType.TIMESTAMPTZ)
                schema.add_field("dense", DataType.FLOAT_VECTOR, dim=2048)
                await self._milvus.create_collection(
                    "state_memory", 
                    2048,
                    primary_field_name="id",
                    schema=schema,
                )
                # Load the collection into memory
                await self._milvus.load_collection("state_memory")
            
            # Mark as initialized
            self._is_initialized = True
        return self._milvus
