"""MCP插件注册表 - 管理运行时插件实例"""
import asyncio
import time
import httpx
from typing import Dict, Optional, Any, List, Tuple
from collections import OrderedDict
from app.mcp.http_client import HTTPMCPClient, MCPError
from app.models.mcp_plugin import MCPPlugin
from app.logger import get_logger

logger = get_logger(__name__)


class MCPPluginRegistry:
    """MCP插件注册表 - 管理运行时插件实例（多用户优化版）"""
    
    def __init__(self, max_clients: int = 1000, client_ttl: int = 3600):
        """
        初始化注册表
        
        Args:
            max_clients: 最大缓存客户端数量
            client_ttl: 客户端过期时间（秒），默认1小时
        """
        # 存储格式: {plugin_id: (client, last_access_time)}
        self._clients: OrderedDict[str, Tuple[HTTPMCPClient, float]] = OrderedDict()
        
        # 细粒度锁：每个用户一个锁
        self._user_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # 保护locks字典本身
        
        # 配置参数
        self._max_clients = max_clients
        self._client_ttl = client_ttl
        
        # 共享HTTP客户端池（用于所有MCP HTTP请求）
        self._shared_http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=100,
                max_connections=200,
                keepalive_expiry=30.0
            ),
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0),
            headers={
                "User-Agent": "MuMuAINovel-MCP-Client/1.0"
            }
        )
        
        # 启动后台清理任务
        self._cleanup_task = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ MCP插件注册表后台清理任务已启动")
    
    async def _cleanup_loop(self):
        """后台清理过期客户端"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await self._cleanup_expired_clients()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务异常: {e}")
    
    async def _cleanup_expired_clients(self):
        """清理过期的客户端"""
        now = time.time()
        expired_ids = []
        
        # 收集过期的plugin_id
        for plugin_id, (client, last_access) in list(self._clients.items()):
            if now - last_access > self._client_ttl:
                expired_ids.append(plugin_id)
        
        if expired_ids:
            logger.info(f"🧹 清理 {len(expired_ids)} 个过期的MCP客户端")
            for plugin_id in expired_ids:
                # 提取user_id来获取对应的锁
                user_id = plugin_id.split(':', 1)[0]
                user_lock = await self._get_user_lock(user_id)
                
                async with user_lock:
                    if plugin_id in self._clients:
                        await self._unload_plugin_unsafe(plugin_id)
    
    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """
        获取用户专属的锁（细粒度锁）
        
        Args:
            user_id: 用户ID
            
        Returns:
            该用户的锁对象
        """
        async with self._locks_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]
    
    def _touch_client(self, plugin_id: str):
        """
        更新客户端的最后访问时间（LRU）
        
        Args:
            plugin_id: 插件ID
        """
        if plugin_id in self._clients:
            client, _ = self._clients[plugin_id]
            self._clients[plugin_id] = (client, time.time())
            # 移到末尾（LRU）
            self._clients.move_to_end(plugin_id)
    
    async def _evict_lru_client(self):
        """驱逐最久未使用的客户端（当达到max_clients限制时）"""
        if len(self._clients) >= self._max_clients:
            # 获取最旧的plugin_id
            oldest_id = next(iter(self._clients))
            logger.info(f"📤 达到最大客户端数量限制，驱逐: {oldest_id}")
            await self._unload_plugin_unsafe(oldest_id)
    
    async def load_plugin(self, plugin: MCPPlugin) -> bool:
        """
        从配置加载插件
        
        Args:
            plugin: 插件配置
            
        Returns:
            是否加载成功
        """
        # 使用细粒度锁（只锁定当前用户）
        user_lock = await self._get_user_lock(plugin.user_id)
        async with user_lock:
            try:
                plugin_id = f"{plugin.user_id}:{plugin.plugin_name}"
                
                # 如果已加载，先卸载
                if plugin_id in self._clients:
                    await self._unload_plugin_unsafe(plugin_id)
                
                # 检查是否需要驱逐LRU客户端
                await self._evict_lru_client()
                
                # 目前只支持HTTP类型
                if plugin.plugin_type == "http":
                    if not plugin.server_url:
                        logger.error(f"HTTP插件缺少server_url: {plugin.plugin_name}")
                        return False
                    
                    # 使用共享HTTP连接池创建客户端
                    client = HTTPMCPClient(
                        url=plugin.server_url,
                        headers=plugin.headers or {},
                        env=plugin.env or {},
                        timeout=plugin.config.get('timeout', 60.0) if plugin.config else 60.0,
                        http_client=self._shared_http_client  # 传入共享连接池
                    )
                    
                    # 存储客户端和当前时间戳
                    self._clients[plugin_id] = (client, time.time())
                    logger.info(f"✅ 加载MCP插件: {plugin_id}")
                    return True
                else:
                    logger.warning(f"暂不支持的插件类型: {plugin.plugin_type}")
                    return False
                    
            except Exception as e:
                logger.error(f"加载插件失败 {plugin.plugin_name}: {e}")
                return False
    
    async def unload_plugin(self, user_id: str, plugin_name: str):
        """
        卸载插件
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
        """
        # 使用细粒度锁（只锁定当前用户）
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            plugin_id = f"{user_id}:{plugin_name}"
            await self._unload_plugin_unsafe(plugin_id)
    
    async def _unload_plugin_unsafe(self, plugin_id: str):
        """卸载插件（不加锁，内部使用）"""
        if plugin_id in self._clients:
            client, _ = self._clients[plugin_id]  # 解包 (client, timestamp)
            try:
                await client.close()
            except Exception as e:
                logger.error(f"关闭插件客户端失败 {plugin_id}: {e}")
            
            del self._clients[plugin_id]
            logger.info(f"卸载MCP插件: {plugin_id}")
    
    async def reload_plugin(self, plugin: MCPPlugin) -> bool:
        """
        重新加载插件
        
        Args:
            plugin: 插件配置
            
        Returns:
            是否重载成功
        """
        await self.unload_plugin(plugin.user_id, plugin.plugin_name)
        return await self.load_plugin(plugin)
    
    def get_client(self, user_id: str, plugin_name: str) -> Optional[HTTPMCPClient]:
        """
        获取插件客户端（支持LRU访问时间更新）
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            
        Returns:
            客户端实例或None
        """
        plugin_id = f"{user_id}:{plugin_name}"
        entry = self._clients.get(plugin_id)
        if entry:
            # 更新访问时间（LRU）
            self._touch_client(plugin_id)
            return entry[0]  # 返回客户端对象
        return None
    
    async def call_tool(
        self,
        user_id: str,
        plugin_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        调用插件工具
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
            
        Raises:
            ValueError: 插件不存在或未启用
            MCPError: 工具调用失败
        """
        client = self.get_client(user_id, plugin_name)
        
        if not client:
            raise ValueError(f"插件未加载: {plugin_name}")
        
        try:
            result = await client.call_tool(tool_name, arguments)
            logger.info(f"✅ 工具调用成功: {plugin_name}.{tool_name}")
            # logger.info(f"✅ 工具返回内容: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ 工具调用失败: {plugin_name}.{tool_name}, 错误: {e}")
            raise
    
    async def get_plugin_tools(
        self,
        user_id: str,
        plugin_name: str
    ) -> List[Dict[str, Any]]:
        """
        获取插件的工具列表
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            
        Returns:
            工具列表
        """
        client = self.get_client(user_id, plugin_name)
        
        if not client:
            raise ValueError(f"插件未加载: {plugin_name}")
        
        try:
            tools = await client.list_tools()
            return tools
        except Exception as e:
            logger.error(f"获取工具列表失败: {plugin_name}, 错误: {e}")
            raise
    
    async def test_plugin(
        self,
        user_id: str,
        plugin_name: str
    ) -> Dict[str, Any]:
        """
        测试插件连接
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            
        Returns:
            测试结果
        """
        client = self.get_client(user_id, plugin_name)
        
        if not client:
            raise ValueError(f"插件未加载: {plugin_name}")
        
        return await client.test_connection()
    
    async def cleanup_all(self):
        """清理所有插件和资源"""
        # 停止后台清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 清理所有客户端
        plugin_ids = list(self._clients.keys())
        for plugin_id in plugin_ids:
            user_id = plugin_id.split(':', 1)[0]
            user_lock = await self._get_user_lock(user_id)
            async with user_lock:
                await self._unload_plugin_unsafe(plugin_id)
        
        # 关闭共享HTTP客户端
        try:
            await self._shared_http_client.aclose()
        except Exception as e:
            logger.error(f"关闭共享HTTP客户端失败: {e}")
        
        logger.info("✅ 已清理所有MCP插件和资源")


# 全局注册表实例
mcp_registry = MCPPluginRegistry()