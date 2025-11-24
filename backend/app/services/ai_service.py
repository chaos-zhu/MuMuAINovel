"""AI服务封装 - 统一的OpenAI和Claude接口"""
from typing import Optional, AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from app.config import settings as app_settings
from app.logger import get_logger
from app.mcp.adapters import UniversalMCPAdapter, PromptInjectionAdapter
import httpx
import json
import hashlib

logger = get_logger(__name__)

# 全局HTTP客户端池（按配置复用）
_http_client_pool: Dict[str, httpx.AsyncClient] = {}
_client_pool_lock = False  # 简单的锁标志


def _get_client_key(provider: str, base_url: Optional[str], api_key: str) -> str:
    """生成HTTP客户端的唯一键
    
    Args:
        provider: 提供商名称
        base_url: API基础URL
        api_key: API密钥（用于区分不同用户）
        
    Returns:
        客户端唯一键
    """
    # 使用API密钥的哈希值（安全性）+ 提供商 + base_url 作为键
    key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
    url_part = base_url or "default"
    return f"{provider}_{url_part}_{key_hash}"


def _get_or_create_http_client(
    provider: str,
    base_url: Optional[str],
    api_key: str
) -> httpx.AsyncClient:
    """获取或创建HTTP客户端（复用连接）
    
    Args:
        provider: 提供商名称
        base_url: API基础URL
        api_key: API密钥
        
    Returns:
        httpx.AsyncClient实例
    """
    global _http_client_pool
    
    client_key = _get_client_key(provider, base_url, api_key)
    
    # 检查是否已存在
    if client_key in _http_client_pool:
        client = _http_client_pool[client_key]
        # 检查客户端是否仍然有效
        if not client.is_closed:
            logger.debug(f"♻️ 复用HTTP客户端: {client_key}")
            return client
        else:
            # 客户端已关闭，从池中移除
            logger.warning(f"⚠️ HTTP客户端已关闭，重新创建: {client_key}")
            del _http_client_pool[client_key]
    
    # 创建新客户端
    limits = httpx.Limits(
        max_keepalive_connections=50,  # 最大保持连接数
        max_connections=100,  # 最大总连接数
        keepalive_expiry=30.0  # 保持连接30秒
    )
    
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=60.0,  # 连接超时
            read=180.0,  # 读取超时
            write=60.0,  # 写入超时
            pool=60.0  # 连接池超时
        ),
        limits=limits,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )
    
    # 添加到池中
    _http_client_pool[client_key] = client
    logger.info(f"✅ 创建新HTTP客户端并加入池: {client_key} (池大小: {len(_http_client_pool)})")
    
    return client


async def cleanup_http_clients():
    """清理所有HTTP客户端（应用关闭时调用）"""
    global _http_client_pool
    
    logger.info(f"🧹 开始清理HTTP客户端池 (共 {len(_http_client_pool)} 个客户端)")
    
    for key, client in list(_http_client_pool.items()):
        try:
            if not client.is_closed:
                await client.aclose()
                logger.debug(f"✅ 关闭HTTP客户端: {key}")
        except Exception as e:
            logger.error(f"❌ 关闭HTTP客户端失败 {key}: {e}")
    
    _http_client_pool.clear()
    logger.info("✅ HTTP客户端池清理完成")


class AIService:
    """AI服务统一接口 - 支持从用户设置或全局配置初始化"""
    
    def __init__(
        self,
        api_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None,
        enable_mcp_adapter: bool = True
    ):
        """
        初始化AI客户端（优化并发性能）
        
        Args:
            api_provider: API提供商 (openai/anthropic)，为None时使用全局配置
            api_key: API密钥，为None时使用全局配置
            api_base_url: API基础URL，为None时使用全局配置
            default_model: 默认模型，为None时使用全局配置
            default_temperature: 默认温度，为None时使用全局配置
            default_max_tokens: 默认最大tokens，为None时使用全局配置
        """
        # 保存用户设置或使用全局配置
        self.api_provider = api_provider or app_settings.default_ai_provider
        self.default_model = default_model or app_settings.default_model
        self.default_temperature = default_temperature or app_settings.default_temperature
        self.default_max_tokens = default_max_tokens or app_settings.default_max_tokens
        
        # 初始化MCP适配器
        self.enable_mcp_adapter = enable_mcp_adapter
        if enable_mcp_adapter:
            self.mcp_adapter = UniversalMCPAdapter()
            logger.info("✅ MCP通用适配器已启用")
        else:
            self.mcp_adapter = None
            logger.info("⚠️ MCP适配器已禁用")
        
        # 初始化OpenAI客户端（使用HTTP客户端池）
        openai_key = api_key if api_provider == "openai" else app_settings.openai_api_key
        if openai_key:
            try:
                base_url = api_base_url if api_provider == "openai" else app_settings.openai_base_url
                
                # 从池中获取或创建HTTP客户端（复用连接）
                http_client = _get_or_create_http_client("openai", base_url, openai_key)
                
                client_kwargs = {
                    "api_key": openai_key,
                    "http_client": http_client
                }
                
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.openai_client = AsyncOpenAI(**client_kwargs)
                self.openai_http_client = http_client
                self.openai_api_key = openai_key
                self.openai_base_url = base_url
                logger.info("✅ OpenAI客户端初始化成功（复用HTTP连接）")
            except Exception as e:
                logger.error(f"OpenAI客户端初始化失败: {e}")
                self.openai_client = None
                self.openai_http_client = None
                self.openai_api_key = None
                self.openai_base_url = None
        else:
            self.openai_client = None
            self.openai_http_client = None
            self.openai_api_key = None
            self.openai_base_url = None
            # 只有当用户明确选择OpenAI作为提供商时才警告
            if self.api_provider == "openai":
                logger.warning("⚠️ OpenAI API key未配置，但被设置为当前AI提供商")
        
        # 初始化Anthropic客户端（使用HTTP客户端池）
        anthropic_key = api_key if api_provider == "anthropic" else app_settings.anthropic_api_key
        if anthropic_key:
            try:
                base_url = api_base_url if api_provider == "anthropic" else app_settings.anthropic_base_url
                
                # 从池中获取或创建HTTP客户端（复用连接）
                http_client = _get_or_create_http_client("anthropic", base_url, anthropic_key)
                
                client_kwargs = {
                    "api_key": anthropic_key,
                    "http_client": http_client
                }
                
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.anthropic_client = AsyncAnthropic(**client_kwargs)
                logger.info("✅ Anthropic客户端初始化成功（复用HTTP连接）")
            except Exception as e:
                logger.error(f"Anthropic客户端初始化失败: {e}")
                self.anthropic_client = None
        else:
            self.anthropic_client = None
            # 只有当用户明确选择Anthropic作为提供商时才警告
            if self.api_provider == "anthropic":
                logger.warning("⚠️ Anthropic API key未配置，但被设置为当前AI提供商")
    
    async def generate_text(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成文本（支持工具调用）
        
        Args:
            prompt: 用户提示词
            provider: AI提供商 (openai/anthropic)
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            system_prompt: 系统提示词
            tools: 可用工具列表（MCP工具格式）
            tool_choice: 工具选择策略 (auto/required/none)
            
        Returns:
            Dict包含:
            - content: 文本内容（如果没有工具调用）
            - tool_calls: 工具调用列表（如果AI决定调用工具）
            - finish_reason: 完成原因
        """
        provider = provider or self.api_provider
        model = model or self.default_model
        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens
        
        if provider == "openai":
            return await self._generate_openai_with_tools(
                prompt, model, temperature, max_tokens, system_prompt, tools, tool_choice
            )
        elif provider == "anthropic":
            return await self._generate_anthropic_with_tools(
                prompt, model, temperature, max_tokens, system_prompt, tools, tool_choice
            )
        else:
            raise ValueError(f"不支持的AI提供商: {provider}")
    
    async def generate_text_stream(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式生成文本
        
        Args:
            prompt: 用户提示词
            provider: AI提供商
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            system_prompt: 系统提示词
            
        Yields:
            生成的文本片段
        """
        provider = provider or self.api_provider
        model = model or self.default_model
        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens
        
        if provider == "openai":
            async for chunk in self._generate_openai_stream(
                prompt, model, temperature, max_tokens, system_prompt
            ):
                yield chunk
        elif provider == "anthropic":
            async for chunk in self._generate_anthropic_stream(
                prompt, model, temperature, max_tokens, system_prompt
            ):
                yield chunk
        else:
            raise ValueError(f"不支持的AI提供商: {provider}")
    
    async def _generate_openai(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> str:
        """使用OpenAI生成文本"""
        if not self.openai_http_client:
            raise ValueError("OpenAI客户端未初始化，请检查API key配置")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"🔵 开始调用OpenAI API（直接HTTP请求）")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - 温度: {temperature}")
            logger.info(f"  - 最大tokens: {max_tokens}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 消息数量: {len(messages)}")
            
            url = f"{self.openai_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            logger.debug(f"  - 请求URL: {url}")
            logger.debug(f"  - 请求头: Authorization=Bearer ***")
            
            response = await self.openai_http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(f"✅ OpenAI API调用成功")
            logger.info(f"  - 响应ID: {data.get('id', 'N/A')}")
            logger.info(f"  - 选项数量: {len(data.get('choices', []))}")
            logger.debug(f"  - 完整API响应: {data}")
            
            if not data.get('choices'):
                logger.error("❌ OpenAI返回的choices为空")
                raise ValueError("API返回的响应格式错误：choices字段为空")
            
            choice = data['choices'][0]
            message = choice.get('message', {})
            finish_reason = choice.get('finish_reason')
            
            # DeepSeek R1特殊处理：只使用content（最终答案），忽略reasoning_content（思考过程）
            # reasoning_content是AI的思考过程，不是我们需要的JSON结果
            content = message.get('content', '')
            
            # 检查是否因达到长度限制而截断
            if finish_reason == 'length':
                logger.warning(f"⚠️  响应因达到max_tokens限制而被截断")
                logger.warning(f"  - 当前max_tokens: {max_tokens}")
                logger.warning(f"  - 建议: 增加max_tokens参数（推荐2000+）")
            
            if content:
                logger.info(f"  - 返回内容长度: {len(content)} 字符")
                logger.info(f"  - 完成原因: {finish_reason}")
                logger.info(f"  - 返回内容预览（前200字符）: {content[:200]}")
                return content
            else:
                logger.error("❌ AI返回了空内容")
                logger.error(f"  - 完整响应: {data}")
                logger.error(f"  - 完成原因: {finish_reason}")
                
                # 提供更详细的错误信息
                if finish_reason == 'length':
                    raise ValueError(f"AI响应被截断且无有效内容。请增加max_tokens参数（当前: {max_tokens}，建议: 2000+）")
                else:
                    raise ValueError(f"AI返回了空内容（finish_reason: {finish_reason}），请检查API配置或稍后重试")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ OpenAI API调用失败 (HTTP {e.response.status_code})")
            logger.error(f"  - 错误信息: {e.response.text}")
            logger.error(f"  - 模型: {model}")
            raise Exception(f"API返回错误 ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ OpenAI API调用失败")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误信息: {str(e)}")
            logger.error(f"  - 模型: {model}")
            raise
    

    async def _generate_openai_with_tools(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用OpenAI生成文本（支持工具调用，集成MCP适配器）"""
        if not self.openai_http_client:
            raise ValueError("OpenAI客户端未初始化，请检查API key配置")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # 如果启用了MCP适配器且有工具，使用适配器处理
        if self.enable_mcp_adapter and self.mcp_adapter and tools:
            logger.info(f"🎯 使用MCP适配器处理工具调用")
            
            # 生成API标识符
            api_identifier = f"openai_{self.openai_base_url or 'default'}"
            
            # 定义API调用函数
            async def call_api(message: str, tools_param: Optional[List] = None, tool_choice_param: Optional[str] = None):
                """实际调用OpenAI API的函数"""
                call_messages = messages.copy()
                call_messages[-1]["content"] = message
                
                url = f"{self.openai_base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": call_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                
                # 只在tools_param不为None时添加工具参数
                if tools_param is not None:
                    # 清理工具定义，移除$schema字段（某些API不支持）
                    cleaned_tools = []
                    for tool in tools_param:
                        cleaned_tool = tool.copy()
                        if "function" in cleaned_tool and "parameters" in cleaned_tool["function"]:
                            params = cleaned_tool["function"]["parameters"].copy()
                            # 移除$schema字段
                            params.pop("$schema", None)
                            cleaned_tool["function"]["parameters"] = params
                        cleaned_tools.append(cleaned_tool)
                    
                    payload["tools"] = cleaned_tools
                    if tool_choice_param:
                        payload["tool_choice"] = tool_choice_param
                
                response = await self.openai_http_client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
            
            # 定义测试函数（检测API是否支持Function Calling）
            async def test_fc():
                """测试Function Calling支持"""
                test_tools = [{
                    "type": "function",
                    "function": {
                        "name": "test_function",
                        "description": "测试函数",
                        "parameters": {"type": "object", "properties": {}}
                    }
                }]
                try:
                    result = await call_api("测试", tools_param=test_tools, tool_choice_param="none")
                    return result
                except Exception as e:
                    logger.debug(f"Function Calling测试失败: {e}")
                    raise
            
            try:
                # 使用适配器处理（自动检测、降级、缓存）
                result = await self.mcp_adapter.call_with_fallback(
                    api_identifier=api_identifier,
                    tools=tools,
                    user_message=prompt,
                    call_function=call_api,
                    test_function=test_fc
                )
                
                # 转换结果格式
                if result.has_tool_calls:
                    return {
                        "tool_calls": result.tool_calls,
                        "content": result.raw_response,
                        "finish_reason": "tool_calls"
                    }
                else:
                    return {
                        "content": result.raw_response,
                        "finish_reason": "stop"
                    }
                    
            except Exception as e:
                logger.error(f"❌ MCP适配器调用失败: {str(e)}")
                # 降级到原始实现
                logger.warning("⚠️ 降级到原始OpenAI调用")
        
        # 原始实现（无适配器或降级）
        try:
            logger.info(f"🔵 开始调用OpenAI API（原始模式）")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - 工具数量: {len(tools) if tools else 0}")
            
            url = f"{self.openai_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # 添加工具参数
            if tools:
                payload["tools"] = tools
                if tool_choice:
                    if tool_choice == "required":
                        payload["tool_choice"] = "required"
                    elif tool_choice == "auto":
                        payload["tool_choice"] = "auto"
                    elif tool_choice == "none":
                        payload["tool_choice"] = "none"
            
            response = await self.openai_http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(f"✅ OpenAI API调用成功")
            logger.debug(f"  - 完整API响应: {data}")
            
            if not data.get('choices'):
                logger.error(f"❌ API返回的choices为空")
                logger.error(f"  - 完整响应: {data}")
                logger.error(f"  - 响应键: {list(data.keys())}")
                raise ValueError(f"API返回的响应格式错误：choices字段为空。完整响应: {data}")
            
            choice = data['choices'][0]
            message = choice.get('message', {})
            finish_reason = choice.get('finish_reason')
            
            # 检查是否有工具调用
            tool_calls = message.get('tool_calls')
            if tool_calls:
                logger.info(f"🔧 AI请求调用 {len(tool_calls)} 个工具")
                return {
                    "tool_calls": tool_calls,
                    "content": message.get('content', ''),
                    "finish_reason": finish_reason
                }
            
            # 没有工具调用，返回普通内容
            content = message.get('content', '')
            if content:
                return {
                    "content": content,
                    "finish_reason": finish_reason
                }
            else:
                raise ValueError(f"AI返回了空内容（finish_reason: {finish_reason}）")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ OpenAI API调用失败 (HTTP {e.response.status_code})")
            logger.error(f"  - 错误信息: {e.response.text}")
            raise Exception(f"API返回错误 ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"❌ OpenAI API调用失败: {str(e)}")
            raise

    async def _generate_anthropic_with_tools(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用Anthropic生成文本（支持工具调用）"""
        if not self.anthropic_client:
            raise ValueError("Anthropic客户端未初始化，请检查API key配置")
        
        try:
            logger.info(f"🔵 开始调用Anthropic API（支持工具调用）")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - 工具数量: {len(tools) if tools else 0}")
            
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            if system_prompt:
                kwargs["system"] = system_prompt
            
            # 添加工具参数
            if tools:
                kwargs["tools"] = tools
                if tool_choice == "required":
                    kwargs["tool_choice"] = {"type": "any"}
                elif tool_choice == "auto":
                    kwargs["tool_choice"] = {"type": "auto"}
            
            response = await self.anthropic_client.messages.create(**kwargs)
            
            # 检查是否有工具调用
            tool_calls = []
            content_text = ""
            
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": block.input
                        }
                    })
                elif block.type == "text":
                    content_text += block.text
            
            if tool_calls:
                logger.info(f"🔧 AI请求调用 {len(tool_calls)} 个工具")
                return {
                    "tool_calls": tool_calls,
                    "content": content_text,
                    "finish_reason": response.stop_reason
                }
            
            return {
                "content": content_text,
                "finish_reason": response.stop_reason
            }
            
        except Exception as e:
            logger.error(f"❌ Anthropic API调用失败: {str(e)}")
            raise

    async def _generate_openai_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> AsyncGenerator[str, None]:
        """使用OpenAI流式生成文本"""
        if not self.openai_http_client:
            raise ValueError("OpenAI客户端未初始化，请检查API key配置")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"🔵 开始调用OpenAI流式API（直接HTTP请求）")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 最大tokens: {max_tokens}")
            
            url = f"{self.openai_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }
            
            async with self.openai_http_client.stream('POST', url, headers=headers, json=payload) as response:
                response.raise_for_status()
                logger.info(f"✅ OpenAI流式API连接成功，开始接收数据...")
                
                chunk_count = 0
                has_content = False
                finish_reason = None
                
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        
                        try:
                            import json
                            data = json.loads(data_str)
                            if 'choices' in data and len(data['choices']) > 0:
                                choice = data['choices'][0]
                                delta = choice.get('delta', {})
                                finish_reason = choice.get('finish_reason') or finish_reason
                                
                                # DeepSeek R1特殊处理：只收集content（最终答案），忽略reasoning_content（思考过程）
                                # reasoning_content是AI的思考过程，不是我们需要的JSON结果
                                content = delta.get('content', '')
                                
                                if content:
                                    chunk_count += 1
                                    has_content = True
                                    yield content
                        except json.JSONDecodeError:
                            continue
                
                # 检查是否因长度限制截断
                if finish_reason == 'length':
                    logger.warning(f"⚠️  流式响应因达到max_tokens限制而被截断")
                    logger.warning(f"  - 当前max_tokens: {max_tokens}")
                    logger.warning(f"  - 建议: 增加max_tokens参数（推荐2000+）")
                
                if not has_content:
                    logger.warning(f"⚠️  流式响应未返回任何内容")
                    logger.warning(f"  - 完成原因: {finish_reason}")
                
                logger.info(f"✅ OpenAI流式生成完成，共接收 {chunk_count} 个chunk，完成原因: {finish_reason}")
            
        except httpx.TimeoutException as e:
            logger.error(f"❌ OpenAI流式API超时")
            logger.error(f"  - 错误: {str(e)}")
            logger.error(f"  - 提示: 请检查网络连接或考虑缩短prompt长度")
            raise TimeoutError(f"AI服务超时（180秒），请稍后重试或减少上下文长度") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ OpenAI流式API调用失败 (HTTP {e.response.status_code})")
            logger.error(f"  - 错误信息: {await e.response.aread()}")
            raise
        except Exception as e:
            logger.error(f"❌ OpenAI流式API调用失败: {str(e)}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            raise
    
    async def _generate_anthropic(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> str:
        """使用Anthropic生成文本"""
        if not self.anthropic_client:
            raise ValueError("Anthropic客户端未初始化，请检查API key配置")
        
        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API调用失败: {str(e)}")
            raise
    
    async def _generate_anthropic_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str]
    ) -> AsyncGenerator[str, None]:
        """使用Anthropic流式生成文本"""
        if not self.anthropic_client:
            raise ValueError("Anthropic客户端未初始化，请检查API key配置")
        
        try:
            logger.info(f"🔵 开始调用Anthropic流式API")
            logger.info(f"  - 模型: {model}")
            logger.info(f"  - Prompt长度: {len(prompt)} 字符")
            logger.info(f"  - 最大tokens: {max_tokens}")
            
            async with self.anthropic_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                logger.info(f"✅ Anthropic流式API连接成功，开始接收数据...")
                
                chunk_count = 0
                async for text in stream.text_stream:
                    chunk_count += 1
                    yield text
                
                logger.info(f"✅ Anthropic流式生成完成，共接收 {chunk_count} 个chunk")
                
        except httpx.TimeoutException as e:
            logger.error(f"❌ Anthropic流式API超时")
            logger.error(f"  - 错误: {str(e)}")
            raise TimeoutError(f"AI服务超时（180秒），请稍后重试或减少上下文长度") from e
        except Exception as e:
            logger.error(f"❌ Anthropic流式API调用失败: {str(e)}")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            raise
    
    async def generate_text_with_mcp(
        self,
        prompt: str,
        user_id: str,
        db_session,
        enable_mcp: bool = True,
        max_tool_rounds: int = 3,
        tool_choice: str = "auto",
        **kwargs
    ) -> Dict[str, Any]:
        """
        支持MCP工具的AI文本生成（非流式）
        
        Args:
            prompt: 用户提示词
            user_id: 用户ID，用于获取MCP工具
            db_session: 数据库会话
            enable_mcp: 是否启用MCP增强
            max_tool_rounds: 最大工具调用轮次
            tool_choice: 工具选择策略（auto/required/none）
            **kwargs: 其他AI参数（provider, model, temperature等）
        
        Returns:
            {
                "content": "AI生成的最终文本",
                "tool_calls_made": 2,  # 实际调用的工具次数
                "tools_used": ["exa_search", "filesystem_read"],
                "finish_reason": "stop",
                "mcp_enhanced": True
            }
        """
        from app.services.mcp_tool_service import mcp_tool_service, MCPToolServiceError
        
        # 初始化返回结果
        result = {
            "content": "",
            "tool_calls_made": 0,
            "tools_used": [],
            "finish_reason": "",
            "mcp_enhanced": False
        }
        
        # 1. 获取MCP工具（如果启用）
        tools = None
        if enable_mcp:
            try:
                tools = await mcp_tool_service.get_user_enabled_tools(
                    user_id=user_id,
                    db_session=db_session
                )
                if tools:
                    logger.info(f"MCP增强: 加载了 {len(tools)} 个工具")
                    result["mcp_enhanced"] = True
            except MCPToolServiceError as e:
                logger.error(f"获取MCP工具失败，降级为普通生成: {e}")
                tools = None
        
        # 2. 工具调用循环
        conversation_history = [
            {"role": "user", "content": prompt}
        ]
        
        for round_num in range(max_tool_rounds):
            logger.info(f"MCP工具调用轮次: {round_num + 1}/{max_tool_rounds}")
            
            # 调用AI
            ai_response = await self.generate_text(
                prompt=conversation_history[-1]["content"],
                tools=tools if round_num == 0 else None,  # 只在第一轮传递工具
                tool_choice=tool_choice if round_num == 0 else None,
                **kwargs
            )
            
            # 检查是否有工具调用
            tool_calls = ai_response.get("tool_calls", [])
            
            if not tool_calls:
                # AI返回最终内容
                result["content"] = ai_response.get("content", "")
                result["finish_reason"] = ai_response.get("finish_reason", "stop")
                break
            
            # 3. 执行工具调用
            logger.info(f"AI请求调用 {len(tool_calls)} 个工具")
            
            try:
                tool_results = await mcp_tool_service.execute_tool_calls(
                    user_id=user_id,
                    tool_calls=tool_calls,
                    db_session=db_session
                )
                
                # 记录使用的工具
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    if tool_name not in result["tools_used"]:
                        result["tools_used"].append(tool_name)
                
                result["tool_calls_made"] += len(tool_calls)
                
                # 4. 构建工具上下文
                tool_context = await mcp_tool_service.build_tool_context(
                    tool_results,
                    format="markdown"
                )
                
                # 5. 更新对话历史
                conversation_history.append({
                    "role": "assistant",
                    "content": ai_response.get("content", ""),
                    "tool_calls": tool_calls
                })
                
                for tool_result in tool_results:
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_result["tool_call_id"],
                        "content": tool_result["content"]
                    })
                
                # 6. 构建下一轮提示
                next_prompt = (
                    f"{prompt}\n\n"
                    f"{tool_context}\n\n"
                    f"请基于以上工具查询结果，继续完成任务。"
                )
                conversation_history.append({
                    "role": "user",
                    "content": next_prompt
                })
                
            except Exception as e:
                logger.error(f"执行MCP工具失败: {e}", exc_info=True)
                # 降级：返回当前AI响应
                result["content"] = ai_response.get("content", "")
                result["finish_reason"] = "tool_error"
                break
        
        else:
            # 达到最大轮次
            logger.warning(f"达到MCP最大调用轮次 {max_tool_rounds}")
            result["content"] = conversation_history[-1].get("content", "")
            result["finish_reason"] = "max_rounds"
        
        return result
    
    async def generate_text_stream_with_mcp(
        self,
        prompt: str,
        user_id: str,
        db_session,
        enable_mcp: bool = True,
        mcp_planning_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        支持MCP工具的AI流式文本生成（两阶段模式）
        
        Args:
            prompt: 用户提示词
            user_id: 用户ID
            db_session: 数据库会话
            enable_mcp: 是否启用MCP增强
            mcp_planning_prompt: MCP规划阶段的提示词（可选）
            **kwargs: 其他AI参数
        
        Yields:
            流式文本chunk
        """
        from app.services.mcp_tool_service import mcp_tool_service
        
        # 阶段1: 工具调用阶段（非流式）
        enhanced_prompt = prompt
        
        if enable_mcp:
            try:
                # 获取MCP工具
                tools = await mcp_tool_service.get_user_enabled_tools(
                    user_id=user_id,
                    db_session=db_session
                )
                
                if tools:
                    logger.info(f"MCP增强（流式）: 加载了 {len(tools)} 个工具")
                    
                    # 使用规划提示让AI决定需要查询什么
                    if not mcp_planning_prompt:
                        mcp_planning_prompt = (
                            f"任务: {prompt}\n\n"
                            f"请分析这个任务，决定是否需要查询外部信息。"
                            f"如果需要，请调用相应的工具获取信息。"
                        )
                    
                    # 非流式调用获取工具结果
                    planning_result = await self.generate_text_with_mcp(
                        prompt=mcp_planning_prompt,
                        user_id=user_id,
                        db_session=db_session,
                        enable_mcp=True,
                        max_tool_rounds=2,
                        tool_choice="auto",
                        **kwargs
                    )
                    
                    # 如果有工具调用，将结果融入提示
                    if planning_result["tool_calls_made"] > 0:
                        enhanced_prompt = (
                            f"{prompt}\n\n"
                            f"【参考资料】\n"
                            f"{planning_result.get('content', '')}"
                        )
                        logger.info(
                            f"MCP工具规划完成，调用了 "
                            f"{planning_result['tool_calls_made']} 次工具"
                        )
            
            except Exception as e:
                logger.error(f"MCP工具规划失败，使用原始提示: {e}")
        
        # 阶段2: 内容生成阶段（流式）
        async for chunk in self.generate_text_stream(
            prompt=enhanced_prompt,
            **kwargs
        ):
            yield chunk


# 创建全局AI服务实例
ai_service = AIService()


def create_user_ai_service(
    api_provider: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    temperature: float,
    max_tokens: int
) -> AIService:
    """
    根据用户设置创建AI服务实例
    
    Args:
        api_provider: API提供商
        api_key: API密钥
        api_base_url: API基础URL
        model_name: 模型名称
        temperature: 温度参数
        max_tokens: 最大tokens
        
    Returns:
        AIService实例
    """
    return AIService(
        api_provider=api_provider,
        api_key=api_key,
        api_base_url=api_base_url,
        default_model=model_name,
        default_temperature=temperature,
        default_max_tokens=max_tokens
    )