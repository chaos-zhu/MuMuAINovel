"""Server-Sent Events (SSE) 响应工具类"""
import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from fastapi.responses import StreamingResponse
from app.logger import get_logger

logger = get_logger(__name__)


class SSEResponse:
    """SSE响应构建器"""
    
    @staticmethod
    def format_sse(data: Dict[str, Any], event: Optional[str] = None) -> str:
        """
        格式化SSE消息
        
        Args:
            data: 要发送的数据字典
            event: 事件类型(可选)
            
        Returns:
            格式化后的SSE消息字符串
        """
        try:
            message = ""
            if event:
                message += f"event: {event}\n"
            message += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            return message
        except Exception as e:
            logger.error(f"❌ SSE格式化失败: {type(e).__name__}: {e}")
            logger.error(f"   data类型: {type(data)}")
            logger.error(f"   data内容: {str(data)[:500]}")
            # 返回错误消息而不是崩溃
            error_message = ""
            if event:
                error_message += f"event: {event}\n"
            error_message += f'data: {{"type": "error", "error": "SSE格式化失败: {str(e)}", "code": 500}}\n\n'
            return error_message
    
    @staticmethod
    async def send_progress(
        message: str,
        progress: int,
        status: str = "processing"
    ) -> str:
        """
        发送进度消息
        
        Args:
            message: 进度消息
            progress: 进度百分比(0-100)
            status: 状态(processing/success/error)
        """
        return SSEResponse.format_sse({
            "type": "progress",
            "message": message,
            "progress": progress,
            "status": status
        })
    
    @staticmethod
    async def send_chunk(content: str) -> str:
        """
        发送内容块(用于流式输出AI生成内容)
        
        Args:
            content: 内容块
        """
        return SSEResponse.format_sse({
            "type": "chunk",
            "content": content
        })
    
    @staticmethod
    async def send_result(data: Dict[str, Any]) -> str:
        """
        发送最终结果
        
        Args:
            data: 结果数据
        """
        return SSEResponse.format_sse({
            "type": "result",
            "data": data
        })
    
    @staticmethod
    async def send_event(event: str, data: Dict[str, Any]) -> str:
        """
        发送自定义事件类型的SSE消息
        
        Args:
            event: 事件类型名称
            data: 事件数据
        """
        return SSEResponse.format_sse(data, event=event)
    
    @staticmethod
    async def send_error(error: str, code: int = 500) -> str:
        """
        发送错误消息
        
        Args:
            error: 错误描述
            code: 错误码
        """
        return SSEResponse.format_sse({
            "type": "error",
            "error": error,
            "code": code
        })
    
    @staticmethod
    async def send_done() -> str:
        """发送完成消息"""
        return SSEResponse.format_sse({
            "type": "done"
        })
    
    @staticmethod
    async def send_heartbeat() -> str:
        """发送心跳消息(保持连接活跃)"""
        return ": heartbeat\n\n"


async def create_sse_generator(
    async_gen: AsyncGenerator[str, None],
    show_progress: bool = True
) -> AsyncGenerator[str, None]:
    """
    创建SSE生成器包装器
    
    Args:
        async_gen: 异步生成器
        show_progress: 是否显示进度
        
    Yields:
        格式化的SSE消息
    """
    try:
        if show_progress:
            yield await SSEResponse.send_progress("开始生成...", 0)
        
        # 累积内容用于进度计算
        accumulated_content = ""
        chunk_count = 0
        
        async for chunk in async_gen:
            chunk_count += 1
            accumulated_content += chunk
            
            # 发送内容块
            yield await SSEResponse.send_chunk(chunk)
            
            # 每10个块发送一次心跳
            if chunk_count % 10 == 0:
                yield await SSEResponse.send_heartbeat()
        
        if show_progress:
            yield await SSEResponse.send_progress("生成完成", 100, "success")
        
        # 发送完成信号
        yield await SSEResponse.send_done()
        
    except Exception as e:
        logger.error(f"SSE生成器错误: {str(e)}")
        yield await SSEResponse.send_error(str(e))


def create_sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """
    创建SSE StreamingResponse - 兼容HTTP/2协议
    
    Args:
        generator: SSE消息生成器
        
    Returns:
        StreamingResponse对象
    
    注意：
    - HTTP/2不支持Connection头，已移除
    - 明确指定charset=utf-8以确保编码正确
    - 添加CORS头以支持跨域请求
    """
    async def wrapper():
        """包装生成器以捕获StreamingResponse初始化时的GeneratorExit"""
        try:
            async for chunk in generator:
                yield chunk
        except GeneratorExit:
            # StreamingResponse在初始化时会进行类型检查，导致GeneratorExit
            # 这是正常行为，不需要记录警告
            pass
    
    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream; charset=utf-8",  # 明确指定charset
        headers={
            "Cache-Control": "no-cache, no-transform",  # 禁用缓存和转换
            # 移除 Connection: keep-alive (HTTP/2不兼容)
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
            "Access-Control-Allow-Origin": "*",  # CORS支持
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )