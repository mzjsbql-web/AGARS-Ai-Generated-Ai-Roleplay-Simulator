# AGARS — AI-Generated AI Roleplay Simulator

[English](./README-EN.md) | [中文文档](./README.md)

## About

**AGARS** is a project built upon [MiroFish](https://github.com/666ghj/MiroFish), focusing on AI-driven roleplay simulation.

Conventional AI roleplay frontends cram narrative, character roleplay, and world management into a single dialogue turn, severely diluting AI reasoning capacity — then compensate by stacking ever-longer context windows, which is both expensive and lossy. This project separates these tasks into independent agents, each focused on a single job per call, significantly improving output quality. A knowledge graph replaces brute-force context stacking with on-demand retrieval, and tiered model scheduling keeps overall costs comparable to conventional frontends.

### Key Features

- **Task Separation Architecture**: Narrative, character roleplay, and world management are handled by independent agents — instead of cramming everything into a single dialogue turn, the AI focuses on one job at a time, significantly improving reasoning quality
- **Knowledge Graph Memory**: Structured memory via FalkorDB / Zep replaces brute-force context stacking — character relationships and world facts are persisted and retrieved on demand, not dumped wholesale into the prompt
- **AI Plot Planning**: A dedicated planner orchestrates NPC reactions, scene transitions, and new character introductions after each player action, producing dramatic pacing rather than mechanical turn-cycling
- **Dynamic World Modeling**: Map topology, character locations, and item ownership are tracked at the engine level with adjacency-validated movement — world state lives in the runtime, not in the prompt
- **Deep Prompt Control**: Context wrapping and text variable invocation provide highly customizable prompt engineering, with a built-in monitor for real-time inspection of every LLM call for debugging and tuning
- **Cost Efficiency**: Agents are assigned different models and context windows by role; knowledge graph retrieval replaces long-context stacking — overall cost stays comparable to conventional single-turn frontends

## Screenshots

### Narrative Mode
![Narrative Mode](./static/image/叙事模式.jpg)

### Knowledge Graph & Monitor
![Knowledge Graph & Monitor](./static/image/前端monitor.png)

### Prompt Editor
![Prompt Editor](./static/image/prompt编辑.png)

### Message Wrapping
![Message Wrapping](./static/image/消息包装.png)

### Text Variable Reference
![Text Variable Reference](./static/image/变量名说明.png)

### Monitor History
![Monitor History](./static/image/monitor%20history%20page.png)

## Setup

### Prerequisites

| Tool | Version | Description |
|------|---------|-------------|
| **Node.js** | >= 18 | Frontend runtime |
| **Python** | >= 3.11 | Backend runtime |
| **uv** | Latest | Python package manager |
| **Docker** | Latest | Required for running FalkorDB |

The LLM API must be compatible with the OpenAI SDK format and support `response_format` with `json_schema` mode (structured output).

### 1. Start FalkorDB

```bash
docker run -d --name falkordb -p 6379:6379 falkordb/falkordb
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit the `.env` file with the following:

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_API_KEY` | Yes | LLM API key |
| `LLM_BASE_URL` | Yes | LLM API endpoint (OpenAI SDK format) |
| `LLM_MODEL_NAME` | Yes | Model name |
| `ZEP_API_KEY` | Yes | Zep Cloud API key ([free signup](https://app.getzep.com/)) |
| `EMBEDDING_API_KEY` | Yes | Embedding model API key, must support `/embeddings` endpoint |
| `EMBEDDING_BASE_URL` | Yes | Embedding API endpoint |
| `EMBEDDING_MODEL_NAME` | Yes | Embedding model name (recommended: `text-embedding-3-small`) |
| `FALKORDB_HOST` | No | FalkorDB host (default: `localhost`) |
| `FALKORDB_PORT` | No | FalkorDB port (default: `6379`) |
| `FALKORDB_PASSWORD` | No | FalkorDB password (default: empty) |

### 3. Install Dependencies

```bash
# Install all dependencies at once (Node + Python)
npm run setup:all
```

### 4. Start Services

```bash
npm run dev
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

### Docker Deployment

Alternatively, deploy with Docker Compose:

```bash
cp .env.example .env
# Edit .env with your configuration
docker compose up -d
```

## Acknowledgments

This project is built upon the following open-source projects. We thank them for their contributions:

- **[MiroFish](https://github.com/666ghj/MiroFish)** — Swarm intelligence prediction engine, the foundation of this project
- **[OASIS](https://github.com/camel-ai/oasis)** / **[CAMEL-AI](https://github.com/camel-ai/camel)** — Multi-agent social simulation framework
- **[Graphiti](https://github.com/getzep/graphiti)** — Knowledge graph construction engine
- **[Zep](https://github.com/getzep/zep)** — Long-term memory service for agents
- **[FalkorDB](https://github.com/FalkorDB/FalkorDB)** — High-performance graph database
- **[D3.js](https://github.com/d3/d3)** — Data visualization library

## License

This project is licensed under [AGPL-3.0](./LICENSE).
