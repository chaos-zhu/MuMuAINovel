-- 迁移写作风格从项目级别到用户级别
-- 将 writing_styles 表的 project_id 字段改为 user_id

-- 步骤1: 添加新的 user_id 字段
ALTER TABLE writing_styles ADD COLUMN user_id VARCHAR(255);

-- 步骤2: 将现有数据从 project_id 映射到 user_id
-- 通过 projects 表关联，将项目的用户ID填充到风格的 user_id
UPDATE writing_styles ws
SET user_id = (
    SELECT p.user_id 
    FROM projects p 
    WHERE p.id = ws.project_id
)
WHERE ws.project_id IS NOT NULL;

-- 步骤3: 添加外键约束
ALTER TABLE writing_styles
ADD CONSTRAINT fk_writing_styles_user
FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

-- 步骤4: 删除旧的 project_id 外键约束
ALTER TABLE writing_styles DROP CONSTRAINT IF EXISTS writing_styles_project_id_fkey;

-- 步骤5: 删除 project_id 列
ALTER TABLE writing_styles DROP COLUMN project_id;

-- 步骤6: 更新注释
COMMENT ON COLUMN writing_styles.user_id IS '所属用户ID（NULL表示全局预设风格）';

-- 验证迁移结果
SELECT 
    COUNT(*) as total_styles,
    COUNT(user_id) as user_styles,
    COUNT(*) FILTER (WHERE user_id IS NULL) as preset_styles
FROM writing_styles;
