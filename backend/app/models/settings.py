"""设置数据模型"""
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Settings(Base):
    """设置表"""
    __tablename__ = "settings"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(50), nullable=False, unique=True, index=True, comment="用户ID")
    api_provider = Column(String(50), default="openai", comment="API提供商")
    api_key = Column(String(500), comment="API密钥")
    api_base_url = Column(String(500), comment="自定义API地址")
    llm_model = Column(String(100), default="gpt-4", comment="模型名称")
    temperature = Column(Float, default=0.7, comment="温度参数")
    max_tokens = Column(Integer, default=2000, comment="最大token数")
    system_prompt = Column(Text, comment="系统级别提示词，每次AI调用都会使用")

    # 封面图片生成配置
    cover_api_provider = Column(String(50), comment="封面图片API提供商")
    cover_api_key = Column(String(500), comment="封面图片API密钥")
    cover_api_base_url = Column(String(500), comment="封面图片自定义API地址")
    cover_image_model = Column(String(100), comment="封面图片模型名称")
    cover_enabled = Column(Boolean, default=False, server_default="0", nullable=False, comment="是否启用封面图片生成")

    preferences = Column(Text, comment="其他偏好设置(JSON)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index('idx_user_id', 'user_id'),
    )
    
    def __repr__(self):
        return f"<Settings(id={self.id}, user_id={self.user_id}, api_provider={self.api_provider})>"
