-- 创建提示词模板表
CREATE TABLE IF NOT EXISTS prompt_templates (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    template_name VARCHAR(200) NOT NULL,
    template_content TEXT NOT NULL,
    description TEXT,
    category VARCHAR(50),
    parameters TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    is_system_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uk_user_template UNIQUE (user_id, template_key)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_user_template ON prompt_templates(user_id, template_key);
CREATE INDEX IF NOT EXISTS idx_user_id ON prompt_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_category ON prompt_templates(category);

-- 添加注释
COMMENT ON TABLE prompt_templates IS '提示词模板表';
COMMENT ON COLUMN prompt_templates.user_id IS '用户ID';
COMMENT ON COLUMN prompt_templates.template_key IS '模板键名';
COMMENT ON COLUMN prompt_templates.template_name IS '模板显示名称';
COMMENT ON COLUMN prompt_templates.template_content IS '模板内容';
COMMENT ON COLUMN prompt_templates.description IS '模板描述';
COMMENT ON COLUMN prompt_templates.category IS '模板分类';
COMMENT ON COLUMN prompt_templates.parameters IS '模板参数定义(JSON)';
COMMENT ON COLUMN prompt_templates.is_active IS '是否启用';
COMMENT ON COLUMN prompt_templates.is_system_default IS '是否为系统默认模板';