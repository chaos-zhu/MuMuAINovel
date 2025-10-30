"""
认证中间件 - 从 Cookie 中提取用户信息并注入到 request.state
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.user_manager import user_manager


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件"""
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求，从 Cookie 中提取用户 ID 并注入到 request.state
        """
        # 从 Cookie 中获取用户 ID
        user_id = request.cookies.get("user_id")
        
        # 注入到 request.state
        if user_id:
            user = await user_manager.get_user(user_id)
            if user:
                request.state.user_id = user_id
                request.state.user = user
                request.state.is_admin = user.is_admin
            else:
                # 用户不存在，清除状态
                request.state.user_id = None
                request.state.user = None
                request.state.is_admin = False
        else:
            # 未登录
            request.state.user_id = None
            request.state.user = None
            request.state.is_admin = False
        
        # 继续处理请求
        response = await call_next(request)
        return response