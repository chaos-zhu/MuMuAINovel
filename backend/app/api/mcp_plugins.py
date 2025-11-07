"""MCP插件管理API"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.mcp_plugin import MCPPlugin
from app.schemas.mcp_plugin import (
    MCPPluginCreate,
    MCPPluginSimpleCreate,
    MCPPluginUpdate,
    MCPPluginResponse,
    MCPToolCall,
    MCPTestResult
)
import json
from app.user_manager import User
from app.mcp.registry import mcp_registry
from app.logger import get_logger
from app.services.ai_service import create_user_ai_service
from app.models.settings import Settings as UserSettings

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/plugins", tags=["MCP插件管理"])


def require_login(request: Request) -> User:
    """依赖：要求用户已登录"""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="需要登录")
    return request.state.user


@router.get("", response_model=List[MCPPluginResponse])
async def list_plugins(
    enabled_only: bool = Query(False, description="只返回启用的插件"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的所有MCP插件
    """
    query = select(MCPPlugin).where(MCPPlugin.user_id == user.user_id)
    
    if enabled_only:
        query = query.where(MCPPlugin.enabled == True)
    
    if category:
        query = query.where(MCPPlugin.category == category)
    
    query = query.order_by(MCPPlugin.sort_order, MCPPlugin.created_at)
    
    result = await db.execute(query)
    plugins = result.scalars().all()
    
    logger.info(f"用户 {user.user_id} 查询插件列表，共 {len(plugins)} 个")
    return plugins


@router.post("", response_model=MCPPluginResponse)
async def create_plugin(
    data: MCPPluginCreate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    创建新的MCP插件
    """
    # 检查插件名是否已存在
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.user_id == user.user_id,
            MCPPlugin.plugin_name == data.plugin_name
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"插件名已存在: {data.plugin_name}")
    
    # 创建插件数据
    plugin_data = data.model_dump()
    
    # 如果没有提供display_name，使用plugin_name作为默认值
    if not plugin_data.get("display_name"):
        plugin_data["display_name"] = plugin_data["plugin_name"]
    
    # 创建插件
    plugin = MCPPlugin(
        user_id=user.user_id,
        **plugin_data
    )
    
    db.add(plugin)
    await db.commit()
    await db.refresh(plugin)
    
    # 如果启用，加载到注册表
    if plugin.enabled:
        success = await mcp_registry.load_plugin(plugin)
        if success:
            plugin.status = "active"
        else:
            plugin.status = "error"
            plugin.last_error = "加载失败"
        await db.commit()
        await db.refresh(plugin)
    
    logger.info(f"用户 {user.user_id} 创建插件: {plugin.plugin_name}")
    return plugin


@router.post("/simple", response_model=MCPPluginResponse)
async def create_plugin_simple(
    data: MCPPluginSimpleCreate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    通过标准MCP配置JSON创建或更新插件（简化版）
    
    接受格式：
    {
      "config_json": '{"mcpServers": {"exa": {"type": "http", "url": "...", "headers": {}}}}',
      "category": "search"
    }
    
    自动从mcpServers中提取插件名称（取第一个键）
    如果插件已存在，则更新；否则创建新插件
    """
    try:
        # 解析配置JSON
        config = json.loads(data.config_json)
        
        # 验证格式
        if "mcpServers" not in config:
            raise HTTPException(status_code=400, detail="配置JSON必须包含mcpServers字段")
        
        servers = config["mcpServers"]
        if not servers or len(servers) == 0:
            raise HTTPException(status_code=400, detail="mcpServers不能为空")
        
        # 自动提取第一个插件名称
        plugin_name = list(servers.keys())[0]
        server_config = servers[plugin_name]
        
        logger.info(f"从配置中提取插件名称: {plugin_name}")
        
        # 提取配置
        server_type = server_config.get("type", "http")
        
        if server_type not in ["http", "stdio"]:
            raise HTTPException(status_code=400, detail=f"不支持的服务器类型: {server_type}")
        
        # 检查插件名是否已存在
        result = await db.execute(
            select(MCPPlugin).where(
                MCPPlugin.user_id == user.user_id,
                MCPPlugin.plugin_name == plugin_name
            )
        )
        existing = result.scalar_one_or_none()
        
        # 构建插件数据
        plugin_data = {
            "plugin_name": plugin_name,
            "display_name": plugin_name, 
            "plugin_type": server_type,
            "enabled": data.enabled,
            "category": data.category,
            "sort_order": 0
        }
        
        if server_type == "http":
            plugin_data["server_url"] = server_config.get("url")
            plugin_data["headers"] = server_config.get("headers", {})
            
            if not plugin_data["server_url"]:
                raise HTTPException(status_code=400, detail="HTTP类型插件必须提供url字段")
        
        elif server_type == "stdio":
            plugin_data["command"] = server_config.get("command")
            plugin_data["args"] = server_config.get("args", [])
            plugin_data["env"] = server_config.get("env", {})
            
            if not plugin_data["command"]:
                raise HTTPException(status_code=400, detail="Stdio类型插件必须提供command字段")
        
        if existing:
            # 更新现有插件
            logger.info(f"插件 {plugin_name} 已存在，执行更新操作")
            
            # 先卸载旧插件
            if existing.enabled:
                await mcp_registry.unload_plugin(user.user_id, existing.plugin_name)
            
            # 更新字段
            for key, value in plugin_data.items():
                setattr(existing, key, value)
            
            plugin = existing
            await db.commit()
            await db.refresh(plugin)
            
            # 如果启用，重新加载
            if plugin.enabled:
                success = await mcp_registry.load_plugin(plugin)
                if success:
                    plugin.status = "active"
                    plugin.last_error = None
                else:
                    plugin.status = "error"
                    plugin.last_error = "加载失败"
                await db.commit()
                await db.refresh(plugin)
            
            logger.info(f"用户 {user.user_id} 更新插件: {plugin_name}")
        else:
            # 创建新插件
            plugin = MCPPlugin(
                user_id=user.user_id,
                **plugin_data
            )
            
            db.add(plugin)
            await db.commit()
            await db.refresh(plugin)
            
            # 如果启用，加载到注册表
            if plugin.enabled:
                success = await mcp_registry.load_plugin(plugin)
                if success:
                    plugin.status = "active"
                else:
                    plugin.status = "error"
                    plugin.last_error = "加载失败"
                await db.commit()
                await db.refresh(plugin)
            
            logger.info(f"用户 {user.user_id} 通过简化配置创建插件: {plugin_name}")
        
        return plugin
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"配置JSON格式错误: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建插件失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建插件失败: {str(e)}")


@router.get("/{plugin_id}", response_model=MCPPluginResponse)
async def get_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取插件详情
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    return plugin


@router.put("/{plugin_id}", response_model=MCPPluginResponse)
async def update_plugin(
    plugin_id: str,
    data: MCPPluginUpdate,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    更新插件配置
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plugin, key, value)
    
    await db.commit()
    await db.refresh(plugin)
    
    # 如果插件已启用，重新加载
    if plugin.enabled:
        await mcp_registry.reload_plugin(plugin)
    
    logger.info(f"用户 {user.user_id} 更新插件: {plugin.plugin_name}")
    return plugin


@router.delete("/{plugin_id}")
async def delete_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    删除插件
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    # 从注册表卸载
    await mcp_registry.unload_plugin(user.user_id, plugin.plugin_name)
    
    # 删除数据库记录
    await db.delete(plugin)
    await db.commit()
    
    logger.info(f"用户 {user.user_id} 删除插件: {plugin.plugin_name}")
    return {"message": "插件已删除", "plugin_name": plugin.plugin_name}


@router.post("/{plugin_id}/toggle", response_model=MCPPluginResponse)
async def toggle_plugin(
    plugin_id: str,
    enabled: bool = Query(..., description="启用或禁用"),
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    启用或禁用插件
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    plugin.enabled = enabled
    
    if enabled:
        # 启用：加载到注册表
        success = await mcp_registry.load_plugin(plugin)
        if success:
            plugin.status = "active"
            plugin.last_error = None
        else:
            plugin.status = "error"
            plugin.last_error = "加载失败"
    else:
        # 禁用：从注册表卸载
        await mcp_registry.unload_plugin(user.user_id, plugin.plugin_name)
        plugin.status = "inactive"
    
    await db.commit()
    await db.refresh(plugin)
    
    action = "启用" if enabled else "禁用"
    logger.info(f"用户 {user.user_id} {action}插件: {plugin.plugin_name}")
    return plugin


@router.post("/{plugin_id}/test", response_model=MCPTestResult)
async def test_plugin(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    测试插件连接并调用工具验证功能
    
    测试流程:
    1. 测试MCP服务器连接
    2. 获取工具列表
    3. 自动选择一个工具进行实际调用测试
    4. 返回完整测试结果
    """
    import time
    
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    if not plugin.enabled:
        return MCPTestResult(
            success=False,
            message="插件未启用",
            error="请先启用插件",
            suggestions=["点击开关按钮启用插件"]
        )
    
    start_time = time.time()
    
    try:
        # 1. 确保插件已加载
        if not mcp_registry.get_client(user.user_id, plugin.plugin_name):
            success = await mcp_registry.load_plugin(plugin)
            if not success:
                return MCPTestResult(
                    success=False,
                    message="插件加载失败",
                    error="无法创建MCP客户端",
                    suggestions=["请检查插件配置", "请确认服务器URL正确"]
                )
        
        # 2. 测试连接并获取工具列表
        test_result = await mcp_registry.test_plugin(user.user_id, plugin.plugin_name)
        
        if not test_result["success"]:
            plugin.status = "error"
            plugin.last_error = test_result.get("error", "连接测试失败")
            plugin.last_test_at = datetime.now()
            await db.commit()
            return MCPTestResult(**test_result)
        
        tools = test_result.get("tools", [])
        
        if not tools:
            plugin.status = "error"
            plugin.last_error = "插件没有提供任何工具"
            plugin.last_test_at = datetime.now()
            await db.commit()
            
            return MCPTestResult(
                success=False,
                message="插件没有提供任何工具",
                error="工具列表为空",
                response_time_ms=test_result.get("response_time_ms"),
                suggestions=["请检查插件配置", "请确认MCP服务器正常运行"]
            )
        
        # 3. 使用AI智能选择工具并生成测试参数
        logger.info(f"使用AI分析工具并生成测试计划...")
        
        # 获取用户的AI设置
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user.user_id)
        )
        user_settings = settings_result.scalar_one_or_none()
        
        if not user_settings or not user_settings.api_key:
            # 如果没有AI配置，回退到简单测试
            logger.warning("用户未配置AI服务，使用简单连接测试")
            plugin.status = "active"
            plugin.last_error = None
            plugin.last_test_at = datetime.now()
            plugin.tools = tools
            await db.commit()
            
            return MCPTestResult(
                success=True,
                message=f"✅ 连接测试成功（未配置AI，跳过工具调用测试）",
                response_time_ms=test_result.get("response_time_ms"),
                tools_count=len(tools),
                suggestions=[
                    f"连接测试: 成功",
                    f"可用工具数: {len(tools)}",
                    "提示: 配置AI服务后可进行智能工具调用测试"
                ]
            )
        
        # 使用AI的标准Function Calling机制选择工具
        ai_service = create_user_ai_service(
            api_provider=user_settings.api_provider,
            api_key=user_settings.api_key,
            api_base_url=user_settings.api_base_url,
            model_name=user_settings.llm_model,
            temperature=0.3,
            max_tokens=1000
        )
        
        # 将MCP工具格式转换为OpenAI Function Calling格式
        openai_tools = []
        for tool in tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                }
            }
            # 将 inputSchema 转换为 parameters
            if "inputSchema" in tool:
                openai_tool["function"]["parameters"] = tool["inputSchema"]
            
            openai_tools.append(openai_tool)
        
        logger.info(f"转换了 {len(openai_tools)} 个MCP工具为OpenAI格式")
        logger.info(f"工具列表: {[t['function']['name'] for t in openai_tools]}")
        
        # 使用标准的Function Calling，将转换后的工具传递给AI
        prompt = f"""你是MCP插件测试助手，需要测试插件 '{plugin.plugin_name}' 的功能。

请选择一个合适的工具进行测试，优先选择搜索、查询类工具。
生成真实有效的测试参数（例如搜索"人工智能最新进展"而不是"test"）。

现在开始测试这个插件。"""

        system_prompt = "你是专业的API测试工具。当给定工具列表时，选择一个工具并使用合适的参数调用它。"
        
        # 调用AI的Function Calling
        logger.info(f"📞 准备调用AI Function Calling")
        logger.info(f"  - Provider: {user_settings.api_provider}")
        logger.info(f"  - Model: {user_settings.llm_model}")
        logger.info(f"  - Tools count: {len(openai_tools)}")
        logger.debug(f"  - Tools: {json.dumps(openai_tools, ensure_ascii=False, indent=2)}")
        
        ai_response = await ai_service.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            tools=openai_tools,  # 传递转换后的OpenAI格式工具
            tool_choice="required"  # 要求AI必须选择一个工具
        )
        
        logger.info(f"📥 收到AI响应")
        logger.info(f"  - Response keys: {list(ai_response.keys())}")
        logger.debug(f"  - Full response: {json.dumps(ai_response, ensure_ascii=False, indent=2)}")
        
        # 检查AI是否请求调用工具
        if not ai_response.get("tool_calls"):
            # AI未调用工具，记录详细信息
            logger.error(f"❌ AI未返回工具调用")
            logger.error(f"  - Response: {ai_response}")
            logger.error(f"  - Content: {ai_response.get('content', 'N/A')}")
            logger.error(f"  - Finish reason: {ai_response.get('finish_reason', 'N/A')}")
            
            plugin.status = "error"
            plugin.last_error = "AI未返回工具调用请求"
            plugin.last_test_at = datetime.now()
            await db.commit()
            
            return MCPTestResult(
                success=False,
                message="❌ AI Function Calling失败",
                error=f"AI未返回工具调用请求。响应: {ai_response.get('content', 'N/A')[:200]}",
                tools_count=len(tools),
                suggestions=[
                    "请确认使用的AI模型支持Function Calling",
                    "OpenAI: 需要gpt-4, gpt-3.5-turbo等模型",
                    "Anthropic: 需要claude-3系列模型",
                    f"当前Provider: {user_settings.api_provider}",
                    f"当前模型: {user_settings.llm_model}",
                    f"AI返回内容: {ai_response.get('content', 'N/A')[:100]}"
                ]
            )
        
        # 获取第一个工具调用
        tool_call = ai_response["tool_calls"][0]
        function = tool_call["function"]
        tool_name = function["name"]
        test_arguments = function["arguments"]
        
        # AI返回的arguments可能是JSON字符串，需要解析
        if isinstance(test_arguments, str):
            try:
                test_arguments = json.loads(test_arguments)
                logger.info(f"✅ 解析AI返回的JSON字符串参数")
            except json.JSONDecodeError as e:
                logger.error(f"❌ 解析AI参数失败: {e}")
                return MCPTestResult(
                    success=False,
                    message="❌ AI返回的参数格式错误",
                    error=f"无法解析参数JSON: {str(e)}",
                    tools_count=len(tools),
                    suggestions=["AI返回的参数不是有效的JSON格式"]
                )
        
        logger.info(f"🤖 AI通过Function Calling选择的工具: {tool_name}")
        logger.info(f"📝 AI生成的参数: {test_arguments}")
        logger.info(f"📝 参数类型: {type(test_arguments).__name__}")
        
        # 4. 使用AI选择的工具和参数调用MCP工具
        call_start = time.time()
        try:
            tool_result = await mcp_registry.call_tool(
                user.user_id,
                plugin.plugin_name,
                tool_name,
                test_arguments
            )
            
            call_end = time.time()
            call_time = round((call_end - call_start) * 1000, 2)
            total_time = round((call_end - start_time) * 1000, 2)
            
            # 6. 测试成功，更新插件状态
            plugin.status = "active"
            plugin.last_error = None
            plugin.last_test_at = datetime.now()
            plugin.tools = tools  # 缓存工具列表
            await db.commit()
            
            # 格式化工具结果用于显示
            result_str = str(tool_result)
            
            # 如果结果太长，截取前800字符
            if len(result_str) > 800:
                result_preview = result_str[:800] + "\n...(结果已截断，完整结果请查看日志)"
            else:
                result_preview = result_str
            
            return MCPTestResult(
                success=True,
                message=f"✅ Function Calling测试成功！工具 '{tool_name}' 调用正常",
                response_time_ms=total_time,
                tools_count=len(tools),
                suggestions=[
                    f"🤖 AI (Function Calling) 选择: {tool_name}",
                    f"📝 AI生成的参数: {json.dumps(test_arguments, ensure_ascii=False)}",
                    f"⏱️ 调用耗时: {call_time}ms",
                    f"📊 返回结果:\n{result_preview}"
                ]
            )
            
        except Exception as call_error:
            call_end = time.time()
            total_time = round((call_end - start_time) * 1000, 2)
            
            logger.warning(f"工具调用失败: {tool_name}, 错误: {call_error}")
            
            # 工具调用失败,但连接成功
            plugin.status = "active"  # 仍标记为active,因为连接是成功的
            plugin.last_error = f"工具调用测试失败: {str(call_error)}"
            plugin.last_test_at = datetime.now()
            plugin.tools = tools
            await db.commit()
            
            return MCPTestResult(
                success=True,  # 连接成功就算测试通过
                message=f"⚠️ 连接成功，但工具调用失败",
                response_time_ms=total_time,
                tools_count=len(tools),
                error=f"工具 '{tool_name}' 调用失败: {str(call_error)}",
                suggestions=[
                    f"✅ 连接测试: 成功",
                    f"❌ 工具调用测试: 失败",
                    f"🤖 AI (Function Calling) 选择: {tool_name}",
                    f"📝 AI生成的参数: {json.dumps(test_arguments, ensure_ascii=False)}",
                    f"❌ 错误: {str(call_error)}",
                    "💡 可能原因: API Key无效、参数错误或服务限制"
                ]
            )
        
    except Exception as e:
        end_time = time.time()
        total_time = round((end_time - start_time) * 1000, 2)
        
        logger.error(f"测试插件失败: {plugin.plugin_name}, 错误: {e}")
        
        plugin.status = "error"
        plugin.last_error = str(e)
        plugin.last_test_at = datetime.now()
        await db.commit()
        
        return MCPTestResult(
            success=False,
            message="❌ 测试失败",
            response_time_ms=total_time,
            error=str(e),
            error_type=type(e).__name__,
            suggestions=["请检查服务器是否在线", "请确认配置正确", "请检查API Key是否有效"]
        )


def _build_test_arguments(tool_name: str, input_schema: dict, plugin_name: str) -> dict:
    """
    根据工具schema智能构造测试参数
    
    Args:
        tool_name: 工具名称
        input_schema: 输入schema
        plugin_name: 插件名称
        
    Returns:
        测试参数字典
    """
    # 针对常见MCP工具的默认测试参数
    test_cases = {
        # Exa搜索工具
        "search": {
            "query": "AI technology",
            "num_results": 3
        },
        "search_and_contents": {
            "query": "artificial intelligence",
            "num_results": 2
        },
        # Brave搜索
        "brave_web_search": {
            "query": "AI news",
            "count": 3
        },
        # Filesystem工具
        "read_file": {
            "path": "README.md"
        },
        "list_directory": {
            "path": "."
        },
    }
    
    # 如果有针对特定工具的测试用例，使用它
    if tool_name in test_cases:
        logger.info(f"使用预定义测试参数: {test_cases[tool_name]}")
        return test_cases[tool_name]
    
    # 否则根据schema自动构造
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])
    
    test_args = {}
    
    for prop_name, prop_schema in properties.items():
        # 只填充必需的参数
        if prop_name not in required:
            continue
            
        prop_type = prop_schema.get("type", "string")
        
        # 根据参数名称和类型猜测合适的测试值
        if "query" in prop_name.lower() or "search" in prop_name.lower():
            test_args[prop_name] = "test query"
        elif "url" in prop_name.lower():
            test_args[prop_name] = "https://example.com"
        elif "path" in prop_name.lower():
            test_args[prop_name] = "."
        elif "count" in prop_name.lower() or "limit" in prop_name.lower() or "num" in prop_name.lower():
            test_args[prop_name] = 3
        elif prop_type == "string":
            test_args[prop_name] = "test"
        elif prop_type == "number" or prop_type == "integer":
            test_args[prop_name] = 1
        elif prop_type == "boolean":
            test_args[prop_name] = True
        elif prop_type == "array":
            test_args[prop_name] = []
        elif prop_type == "object":
            test_args[prop_name] = {}
    
    logger.info(f"自动构造测试参数: {test_args}")
    return test_args


@router.get("/{plugin_id}/tools")
async def get_plugin_tools(
    plugin_id: str,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    获取插件提供的工具列表
    """
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    if not plugin.enabled:
        raise HTTPException(status_code=400, detail="插件未启用")
    
    try:
        tools = await mcp_registry.get_plugin_tools(user.user_id, plugin.plugin_name)
        
        # 更新缓存
        plugin.tools = tools
        await db.commit()
        
        return {
            "plugin_name": plugin.plugin_name,
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        logger.error(f"获取工具列表失败: {plugin.plugin_name}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")


@router.post("/call")
async def call_mcp_tool(
    data: MCPToolCall,
    user: User = Depends(require_login),
    db: AsyncSession = Depends(get_db)
):
    """
    调用MCP工具
    """
    # 获取插件
    result = await db.execute(
        select(MCPPlugin).where(
            MCPPlugin.id == data.plugin_id,
            MCPPlugin.user_id == user.user_id
        )
    )
    plugin = result.scalar_one_or_none()
    
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    
    if not plugin.enabled:
        raise HTTPException(status_code=400, detail="插件未启用")
    
    try:
        # 调用工具
        result = await mcp_registry.call_tool(
            user.user_id,
            plugin.plugin_name,
            data.tool_name,
            data.arguments
        )
        
        return {
            "success": True,
            "plugin_name": plugin.plugin_name,
            "tool_name": data.tool_name,
            "result": result
        }
    except Exception as e:
        logger.error(f"调用工具失败: {plugin.plugin_name}.{data.tool_name}, 错误: {e}")
        raise HTTPException(status_code=500, detail=f"工具调用失败: {str(e)}")