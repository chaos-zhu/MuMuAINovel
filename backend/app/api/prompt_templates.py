"""提示词模板管理 API"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List, Optional
from datetime import datetime
import json

from app.database import get_db
from app.models.prompt_template import PromptTemplate
from app.schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTemplateResponse,
    PromptTemplateListResponse,
    PromptTemplateCategoryResponse,
    PromptTemplateExport,
    PromptTemplatePreviewRequest
)
from app.services.prompt_service import PromptService
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/prompt-templates", tags=["提示词模板管理"])


@router.get("", response_model=PromptTemplateListResponse)
async def get_all_templates(
    request: Request,
    category: Optional[str] = Query(None, description="按分类筛选"),
    is_active: Optional[bool] = Query(None, description="按启用状态筛选"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户所有提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    query = select(PromptTemplate).where(PromptTemplate.user_id == user_id)
    
    if category:
        query = query.where(PromptTemplate.category == category)
    if is_active is not None:
        query = query.where(PromptTemplate.is_active == is_active)
    
    query = query.order_by(PromptTemplate.category, PromptTemplate.template_key)
    
    result = await db.execute(query)
    templates = result.scalars().all()
    
    # 获取所有分类
    categories_result = await db.execute(
        select(PromptTemplate.category)
        .where(PromptTemplate.user_id == user_id)
        .distinct()
    )
    categories = [c for c in categories_result.scalars().all() if c]
    
    return PromptTemplateListResponse(
        templates=templates,
        total=len(templates),
        categories=sorted(categories)
    )


@router.get("/categories", response_model=List[PromptTemplateCategoryResponse])
async def get_templates_by_category(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    按分类获取提示词模板（合并用户自定义和系统默认）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 1. 查询用户自定义模板
    result = await db.execute(
        select(PromptTemplate)
        .where(PromptTemplate.user_id == user_id)
        .order_by(PromptTemplate.category, PromptTemplate.template_key)
    )
    user_templates = result.scalars().all()
    
    # 2. 获取所有系统默认模板
    system_templates = PromptService.get_all_system_templates()
    
    # 3. 构建用户自定义模板的键集合
    user_template_keys = {t.template_key for t in user_templates}
    
    # 4. 合并模板：用户自定义的 + 未自定义的系统默认
    all_templates = []
    current_time = datetime.now()
    
    # 添加用户自定义的模板
    for user_template in user_templates:
        user_template.is_system_default = False  # 标记为已自定义
        all_templates.append(user_template)
    
    # 添加未自定义的系统默认模板
    for sys_template in system_templates:
        if sys_template['template_key'] not in user_template_keys:
            # 这个系统模板用户还没有自定义，创建临时对象
            template_obj = PromptTemplate(
                id=sys_template['template_key'],  # 使用template_key作为临时ID
                user_id=user_id,
                template_key=sys_template['template_key'],
                template_name=sys_template['template_name'],
                template_content=sys_template['content'],
                description=sys_template['description'],
                category=sys_template['category'],
                parameters=json.dumps(sys_template['parameters']),
                is_active=True,
                is_system_default=True,
                created_at=current_time,
                updated_at=current_time
            )
            all_templates.append(template_obj)
    
    # 5. 按分类分组
    category_dict = {}
    for template in all_templates:
        cat = template.category or "未分类"
        if cat not in category_dict:
            category_dict[cat] = []
        category_dict[cat].append(template)
    
    # 6. 构建响应
    response = []
    for category, temps in sorted(category_dict.items()):
        # 按template_key排序，确保顺序一致
        temps.sort(key=lambda t: t.template_key)
        response.append(PromptTemplateCategoryResponse(
            category=category,
            count=len(temps),
            templates=temps
        ))
    
    return response


@router.get("/system-defaults")
async def get_system_defaults(
    request: Request
):
    """
    获取所有系统默认提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 从PromptService获取所有系统默认模板
    system_templates = PromptService.get_all_system_templates()
    
    return {
        "templates": system_templates,
        "total": len(system_templates)
    }


@router.get("/{template_key}", response_model=PromptTemplateResponse)
async def get_template(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    获取指定的提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    return template


@router.post("", response_model=PromptTemplateResponse)
async def create_or_update_template(
    data: PromptTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    创建或更新提示词模板（Upsert）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 查找现有模板
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == data.template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if template:
        # 更新现有模板
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(template, key, value)
        logger.info(f"用户 {user_id} 更新模板 {data.template_key}")
    else:
        # 创建新模板
        template = PromptTemplate(
            user_id=user_id,
            **data.model_dump()
        )
        db.add(template)
        logger.info(f"用户 {user_id} 创建模板 {data.template_key}")
    
    await db.commit()
    await db.refresh(template)
    
    return template


@router.put("/{template_key}", response_model=PromptTemplateResponse)
async def update_template(
    template_key: str,
    data: PromptTemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    更新提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    # 更新模板
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    await db.commit()
    await db.refresh(template)
    logger.info(f"用户 {user_id} 更新模板 {template_key}")
    
    return template


@router.delete("/{template_key}")
async def delete_template(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    删除自定义提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {template_key} 不存在")
    
    await db.delete(template)
    await db.commit()
    logger.info(f"用户 {user_id} 删除模板 {template_key}")
    
    return {"message": "模板已删除", "template_key": template_key}


@router.post("/{template_key}/reset")
async def reset_to_default(
    template_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    重置为系统默认模板（删除用户自定义版本）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 验证系统默认模板是否存在
    system_template = PromptService.get_system_template_info(template_key)
    if not system_template:
        raise HTTPException(status_code=404, detail=f"系统默认模板 {template_key} 不存在")
    
    # 查找并删除用户的自定义模板
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.user_id == user_id,
            PromptTemplate.template_key == template_key
        )
    )
    template = result.scalar_one_or_none()
    
    if template:
        await db.delete(template)
        await db.commit()
        logger.info(f"用户 {user_id} 删除自定义模板 {template_key}，恢复为系统默认")
        return {"message": "已重置为系统默认", "template_key": template_key}
    else:
        # 用户本来就没有自定义，已经是系统默认状态
        logger.info(f"用户 {user_id} 的模板 {template_key} 本来就是系统默认")
        return {"message": "已是系统默认状态", "template_key": template_key}


@router.post("/export", response_model=PromptTemplateExport)
async def export_templates(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    导出用户所有自定义模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.user_id == user_id)
    )
    templates = result.scalars().all()
    
    # 转换为导出格式
    export_data = [
        {
            "template_key": t.template_key,
            "template_name": t.template_name,
            "template_content": t.template_content,
            "description": t.description,
            "category": t.category,
            "parameters": t.parameters,
            "is_active": t.is_active
        }
        for t in templates
    ]
    
    logger.info(f"用户 {user_id} 导出了 {len(export_data)} 个模板")
    
    return PromptTemplateExport(
        templates=export_data,
        export_time=datetime.now()
    )


@router.post("/import")
async def import_templates(
    data: PromptTemplateExport,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    导入提示词模板
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    imported_count = 0
    updated_count = 0
    
    for template_data in data.templates:
        # 查找是否已存在
        result = await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.user_id == user_id,
                PromptTemplate.template_key == template_data.template_key
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新现有模板
            for key, value in template_data.model_dump().items():
                setattr(existing, key, value)
            updated_count += 1
        else:
            # 创建新模板
            new_template = PromptTemplate(
                user_id=user_id,
                **template_data.model_dump()
            )
            db.add(new_template)
            imported_count += 1
    
    await db.commit()
    logger.info(f"用户 {user_id} 导入了 {imported_count} 个新模板，更新了 {updated_count} 个模板")
    
    return {
        "message": "导入成功",
        "imported": imported_count,
        "updated": updated_count,
        "total": imported_count + updated_count
    }


@router.post("/{template_key}/preview")
async def preview_template(
    template_key: str,
    data: PromptTemplatePreviewRequest,
    request: Request
):
    """
    预览提示词模板（渲染变量）
    """
    # 从认证中间件获取用户ID
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    try:
        # 使用PromptService的format_prompt方法
        rendered = PromptService.format_prompt(
            data.template_content,
            **data.parameters
        )
        
        return {
            "success": True,
            "rendered_content": rendered,
            "parameters_used": list(data.parameters.keys())
        }
    except KeyError as e:
        return {
            "success": False,
            "error": f"缺少必需的参数: {str(e)}",
            "rendered_content": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"渲染失败: {str(e)}",
            "rendered_content": None
        }