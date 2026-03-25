# AGARS — AI-Generated AI Roleplay Simulator

[English](./README-EN.md) | [中文文档](./README.md)

## 项目介绍

**AGARS** 是基于 [MiroFish](https://github.com/666ghj/MiroFish) 的二次开发项目，专注于 AI 驱动的角色扮演模拟。

项目在 MiroFish 多智能体预测引擎的基础上，新增了**叙事引擎**（Narrative Engine）系统，支持以沉浸式的叙事视角体验模拟过程。同时引入 **FalkorDB 本地知识图谱**替代纯云端方案，增加了 **LLM 调用监控**、**Prompt 配置管理**等功能。

## 演示视频
  <div align="center">
    <a href="https://www.bilibili.com/video/BV1MBXwBSEvp" target="_blank">
      <img src="./static/image/视频封面.png" width="600" alt="演示视频"/>
    </a>
  </div>

### 核心功能

- **多智能体模拟**：基于种子材料自动构建数字世界，智能体具备独立人格与长期记忆
- **叙事引擎**：将模拟过程转化为可交互的叙事体验
- **知识图谱**：支持 Zep Cloud 与 FalkorDB 本地图谱双模式
- **报告生成**：模拟结束后自动生成分析报告
- **深度交互**：与模拟世界中的任意角色对话

## 环境配置

### 前置要求

| 工具 | 版本要求 | 说明 |
|------|---------|------|
| **Node.js** | >= 18 | 前端运行环境 |
| **Python** | >= 3.11 | 后端运行环境 |
| **uv** | 最新版 | Python 包管理器 |
| **Docker** | 最新版 | 用于运行 FalkorDB |

LLM API 需兼容 OpenAI SDK 格式，并支持 `response_format` 的 `json_schema` 模式（结构化输出）。

### 1. 启动 FalkorDB

```bash
docker run -d --name falkordb -p 6379:6379 falkordb/falkordb
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下配置：

| 变量 | 必需 | 说明 |
|------|------|------|
| `LLM_API_KEY` | 是 | LLM API 密钥 |
| `LLM_BASE_URL` | 是 | LLM API 地址（OpenAI SDK 格式） |
| `LLM_MODEL_NAME` | 是 | 模型名称 |
| `ZEP_API_KEY` | 是 | Zep Cloud API 密钥（[免费注册](https://app.getzep.com/)） |
| `EMBEDDING_API_KEY` | 是 | Embedding 模型密钥，需支持 `/embeddings` 接口 |
| `EMBEDDING_BASE_URL` | 是 | Embedding API 地址 |
| `EMBEDDING_MODEL_NAME` | 是 | Embedding 模型名称（推荐 `text-embedding-3-small`） |
| `FALKORDB_HOST` | 否 | FalkorDB 地址（默认 `localhost`） |
| `FALKORDB_PORT` | 否 | FalkorDB 端口（默认 `6379`） |
| `FALKORDB_PASSWORD` | 否 | FalkorDB 密码（默认为空） |

### 3. 安装依赖

```bash
# 一键安装所有依赖（Node + Python）
npm run setup:all
```

### 4. 启动服务

```bash
npm run dev
```

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

### Docker 部署

也可以使用 Docker Compose 一键部署：

```bash
cp .env.example .env
# 编辑 .env 填入配置
docker compose up -d
```

## 致谢

本项目基于以下开源项目构建，感谢这些项目的贡献：

- **[MiroFish](https://github.com/666ghj/MiroFish)** — 群体智能预测引擎，本项目的基础框架
- **[OASIS](https://github.com/camel-ai/oasis)** / **[CAMEL-AI](https://github.com/camel-ai/camel)** — 多智能体社交模拟框架
- **[Graphiti](https://github.com/getzep/graphiti)** — 知识图谱构建引擎
- **[Zep](https://github.com/getzep/zep)** — 智能体长期记忆服务
- **[FalkorDB](https://github.com/FalkorDB/FalkorDB)** — 高性能图数据库
- **[D3.js](https://github.com/d3/d3)** — 数据可视化库

## 许可证

本项目基于 [AGPL-3.0](./LICENSE) 许可证开源。
