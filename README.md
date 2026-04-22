# Puzzle Demo

一个以谜题编辑器为核心的实验仓库，当前推荐从 `v1/` 入口开始使用。

这个仓库现在主要包含三部分：

- `v1/`：当前主用的 V1 编辑器页面
- `v1/node-bridge/`：可选的本地求解桥接层
- `backend/`：可选的 AI agent 后端

如果你只是想本地打开 demo 试玩或编辑关卡，可以先完全跳过 AI 相关部分。

## 仓库结构

- `v1/`
  当前主要演示目录，包含编辑器页面、规则包、前端求解器适配层和 AI 面板
- `v1/node-bridge/`
  本地 Node 桥接服务。默认会尝试调用 Java 求解器，失败时回退到内置 JS 求解器
- `backend/`
  FastAPI + LangGraph 的 AI agent 后端，给 `v1` 的聊天/分析/修改能力提供接口
- `v1/java-solver/`
  Java 求解器骨架
- `puzzle_grid_editor.html`、`src/`、`dist/`
  早期编辑器与旧实验代码

## 本地运行（无需依赖 AI）

这是最推荐的快速上手方式。

### 依赖

- Node.js 18+（建议）
- 现代浏览器

### 启动步骤

1. 进入仓库根目录

```powershell
git clone <your-repo-url>
cd puzzle-demo
```

2. 启动本地静态服务

```powershell
node serve-v1-local.mjs
```

3. 在浏览器打开

- [http://127.0.0.1:8000/v1/index.html](http://127.0.0.1:8000/v1/index.html)

### 这一模式下你能做什么

- 打开 `v1` 编辑器
- 编辑棋盘、物体、区域
- 导入导出 JSON
- 做规则校验
- 使用前端内置求解能力进行基础求解和回放

### 说明

- 这条路径不依赖 `backend/`
- 这条路径不依赖 Conda
- 这条路径也不要求先安装 AI 相关 Python 包
- 对 GitHub 访客来说，先跑这条路径最稳

### 可选：再开本地 Node bridge

如果你希望把 `v1` 页面接到本地 Node 求解桥接层，可以额外再开一个终端：

```powershell
cd v1\node-bridge
npm start
```

或者在 Windows 上直接运行：

```powershell
v1\start-v1.cmd
```

默认健康检查地址：

- [http://127.0.0.1:3210/health](http://127.0.0.1:3210/health)

注意：`node-bridge` 是可选项，不开也可以先用。

## 如果要接入 Agent / AI 后端

这部分是给想启用右侧 AI 助手、聊天分析、异步修改任务的人准备的。

### 你还需要准备什么

- Node.js
- Conda 或 Miniconda
- 一个可用的模型 API Key

当前后端默认按 DashScope 兼容 OpenAI 接口来配置，默认模型是 `qwen-flash`。

后端代码也支持这些环境变量名：

- API Key：`DASHSCOPE_API_KEY`、`LLM_API_KEY`、`OPENAI_API_KEY`
- 模型名：`LLM_MODEL`、`DASHSCOPE_MODEL`、`OPENAI_MODEL`
- Base URL：`LLM_BASE_URL`
- 其他：`LLM_MAX_TOKENS`、`LLM_TEMPERATURE`

### 安装步骤

1. 创建并激活 Conda 环境

```powershell
conda create -n puzzle-ai python=3.11 -y
conda activate puzzle-ai
```

2. 安装后端依赖

```powershell
pip install -r backend/requirements.txt
```

3. 配置 API Key

如果你用 DashScope，可以这样设置：

```powershell
setx DASHSCOPE_API_KEY "your_key"
```

设置完成后，重新打开一个新的终端窗口再继续。

如果你接的是别的 OpenAI-compatible 服务，通常需要设置这些变量：

```powershell
setx LLM_API_KEY "your_key"
setx LLM_BASE_URL "https://your-provider.example.com/v1"
setx LLM_MODEL "your-model-name"
```

### 启动方式

最省事的方式是直接运行：

```powershell
v1\start-v1-ai.cmd
```

这个脚本会尝试同时启动：

- 静态网页：`http://127.0.0.1:8000/v1/index.html`
- Node bridge：`http://127.0.0.1:3210/health`
- AI 后端：`http://127.0.0.1:8011/health`

### 手动启动方式

如果你想分开排查，也可以手动启动：

1. 终端 A：启动网页

```powershell
cd puzzle-demo
node serve-v1-local.mjs
```

2. 终端 B：启动 Node bridge

```powershell
cd puzzle-demo\v1\node-bridge
npm start
```

3. 终端 C：激活 Conda 环境后启动 AI 后端

```powershell
cd puzzle-demo
conda activate puzzle-ai
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8011 --reload
```

### 接入成功后你应该看到什么

- 页面右侧 AI 面板可以正常发起分析请求
- `http://127.0.0.1:8011/health` 返回后端状态
- 后端 health 中会显示当前模型名、base URL、API key 是否存在

## 常见问题

### 1. 我只想把 demo 跑起来，必须装 AI 吗？

不需要。先按“本地运行（无需依赖 AI）”那一节操作就够了。

### 2. 必须先开 Node bridge 吗？

不是必须。对初次体验来说，先开 `serve-v1-local.mjs` 就可以。

### 3. `start-v1-ai.cmd` 没把 AI 后端拉起来怎么办？

优先检查这几项：

- 你是否已经安装并激活了名为 `puzzle-ai` 的 Conda 环境
- `DASHSCOPE_API_KEY`、`LLM_API_KEY` 或 `OPENAI_API_KEY` 是否已经设置
- 设置环境变量后，是否重新打开了终端
- `pip install -r backend/requirements.txt` 是否已经执行成功

### 4. 上传到 GitHub 后，别人点开仓库就能直接在线用 AI 吗？

不能直接保证。

把仓库上传到 GitHub 只能分享代码。  
如果要让别人通过网页直接使用 AI，你还需要把前端和 `backend/` 分别部署到可访问的线上环境，再把前端的 AI 请求地址改成线上 API 地址。

## 补充文档

- [v1/README.md](v1/README.md)
- [v1/node-bridge/README.md](v1/node-bridge/README.md)
- [v1/java-solver/README.md](v1/java-solver/README.md)
