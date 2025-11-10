-- PostgreSQL 初始化脚本
-- 此脚本会在PostgreSQL容器首次启动时自动执行

-- 确保使用UTF8编码
SET client_encoding = 'UTF8';

-- 创建必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 设置时区
SET timezone = 'Asia/Shanghai';

-- 优化配置（这些设置会在容器启动后生效）
-- 注意：部分配置已在docker-compose.yml的command中设置

-- 创建索引优化查询性能（表会由SQLAlchemy自动创建）
-- 这里只是预留空间，实际索引会在应用启动时创建

-- 输出初始化信息
DO $$
BEGIN
    RAISE NOTICE '==================================================';
    RAISE NOTICE 'MuMuAINovel PostgreSQL 数据库初始化完成';
    RAISE NOTICE '数据库名称: mumuai_novel';
    RAISE NOTICE '字符编码: UTF8';
    RAISE NOTICE '时区设置: Asia/Shanghai';
    RAISE NOTICE '扩展已安装: uuid-ossp, pg_trgm';
    RAISE NOTICE '==================================================';
END $$;