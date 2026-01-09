"""MCP插件状态同步服务

将内存中的会话状态变更同步到数据库，确保状态一致性。
"""

from typing import Dict, Any
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.mcp_plugin import MCPPlugin
from app.logger import get_logger

logger = get_logger(__name__)


async def sync_status_to_db(event: Dict[str, Any]):
    """
    状态变更回调 - 同步到数据库
    """
    user_id = event["user_id"]
    plugin_name = event["plugin_name"]
    new_status = event["new_status"]
    reason = event.get("reason", "")
    
    try:
        from app.database import get_engine
        
        engine = await get_engine(user_id)
        AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with AsyncSessionLocal() as db:
            stmt = (
                update(MCPPlugin)
                .where(MCPPlugin.user_id == user_id, MCPPlugin.plugin_name == plugin_name)
                .values(status=new_status, last_error=reason if new_status == "error" else None)
            )
            await db.execute(stmt)
            await db.commit()
            
            logger.debug(f"✅ 状态已同步到数据库: {plugin_name} -> {new_status}")
            
    except Exception as e:
        logger.error(f"❌ 状态同步失败: {plugin_name}, 错误: {e}")


def register_status_sync():
    """注册状态同步回调到MCP客户端"""
    from app.mcp import mcp_client
    mcp_client.register_status_callback(sync_status_to_db)
    logger.info("✅ MCP状态同步服务已注册")