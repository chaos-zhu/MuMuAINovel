"""MCP适配器模块 - 支持多种AI API的工具调用方式"""

from .base import BaseMCPAdapter, AdapterType
from .prompt_injection import PromptInjectionAdapter
from .function_calling import FunctionCallingAdapter
from .universal import UniversalMCPAdapter

__all__ = [
    "BaseMCPAdapter",
    "AdapterType",
    "PromptInjectionAdapter",
    "FunctionCallingAdapter",
    "UniversalMCPAdapter",
]