"""Function Calling适配器 - 支持原生Function Calling的API"""

import json
from typing import Dict, Any, List
from app.mcp.adapters.base import BaseMCPAdapter, AdapterType, ToolCallResult
from app.logger import get_logger

logger = get_logger(__name__)


class FunctionCallingAdapter(BaseMCPAdapter):
    """Function Calling适配器 - 用于支持原生工具调用的AI API（如OpenAI）"""
    
    def __init__(self):
        super().__init__()
        self.adapter_type = AdapterType.FUNCTION_CALLING
    
    def supports_native_tools(self) -> bool:
        """支持原生工具调用"""
        return True
    
    def format_tools_for_prompt(
        self,
        tools: List[Dict[str, Any]],
        user_message: str
    ) -> str:
        """
        Function Calling模式下，工具通过API参数传递，不需要修改提示词
        
        Returns:
            原始用户消息
        """
        return user_message
    
    def get_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        获取适用于API的工具格式
        
        Args:
            tools: MCP工具列表
            
        Returns:
            适用于OpenAI Function Calling的工具格式
        """
        return tools
    
    def parse_tool_calls(self, ai_response: Any) -> ToolCallResult:
        """
        从AI响应中解析工具调用（Function Calling格式）
        
        Args:
            ai_response: AI响应对象（通常是OpenAI的ChatCompletion对象）
            
        Returns:
            解析结果
        """
        
        try:
            # 处理不同类型的响应
            if isinstance(ai_response, dict):
                # 字典格式（OpenAI API响应）
                message = ai_response.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls", [])
                content = message.get("content", "")
                
            elif hasattr(ai_response, "choices"):
                # 对象格式（OpenAI SDK响应）
                message = ai_response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None) or []
                content = getattr(message, "content", "") or ""
                
                # 转换为字典格式
                if tool_calls:
                    tool_calls = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in tool_calls
                    ]
            else:
                # 字符串格式（降级为文本响应）
                return ToolCallResult(
                    tool_calls=[],
                    raw_response=str(ai_response),
                    has_tool_calls=False
                )
            
            has_tool_calls = len(tool_calls) > 0
            
            if has_tool_calls:
                logger.info(f"✅ Function Calling模式解析出 {len(tool_calls)} 个工具调用")
                for tc in tool_calls:
                    logger.info(f"  - {tc['function']['name']}")
            
            return ToolCallResult(
                tool_calls=tool_calls,
                raw_response=content or "",
                has_tool_calls=has_tool_calls,
                needs_continuation=has_tool_calls
            )
            
        except Exception as e:
            logger.error(f"❌ 解析Function Calling响应失败: {e}", exc_info=True)
            return ToolCallResult(
                tool_calls=[],
                raw_response=str(ai_response),
                has_tool_calls=False
            )
    
    def build_continuation_prompt(
        self,
        original_message: str,
        ai_response: str,
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """
        构建包含工具结果的继续对话提示词
        
        在Function Calling模式下，这通常不需要，因为工具结果会作为消息历史的一部分
        """
        # Function Calling模式下通常通过消息历史传递工具结果
        # 这里提供一个降级方案
        results_text = "\n\n".join([
            f"工具 {r['name']} 的结果:\n{r['content']}"
            for r in tool_results
        ])
        
        return f"{original_message}\n\n工具执行结果:\n{results_text}\n\n请基于以上工具结果回答用户的问题。"
    
    def build_messages_with_tool_results(
        self,
        messages: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        构建包含工具结果的消息历史（Function Calling标准格式）
        
        Args:
            messages: 原始消息历史
            tool_calls: AI的工具调用
            tool_results: 工具执行结果
            
        Returns:
            更新后的消息历史
        """
        
        new_messages = messages.copy()
        
        # 添加助手的工具调用消息
        new_messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls
        })
        
        # 添加工具结果消息
        for result in tool_results:
            new_messages.append({
                "role": "tool",
                "tool_call_id": result.get("tool_call_id", ""),
                "name": result.get("name", ""),
                "content": result.get("content", "")
            })
        
        return new_messages