"""通用MCP适配器 - 自动检测API能力并选择最佳适配器"""

import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.mcp.adapters.base import BaseMCPAdapter, AdapterType, ToolCallResult
from app.mcp.adapters.prompt_injection import PromptInjectionAdapter
from app.mcp.adapters.function_calling import FunctionCallingAdapter
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass
class APICapability:
    """API能力检测结果"""
    supports_function_calling: bool
    tested_at: datetime
    test_duration_ms: float
    error_message: Optional[str] = None


class UniversalMCPAdapter:
    """
    通用MCP适配器管理器
    
    功能：
    1. 自动检测API是否支持Function Calling
    2. 缓存检测结果
    3. 自动降级策略：FC失败时切换到提示词注入
    4. 提供统一接口
    """
    
    def __init__(
        self,
        cache_ttl_hours: int = 24,
        enable_auto_fallback: bool = True
    ):
        """
        初始化通用适配器
        
        Args:
            cache_ttl_hours: 能力检测缓存时长（小时）
            enable_auto_fallback: 是否启用自动降级
        """
        # 适配器实例
        self.adapters = {
            AdapterType.FUNCTION_CALLING: FunctionCallingAdapter(),
            AdapterType.PROMPT_INJECTION: PromptInjectionAdapter()
        }
        
        # API能力缓存: {api_identifier: APICapability}
        self._capability_cache: Dict[str, APICapability] = {}
        self._cache_ttl = timedelta(hours=cache_ttl_hours)
        self._cache_lock = asyncio.Lock()
        
        # 配置
        self._enable_auto_fallback = enable_auto_fallback
        
        logger.info(
            f"✅ UniversalMCPAdapter初始化完成 "
            f"(缓存TTL={cache_ttl_hours}小时, 自动降级={'开启' if enable_auto_fallback else '关闭'})"
        )
    
    async def get_adapter(
        self,
        api_identifier: str,
        test_function: Optional[callable] = None
    ) -> BaseMCPAdapter:
        """
        获取适合当前API的适配器
        
        Args:
            api_identifier: API标识符（如"openai_official", "azure_openai"等）
            test_function: 可选的测试函数，用于检测API能力
            
        Returns:
            最适合的适配器实例
        """
        
        # 检查缓存
        capability = await self._get_cached_capability(api_identifier)
        
        if capability is None and test_function:
            # 缓存未命中，执行检测
            capability = await self._detect_capability(api_identifier, test_function)
        
        # 选择适配器
        if capability and capability.supports_function_calling:
            logger.info(f"🎯 使用Function Calling适配器: {api_identifier}")
            return self.adapters[AdapterType.FUNCTION_CALLING]
        else:
            logger.info(f"🎯 使用提示词注入适配器: {api_identifier}")
            return self.adapters[AdapterType.PROMPT_INJECTION]
    
    async def _get_cached_capability(
        self,
        api_identifier: str
    ) -> Optional[APICapability]:
        """获取缓存的能力检测结果"""
        
        async with self._cache_lock:
            if api_identifier not in self._capability_cache:
                return None
            
            capability = self._capability_cache[api_identifier]
            
            # 检查是否过期
            if datetime.now() - capability.tested_at > self._cache_ttl:
                logger.info(f"⏰ API能力缓存过期: {api_identifier}")
                del self._capability_cache[api_identifier]
                return None
            
            logger.debug(f"🎯 API能力缓存命中: {api_identifier}")
            return capability
    
    async def _detect_capability(
        self,
        api_identifier: str,
        test_function: callable
    ) -> APICapability:
        """
        检测API能力
        
        Args:
            api_identifier: API标识符
            test_function: 测试函数，应该尝试使用Function Calling
            
        Returns:
            能力检测结果
        """
        
        logger.info(f"🔍 开始检测API能力: {api_identifier}")
        start_time = time.time()
        
        try:
            # 调用测试函数
            result = await test_function()
            
            # 判断是否成功
            supports_fc = self._is_function_calling_response(result)
            
            duration_ms = (time.time() - start_time) * 1000
            
            capability = APICapability(
                supports_function_calling=supports_fc,
                tested_at=datetime.now(),
                test_duration_ms=duration_ms
            )
            
            # 缓存结果
            async with self._cache_lock:
                self._capability_cache[api_identifier] = capability
            
            status = "✅ 支持" if supports_fc else "❌ 不支持"
            logger.info(
                f"{status} Function Calling: {api_identifier} "
                f"(耗时: {duration_ms:.2f}ms)"
            )
            
            return capability
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            logger.warning(
                f"⚠️ API能力检测失败: {api_identifier}, 错误: {e}, "
                f"将使用提示词注入模式"
            )
            
            capability = APICapability(
                supports_function_calling=False,
                tested_at=datetime.now(),
                test_duration_ms=duration_ms,
                error_message=str(e)
            )
            
            # 缓存失败结果（避免重复测试）
            async with self._cache_lock:
                self._capability_cache[api_identifier] = capability
            
            return capability
    
    def _is_function_calling_response(self, response: Any) -> bool:
        """
        判断响应是否是Function Calling格式
        
        Args:
            response: API响应
            
        Returns:
            是否支持Function Calling
        """
        
        try:
            # 检查字典格式
            if isinstance(response, dict):
                message = response.get("choices", [{}])[0].get("message", {})
                return "tool_calls" in message or "function_call" in message
            
            # 检查对象格式（OpenAI SDK）
            if hasattr(response, "choices"):
                message = response.choices[0].message
                return hasattr(message, "tool_calls") or hasattr(message, "function_call")
            
            return False
            
        except Exception:
            return False
    
    async def call_with_fallback(
        self,
        api_identifier: str,
        tools: List[Dict[str, Any]],
        user_message: str,
        call_function: callable,
        test_function: Optional[callable] = None
    ) -> ToolCallResult:
        """
        带降级策略的工具调用
        
        Args:
            api_identifier: API标识符
            tools: MCP工具列表
            user_message: 用户消息
            call_function: 实际调用API的函数
            test_function: 可选的测试函数
            
        Returns:
            工具调用结果
        """
        
        # 获取适配器
        adapter = await self.get_adapter(api_identifier, test_function)
        
        # 首次尝试
        try:
            if adapter.supports_native_tools():
                # Function Calling模式
                logger.info("🚀 尝试使用Function Calling模式")
                result = await self._try_function_calling(
                    tools, user_message, call_function, adapter
                )
            else:
                # 提示词注入模式
                logger.info("🚀 使用提示词注入模式")
                result = await self._try_prompt_injection(
                    tools, user_message, call_function, adapter
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 工具调用失败: {e}")
            
            # 自动降级
            if self._enable_auto_fallback and adapter.supports_native_tools():
                logger.warning("⚠️ Function Calling失败，降级到提示词注入模式")
                
                # 更新缓存，标记为不支持
                async with self._cache_lock:
                    self._capability_cache[api_identifier] = APICapability(
                        supports_function_calling=False,
                        tested_at=datetime.now(),
                        test_duration_ms=0,
                        error_message=str(e)
                    )
                
                # 使用提示词注入重试
                fallback_adapter = self.adapters[AdapterType.PROMPT_INJECTION]
                return await self._try_prompt_injection(
                    tools, user_message, call_function, fallback_adapter
                )
            
            raise
    
    async def _try_function_calling(
        self,
        tools: List[Dict[str, Any]],
        user_message: str,
        call_function: callable,
        adapter: FunctionCallingAdapter
    ) -> ToolCallResult:
        """尝试Function Calling模式"""
        
        # Function Calling不需要修改提示词
        response = await call_function(
            message=user_message,
            tools_param=tools,
            tool_choice_param="auto"
        )
        
        return adapter.parse_tool_calls(response)
    
    async def _try_prompt_injection(
        self,
        tools: List[Dict[str, Any]],
        user_message: str,
        call_function: callable,
        adapter: PromptInjectionAdapter
    ) -> ToolCallResult:
        """尝试提示词注入模式"""
        
        # 注入工具到提示词
        enhanced_prompt = adapter.format_tools_for_prompt(tools, user_message)
        
        # 调用API（不传tools参数）
        response = await call_function(
            message=enhanced_prompt,
            tools_param=None,
            tool_choice_param=None
        )
        
        # 从文本响应中解析工具调用
        return adapter.parse_tool_calls(response)
    
    def clear_cache(self, api_identifier: Optional[str] = None):
        """
        清理能力缓存
        
        Args:
            api_identifier: 可选，只清理特定API的缓存
        """
        if api_identifier:
            if api_identifier in self._capability_cache:
                del self._capability_cache[api_identifier]
                logger.info(f"🧹 已清理API能力缓存: {api_identifier}")
        else:
            self._capability_cache.clear()
            logger.info("🧹 已清理所有API能力缓存")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "total_cached": len(self._capability_cache),
            "cache_ttl_hours": self._cache_ttl.total_seconds() / 3600,
            "cached_apis": [
                {
                    "api_identifier": api_id,
                    "supports_fc": cap.supports_function_calling,
                    "tested_at": cap.tested_at.isoformat(),
                    "test_duration_ms": cap.test_duration_ms
                }
                for api_id, cap in self._capability_cache.items()
            ]
        }


# 全局单例
universal_mcp_adapter = UniversalMCPAdapter()