"""HTTP MCP客户端 - 实现JSON-RPC 2.0协议"""
import httpx
from typing import Dict, Any, List, Optional
from app.logger import get_logger
import time

logger = get_logger(__name__)


class MCPError(Exception):
    """MCP错误"""
    pass


class HTTPMCPClient:
    """HTTP模式MCP客户端（类似Cursor/Claude Code实现）"""
    
    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        http_client: Optional[httpx.AsyncClient] = None
    ):
        """
        初始化HTTP MCP客户端
        
        Args:
            url: MCP服务器URL
            headers: HTTP请求头
            env: 环境变量（用于API Key等）
            timeout: 超时时间（秒）
            http_client: 可选的共享HTTP客户端（用于连接池复用）
        """
        self.url = url.rstrip('/')
        self.headers = headers or {}
        self.env = env or {}
        self.timeout = timeout
        
        # 设置MCP必需的Accept头
        # MCP服务器要求客户端必须接受 application/json 和 text/event-stream
        if 'Accept' not in self.headers:
            self.headers['Accept'] = 'application/json, text/event-stream'
        
        # 设置Content-Type
        if 'Content-Type' not in self.headers:
            self.headers['Content-Type'] = 'application/json'
        
        # 如果env中有API Key，添加到headers
        if 'API_KEY' in self.env:
            self.headers['Authorization'] = f'Bearer {self.env["API_KEY"]}'
        
        # 使用共享客户端或创建新客户端
        self._owns_client = http_client is None
        if http_client:
            self.client = http_client
        else:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                headers=self.headers
            )
        self._request_id = 0
    
    def _next_request_id(self) -> int:
        """获取下一个请求ID"""
        self._request_id += 1
        return self._request_id
    
    async def _call_jsonrpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用JSON-RPC 2.0方法
        
        Args:
            method: 方法名
            params: 参数
            
        Returns:
            响应结果
            
        Raises:
            MCPError: 调用失败时抛出
        """
        request_id = self._next_request_id()
        
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            logger.debug(f"MCP请求: {method} -> {self.url}")
            
            response = await self.client.post(
                self.url,
                json=payload,
                headers=self.headers  # 显式传递headers（对于共享客户端很重要）
            )
            
            response.raise_for_status()
            
            # 获取响应内容
            response_text = response.text
            content_type = response.headers.get('content-type', '')
            
            # 如果是空响应
            if not response_text or response_text.strip() == '':
                raise MCPError("服务器返回空响应")
            
            # 处理SSE格式响应
            if 'text/event-stream' in content_type or response_text.startswith('event:'):
                logger.debug("检测到SSE格式响应，开始解析")
                data = self._parse_sse_response(response_text)
            else:
                # 标准JSON响应
                try:
                    data = response.json()
                except ValueError as e:
                    logger.error(f"JSON解析失败，响应内容: {response_text[:500]}")
                    raise MCPError(f"无法解析JSON响应: {str(e)}")
            
            # 检查JSON-RPC错误
            if "error" in data:
                error = data["error"]
                error_msg = error.get("message", "Unknown error")
                error_code = error.get("code", -1)
                logger.error(f"MCP错误 [{error_code}]: {error_msg}")
                raise MCPError(f"[{error_code}] {error_msg}")
            
            if "result" not in data:
                raise MCPError("响应中缺少result字段")
            
            return data["result"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP错误 {e.response.status_code}: {e.response.text}")
            raise MCPError(f"HTTP错误 {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"请求错误: {str(e)}")
            raise MCPError(f"请求错误: {str(e)}")
        except MCPError:
            raise
        except Exception as e:
            logger.error(f"未知错误: {str(e)}")
            raise MCPError(f"未知错误: {str(e)}")
    
    def _parse_sse_response(self, sse_text: str) -> Dict[str, Any]:
        """
        解析SSE格式的响应
        
        SSE格式示例:
        event: message
        data: {"result": {...}}
        
        Args:
            sse_text: SSE格式的文本
            
        Returns:
            解析后的JSON数据
        """
        import json
        
        lines = sse_text.strip().split('\n')
        data_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('data:'):
                # 提取data后面的内容
                data_content = line[5:].strip()
                data_lines.append(data_content)
        
        if not data_lines:
            raise MCPError("SSE响应中没有找到data字段")
        
        # 合并所有data行（某些SSE可能分多行）
        full_data = ''.join(data_lines)
        
        try:
            return json.loads(full_data)
        except json.JSONDecodeError as e:
            logger.error(f"解析SSE data失败: {full_data[:200]}")
            raise MCPError(f"SSE data不是有效的JSON: {str(e)}")
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        列举可用工具
        
        Returns:
            工具列表
        """
        try:
            result = await self._call_jsonrpc("tools/list")
            tools = result.get("tools", [])
            logger.info(f"获取到 {len(tools)} 个工具")
            return tools
        except Exception as e:
            logger.error(f"获取工具列表失败: {e}")
            raise
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        try:
            logger.info(f"调用工具: {tool_name}")
            logger.debug(f"参数: {arguments}")
            
            result = await self._call_jsonrpc(
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments
                }
            )
            
            # MCP返回的result通常包含content数组
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    # 提取第一个content项的text
                    first_content = content[0]
                    if isinstance(first_content, dict) and "text" in first_content:
                        return first_content["text"]
                    return first_content
                return content
            
            return result
            
        except Exception as e:
            logger.error(f"调用工具失败: {tool_name}, 错误: {e}")
            raise
    
    async def list_resources(self) -> List[Dict[str, Any]]:
        """
        列举可用资源
        
        Returns:
            资源列表
        """
        try:
            result = await self._call_jsonrpc("resources/list")
            resources = result.get("resources", [])
            logger.info(f"获取到 {len(resources)} 个资源")
            return resources
        except Exception as e:
            logger.error(f"获取资源列表失败: {e}")
            raise
    
    async def read_resource(self, uri: str) -> Any:
        """
        读取资源
        
        Args:
            uri: 资源URI
            
        Returns:
            资源内容
        """
        try:
            result = await self._call_jsonrpc(
                "resources/read",
                {"uri": uri}
            )
            return result
        except Exception as e:
            logger.error(f"读取资源失败: {uri}, 错误: {e}")
            raise
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接
        
        Returns:
            测试结果
        """
        start_time = time.time()
        
        try:
            # 尝试列举工具来测试连接
            tools = await self.list_tools()
            
            end_time = time.time()
            response_time = round((end_time - start_time) * 1000, 2)
            
            return {
                "success": True,
                "message": "连接测试成功",
                "response_time_ms": response_time,
                "tools_count": len(tools),
                "tools": tools
            }
        except MCPError as e:
            end_time = time.time()
            response_time = round((end_time - start_time) * 1000, 2)
            
            return {
                "success": False,
                "message": "连接测试失败",
                "response_time_ms": response_time,
                "error": str(e),
                "error_type": "MCPError",
                "suggestions": [
                    "请检查服务器URL是否正确",
                    "请确认API Key是否有效",
                    "请检查网络连接"
                ]
            }
        except Exception as e:
            end_time = time.time()
            response_time = round((end_time - start_time) * 1000, 2)
            
            return {
                "success": False,
                "message": "连接测试失败",
                "response_time_ms": response_time,
                "error": str(e),
                "error_type": type(e).__name__,
                "suggestions": [
                    "请检查服务器是否在线",
                    "请确认配置是否正确"
                ]
            }
    
    async def close(self):
        """关闭客户端（仅在拥有客户端所有权时关闭）"""
        if self._owns_client and self.client:
            await self.client.aclose()