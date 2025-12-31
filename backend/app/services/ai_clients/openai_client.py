"""OpenAI 客户端"""
import json
from typing import Any, AsyncGenerator, Dict, Optional

from app.logger import get_logger
from .base_client import BaseAIClient

logger = get_logger(__name__)


class OpenAIClient(BaseAIClient):
    """OpenAI API 客户端"""

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if tools:
            # 清理 $schema 字段
            cleaned = []
            for t in tools:
                tc = t.copy()
                if "function" in tc and "parameters" in tc["function"]:
                    tc["function"]["parameters"] = {
                        k: v for k, v in tc["function"]["parameters"].items() if k != "$schema"
                    }
                cleaned.append(tc)
            payload["tools"] = cleaned
            if tool_choice:
                payload["tool_choice"] = tool_choice
        return payload

    async def chat_completion(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = self._build_payload(messages, model, temperature, max_tokens, tools, tool_choice)
        
        logger.debug(f"📤 OpenAI 请求 payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        
        data = await self._request_with_retry("POST", "/chat/completions", payload)
        
        # 调试日志：输出原始响应
        logger.debug(f"📥 OpenAI 原始响应: {json.dumps(data, ensure_ascii=False, indent=2)}")

        choices = data.get("choices", [])
        if not choices or len(choices) == 0:
            raise ValueError("API 返回空 choices 或 choices 为空列表")

        choice = choices[0]
        message = choice.get("message", {})
        return {
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls"),
            "finish_reason": choice.get("finish_reason"),
        }

    async def chat_completion_stream(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_payload(messages, model, temperature, max_tokens, stream=True)
        
        try:
            async with await self._request_with_retry("POST", "/chat/completions", payload, stream=True) as response:
                response.raise_for_status()
                try:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices and len(choices) > 0:
                                    content = choices[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
                except GeneratorExit:
                    # 生成器被关闭，这是正常的清理过程
                    logger.debug("流式响应生成器被关闭(GeneratorExit)")
                    raise
                except Exception as iter_error:
                    logger.error(f"流式响应迭代出错: {str(iter_error)}")
                    raise
        except GeneratorExit:
            # 重新抛出GeneratorExit，让调用方处理
            raise
        except Exception as e:
            logger.error(f"流式请求出错: {str(e)}")
            raise