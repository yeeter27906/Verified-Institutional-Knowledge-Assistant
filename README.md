# Team Name: Team 2

## Team Members
* Member 1: Ruhaan Kakar - [invincible1786](https://github.com/invincible1786)
* Member 2: Pawan Manighadhan - [pawan188](https://github.com/pawan188)
* Member 3: Sakshi S. Dwivedi - [dwivedi-jiii](https://github.com/dwivedi-jiii)
* Member 4: Arsh Goyal - [arshGoyalDev](https://github.com/arshGoyalDev)

## Technical Implementation

### 1. Data Pipeline (Scraping)
* Tools used: Python scraper (mwclient, mwparserfromhell, BeautifulSoup), concurrent/multi-threaded scraper, batch output to JSON.
* Strategy: We fetch the full page list from MetaKGP, then scrape pages in concurrent batches. Wikitext is cleaned into readable Markdown, infoboxes are extracted into a summary block, and links/templates are normalized.
* Chunking & Indexing: Cleaned page text is chunked (configurable) and sent to the indexer which produces embeddings (Modal service) and stores vectors in ChromaDB for RAG.
* Key files:
  - `submissions/team_2/scraper/src/main.py` — concurrent scraper and batch output
  - `submissions/team_2/scraper/src/wikitext_cleaner.py` — converts wikitext → cleaned Markdown + infobox extraction
  - `submissions/team_2/scraper/results/` — contains `all_pages.json`, `scraped_data/` with cleaned pages

### 2. Graph of Thoughts (GoT)
* Reasoning model: The system represents reasoning as a directed graph of "thought" nodes. Each node is derived from retrieved chunks (facts) from MetaKGP pages. Edges represent logical or topical connections discovered during retrieval and candidate generation.
* Node structure: extracted fact / claim text, source metadata (page title, chunk id, score), and a small provenance snippet.
* Edge logic: edges are created when two facts share strong semantic similarity, explicit links, or when the Logic Expert recommends merging nodes. This allows connecting a "Society" page to a related "Student" or "Event" page via intermediate facts.
* Key files:
  - `submissions/team_2/chatbot/backend/src/services/chat_agent/engine.py` — orchestrates GoT construction and search
  - `submissions/team_2/chatbot/backend/src/services/chat_agent/router.py` — exposes endpoints for the GoT-driven query flow

### 3. Mixture of Experts (MoE) Verification
We implemented a small Gauntlet of three experts that verify each candidate thought before it is accepted into the reasoning graph or included in the final answer.

1. Expert 1 — Source Matcher:
   - Verifies whether the meaning of a thought is semantically contained in the retrieved context chunks.
   - Returns a confidence score and a short reasoning string.
   - Implemented in `src/services/chat_agent/experts.py` as `SourceMatcher`.

2. Expert 2 — Hallucination Hunter:
   - Detects claims in a thought that are unsupported by the context and lists significant unsupported claims.
   - Implements JSON-based verdicts (PASS/FAIL) and a confidence metric.
   - Implemented in `src/services/chat_agent/experts.py` as `HallucinationHunter`.

3. Expert 3 — Logic Expert:
   - Ensures the candidate thought fits coherently into the existing reasoning chain (graph history), flags redundancy, and recommends actions: keep | merge | discard.
   - Implemented in `src/services/chat_agent/experts.py` as `LogicExpert`.

Orchestration: `MoEGauntlet` runs the three experts in parallel and computes a weighted vote to decide whether a thought passes. The project uses a lenient weighted formula (source: 40%, hallucination: 30%, logic: 30%) and conservative pass thresholds so the system prioritizes recall while still surfacing provenance and failure reasons.

## Setup Instructions

### Prerequisites
* Python 3.11+ / 3.13+ (project tested with modern Python versions)
* Node 18+ (for the frontend dev server)
* PostgreSQL (optional but required for the indexer if using DB upload)
* Modal account (for GPU-accelerated embeddings service)
* Groq API key (required for LLM inference) - get from https://console.groq.com/

### Environment Variables

**Important:** This project uses a **single unified `.env` file** at `submissions/team_2/.env`

1. Copy the example configuration:
```bash
cd submissions/team_2
cp .env.example .env
```

2. Edit `.env` with your credentials:
```bash
nano .env
```

Required variables:
```bash
# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=metakgp_content
DB_USER=your_username
DB_PASSWORD=your_password
DB_SSLMODE=require

# Modal Services (Embeddings only)
MODAL_URL=https://your-workspace--metakgp-embeddings-fastapi-app.modal.run

# LLM API Keys (Required)
# Groq hosts Llama models for GoT reasoning and MoE verification
GROQ_API_KEY=your_groq_api_key_here

# Backend Configuration (use default values)
CHROMA_DIR=./chroma_data
CACHE_DIR=./cache
HOST=0.0.0.0
PORT=8000
BATCH_SIZE=100
```

**Note:** The scraper, backend, and all services read from this single `.env` file at the project root (`submissions/team_2/.env`).

**LLM Architecture:**
- **Embeddings**: Modal-hosted `all-MiniLM-L6-v2` (for semantic search)
- **LLM Inference**: Groq-hosted `Llama-4-Scout-17b-16e` (for reasoning, MoE verification)

### How to Run Scraper
1. Create and activate a Python venv in `submissions/team_2/scraper` and install requirements:

```
cd submissions/team_2/scraper
source venv/bin/activate
pip install -r requirements.txt
```

2. Fetch all page links (one-time):
```
python src/fetch_all_links.py
```

3. Scrape pages (examples):
```
# Quick test (10 pages)
python src/main.py results/all_pages.json --limit 10

# Batch scrape (100 pages in batches of 25)
python src/main.py results/all_pages.json --limit 100 --pages 25 --threads 8

# Full wiki (batches of 50)
python src/main.py results/all_pages.json --pages 50 --threads 4
```

### How to Run Bot (Backend)
1. Setup environment and install dependencies:

```bash
cd submissions/team_2/chatbot/backend
uv venv
uv pip install -e .
python -m spacy download en_core_web_sm
```

2. Ensure `.env` exists at project root with required variables (see Environment Variables section above)

3. (Optional) Deploy Modal embedding service and set `MODAL_URL` in `.env`:

```bash
modal setup
modal deploy src/utils/modal_embeddings.py
# copy the returned URL into MODAL_URL in submissions/team_2/.env
```

4. Start services:
```bash
./start.sh
# or run individual services:
# uvicorn src.app.main:app --reload
```

### How to Run Frontend
```
cd submissions/team_2/chatbot/frontend
npm install
npm run dev
```
The frontend expects the backend query route at `http://localhost:8000/got/query` by default.

## 📸 Screenshots
* <img width="1882" height="1161" alt="image" src="https://github.com/user-attachments/assets/657f1da5-8956-4b1f-9678-177a9106b5df" />


## Notes on Behavior & Constraints
* Data Source Rule: All answers must be traceable to scraped MetaKGP content. If the system cannot find supporting evidence it returns "I don't know." (enforced by the Source Matcher and Hallucination Hunter).
* Provenance: Final answers include page titles and short source snippets for traceability.
* Extensibility: The FastAPI app is modular; new experts or reasoning strategies can be added under `src/services/chat_agent/` and mounted via routers.

## How we validated
* Scraper: sample runs (10/100 pages) and cleaned output checked in `submissions/team_2/scraper/results/scraped_data/`.
* Indexing: ChromaDB persisted vectors in `chroma_data/` and embedding calls are routed to Modal or a provided embedding endpoint.
* MoE: `MoEGauntlet` tests experts in parallel; the code is in `src/services/chat_agent/experts.py`.

## Troubleshooting
* Check logs under `submissions/team_2/chatbot/backend/logs/` (indexer.log, query_service.log).
* Common fixes: ensure `.env` is populated, Modal URL points to a deployed embedding service, and PostgreSQL credentials are correct when using DB upload.

## Deliverables Checklist
* [x] Scraper (source + results)
* [x] Backend (RAG indexer + FastAPI query service)
* [x] Frontend (React chat UI)
* [ ] Demo video (link placeholder)
* [ ] Hosted demo (optional)
