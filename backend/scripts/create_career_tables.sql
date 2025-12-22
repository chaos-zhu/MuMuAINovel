-- 职业体系模块数据库迁移脚本（PostgreSQL版本）
-- 创建时间: 2025-12-20
-- 说明: 添加职业表和角色职业关联表

-- ===== 1. 创建职业表 =====
CREATE TABLE IF NOT EXISTS careers (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL,
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,  -- 职业类型: main(主职业)/sub(副职业)
    description TEXT,  -- 职业描述
    category VARCHAR(50),  -- 职业分类（如：战斗系、生产系、辅助系）
    
    -- 阶段设定
    stages TEXT NOT NULL,  -- 职业阶段列表(JSON): [{"level":1, "name":"", "description":""}, ...]
    max_stage INT NOT NULL DEFAULT 10,  -- 最大阶段数
    
    -- 职业特性
    requirements TEXT,  -- 职业要求/限制
    special_abilities TEXT,  -- 特殊能力描述
    worldview_rules TEXT,  -- 世界观规则关联
    
    -- 职业属性加成（可选，JSON格式）
    attribute_bonuses TEXT,  -- 属性加成(JSON): {"strength": "+10%", "intelligence": "+5%"}
    
    -- 元数据
    source VARCHAR(20) DEFAULT 'ai',  -- 来源: ai/manual
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 更新时间
    
    -- 外键约束
    CONSTRAINT fk_career_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_careers_project_id ON careers(project_id);
CREATE INDEX IF NOT EXISTS idx_careers_type ON careers(type);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_careers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_careers_updated_at
    BEFORE UPDATE ON careers
    FOR EACH ROW
    EXECUTE FUNCTION update_careers_updated_at();

-- 添加表注释
COMMENT ON TABLE careers IS '职业表';
COMMENT ON COLUMN careers.name IS '职业名称';
COMMENT ON COLUMN careers.type IS '职业类型: main(主职业)/sub(副职业)';
COMMENT ON COLUMN careers.description IS '职业描述';
COMMENT ON COLUMN careers.category IS '职业分类（如：战斗系、生产系、辅助系）';
COMMENT ON COLUMN careers.stages IS '职业阶段列表(JSON)';
COMMENT ON COLUMN careers.max_stage IS '最大阶段数';
COMMENT ON COLUMN careers.requirements IS '职业要求/限制';
COMMENT ON COLUMN careers.special_abilities IS '特殊能力描述';
COMMENT ON COLUMN careers.worldview_rules IS '世界观规则关联';
COMMENT ON COLUMN careers.attribute_bonuses IS '属性加成(JSON)';
COMMENT ON COLUMN careers.source IS '来源: ai/manual';
COMMENT ON COLUMN careers.created_at IS '创建时间';
COMMENT ON COLUMN careers.updated_at IS '更新时间';

-- ===== 2. 创建角色职业关联表 =====
CREATE TABLE IF NOT EXISTS character_careers (
    id VARCHAR(36) PRIMARY KEY,
    character_id VARCHAR(36) NOT NULL,
    career_id VARCHAR(36) NOT NULL,
    career_type VARCHAR(20) NOT NULL,  -- main(主职业)/sub(副职业)
    
    -- 阶段进度
    current_stage INT NOT NULL DEFAULT 1,  -- 当前阶段（对应职业中的数值）
    stage_progress INT DEFAULT 0,  -- 阶段内进度（0-100）
    
    -- 时间记录
    started_at VARCHAR(100),  -- 开始修炼时间（小说时间线）
    reached_current_stage_at VARCHAR(100),  -- 到达当前阶段时间
    
    -- 备注
    notes TEXT,  -- 备注（如：修炼心得、特殊事件）
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 更新时间
    
    -- 外键约束
    CONSTRAINT fk_charcareer_character FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
    CONSTRAINT fk_charcareer_career FOREIGN KEY (career_id) REFERENCES careers(id) ON DELETE CASCADE,
    
    -- 唯一约束：一个角色不能重复拥有同一个职业
    CONSTRAINT uk_character_career UNIQUE (character_id, career_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_character_careers_character_id ON character_careers(character_id);
CREATE INDEX IF NOT EXISTS idx_character_careers_career_type ON character_careers(career_type);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_character_careers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_character_careers_updated_at
    BEFORE UPDATE ON character_careers
    FOR EACH ROW
    EXECUTE FUNCTION update_character_careers_updated_at();

-- 添加表注释
COMMENT ON TABLE character_careers IS '角色职业关联表';
COMMENT ON COLUMN character_careers.career_type IS 'main(主职业)/sub(副职业)';
COMMENT ON COLUMN character_careers.current_stage IS '当前阶段（对应职业中的数值）';
COMMENT ON COLUMN character_careers.stage_progress IS '阶段内进度（0-100）';
COMMENT ON COLUMN character_careers.started_at IS '开始修炼时间（小说时间线）';
COMMENT ON COLUMN character_careers.reached_current_stage_at IS '到达当前阶段时间';
COMMENT ON COLUMN character_careers.notes IS '备注（如：修炼心得、特殊事件）';

-- ===== 3. 扩展角色表（添加冗余字段，可选） =====
-- 注意：这部分是可选的，用于提升查询性能
-- 检查字段是否存在，如果不存在则添加

DO $$ 
BEGIN
    -- 添加 main_career_id 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='characters' AND column_name='main_career_id') THEN
        ALTER TABLE characters ADD COLUMN main_career_id VARCHAR(36);
        COMMENT ON COLUMN characters.main_career_id IS '主职业ID';
    END IF;
    
    -- 添加 main_career_stage 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='characters' AND column_name='main_career_stage') THEN
        ALTER TABLE characters ADD COLUMN main_career_stage INT;
        COMMENT ON COLUMN characters.main_career_stage IS '主职业当前阶段';
    END IF;
    
    -- 添加 sub_careers 字段
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='characters' AND column_name='sub_careers') THEN
        ALTER TABLE characters ADD COLUMN sub_careers TEXT;
        COMMENT ON COLUMN characters.sub_careers IS '副职业列表(JSON): [{"career_id": "xxx", "stage": 3}, ...]';
    END IF;
END $$;

-- 添加外键约束（如果需要）
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name='fk_main_career' AND table_name='characters') THEN
        ALTER TABLE characters
        ADD CONSTRAINT fk_main_career 
        FOREIGN KEY (main_career_id) REFERENCES careers(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ===== 4. 创建视图（可选，便于查询） =====
CREATE OR REPLACE VIEW v_character_career_details AS
SELECT 
    cc.id AS relation_id,
    cc.character_id,
    c.name AS character_name,
    cc.career_id,
    ca.name AS career_name,
    ca.type AS career_type_name,
    cc.career_type,
    cc.current_stage,
    ca.max_stage,
    cc.stage_progress,
    cc.started_at,
    cc.reached_current_stage_at,
    cc.notes,
    ca.description AS career_description,
    ca.category AS career_category,
    ca.stages AS career_stages_json,
    cc.created_at,
    cc.updated_at
FROM character_careers cc
JOIN characters c ON cc.character_id = c.id
JOIN careers ca ON cc.career_id = ca.id
ORDER BY cc.career_type DESC, cc.created_at;

COMMENT ON VIEW v_character_career_details IS '角色职业详细信息视图';

-- ===== 5. 插入测试数据（可选） =====
-- 这里可以插入一些示例职业数据用于测试
-- 注意：project_id需要替换为实际存在的项目ID

/*
-- 示例：修仙类主职业
INSERT INTO careers (id, project_id, name, type, description, category, stages, max_stage, requirements, special_abilities, worldview_rules, source) 
VALUES (
    gen_random_uuid()::text,
    'YOUR_PROJECT_ID_HERE',
    '剑修',
    'main',
    '以剑入道，追求极致剑意，是修仙界最强大的战斗职业之一。',
    '战斗系',
    '[
        {"level": 1, "name": "炼气期", "description": "初窥门径，凝聚剑气"},
        {"level": 2, "name": "筑基期", "description": "根基稳固，剑气成形"},
        {"level": 3, "name": "金丹期", "description": "凝结金丹，剑意初显"},
        {"level": 4, "name": "元婴期", "description": "元婴成就，剑意大成"},
        {"level": 5, "name": "化神期", "description": "化神蜕变，剑道通神"},
        {"level": 6, "name": "炼虚期", "description": "炼虚合道，剑破虚空"},
        {"level": 7, "name": "合体期", "description": "天人合一，剑心合道"},
        {"level": 8, "name": "大乘期", "description": "大乘境界，剑开天地"},
        {"level": 9, "name": "渡劫期", "description": "渡劫飞升，剑斩天劫"},
        {"level": 10, "name": "仙人", "description": "飞升成仙，剑意永恒"}
    ]',
    10,
    '需要剑道天赋，坚韧不拔的意志',
    '剑气纵横、剑意凌云、御剑飞行',
    '符合修仙世界观，属于正统修炼体系',
    'ai'
);

-- 示例：副职业
INSERT INTO careers (id, project_id, name, type, description, category, stages, max_stage, requirements, special_abilities, source) 
VALUES (
    gen_random_uuid()::text,
    'YOUR_PROJECT_ID_HERE',
    '炼丹师',
    'sub',
    '精通丹药炼制，能够炼制各种增强修为、疗伤、辅助的丹药。',
    '生产系',
    '[
        {"level": 1, "name": "学徒", "description": "初学炼丹，成功率较低"},
        {"level": 2, "name": "初级炼丹师", "description": "可炼制基础丹药"},
        {"level": 3, "name": "中级炼丹师", "description": "可炼制进阶丹药"},
        {"level": 4, "name": "高级炼丹师", "description": "可炼制高级丹药"},
        {"level": 5, "name": "宗师级炼丹师", "description": "炉火纯青，可炼制顶级丹药"}
    ]',
    5,
    '需要对火候的精准掌控和丰富的药材知识',
    '丹药炼制、药性分析、丹劫应对',
    'ai'
);
*/

-- ===== 完成提示 =====
DO $$ 
BEGIN
    RAISE NOTICE '职业体系数据库表创建完成！';
    RAISE NOTICE '职业表记录数: %', (SELECT COUNT(*) FROM careers);
    RAISE NOTICE '角色职业关联表记录数: %', (SELECT COUNT(*) FROM character_careers);
END $$;