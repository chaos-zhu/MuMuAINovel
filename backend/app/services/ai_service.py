"""AI服务封装 - 统一的OpenAI和Claude接口"""
from typing import Optional, AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from app.config import settings as app_settings
from app.logger import get_logger
import httpx

logger = get_logger(__name__)


class AIService:
    """AI服务统一接口 - 支持从用户设置或全局配置初始化"""
    
    def __init__(
        self,
        api_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None
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
        
        # 初始化OpenAI客户端
        openai_key = api_key if api_provider == "openai" else app_settings.openai_api_key
        if openai_key:
            try:
                limits = httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=100,
                    keepalive_expiry=30.0
                )
                
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=60.0, read=180.0, write=60.0, pool=60.0),
                    limits=limits,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                
                client_kwargs = {
                    "api_key": openai_key,
                    "http_client": http_client
                }
                
                base_url = api_base_url if api_provider == "openai" else app_settings.openai_base_url
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.openai_client = AsyncOpenAI(**client_kwargs)
                self.openai_http_client = http_client
                self.openai_api_key = openai_key
                self.openai_base_url = base_url
                logger.info("✅ OpenAI客户端初始化成功")
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
            logger.warning("OpenAI API key未配置")
        
        # 初始化Anthropic客户端
        anthropic_key = api_key if api_provider == "anthropic" else app_settings.anthropic_api_key
        if anthropic_key:
            try:
                limits = httpx.Limits(
                    max_keepalive_connections=50,
                    max_connections=100,
                    keepalive_expiry=30.0
                )
                
                http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=60.0, read=180.0, write=60.0, pool=60.0),
                    limits=limits,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                
                client_kwargs = {
                    "api_key": anthropic_key,
                    "http_client": http_client
                }
                
                base_url = api_base_url if api_provider == "anthropic" else app_settings.anthropic_base_url
                if base_url:
                    client_kwargs["base_url"] = base_url
                
                self.anthropic_client = AsyncAnthropic(**client_kwargs)
                logger.info("✅ Anthropic客户端初始化成功")
            except Exception as e:
                logger.error(f"Anthropic客户端初始化失败: {e}")
                self.anthropic_client = None
        else:
            self.anthropic_client = None
            logger.warning("Anthropic API key未配置")
    
    async def generate_text(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 用户提示词
            provider: AI提供商 (openai/anthropic)
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            system_prompt: 系统提示词
            
        Returns:
            生成的文本
        """
        provider = provider or self.api_provider
        model = model or self.default_model
        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens
        
        if provider == "openai":
            return await self._generate_openai(
                prompt, model, temperature, max_tokens, system_prompt
            )
        elif provider == "anthropic":
            return await self._generate_anthropic(
                prompt, model, temperature, max_tokens, system_prompt
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