# MuMuAINovel 📚✨

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green.svg)
![React](https://img.shields.io/badge/react-18.3.1-blue.svg)
![TypeScript](https://img.shields.io/badge/typescript-5.9.3-blue.svg)
![License](https://img.shields.io/badge/license-GPL%20v3-blue.svg)

**一款基于 AI 的智能小说创作助手，帮助你轻松创作精彩故事**

[特性](## ✨ 特性) • [快速开始](#快速开始) • [部署方式](#部署方式) • [配置说明](#配置说明) • [项目结构](#项目结构)

</div>

---

## ✨ 特性

- 🤖 **多 AI 模型支持** - 支持 OpenAI、Google Gemini、Anthropic Claude 等主流 AI 模型
- 📝 **智能向导** - 通过向导式引导快速创建小说项目，AI 自动生成大纲、角色和世界观
- 👥 **角色管理** - 创建和管理小说角色，包括人物关系、组织架构等
- 📖 **章节编辑** - 支持章节的创建、编辑、重新生成和润色功能
- 🌐 **世界观设定** - 构建完整的故事世界观和背景设定
- 🔐 **多种登录方式** - 支持 LinuxDO OAuth 登录和本地账户登录
- 🐳 **Docker 部署** - 一键部署，开箱即用
- 💾 **数据持久化** - 基于 SQLite 的本地数据存储，支持多用户隔离
- 🎨 **现代化 UI** - 基于 Ant Design 的美观界面，响应式设计

## 🚀 快速开始

### 前置要求

- **Docker 部署**：Docker 和 Docker Compose
- **本地开发**：Python 3.11+ 和 Node.js 18+
- **必需**：至少一个 AI 服务的 API Key（OpenAI/Gemini/Anthropic）

### 方式一：从源码构建 Docker 镜像

```bash
# 1. 克隆项目
git clone https://github.com/xiamuceer-j/MuMuAINovel.git
cd MuMuAINovel

# 2. 配置环境变量
cp backend/.env.example .env
# 编辑 .env 文件，填入你的 API Keys

# 3. 启动服务（会自动构建镜像）
docker-compose up -d

# 4. 访问应用
# 打开浏览器访问 http://localhost:8000
```

### 方式二：本地开发

#### 后端设置

```bash
# 进入后端目录
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的配置

# 启动后端服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 前端设置

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 开发模式（需要后端已启动）
npm run dev

# 或构建生产版本
npm run build
```

## 🐳 部署方式

### Docker Compose 部署

#### 使用 Docker Hub 镜像（推荐）

项目已发布到 Docker Hub，可直接拉取使用：

```bash
# 查看可用版本
docker pull mumujie/mumuainovel:latest

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 更新到最新版本
docker-compose pull
docker-compose up -d
```

#### Docker Compose 配置文件示例

使用 Docker Hub 镜像的完整配置：

```yaml
services:
  ai-story:
    image: mumujie/mumuainovel:latest
    container_name: mumuainovel
    ports:
      - "8800:8000"  # 宿主机端口:容器端口
    volumes:
      # 持久化数据库和日志
      - ./data:/app/data
      - ./logs:/app/logs
      # 挂载环境变量文件
      - ./.env:/app/.env:ro
    environment:
      - APP_NAME=mumuainovel
      - APP_VERSION=1.0.0
      - APP_HOST=0.0.0.0
      - APP_PORT=8000
      - DEBUG=false
      # 其他环境变量会从 .env 文件自动加载
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    networks:
      - ai-story-network

networks:
  ai-story-network:
    driver: bridge
```

### 生产环境部署建议

#### 1. 环境变量配置

**必需配置**：
- `OPENAI_API_KEY` 或 `GEMINI_API_KEY`：至少配置一个 AI 服务
- `LOCAL_AUTH_PASSWORD`：修改为强密码

**推荐配置**：
- `OPENAI_BASE_URL`：如果使用中转 API，修改为中转服务地址
- `DEFAULT_AI_PROVIDER`：根据你的 API Key 选择 `openai`、`gemini` 或 `anthropic`
- `DEFAULT_MODEL`：选择合适的模型（如 `gpt-4o-mini`、`gemini-2.0-flash-exp`）

#### 2. 数据持久化

数据目录已通过 volume 挂载，数据不会丢失：
- `./data`：SQLite 数据库文件
- `./logs`：应用日志文件

#### 3. 端口配置

默认端口映射：`8800:8000`
- 宿主机端口：`8800`（可自定义修改）
- 容器内端口：`8000`（固定，不要修改）

访问地址：`http://your-server-ip:8800`

#### 4. 反向代理配置（Nginx）

推荐使用 Nginx 配置 HTTPS：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8800;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 支持 SSE（服务器推送事件）
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

配置后记得更新 `.env` 中的 `LINUXDO_REDIRECT_URI` 和 `FRONTEND_URL`。

#### 5. 资源限制（可选）

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  ai-story:
    # ... 其他配置
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 端口说明

- **默认端口**：`8800`（宿主机）→ `8000`（容器）
- **可自定义**：修改 docker-compose.yml 中的 `ports` 配置
- **健康检查**：容器内部使用 `8000` 端口进行健康检查

## ⚙️ 配置说明

### 环境变量

创建 `.env` 文件并配置以下变量：

```bash
# ===== AI 服务配置（必填）=====
# OpenAI 配置（支持官方API和中转API）
OPENAI_API_KEY=your_openai_key_here
OPENAI_BASE_URL=https://api.openai.com/v1

# Google Gemini 配置（推荐，免费额度大）
# GEMINI_API_KEY=your_gemini_key_here

# Anthropic 配置
# ANTHROPIC_API_KEY=your_anthropic_key_here
# ANTHROPIC_BASE_URL=https://api.anthropic.com

# 中转API配置示例（使用OpenAI格式）
# New API 中转服务
# OPENAI_API_KEY=your_newapi_key_here
# OPENAI_BASE_URL=https://api.new-api.com/v1

# API2D 中转服务
# OPENAI_API_KEY=your_api2d_key_here
# OPENAI_BASE_URL=https://api.api2d.com/v1

# OpenAI-SB 中转服务
# OPENAI_API_KEY=your_openai_sb_key_here
# OPENAI_BASE_URL=https://api.openai-sb.com/v1

# 其他支持 OpenAI 格式的中转服务
# OPENAI_API_KEY=your_api_key_here
# OPENAI_BASE_URL=https://your-api-proxy.com/v1

# 默认 AI 提供商和模型
DEFAULT_AI_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini
DEFAULT_TEMPERATURE=0.8
DEFAULT_MAX_TOKENS=32000

# ===== 应用配置 =====
APP_NAME=MuMuAINovel
APP_VERSION=1.0.0
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=false

# ===== LinuxDO OAuth 配置（可选）=====
LINUXDO_CLIENT_ID=your_client_id_here
LINUXDO_CLIENT_SECRET=your_client_secret_here
LINUXDO_REDIRECT_URI=http://localhost:8000/api/auth/callback
FRONTEND_URL=http://localhost:8000

# ===== 本地账户登录配置 =====
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=your_secure_password_here
LOCAL_AUTH_DISPLAY_NAME=管理员

# ===== CORS 配置（生产环境）=====
# CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

### AI 模型配置

项目支持多个 AI 提供商，你可以根据需要配置：

| 提供商 | 推荐模型 | 用途 |
|--------|---------|------|
| OpenAI | gpt-4, gpt-3.5-turbo | 高质量文本生成 |
| Anthropic | claude-3-opus, claude-3-sonnet | 长文本创作 |

#### 使用中转API服务

如果你无法直接访问 OpenAI 官方 API，或者想使用更经济实惠的中转服务，本项目完全支持各种 OpenAI 兼容格式的中转 API：

##### 配置方法

只需修改 `.env` 文件中的两个参数：

```bash
# 1. 填入中转服务提供的 API Key
OPENAI_API_KEY=your_api_key_from_proxy_service

# 2. 修改 Base URL 为中转服务的地址
OPENAI_BASE_URL=https://your-proxy-service.com/v1
```

##### 常见中转服务配置示例

**New API**
```bash
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.new-api.com/v1
```

**API2D**
```bash
OPENAI_API_KEY=fk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.api2d.com/v1
```

**OpenAI-SB**
```bash
OPENAI_API_KEY=sb-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai-sb.com/v1
```

**自建 One API / New API**
```bash
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://your-domain.com/v1
```

##### 注意事项

- ✅ 所有支持 OpenAI 接口格式的服务都可以使用
- ✅ 确保中转服务的 Base URL 以 `/v1` 结尾
- ✅ 根据中转服务支持的模型，修改 `DEFAULT_MODEL` 参数
- ⚠️ 不同中转服务的模型名称可能不同，请参考服务商文档
- ⚠️ 部分中转服务可能对请求频率或并发有限制

##### 推荐的中转服务

如果你需要中转服务，以下是一些常见选择：

1. **New API** - 开源的 API 分发系统，支持多种模型
2. **API2D** - 国内稳定的 API 中转服务
3. **OpenAI-SB** - 提供多种 AI 模型的中转
4. **自建服务** - 使用 One API 或 New API 自行搭建

> 💡 提示：使用中转服务时，请确保服务提供商的可靠性和数据安全性

### 登录方式配置

#### 本地账户登录（默认启用）

适合个人使用或小型团队：

```bash
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=your_password
```

#### LinuxDO OAuth 登录

适合需要社区集成的场景，需要在 [LinuxDO](https://linux.do) 注册 OAuth 应用：

```bash
LINUXDO_CLIENT_ID=your_client_id
LINUXDO_CLIENT_SECRET=your_client_secret
LINUXDO_REDIRECT_URI=http://your-domain:8000/api/auth/callback
```

## 📁 项目结构

```
MuMuAINovel/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/               # API 路由
│   │   │   ├── auth.py        # 认证接口
│   │   │   ├── projects.py    # 项目管理
│   │   │   ├── chapters.py    # 章节管理
│   │   │   ├── characters.py  # 角色管理
│   │   │   ├── wizard_stream.py # 向导流式生成
│   │   │   └── ...
│   │   ├── models/            # 数据模型
│   │   ├── schemas/           # Pydantic 模型
│   │   ├── services/          # 业务逻辑
│   │   │   ├── ai_service.py  # AI 服务封装
│   │   │   └── oauth_service.py # OAuth 服务
│   │   ├── middleware/        # 中间件
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   └── main.py            # 应用入口
│   ├── data/                  # 数据存储目录
│   ├── static/                # 前端静态文件（构建后）
│   ├── requirements.txt       # Python 依赖
│   └── .env.example           # 环境变量示例
├── frontend/                  # 前端应用
│   ├── src/
│   │   ├── pages/            # 页面组件
│   │   │   ├── ProjectList.tsx      # 项目列表
│   │   │   ├── ProjectWizardNew.tsx # 创建向导
│   │   │   ├── Chapters.tsx         # 章节管理
│   │   │   ├── Characters.tsx       # 角色管理
│   │   │   └── ...
│   │   ├── components/       # 通用组件
│   │   ├── services/         # API 服务
│   │   ├── store/           # 状态管理（Zustand）
│   │   ├── types/           # TypeScript 类型
│   │   └── utils/           # 工具函数
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml         # Docker Compose 配置
├── Dockerfile                 # Docker 镜像构建
└── README.md                  # 项目说明文档
```

## 🛠️ 技术栈

### 后端

- **框架**：FastAPI 0.109.0
- **数据库**：SQLite + SQLAlchemy（异步）
- **AI 集成**：OpenAI、Anthropic、Google Gemini SDK
- **认证**：LinuxDO OAuth2、本地账户
- **日志**：Python logging + 文件轮转

### 前端

- **框架**：React 18.3 + TypeScript
- **UI 库**：Ant Design 5.27
- **路由**：React Router 6.28
- **状态管理**：Zustand 5.0
- **HTTP 客户端**：Axios
- **构建工具**：Vite 7.1

## 📖 使用指南

### 创建第一个小说项目

1. **登录系统**
   - 使用本地账户或 LinuxDO 账户登录

2. **创建项目**
   - 点击"创建项目"按钮
   - 选择"使用向导创建"或"手动创建"

3. **使用向导（推荐）**
   - 输入小说基本信息（标题、类型、背景等）
   - AI 自动生成大纲、角色和世界观
   - 实时查看生成进度

4. **编辑和完善**
   - 在项目详情页查看和编辑大纲
   - 管理角色和人物关系
   - 生成和编辑章节内容


### API 文档

应用启动后，可访问自动生成的 API 文档：

- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

## 🔧 开发指南

### 后端开发

```bash
cd backend

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows

# 启动开发服务器（热重载）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端开发

```bash
cd frontend

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

### 代码规范

- **后端**：遵循 PEP 8 规范
- **前端**：使用 ESLint + TypeScript 严格模式
- **提交**：建议使用语义化提交信息

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📝 许可证

本项目采用 [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html) 开源协议

**这意味着：**

- ✅ **可以** - 自由使用、复制、修改和分发本项目
- ✅ **可以** - 用于商业目的
- ✅ **可以** - 用于个人学习和研究
- 📝 **必须** - 开源你的修改版本
- 📝 **必须** - 保留原作者版权声明
- 📝 **必须** - 以相同的 GPL v3 协议发布衍生作品

详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架
- [React](https://react.dev/) - 用户界面构建库
- [Ant Design](https://ant.design/) - 企业级 UI 设计语言
- [OpenAI](https://openai.com/) / [Anthropic](https://www.anthropic.com/) - AI 模型提供商

## 📧 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 [Issue](https://github.com/yourusername/MuMuAINovel/issues)
- Linux DO [LD](https://linux.do/t/topic/1100112)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐️ Star 支持一下！**

Made with ❤️

</div>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=xiamuceer-j/MuMuAINovel&type=date&legend=top-left)](https://www.star-history.com/#xiamuceer-j/MuMuAINovel&type=date&legend=top-left)

![Alt](https://repobeats.axiom.co/api/embed/ee7141a5f269c64759302e067abe23b46796bafe.svg "Repobeats analytics image")
