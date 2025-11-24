"""MCP适配器基类"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


class AdapterType(Enum):
    """适配器类型"""
    FUNCTION_CALLING = "function_calling"  # 标准Function Calling
    PROMPT_INJECTION = "prompt_injection"  # 提示词注入
    REACT = "react"  # ReAct模式
    XML = "xml"  # XML标记


@dataclass
class ToolCallResult:
    """工具调用结果"""
    tool_calls: List[Dict[str, Any]]  # 解析出的工具调用
    raw_response: str  # 原始AI响应
    has_tool_calls: bool  # 是否包含工具调用
    needs_continuation: bool = False  # 是否需要继续对话


class BaseMCPAdapter(ABC):
    """MCP适配器基类"""
    
    def __init__(self):
        self.adapter_type: AdapterType = AdapterType.PROMPT_INJECTION
    
    @abstractmethod
    def format_tools_for_prompt(
        self,
        tools: List[Dict[str, Any]],
        user_message: str
    ) -> str:
        """
        将工具列表格式化为提示词
        
        Args:
            tools: MCP工具列表
            user_message: 用户消息
            
        Returns:
            格式化后的提示词
        """
        pass
    
    @abstractmethod
    def parse_tool_calls(self, ai_response: str) -> ToolCallResult:
        """
        从AI响应中解析工具调用
        
        Args:
            ai_response: AI的原始响应
            
        Returns:
            解析结果
        """
        pass
    
    @abstractmethod
    def build_continuation_prompt(
        self,
        original_message: str,
        ai_response: str,
        tool_results: List[Dict[str, Any]]
    ) -> str:
        """
        构建包含工具结果的继续对话提示词
        
        Args:
            original_message: 原始用户消息
            ai_response: AI响应
            tool_results: 工具执行结果
            
        Returns:
            继续对话的提示词
        """
        pass
    
    def supports_native_tools(self) -> bool:
        """是否支持原生工具调用（如Function Calling）"""
        return False
    
    def get_adapter_type(self) -> AdapterType:
        """获取适配器类型"""
        return self.adapter_type