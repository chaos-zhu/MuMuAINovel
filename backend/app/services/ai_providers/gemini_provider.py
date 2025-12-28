"""Gemini Provider"""
from typing import Any, AsyncGenerator, Dict, List, Optional
from app.services.ai_clients.gemini_client import GeminiClient
from .base_provider import BaseAIProvider


class GeminiProvider(BaseAIProvider):
    def __init__(self, client: GeminiClient):
        self.client = client

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        return await self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def generate_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        messages = [{"role": "user", "content": prompt}]
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        ):
            yield chunk