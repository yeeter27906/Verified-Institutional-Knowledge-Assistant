# MetaKGP RAG System

Production-ready Retrieval Augmented Generation (RAG) system for MetaKGP wiki using ChromaDB, Modal, and FastAPI.

## Quick Start

### 1. Install uv (if not already installed)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Setup Project
```bash
# Create virtual environment
uv venv

# Install dependencies
uv pip install -e .

# Download spaCy model
source .venv/bin/activate  # or `source venv/bin/activate`
python -m spacy download en_core_web_sm
```

### 3. Configure Environment
```bash
# The unified .env file is in the team_2 root directory
# Copy the example config
cd ../../  # Go to team_2 root
cp .env.example .env

# Edit with your credentials
nano .env
```

Required variables (see `submissions/team_2/.env.example` for full list):
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=metakgp_content
DB_USER=username
DB_PASSWORD=password
DB_SSLMODE=require

# Modal Services (Embeddings only)
MODAL_URL=https://your-workspace--metakgp-embeddings-fastapi-app.modal.run

# LLM API Keys (Required)
# Groq hosts Llama models for all LLM inference
GROQ_API_KEY=your_groq_api_key_here
```

**Note:** The `.env` file should be at `submissions/team_2/.env` (project root), not in the backend directory.

**LLM Architecture:**
- Embeddings: Modal-hosted `all-MiniLM-L6-v2` 
- LLM: Groq-hosted `Llama-4-Scout-17b-16e` (GoT reasoning + MoE verification)

### 4. Deploy Modal Embedding Service
```bash
# First time setup
modal setup

# Deploy
modal deploy src/utils/modal_embeddings.py

# Copy the returned URL to MODAL_URL in .env
```

### 5. Start Everything
```bash
./start.sh
```

This starts:
- RAG Indexer (PostgreSQL → Chunks → Embeddings → ChromaDB)
- FastAPI Query Service (Semantic search API)

### 6. Stop Everything
```bash
./stop.sh
```

## Monitoring

### View Logs
```bash
# Indexer logs
tail -f logs/indexer.log

# Query service logs
tail -f logs/query_service.log

# Both logs
tail -f logs/*.log
```

### Check Health
```bash
# Overall API health
curl http://localhost:8000/health

# Query service health
curl http://localhost:8000/query/health
```

### API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Usage

### Search Request
```bash
curl -X POST http://localhost:8000/query/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I register for courses?",
    "top_k": 5
  }'
```

### Search with Filters
```bash
curl -X POST http://localhost:8000/query/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "hostel allocation process",
    "top_k": 10,
    "filters": {
      "category": "Hostel",
      "min_entity_count": 3
    }
  }'
```

### Python Usage
```python
import requests

response = requests.post('http://localhost:8000/query/search', json={
    'query': 'What are the placement statistics?',
    'top_k': 5
})

results = response.json()
for result in results['results']:
    print(f"Score: {result['score']:.2f}")
    print(f"Page: {result['metadata']['title']}")
    print(f"Text: {result['text'][:200]}...")
```

## Architecture

### Components

1. **Modal Embedding Service** (`src/utils/modal_embeddings.py`)
   - A100 GPU-accelerated sentence-transformers
   - 384-dimensional embeddings (all-MiniLM-L6-v2)
   - Auto-scaling on Modal with batch_size=500

2. **Embedding Client** (`src/utils/embedding_client.py`)
   - HTTP client for Modal API
   - Retry logic with exponential backoff
   - Health checking

3. **Chunk Processor** (`src/utils/chunk_processor.py`)
   - Text chunking (512 words, 50 overlap)
   - Entity extraction (spaCy)
   - Metadata enrichment

4. **ChromaDB Client** (`src/utils/chroma_client.py`)
   - Persistent vector storage
   - Cosine similarity search
   - Metadata flattening

5. **Indexing Service** (`src/services/indexing/indexer.py`)
   - PostgreSQL streaming
   - Embedding cache
   - Batch processing

6. **Query Service** (`src/services/query_service/`)
   - **service.py**: Business logic for semantic search
   - **router.py**: FastAPI routes (mounted at `/query`)
   - Integrated into main FastAPI app

7. **Main FastAPI App** (`src/app/main.py`)
   - Unified API with all service routers
   - Lifespan management for service initialization
   - Extensible architecture for adding new services

### Data Flow
```
PostgreSQL → Chunk Processor → Embedding Client → ChromaDB
                                      ↓
                              Modal Service (GPU)
```

## Configuration

### Environment Variables (.env)

```bash
# Database (individual variables)
DB_HOST=pg-15260559-arshgoyaldev-9af3.l.aivencloud.com
DB_PORT=22861
DB_NAME=metakgp_content
DB_USER=avnadmin
DB_PASSWORD=your_password
DB_SSLMODE=require

# Modal Embedding Service
MODAL_URL=https://your-workspace--metakgp-embeddings.modal.run

# Storage
CHROMA_DIR=./chroma_data
CACHE_DIR=./cache

# API Server
HOST=0.0.0.0
PORT=8000

# Indexer
BATCH_SIZE=100
```

### Database Schema

The indexer expects a PostgreSQL `metakgp_pages` table:

```sql
CREATE TABLE metakgp_pages (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) UNIQUE,
    title VARCHAR(500),
    cleaned_text TEXT,
    categories TEXT[],
    links TEXT[],
    exists BOOLEAN DEFAULT TRUE,
    redirect BOOLEAN DEFAULT FALSE,
    revision INTEGER
);
```

## Development

### Add Dependencies
```bash
# Edit pyproject.toml to add dependency
# Then:
uv pip install -e .
```

### Run Individual Services

#### Indexer Only
```bash
source .venv/bin/activate
python src/services/indexing/indexer.py \
  --chroma-dir ./chroma_data \
  --cache-dir ./cache
```

#### Query Service Only
```bash
source .venv/bin/activate
uvicorn src.app.main:app --reload
```

### Reset and Reindex
```bash
# Stop services
./stop.sh

# Clear data
rm -rf cache/ chroma_data/

# Start fresh
./start.sh
```

## Performance

- **Indexing Speed**: 50-100 pages/minute
- **Query Latency**: 1-2 seconds
- **Vector Dimensions**: 384 (all-MiniLM-L6-v2)
- **Storage**: ~54.6MB for 2,841 documents

## Troubleshooting

### Port Already in Use
```bash
# Find process on port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Services Won't Stop
```bash
# Force kill all
pkill -9 -f "indexer"
pkill -9 -f "uvicorn.*api"
```

### Import Errors
```bash
# Reinstall dependencies
uv pip install -e .
python -m spacy download en_core_web_sm
```

### Modal Service Issues
```bash
# Check health
curl https://YOUR_MODAL_URL/embedding/health

# Check Modal dashboard
modal app list
```

### Database Connection
```bash
# Test connection
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM metakgp_pages;"
```

## Project Structure

```
backend/
├── src/
│   ├── app/                    # Main FastAPI application
│   │   └── main.py             # Unified API with all routers
│   ├── services/               # Service layer
│   │   ├── indexing/
│   │   │   └── indexer.py      # Indexing pipeline
│   │   └── query_service/
│   │       ├── service.py      # Business logic
│   │       └── router.py       # FastAPI routes
│   ├── utils/                  # Shared utilities
│   │   ├── modal_embeddings.py # Modal deployment
│   │   ├── embedding_client.py # HTTP client
│   │   ├── chunk_processor.py  # NLP processing
│   │   └── chroma_client.py    # Vector storage
│   └── routers/                # Additional routers (future use)
├── cache/                      # Embedding cache
├── chroma_data/                # Vector database
├── logs/                       # Service logs
├── pyproject.toml             # Dependencies
├── .env.example               # Config template
├── start.sh                   # Start script
├── stop.sh                    # Stop script
└── ARCHITECTURE.md            # Architecture docs
```

## Key Features

- Modern Tooling - uv, pyproject.toml, uvicorn  
- Fast Setup - Two commands to start  
- Production-Ready - Retry logic, graceful shutdown  
- Unified API - All services under one FastAPI app with routers
- Extensible - Easy to add new services via routers
- Scalable Architecture - Services, utilities separation
- Resumable - Offset tracking survives restarts  
- GPU Accelerated - Modal A100 auto-scaling  
- Advanced NLP - Entity extraction with spaCy  

## License

MIT

## Contributing

Contributions welcome! Please ensure code passes linting:

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Format code
black src/

# Lint
ruff check src/
```
