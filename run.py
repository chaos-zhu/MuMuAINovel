#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MuMuAINovel 服务启动脚本
用于快速启动后端服务
"""
import sys
import os
from pathlib import Path

# 将backend目录添加到Python路径
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

import uvicorn
from app.config import settings

if __name__ == "__main__":
    print("=" * 60)
    print(f"🚀 启动 {settings.app_name} v{settings.app_version}")
    print("=" * 60)
    print(f"📍 服务地址: http://{settings.app_host}:{settings.app_port}")
    print(f"📚 API文档: http://{settings.app_host}:{settings.app_port}/docs")
    print(f"🔧 调试模式: {'启用' if settings.debug else '禁用'}")
    print(f"🗄️  数据库: PostgreSQL")
    print("=" * 60)
    print()
    
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info"
    )