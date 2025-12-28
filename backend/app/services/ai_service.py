"""AI服务封装 - 统一的AI接口"""
from typing import Optional, AsyncGenerator, List, Dict, Any, Union

from app.config import settings as app_settings
from app.logger import get_logger
from app.services.ai_config import AIClientConfig, default_config
from app.services.ai_clients.openai_client import OpenAIClient
from app.services.ai_clients.anthropic_client import AnthropicClient
from app.services.ai_clients.gemini_client import GeminiClient
from app.services.ai_clients.base_client import cleanup_all_clients
from app.services.ai_providers.openai_provider import OpenAIProvider
from app.services.ai_providers.anthropic_provider import AnthropicProvider
from app.services.ai_providers.gemini_provider import GeminiProvider
from app.services.ai_providers.base_provider import BaseAIProvider
from app.services.json_helper import clean_json_response, parse_json
from app.mcp.adapters.universal import universal_mcp_adapter

# 导出清理函数
cleanup_http_clients = cleanup_all_clients

logger = get_logger(__name__)


class AIService:
    """AI服务统一接口"""

    def __init__(
        self,
        api_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        default_temperature: Optional[float] = None,
        default_max_tokens: Optional[int] = None,
        default_system_prompt: Optional[str] = None,
        enable_mcp_adapter: bool = True,
        config: Optional[AIClientConfig] = None,
    ):
        self.api_provider = api_provider or app_settings.default_ai_provider
        self.default_model = default_model or app_settings.default_model
        self.default_temperature = default_temperature or app_settings.default_temperature
        self.default_max_tokens = default_max_tokens or app_settings.default_max_tokens
        self.default_system_prompt = default_system_prompt
        self.config = config or default_config
        
        self.mcp_adapter = universal_mcp_adapter if enable_mcp_adapter else None
        
        self._openai_provider: Optional[OpenAIProvider] = None
        self._anthropic_provider: Optional[AnthropicProvider] = None
        self._gemini_provider: Optional[GeminiProvider] = None
        
        # 初始化 OpenAI
        openai_key = api_key if api_provider == "openai" else app_settings.openai_api_key
        if openai_key:
            base_url = api_base_url if api_provider == "openai" else app_settings.openai_base_url
            client = OpenAIClient(openai_key, base_url or "https://api.openai.com/v1", self.config)
            self._openai_provider = OpenAIProvider(client)
        
        # 初始化 Anthropic
        anthropic_key = api_key if api_provider == "anthropic" else app_settings.anthropic_api_key
        if anthropic_key:
            base_url = api_base_url if api_provider == "anthropic" else app_settings.anthropic_base_url
            client = AnthropicClient(anthropic_key, base_url, self.config)
            self._anthropic_provider = AnthropicProvider(client)
        
        # 初始化 Gemini
        if api_provider == "gemini" and api_key:
            client = GeminiClient(api_key, api_base_url, self.config)
            self._gemini_provider = GeminiProvider(client)

    def _get_provider(self, provider: Optional[str] = None) -> BaseAIProvider:
        """获取对应的 Provider"""
        p = provider or self.api_provider
        if p == "openai" and self._openai_provider:
            return self._openai_provider
        if p == "anthropic" and self._anthropic_provider:
            return self._anthropic_provider
        if p == "gemini" and self._gemini_provider:
            return self._gemini_provider
        raise ValueError(f"Provider {p} 未初始化")

    async def generate_text(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成文本"""
        prov = self._get_provider(provider)
        return await prov.generate(
            prompt=prompt,
            model=model or self.default_model,
            temperature=temperature or self.default_temperature,
            max_tokens=max_tokens or self.default_max_tokens,
            system_prompt=system_prompt or self.default_system_prompt,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def generate_text_stream(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        prov = self._get_provider(provider)
        async for chunk in prov.generate_stream(
            prompt=prompt,
            model=model or self.default_model,
            temperature=temperature or self.default_temperature,
            max_tokens=max_tokens or self.default_max_tokens,
            system_prompt=system_prompt or self.default_system_prompt,
        ):
            yield chunk

    async def call_with_json_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        expected_type: Optional[str] = None,
    ) -> Union[Dict, List]:
        """带重试的 JSON 调用"""
        last_response = ""
        
        for attempt in range(1, max_retries + 1):
            current_prompt = prompt if attempt == 1 else self._add_json_hint(prompt, last_response, attempt)
            
            result = await self.generate_text(
                prompt=current_prompt,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            )
            
            last_response = result.get("content", "")
            
            try:
                data = parse_json(last_response)
                if expected_type == "object" and not isinstance(data, dict):
                    raise ValueError("期望对象")
                if expected_type == "array" and not isinstance(data, list):
                    raise ValueError("期望数组")
                return data
            except Exception as e:
                if attempt == max_retries:
                    raise ValueError(f"JSON 解析失败: {e}")
        
        raise ValueError("JSON 调用失败")

    @staticmethod
    def _add_json_hint(prompt: str, failed: str, attempt: int) -> str:
        return f"{prompt}\n\n⚠️ 第{attempt}次重试，请返回纯JSON，不要markdown包裹。上次错误: {failed[:200]}..."

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清洗 JSON 响应"""
        return clean_json_response(text)

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
        """支持MCP工具的AI文本生成"""
        from app.services.mcp_tool_service import mcp_tool_service, MCPToolServiceError
        
        result = {"content": "", "tool_calls_made": 0, "tools_used": [], "finish_reason": "", "mcp_enhanced": False}
        tools = None
        
        if enable_mcp:
            try:
                tools = await mcp_tool_service.get_user_enabled_tools(user_id=user_id, db_session=db_session)
                if tools:
                    result["mcp_enhanced"] = True
            except MCPToolServiceError:
                tools = None
        
        original_prompt = prompt  # 保存原始提示词
        
        for round_num in range(max_tool_rounds):
            logger.debug(f"🔄 MCP工具调用 - 第{round_num+1}/{max_tool_rounds}轮")
            logger.debug(f"   prompt长度: {len(prompt)}, tools数量: {len(tools) if tools else 0}, tool_choice: {tool_choice}")
            
            ai_response = await self.generate_text(prompt=prompt, tools=tools, tool_choice=tool_choice, **kwargs)
            logger.debug(f"   AI响应: finish_reason={ai_response.get('finish_reason')}, content长度={len(ai_response.get('content', ''))}")
            
            tool_calls = ai_response.get("tool_calls", [])
            
            if not tool_calls:
                content = ai_response.get("content", "")
                result["content"] = content
                result["finish_reason"] = ai_response.get("finish_reason", "stop")
                logger.debug(f"   ✅ 无工具调用，返回内容长度: {len(content)}")
                
                # 🔧 修复：如果内容为空且已经调用过工具，强制要求AI给出答案
                if not content.strip() and result["tool_calls_made"] > 0:
                    logger.warning(f"⚠️ AI在工具调用后返回空内容，尝试强制要求回答（第{round_num+1}轮）")
                    prompt = f"{prompt}\n\n⚠️ 请注意：你必须基于以上工具查询结果，给出完整的回答。不要返回空内容。"
                    tools = None
                    tool_choice = "none"  # 强制不使用工具
                    continue
                
                break
            
            logger.info(f"🔧 检测到 {len(tool_calls)} 个工具调用")
            for idx, tc in enumerate(tool_calls):
                logger.debug(f"   工具{idx+1}: {tc.get('function', {}).get('name')} - 参数: {tc.get('function', {}).get('arguments')}")
            
            try:
                logger.debug(f"   开始执行工具调用...")
                tool_results = await mcp_tool_service.execute_tool_calls(user_id=user_id, tool_calls=tool_calls, db_session=db_session)
                logger.debug(f"   工具执行完成，结果数量: {len(tool_results)}")
                
                # 🔍 检查工具结果
                for idx, tr in enumerate(tool_results):
                    success = tr.get("success", False)
                    content_preview = tr.get("content", "")[:200] if tr.get("content") else "None"
                    logger.debug(f"   工具结果[{idx}]: success={success}, content预览={content_preview}")
                
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    if name not in result["tools_used"]:
                        result["tools_used"].append(name)
                result["tool_calls_made"] += len(tool_calls)
                
                tool_context = await mcp_tool_service.build_tool_context(tool_results, format="markdown")
                logger.debug(f"   工具上下文长度: {len(tool_context)}")
                logger.debug(f"   工具上下文预览: {tool_context[:300] if len(tool_context) > 300 else tool_context}")
                
                # 🔧 改进：在最后一轮时，明确要求AI给出完整答案
                if round_num == max_tool_rounds - 1:
                    logger.info(f"⚠️ 最后一轮，强制要求AI给出最终答案")
                    prompt = f"{original_prompt}\n\n{tool_context}\n\n⚠️ 重要：这是最后一轮，请基于以上工具查询的参考资料，给出完整详细的最终答案。不要再调用工具。"
                    tool_choice = "none"
                else:
                    prompt = f"{original_prompt}\n\n{tool_context}\n\n请基于以上工具查询结果，继续完成任务。"
                    logger.debug(f"   新prompt长度: {len(prompt)}")
                
                tools = None  # 工具调用后禁用工具列表，避免重复调用
                logger.debug(f"   ✅ 工具调用成功，准备下一轮")
                
            except Exception as tool_error:
                logger.error(f"❌ 工具调用执行失败: {tool_error}", exc_info=True)
                logger.error(f"   错误类型: {type(tool_error).__name__}")
                logger.error(f"   AI响应内容: {ai_response.get('content', '')[:200]}")
                result["content"] = ai_response.get("content", "")
                result["finish_reason"] = "tool_error"
                break
        
        return result


# 全局实例
ai_service = AIService()


def create_user_ai_service(
    api_provider: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    system_prompt: Optional[str] = None,
) -> AIService:
    """创建用户 AI 服务"""
    return AIService(
        api_provider=api_provider,
        api_key=api_key,
        api_base_url=api_base_url,
        default_model=model_name,
        default_temperature=temperature,
        default_max_tokens=max_tokens,
        default_system_prompt=system_prompt,
    )