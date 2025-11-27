-- Migration: Add outline_mode to projects table
-- Description: 为项目表添加大纲模式字段,支持一对一和一对多两种模式
-- Date: 2025-11-27

-- 1. 添加 outline_mode 字段
ALTER TABLE projects 
ADD COLUMN outline_mode VARCHAR(20) NOT NULL DEFAULT 'one-to-many';

-- 2. 添加检查约束,确保只能是两个有效值之一
ALTER TABLE projects
ADD CONSTRAINT check_outline_mode 
CHECK (outline_mode IN ('one-to-one', 'one-to-many'));

-- 3. 创建索引以提高查询性能
CREATE INDEX idx_projects_outline_mode ON projects(outline_mode);

-- 4. 为现有项目设置默认模式为一对多(细化模式)
-- 这是因为现有项目大多使用展开功能
UPDATE projects SET outline_mode = 'one-to-many' WHERE outline_mode IS NULL;

-- 5. 添加注释
COMMENT ON COLUMN projects.outline_mode IS '大纲章节模式: one-to-one(传统模式,1大纲→1章节) 或 one-to-many(细化模式,1大纲→N章节)';

-- 验证迁移结果
-- SELECT id, title, outline_mode FROM projects LIMIT 10;