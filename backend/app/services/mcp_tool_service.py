"""MCP工具服务 - 统一管理MCP工具的注入和执行"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import json
from datetime import datetime

from app.models.mcp_plugin import MCPPlugin
from app.mcp.registry import mcp_registry
from app.logger import get_logger

logger = get_logger(__name__)


class MCPToolServiceError(Exception):
    """MCP工具服务异常"""
    pass


class MCPToolService:
    """MCP工具服务 - 统一管理MCP工具的注入和执行"""
    
    def __init__(self):
        self._tool_cache = {}  # 工具定义缓存
        self._result_cache = {}  # 工具结果缓存（可选）
    
    async def get_user_enabled_tools(
        self,
        user_id: str,
        db_session: AsyncSession,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取用户启用的MCP工具列表
        
        Args:
            user_id: 用户ID
            db_session: 数据库会话
            category: 工具类别筛选（search/analysis/filesystem等）
        
        Returns:
            工具定义列表，格式符合OpenAI Function Calling规范
        """
        try:
            # 1. 查询用户启用的插件（enabled=True即可，不强制要求status=active）
            # 因为新启用的插件status可能还是inactive，需要给它机会被调用
            query = select(MCPPlugin).where(
                MCPPlugin.user_id == user_id,
                MCPPlugin.enabled == True
            )
            
            if category:
                query = query.where(MCPPlugin.category == category)
            
            result = await db_session.execute(query)
            plugins = result.scalars().all()
            
            if not plugins:
                logger.info(f"用户 {user_id} 没有启用的MCP插件")
                return []
            
            # 2. 获取所有工具定义
            all_tools = []
            for plugin in plugins:
                try:
                    # 确保插件已加载到注册表
                    if not mcp_registry.get_client(user_id, plugin.plugin_name):
                        logger.info(f"插件 {plugin.plugin_name} 未加载，尝试加载...")
                        success = await mcp_registry.load_plugin(plugin)
                        if not success:
                            logger.warning(f"插件 {plugin.plugin_name} 加载失败，跳过")
                            continue
                    
                    # 从registry获取该插件的工具列表
                    plugin_tools = await mcp_registry.get_plugin_tools(
                        user_id=user_id,
                        plugin_name=plugin.plugin_name
                    )
                    
                    # 格式化为Function Calling格式
                    formatted_tools = self._format_tools_for_ai(
                        plugin_tools,
                        plugin.plugin_name  # ✅ 修复：使用正确的属性名plugin_name
                    )
                    all_tools.extend(formatted_tools)
                    
                    logger.info(
                        f"从插件 {plugin.plugin_name} 加载了 "
                        f"{len(formatted_tools)} 个工具"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"获取插件 {plugin.plugin_name} 的工具失败: {e}",
                        exc_info=True
                    )
                    continue
            
            logger.info(f"用户 {user_id} 共加载 {len(all_tools)} 个MCP工具")
            return all_tools
            
        except Exception as e:
            logger.error(f"获取用户MCP工具失败: {e}", exc_info=True)
            raise MCPToolServiceError(f"获取MCP工具失败: {str(e)}")
    
    def _format_tools_for_ai(
        self,
        plugin_tools: List[Dict[str, Any]],
        plugin_name: str
    ) -> List[Dict[str, Any]]:
        """
        将MCP工具定义格式化为AI Function Calling格式
        
        Args:
            plugin_tools: MCP插件的工具列表
            plugin_name: 插件名称
        
        Returns:
            格式化后的工具列表
        """
        formatted_tools = []
        
        for tool in plugin_tools:
            formatted_tool = {
                "type": "function",
                "function": {
                    "name": f"{plugin_name}_{tool['name']}",  # 加插件前缀避免冲突
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            formatted_tools.append(formatted_tool)
        
        return formatted_tools
    
    async def execute_tool_calls(
        self,
        user_id: str,
        tool_calls: List[Dict[str, Any]],
        db_session: AsyncSession,
        timeout: float = 60.0
    ) -> List[Dict[str, Any]]:
        """
        批量执行AI请求的工具调用（并行执行）
        
        Args:
            user_id: 用户ID
            tool_calls: AI返回的工具调用列表
            db_session: 数据库会话
            timeout: 单个工具调用的超时时间（秒，默认30秒）
        
        Returns:
            工具调用结果列表
        """
        if not tool_calls:
            return []
        
        logger.info(f"开始执行 {len(tool_calls)} 个工具调用")
        
        # 创建异步任务列表
        tasks = [
            self._execute_single_tool(
                user_id=user_id,
                tool_call=tool_call,
                db_session=db_session,
                timeout=timeout
            )
            for tool_call in tool_calls
        ]
        
        # 并行执行所有工具调用
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        formatted_results = []
        for i, result in enumerate(results):
            tool_call = tool_calls[i]
            
            if isinstance(result, Exception):
                # 工具调用异常
                formatted_results.append({
                    "tool_call_id": tool_call.get("id", f"call_{i}"),
                    "role": "tool",
                    "name": tool_call["function"]["name"],
                    "content": f"工具调用失败: {str(result)}",
                    "success": False,
                    "error": str(result)
                })
            else:
                formatted_results.append(result)
        
        return formatted_results
    
    async def _execute_single_tool(
        self,
        user_id: str,
        tool_call: Dict[str, Any],
        db_session: AsyncSession,
        timeout: float
    ) -> Dict[str, Any]:
        """
        执行单个工具调用
        
        Args:
            user_id: 用户ID
            tool_call: 工具调用信息
            db_session: 数据库会话
            timeout: 超时时间
        
        Returns:
            工具调用结果
        """
        tool_call_id = tool_call.get("id", "unknown")
        function_name = tool_call["function"]["name"]
        
        try:
            # 解析插件名和工具名
            if "_" in function_name:
                plugin_name, tool_name = function_name.split("_", 1)
            else:
                raise ValueError(f"无效的工具名称格式: {function_name}")
            
            # 解析参数
            arguments_str = tool_call["function"]["arguments"]
            if isinstance(arguments_str, str):
                arguments = json.loads(arguments_str)
            else:
                arguments = arguments_str
            
            logger.info(
                f"执行工具: {plugin_name}.{tool_name}, "
                f"参数: {arguments}"
            )
            
            # 设置超时
            try:
                result = await asyncio.wait_for(
                    mcp_registry.call_tool(
                        user_id=user_id,
                        plugin_name=plugin_name,
                        tool_name=tool_name,
                        arguments=arguments
                    ),
                    timeout=timeout
                )
                
                # 成功返回
                return {
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(result, ensure_ascii=False),
                    "success": True,
                    "error": None
                }
                
            except asyncio.TimeoutError:
                raise MCPToolServiceError(
                    f"工具调用超时（>{timeout}秒）"
                )
        
        except Exception as e:
            logger.error(
                f"工具 {function_name} 调用失败: {e}",
                exc_info=True
            )
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": function_name,
                "content": f"工具调用失败: {str(e)}",
                "success": False,
                "error": str(e)
            }
    
    async def build_tool_context(
        self,
        tool_results: List[Dict[str, Any]],
        format: str = "markdown"
    ) -> str:
        """
        将工具调用结果格式化为上下文文本
        
        Args:
            tool_results: 工具调用结果列表
            format: 输出格式（markdown/json/plain）
        
        Returns:
            格式化的上下文字符串
        """
        if not tool_results:
            return ""
        
        if format == "markdown":
            return self._build_markdown_context(tool_results)
        elif format == "json":
            return json.dumps(tool_results, ensure_ascii=False, indent=2)
        else:  # plain
            return self._build_plain_context(tool_results)
    
    def _build_markdown_context(
        self,
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """构建Markdown格式的工具上下文"""
        lines = ["## 🔧 工具调用结果\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("name", "unknown")
            success = result.get("success", False)
            content = result.get("content", "")
            
            status_emoji = "✅" if success else "❌"
            lines.append(f"### {status_emoji} {i}. {tool_name}\n")
            
            if success:
                # 尝试美化JSON内容
                try:
                    content_obj = json.loads(content)
                    content = json.dumps(content_obj, ensure_ascii=False, indent=2)
                except:
                    pass
                lines.append(f"```json\n{content}\n```\n")
            else:
                lines.append(f"**错误**: {content}\n")
        
        return "\n".join(lines)
    
    def _build_plain_context(
        self,
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """构建纯文本格式的工具上下文"""
        lines = ["=== 工具调用结果 ===\n"]
        
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("name", "unknown")
            success = result.get("success", False)
            content = result.get("content", "")
            
            status = "成功" if success else "失败"
            lines.append(f"{i}. {tool_name} - {status}")
            lines.append(f"   结果: {content}\n")
        
        return "\n".join(lines)


# 全局单例
mcp_tool_service = MCPToolService()