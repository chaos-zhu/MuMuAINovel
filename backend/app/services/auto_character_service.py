"""自动角色引入服务 - 在续写大纲时根据剧情推进自动引入新角色"""
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from app.models.character import Character
from app.models.relationship import CharacterRelationship, Organization, OrganizationMember, RelationshipType
from app.models.project import Project
from app.services.ai_service import AIService
from app.services.prompt_service import PromptService
from app.logger import get_logger

logger = get_logger(__name__)


class AutoCharacterService:
    """自动角色引入服务"""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
    
    async def analyze_and_create_characters(
        self,
        project_id: str,
        outline_content: str,
        existing_characters: List[Character],
        db: AsyncSession,
        user_id: str = None,
        enable_mcp: bool = True,
        all_chapters_brief: str = "",
        start_chapter: int = 1,
        chapter_count: int = 3,
        plot_stage: str = "发展",
        story_direction: str = "继续推进主线剧情",
        preview_only: bool = False
    ) -> Dict[str, Any]:
        """
        预测性分析并创建需要的新角色（方案A：先角色后大纲）
        
        Args:
            project_id: 项目ID
            outline_content: 当前批次大纲内容（用于向后兼容，实际不使用）
            existing_characters: 现有角色列表
            db: 数据库会话
            user_id: 用户ID(用于MCP和自定义提示词)
            enable_mcp: 是否启用MCP增强
            all_chapters_brief: 已有章节概览
            start_chapter: 起始章节号
            chapter_count: 续写章节数
            plot_stage: 剧情阶段
            story_direction: 故事发展方向
            preview_only: 仅预测不创建（用于角色确认机制）
            
        Returns:
            {
                "new_characters": [角色对象列表],  # preview_only=True时为空
                "relationships_created": [关系对象列表],  # preview_only=True时为空
                "character_count": 新增角色数量,
                "analysis_result": AI分析结果,
                "predicted_characters": [预测的角色数据]  # 仅preview_only=True时返回
                "needs_new_characters": bool,
                "reason": str
            }
        """
        logger.info(f"🎭 【方案A】预测性分析：检测是否需要引入新角色...")
        logger.info(f"  - 项目ID: {project_id}")
        logger.info(f"  - 续写计划: 第{start_chapter}章起，共{chapter_count}章")
        logger.info(f"  - 剧情阶段: {plot_stage}")
        logger.info(f"  - 发展方向: {story_direction}")
        logger.info(f"  - 现有角色数: {len(existing_characters)}")
        
        # 1. 获取项目信息
        project_result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise ValueError("项目不存在")
        
        # 2. 构建现有角色信息摘要
        existing_chars_summary = self._build_character_summary(existing_characters)
        
        # 3. AI预测性分析是否需要新角色
        analysis_result = await self._analyze_character_needs(
            project=project,
            outline_content=outline_content,  # 保留参数向后兼容
            existing_chars_summary=existing_chars_summary,
            db=db,
            user_id=user_id,
            enable_mcp=enable_mcp,
            all_chapters_brief=all_chapters_brief,
            start_chapter=start_chapter,
            chapter_count=chapter_count,
            plot_stage=plot_stage,
            story_direction=story_direction
        )
        
        # 4. 判断是否需要创建角色
        if not analysis_result or not analysis_result.get("needs_new_characters"):
            logger.info("✅ AI判断：当前剧情不需要引入新角色")
            return {
                "new_characters": [],
                "relationships_created": [],
                "character_count": 0,
                "analysis_result": analysis_result,
                "predicted_characters": [],
                "needs_new_characters": False,
                "reason": analysis_result.get("reason", "当前剧情不需要新角色")
            }
        
        # 5. 如果是预览模式，仅返回预测结果，不创建角色
        if preview_only:
            character_specs = analysis_result.get("character_specifications", [])
            logger.info(f"🔮 预览模式：预测到 {len(character_specs)} 个角色，不创建数据库记录")
            return {
                "new_characters": [],
                "relationships_created": [],
                "character_count": 0,
                "analysis_result": analysis_result,
                "predicted_characters": character_specs,
                "needs_new_characters": True,
                "reason": analysis_result.get("reason", "预测需要新角色")
            }
        
        # 6. 批量生成新角色（非预览模式）
        new_characters = []
        relationships_created = []
        
        character_specs = analysis_result.get("character_specifications", [])
        logger.info(f"🎯 AI建议引入 {len(character_specs)} 个新角色")
        
        for idx, spec in enumerate(character_specs):
            try:
                spec_name = spec.get('name', spec.get('role_description', '未命名'))
                logger.info(f"  [{idx+1}/{len(character_specs)}] 生成角色规格: {spec_name}")
                logger.debug(f"     角色规格内容: {json.dumps(spec, ensure_ascii=False)}")
                
                # 生成角色详细信息
                character_data = await self._generate_character_details(
                    spec=spec,
                    project=project,
                    existing_characters=existing_characters + new_characters,  # 包含新创建的
                    db=db,
                    user_id=user_id,
                    enable_mcp=enable_mcp
                )
                
                logger.debug(f"     AI生成的角色数据: {json.dumps(character_data, ensure_ascii=False)[:200]}")
                
                # 创建角色记录
                character = await self._create_character_record(
                    project_id=project_id,
                    character_data=character_data,
                    db=db
                )
                
                new_characters.append(character)
                logger.info(f"  ✅ 创建新角色: {character.name} ({character.role_type}), ID: {character.id}")
                
                # 建立关系（兼容两种字段名）
                relationships_data = character_data.get("relationships") or character_data.get("relationships_array", [])
                logger.info(f"  🔍 检查关系数据:")
                logger.info(f"     - relationships字段: {character_data.get('relationships')}")
                logger.info(f"     - relationships_array字段: {character_data.get('relationships_array')}")
                logger.info(f"     - 最终使用的数据: {relationships_data}")
                logger.info(f"     - 关系数量: {len(relationships_data) if relationships_data else 0}")
                
                if relationships_data:
                    logger.info(f"  🔗 开始创建 {len(relationships_data)} 条关系...")
                    for idx, rel in enumerate(relationships_data):
                        logger.info(f"     [{idx+1}] {rel.get('target_character_name')} - {rel.get('relationship_type')}")
                else:
                    logger.warning(f"  ⚠️ AI返回的角色数据中没有关系信息！")
                    logger.warning(f"     完整的character_data keys: {list(character_data.keys())}")
                
                rels = await self._create_relationships(
                    new_character=character,
                    relationship_specs=relationships_data,
                    existing_characters=existing_characters + new_characters,
                    project_id=project_id,
                    db=db
                )
                
                relationships_created.extend(rels)
                logger.info(f"  ✅ 实际创建了 {len(rels)} 条关系记录")
                
            except Exception as e:
                logger.error(f"  ❌ 创建角色失败: {e}", exc_info=True)
                continue
        
        # 7. 提交事务（注意：这里只flush，让调用方commit）
        await db.flush()
        
        logger.info(f"🎉 自动角色引入完成: 新增{len(new_characters)}个角色, {len(relationships_created)}条关系")
        
        return {
            "new_characters": new_characters,
            "relationships_created": relationships_created,
            "character_count": len(new_characters),
            "analysis_result": analysis_result
        }
    
    def _build_character_summary(self, characters: List[Character]) -> str:
        """构建现有角色摘要"""
        if not characters:
            return "暂无角色"
        
        summary = []
        for char in characters:
            char_type = "组织" if char.is_organization else "角色"
            role_desc = char.role_type or "未知"
            personality = (char.personality or "")[:50]
            summary.append(f"- {char.name} ({char_type}, {role_desc}): {personality}")
        
        return "\n".join(summary[:20])  # 最多显示20个
    
    async def _analyze_character_needs(
        self,
        project: Project,
        outline_content: str,
        existing_chars_summary: str,
        db: AsyncSession,
        user_id: str,
        enable_mcp: bool,
        all_chapters_brief: str = "",
        start_chapter: int = 1,
        chapter_count: int = 3,
        plot_stage: str = "发展",
        story_direction: str = "继续推进主线剧情"
    ) -> Dict[str, Any]:
        """AI预测性分析是否需要新角色（方案A）"""
        
        # 构建分析提示词
        template = await PromptService.get_template(
            "AUTO_CHARACTER_ANALYSIS",
            user_id,
            db
        )
        
        # 使用新的预测性分析参数
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            theme=project.theme or "未设定",
            genre=project.genre or "未设定",
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            existing_characters=existing_chars_summary,
            all_chapters_brief=all_chapters_brief,
            start_chapter=start_chapter,
            chapter_count=chapter_count,
            plot_stage=plot_stage,
            story_direction=story_direction
        )
        
        try:
            # 调用AI分析（使用统一的JSON调用方法）
            if enable_mcp and user_id:
                result = await self.ai_service.generate_text_with_mcp(
                    prompt=prompt,
                    user_id=user_id,
                    db_session=db,
                    enable_mcp=True,
                    max_tool_rounds=1
                )
                content = result.get("content", "")
                # 使用统一的JSON清洗方法
                cleaned = self.ai_service._clean_json_response(content)
                analysis = json.loads(cleaned)
            else:
                # 非MCP调用：使用带自动重试的JSON调用
                analysis = await self.ai_service.call_with_json_retry(
                    prompt=prompt,
                    max_retries=3
                )
            
            logger.info(f"  ✅ AI分析完成: needs_new_characters={analysis.get('needs_new_characters')}")
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ 角色需求分析JSON解析失败: {e}")
            return {"needs_new_characters": False}
        except Exception as e:
            logger.error(f"  ❌ 角色需求分析失败: {e}")
            return {"needs_new_characters": False}
    
    async def _generate_character_details(
        self,
        spec: Dict[str, Any],
        project: Project,
        existing_characters: List[Character],
        db: AsyncSession,
        user_id: str,
        enable_mcp: bool
    ) -> Dict[str, Any]:
        """生成角色详细信息"""
        
        # 构建角色生成提示词
        template = await PromptService.get_template(
            "AUTO_CHARACTER_GENERATION",
            user_id,
            db
        )
        
        existing_chars_summary = self._build_character_summary(existing_characters)
        
        prompt = PromptService.format_prompt(
            template,
            title=project.title,
            genre=project.genre or "未设定",
            theme=project.theme or "未设定",
            time_period=project.world_time_period or "未设定",
            location=project.world_location or "未设定",
            atmosphere=project.world_atmosphere or "未设定",
            rules=project.world_rules or "未设定",
            existing_characters=existing_chars_summary,
            plot_context="根据剧情需要引入的新角色",
            character_specification=json.dumps(spec, ensure_ascii=False, indent=2),
            mcp_references=""  # 暂时不使用MCP增强
        )
        
        # 调用AI生成（使用统一的JSON调用方法）
        try:
            if enable_mcp and user_id:
                result = await self.ai_service.generate_text_with_mcp(
                    prompt=prompt,
                    user_id=user_id,
                    db_session=db,
                    enable_mcp=True,
                    max_tool_rounds=1
                )
                content = result.get("content", "")
                # 使用统一的JSON清洗方法
                cleaned = self.ai_service._clean_json_response(content)
                character_data = json.loads(cleaned)
            else:
                # 非MCP调用：使用带自动重试的JSON调用
                character_data = await self.ai_service.call_with_json_retry(
                    prompt=prompt,
                    max_retries=3
                )
            
            char_name = character_data.get('name', '未知')
            logger.info(f"    ✅ 角色详情生成成功: {char_name}")
            logger.debug(f"       角色数据字段: {list(character_data.keys())}")
            
            # 确保关键字段存在
            if 'name' not in character_data or not character_data['name']:
                logger.warning(f"    ⚠️ AI返回的角色数据缺少name字段，使用规格中的信息")
                character_data['name'] = spec.get('name', f"新角色{spec.get('role_description', '')[:10]}")
            
            return character_data
            
        except Exception as e:
            logger.error(f"    ❌ 生成角色详情失败: {e}")
            raise
    
    async def _create_character_record(
        self,
        project_id: str,
        character_data: Dict[str, Any],
        db: AsyncSession
    ) -> Character:
        """创建角色数据库记录"""
        
        is_organization = character_data.get("is_organization", False)
        
        # 创建角色
        character = Character(
            project_id=project_id,
            name=character_data.get("name", "未命名角色"),
            age=str(character_data.get("age", "")),
            gender=character_data.get("gender"),
            is_organization=is_organization,
            role_type=character_data.get("role_type", "supporting"),
            personality=character_data.get("personality", ""),
            background=character_data.get("background", ""),
            appearance=character_data.get("appearance", ""),
            relationships=character_data.get("relationships_text", ""),
            organization_type=character_data.get("organization_type") if is_organization else None,
            organization_purpose=character_data.get("organization_purpose") if is_organization else None,
            traits=json.dumps(character_data.get("traits", []), ensure_ascii=False) if character_data.get("traits") else None
        )
        
        db.add(character)
        await db.flush()
        
        # 如果是组织，创建Organization记录
        if is_organization:
            org = Organization(
                character_id=character.id,
                project_id=project_id,
                member_count=0,
                power_level=character_data.get("power_level", 50),
                location=character_data.get("location"),
                motto=character_data.get("motto"),
                color=character_data.get("color")
            )
            db.add(org)
            await db.flush()
            logger.info(f"    ✅ 创建组织详情: {character.name}")
        
        return character
    
    async def _create_relationships(
        self,
        new_character: Character,
        relationship_specs: List[Dict[str, Any]],
        existing_characters: List[Character],
        project_id: str,
        db: AsyncSession
    ) -> List[CharacterRelationship]:
        """创建角色关系"""
        
        if not relationship_specs:
            return []
        
        relationships = []
        
        for rel_spec in relationship_specs:
            try:
                target_name = rel_spec.get("target_character_name")
                if not target_name:
                    continue
                
                # 查找目标角色
                target_char = next(
                    (c for c in existing_characters if c.name == target_name),
                    None
                )
                
                if not target_char:
                    logger.warning(f"    ⚠️ 目标角色不存在: {target_name}")
                    continue
                
                # 检查关系是否已存在
                existing_rel = await db.execute(
                    select(CharacterRelationship).where(
                        CharacterRelationship.project_id == project_id,
                        CharacterRelationship.character_from_id == new_character.id,
                        CharacterRelationship.character_to_id == target_char.id
                    )
                )
                if existing_rel.scalar_one_or_none():
                    logger.debug(f"    ℹ️ 关系已存在: {new_character.name} -> {target_name}")
                    continue
                
                # 创建关系
                relationship = CharacterRelationship(
                    project_id=project_id,
                    character_from_id=new_character.id,
                    character_to_id=target_char.id,
                    relationship_name=rel_spec.get("relationship_type", "未知关系"),
                    intimacy_level=rel_spec.get("intimacy_level", 50),
                    description=rel_spec.get("description", ""),
                    status=rel_spec.get("status", "active"),
                    source="auto"  # 标记为自动生成
                )
                
                # 尝试匹配预定义关系类型
                rel_type_name = rel_spec.get("relationship_type")
                if rel_type_name:
                    rel_type_result = await db.execute(
                        select(RelationshipType).where(
                            RelationshipType.name == rel_type_name
                        )
                    )
                    rel_type = rel_type_result.scalar_one_or_none()
                    if rel_type:
                        relationship.relationship_type_id = rel_type.id
                
                db.add(relationship)
                relationships.append(relationship)
                
                logger.info(
                    f"    ✅ 创建关系: {new_character.name} -> {target_name} "
                    f"({rel_spec.get('relationship_type', '未知')})"
                )
                
            except Exception as e:
                logger.warning(f"    ❌ 创建关系失败: {e}")
                continue
        
        return relationships


# 全局实例缓存
_auto_character_service_instance: Optional[AutoCharacterService] = None


def get_auto_character_service(ai_service: AIService) -> AutoCharacterService:
    """获取自动角色服务实例（单例模式）"""
    global _auto_character_service_instance
    if _auto_character_service_instance is None:
        _auto_character_service_instance = AutoCharacterService(ai_service)
    return _auto_character_service_instance