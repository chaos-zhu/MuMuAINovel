# 大纲分批续写功能说明

## 概述

优化后的大纲续写功能实现了**分批生成**机制，每批次生成5章大纲。这种方式相比一次性生成所有章节具有以下优势：

## 优势

1. **降低API压力**：分批次调用AI接口，避免单次请求过大导致超时
2. **提高成功率**：小批量生成更稳定，减少因token限制导致的失败
3. **更好的连贯性**：每批次基于最新生成的内容继续，确保剧情连贯
4. **渐进式反馈**：用户可以看到分批次的进度，体验更好
5. **容错性强**：单个批次失败不影响已生成的内容

## 技术实现

### 核心逻辑

```python
# 分批配置
batch_size = 5  # 每批生成5章
total_batches = (total_chapters_to_generate + batch_size - 1) // batch_size

# 批次循环
for batch_num in range(total_batches):
    # 计算当前批次章节数
    current_batch_size = min(batch_size, remaining_chapters)
    
    # 获取最新大纲列表（包括之前批次生成的）
    latest_outlines = await db.execute(...)
    
    # 基于最新上下文生成
    prompt = prompt_service.get_outline_continue_prompt(
        chapter_count=current_batch_size,  # 当前批次数量
        ...
    )
    
    # 保存并提交当前批次
    await db.commit()
```

### 关键特性

1. **动态上下文更新**：每个批次都会获取最新的大纲列表，包括之前批次生成的内容
2. **智能章节数计算**：最后一批会自动调整为剩余章节数（不一定是5章）
3. **历史记录**：每个批次都会记录到 `GenerationHistory` 表，便于追溯
4. **事务安全**：每批次独立提交，确保已生成内容不会丢失

## 使用示例

### API 调用

```bash
POST /api/outlines/generate
Content-Type: application/json

{
  "project_id": "project-uuid",
  "mode": "continue",
  "chapter_count": 15,  # 将分3批生成（5+5+5）
  "theme": "科幻冒险",
  "narrative_perspective": "第三人称",
  "plot_stage": "development",
  "story_direction": "主角开始探索新世界"
}
```

### 生成过程

```
续写15章的执行流程：

批次1: 生成第11-15章 (5章)
  ├─ 获取已有1-10章
  ├─ 基于最近2章剧情
  └─ 提交并保存

批次2: 生成第16-20章 (5章)
  ├─ 获取已有1-15章（包括批次1生成的）
  ├─ 基于最近2章剧情（第14-15章）
  └─ 提交并保存

批次3: 生成第21-25章 (5章)
  ├─ 获取已有1-20章（包括批次1-2生成的）
  ├─ 基于最近2章剧情（第19-20章）
  └─ 提交并保存

结果: 总计新增15章，分3批完成
```

## 日志示例

```
[INFO] 续写大纲 - 项目: abc-123, 已有: 10 章
[INFO] 分批生成计划: 总共15章，分3批，每批5章
[INFO] 开始生成第1/3批，章节范围: 11-15
[INFO] 正在调用AI生成第1批...
[INFO] 第1批生成完成，本批生成5章
[INFO] 开始生成第2/3批，章节范围: 16-20
[INFO] 正在调用AI生成第2批...
[INFO] 第2批生成完成，本批生成5章
[INFO] 开始生成第3/3批，章节范围: 21-25
[INFO] 正在调用AI生成第3批...
[INFO] 第3批生成完成，本批生成5章
[INFO] 续写完成 - 共3批，新增 15 章，总计 25 章
```

## 配置说明

### 批次大小

当前固定为 **5章/批次**，在 `_continue_outline` 函数中定义：

```python
batch_size = 5  # 每批生成5章
```

如需调整，修改此值即可。建议值：
- 3-5章：最佳平衡点，稳定性高
- 6-8章：适合长篇小说，需要更强的AI模型
- 1-2章：超稳定模式，但会增加API调用次数

### 提示词优化

提示词已自动适配分批生成：
- `chapter_count`: 动态调整为当前批次的章节数
- `start_chapter`: 当前批次的起始章节号
- `current_chapter_count`: 实时更新已有章节总数
- `recent_plot`: 基于最新的2章剧情

## 注意事项

1. **API费用**：分批生成会增加API调用次数，但单次token消耗更少
2. **生成时间**：总时间会略长于一次性生成（因为有多次网络请求）
3. **连贯性**：通过获取最新上下文确保连贯性，实际效果可能优于一次性生成
4. **中断恢复**：如果某批次失败，已生成的批次内容会保留

## 未来优化方向

1. **可配置批次大小**：允许用户通过API参数自定义批次大小
2. **并行生成**：对于独立的批次可以考虑并行生成（需要仔细设计）
3. **进度推送**：通过WebSocket或SSE实时推送生成进度
4. **智能批次调整**：根据已有章节数和剩余章节数智能调整批次大小

## 相关文件

- **实现文件**: `backend/app/api/outlines.py` - `_continue_outline()` 函数
- **提示词模板**: `backend/app/services/prompt_service.py` - `OUTLINE_CONTINUE_GENERATION`
- **Schema定义**: `backend/app/schemas/outline.py` - `OutlineGenerateRequest`