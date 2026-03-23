# AGARS — AI-Generated AI Roleplay Simulator

[English](./README-EN.md) | [中文文档](./README.md)

## About

**AGARS** is a project built upon [MiroFish](https://github.com/666ghj/MiroFish), focusing on AI-driven roleplay simulation.

Building on MiroFish's multi-agent prediction engine, AGARS introduces a **Narrative Engine** system that enables immersive narrative experiences during simulations. It also incorporates **FalkorDB local knowledge graphs** as an alternative to cloud-only solutions, along with **LLM call monitoring**, **prompt configuration management**, and more.

### Key Features

- **Multi-Agent Simulation**: Automatically constructs a digital world from seed materials, with agents possessing independent personalities and long-term memory
- **Narrative Engine**: Transforms simulation processes into interactive narrative experiences
- **Knowledge Graph**: Supports both Zep Cloud and FalkorDB local graph modes
- **Report Generation**: Automatically generates analysis reports after simulation
- **Deep Interaction**: Chat with any character in the simulated world

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
