# maestro-memory Deep Research Report

Date: 2026-03-16

---

## Topic 1: MiroFish (郭航江 / BaiFu)

### Overview

MiroFish is an open-source multi-agent prediction engine built by Guo Hangjiang (郭航江, alias BaiFu), a senior undergraduate student in China. It topped GitHub's Global Trending list on March 7, 2026.

- **GitHub**: https://github.com/666ghj/MiroFish
- **Stars**: ~27.4k (as of mid-March 2026, grew from 5.9k on March 7)
- **Forks**: 3.3k

### Architecture: Multi-Agent Simulation

MiroFish extracts "seed information" from reality (breaking news, policy drafts, financial signals) and constructs a **high-fidelity parallel digital world** where thousands of AI agents interact and undergo social evolution. The system operates from a "god's perspective" where users can dynamically inject variables to simulate future trajectories.

**Tech stack**:
- Backend: Python 3.11-3.12
- Frontend: Vue + Node.js 18+
- Package manager: UV for Python
- LLM: OpenAI SDK-compatible APIs (Alibaba Qwen recommended)
- Memory: **Zep Cloud** for agent memory management
- Docker: `docker compose up -d` mapping ports 3000 (frontend) and 5001 (backend API)

### Agent Memory and Behavioral Logic

Each agent has:
- **Independent personality** — distinct character traits
- **Long-term memory** — powered by Zep Cloud's temporal knowledge graph
- **Behavioral logic** — rules governing how agents act and react
- **Free interaction** — agents interact with each other and undergo social evolution

The simulation workflow includes "dynamic updates to temporal memory" during simulation phases, meaning agent memories evolve as the simulation progresses.

### Prediction Capabilities

- Generates detailed prediction reports plus interactive digital worlds
- Target scenarios: financial decision-making, policy/public opinion prediction, PR crisis simulation, marketing strategy testing, story/fiction deduction, academic research
- Example demo: predicting the lost ending of *Dream of the Red Chamber*

### Signal Handling

Users upload data analysis reports or creative narratives, then describe prediction needs in natural language. The engine processes news, policies, financial data as seed materials for the parallel world simulation.

### Investment: 陈天桥 (Chen Tianqiao / Shanda)

- **Amount**: 30 million RMB (~$4M+ USD)
- **Timeline**: Within 24 hours of reviewing the demo video
- **Context**: Guo was previously an intern at Shanda; overnight became CEO of an AI startup
- **Previous project**: BettaFish (public opinion analysis across 30+ social media platforms) — gained 30K+ GitHub stars

### Timeline

| Event | Date |
|-------|------|
| BettaFish development | Summer 2025 |
| BettaFish hits 30K+ stars | 2025 |
| MiroFish built in 10 days | Early March 2026 |
| #1 GitHub Global Trending | March 7, 2026 |
| 30M RMB investment secured | Within 24h of demo |

---

## Topic 2: Agent Memory Systems — State of the Art

---

### 2.1 Embedding-Based Systems

#### OpenViking (ByteDance / Volcano Engine)

- **GitHub**: https://github.com/volcengine/OpenViking
- **Stars**: ~1,610 (hit #1 trending March 15, 2026 — growing fast)
- **Core approach**: Virtual filesystem paradigm (not traditional vector store)
- **Storage**: `viking://` protocol with URI-addressable memory/resource/skill nodes
- **Query interface**: Directory recursive retrieval — vector search identifies high-score directory, then recursively drills into subdirectories
- **Tiered loading**: L0/L1/L2 on-demand context loading
- **Time**: Memory self-iteration — auto-compresses conversations, extracts long-term memory
- **Relationships**: Hierarchical directory structure models parent-child relationships
- **Forgetting**: Compression-based — older content gets summarized
- **Strengths**: Novel filesystem metaphor; observable retrieval trajectories; cost-efficient tiered loading
- **Weaknesses**: Very new (March 2026); limited ecosystem; no graph relationships

> Note: The user asked about "Viking DSL" — this is OpenViking from ByteDance. There is no separate "Viking DSL" project. The "DSL" aspect is the `viking://` URI protocol for addressing context.

#### mem0

- **GitHub**: https://github.com/mem0ai/mem0
- **Stars**: ~49.9k
- **Core approach**: LLM-powered memory extraction + vector search + optional graph
- **Storage backends**: 22+ vector stores (Qdrant, Pinecone, ChromaDB, PGVector), 5+ graph DBs (Neo4j, Memgraph, Kuzu, Neptune), SQLite for history tracking
- **Query interface**: Python/JS SDK — `Memory.add(messages, user_id)`, `Memory.search(query, user_id, limit)`
- **Memory extraction pipeline**: Ingest conversation -> LLM extracts facts -> retrieve similar memories via embeddings -> LLM decides ADD/UPDATE/DELETE -> store results
- **Graph memory (mem0g)**: Optional — LLM-based entity extractor identifies entities, relation generator links them with semantic relations (e.g., "Alice --[lives_in]--> Paris"). Stores as directed labeled graphs.
- **Time**: Timestamps on memories; "continuously learns over time" but no explicit decay
- **Relationships**: Via graph memory component (entities + relations)
- **Forgetting**: LLM-decided DELETE operations during memory update cycle
- **Performance**: +26% accuracy vs OpenAI Memory; 91% lower p95 latency; 90% token cost savings
- **Strengths**: Massive adoption (50K stars); simple API; broad integrations (50+); both vector and graph; production-ready managed platform
- **Weaknesses**: Graph memory is optional/add-on; no explicit temporal reasoning; no decay functions; LLM-dependent extraction can be expensive

#### Letta (formerly MemGPT)

- **GitHub**: https://github.com/letta-ai/letta
- **Stars**: ~21.6k
- **Core approach**: OS-inspired tiered memory with agent self-editing
- **Architecture** (3 tiers):
  - **Core memory** (RAM analogue): Editable blocks pinned to context window. Each block has label, description, value, character limit. Always visible to agent. Used for persona, user info, objectives.
  - **Archival memory** (disk analogue): External storage via vector or graph databases. Agent explicitly writes/reads using tools. For long-term processed knowledge.
  - **Recall memory** (conversation history): Complete interaction history, searchable, auto-saved to disk. Available even when outside active context.
- **Storage**: PostgreSQL (primary), vector DBs for archival, auto-persisted recall
- **Query interface**: Python/TypeScript SDK; agents query their own memory via built-in tools
- **Self-editing**: Agents have memory tools as function calls — they can rewrite core memory blocks, insert/search archival memory, search recall memory. The LLM autonomously manages its own context.
- **Sleep-time compute**: Proactive memory refinement during idle periods
- **Time**: No explicit temporal indexing
- **Relationships**: Via archival memory if using graph storage
- **Forgetting**: Agent can overwrite/delete core memory blocks; archival memory is persistent
- **Strengths**: Elegant OS metaphor; agent autonomy over memory; model-agnostic; active development (v0.16.6, March 2026)
- **Weaknesses**: Complex agent loop; no built-in temporal reasoning; no built-in graph; memory quality depends on agent's judgment

#### LangChain Memory

- **Not a standalone project** — memory modules within the LangChain framework
- **Types**:
  - **ConversationBufferMemory**: Stores entire conversation verbatim
  - **ConversationBufferWindowMemory**: Last k messages only
  - **ConversationSummaryMemory**: LLM-generated summary of conversation
  - **ConversationSummaryBufferMemory**: Hybrid — recent messages verbatim + older summarized
  - **EntityMemory**: Extracts and tracks entities (people, places, objects) from conversation
  - **ConversationKGMemory**: Builds knowledge graph from conversation
- **Storage**: In-memory by default; pluggable persistence
- **Strengths**: Easy to use; well-documented; part of popular framework
- **Weaknesses**: Simplistic; no cross-session persistence by default; no temporal reasoning; no hybrid retrieval; being deprecated in favor of LangGraph checkpointing

---

### 2.2 Graph-Based Systems

#### GraphRAG (Microsoft)

- **GitHub**: https://github.com/microsoft/graphrag
- **Stars**: ~25k+
- **Core approach**: Entity extraction -> knowledge graph -> community detection -> community summaries -> retrieval
- **Pipeline**:
  1. LLM extracts entities and relationships from source documents
  2. Builds knowledge graph
  3. Leiden algorithm detects communities (hierarchical clustering)
  4. LLM generates summaries for each community
  5. **Global search**: Each community summary generates partial response; all partial responses summarized into final answer
  6. **Local search**: Focuses on specific entity neighborhoods
- **Storage**: Custom graph storage; supports multiple backends
- **Query interface**: Python SDK with local and global search modes
- **Time**: No explicit temporal modeling
- **Relationships**: Rich entity-relationship extraction via LLM
- **Forgetting**: N/A (batch indexing, not dynamic)
- **Cost**: High — full indexing is expensive (LazyGraphRAG reduces to 0.1% cost)
- **Strengths**: Excels at corpus-level thematic questions; hierarchical community summaries; strong for document understanding
- **Weaknesses**: Expensive indexing; batch-oriented (not incremental); no temporal awareness; not designed for agent memory (designed for document RAG)

#### nano-graphrag

- **GitHub**: https://github.com/gusye1234/nano-graphrag
- **Stars**: ~3.7k
- **Core approach**: Simplified GraphRAG in ~1,100 lines of code
- **Differences from Microsoft GraphRAG**:
  - Omits "covariates" feature
  - Uses top-K important communities instead of map-reduce over all communities
  - Much simpler codebase
- **Storage**: NetworkX or Neo4j (graph); nano-vectordb, HNSW, Milvus, FAISS (vector); file-based KV store
- **Features**: Incremental insertion with MD5 dedup; async operations; batch processing; naive RAG mode; multiple LLM providers
- **Strengths**: Hackable; lightweight; easy to understand and modify
- **Weaknesses**: Less comprehensive than full GraphRAG; limited community; no temporal modeling

#### Zep / Graphiti

- **Paper**: https://arxiv.org/abs/2501.13956
- **GitHub (Graphiti)**: https://github.com/getzep/graphiti
- **Stars (Graphiti)**: ~23.8k
- **Core approach**: **Temporal knowledge graph** — the standout feature
- **Architecture** (3 subgraph types):
  - **Episodic subgraph**: Raw data episodes (source provenance)
  - **Semantic subgraph**: Extracted entities with evolving summaries + relationships (triplets) with validity windows
  - **Community subgraph**: Clustered entity groups with summaries
- **Dual-timestamp model**: Each fact tracks (1) when event occurred and (2) when it was ingested. Enables "what was true at time X" queries.
- **Storage backends**: Neo4j 5.26+, FalkorDB 1.1.2+, Kuzu 0.11.2+, Amazon Neptune
- **Query interface**: Python SDK; hybrid retrieval combining semantic embeddings + BM25 keyword search + graph traversal
- **Time**: First-class temporal modeling — validity windows on facts, automatic invalidation when contradicted
- **Relationships**: Directed labeled relationships between entities, each with temporal bounds
- **Forgetting**: Facts are invalidated (marked superseded) when contradicted by new information, not deleted
- **Performance**: 94.8% on DMR benchmark (vs MemGPT 93.4%); up to 18.5% accuracy improvement; 90% latency reduction
- **Strengths**: Best-in-class temporal reasoning; hybrid retrieval; enterprise-grade; incremental (no batch recomputation); sub-second queries; full provenance tracking
- **Weaknesses**: Requires graph database infrastructure; more complex setup; Neo4j dependency

#### FalkorDB

- **GitHub**: https://github.com/FalkorDB/FalkorDB
- **Stars**: ~3.7k
- **Core approach**: Ultra-fast graph database using GraphBLAS sparse matrices
- **Query language**: OpenCypher with extensions
- **Architecture**: Sparse adjacency matrix representation using linear algebra for queries
- **GraphRAG SDK**: Separate repo (FalkorDB/GraphRAG-SDK) for building knowledge graph agents
- **Integrations**: Graphiti (as storage backend), LangChain, MCP server
- **Strengths**: Up to 5x query speed improvement over traditional methods; 90% hallucination reduction with GraphRAG; multi-tenant; property graph model
- **Weaknesses**: SSPL license; smaller community; primarily a database, not a memory system

---

### 2.3 Hybrid Approaches

#### Cognee

- **GitHub**: https://github.com/topoteretes/cognee
- **Stars**: ~14k
- **Core approach**: Three-layer hybrid — graph + vector + relational
- **Architecture**:
  - **Graph store**: Entities, relationships, structural traversal (Neo4j)
  - **Vector store**: Embeddings for semantic similarity
  - **Relational store**: Documents, chunks, provenance tracking (SQLite default)
- **Memory model**:
  - **Session memory** (short-term): Loads relevant embeddings + graph fragments into runtime context
  - **Permanent memory** (long-term): User data, interaction traces, external documents, derived relationships
- **Query interface**: Python async API (`cognee.add()`, `cognee.cognify()`, `cognee.search()`); CLI (`cognee-cli search`); local UI
- **Time**: Documents evolve as "relationships change and evolve" — but no explicit temporal indexing
- **Relationships**: Via knowledge graph layer
- **Forgetting**: Not explicitly documented
- **Adoption**: 70+ companies including Bayer; 1M+ pipelines/month
- **Strengths**: True hybrid (graph + vector + relational); ontology grounding; multi-language; audit trails; MCP support
- **Weaknesses**: No explicit temporal reasoning; complex pipeline; less transparent than simpler systems

#### RAGFlow

- **GitHub**: https://github.com/infiniflow/ragflow
- **Stars**: ~75.1k
- **Core approach**: Deep document understanding + intelligent chunking + hybrid retrieval
- **Architecture**:
  - DeepDoc: Vision + parser for PDFs (text chunks with positions, table extraction, figure captioning)
  - Template-based intelligent chunking with human-in-the-loop visualization
  - Multiple recall with fused re-ranking
- **Storage**: Elasticsearch (default for full-text + vector), Infinity (alternative); MinIO (objects), MySQL (metadata), Redis (cache)
- **Query interface**: Web UI; API
- **Chunking strategies**: Template-based; long-context RAG with auto-generated TOC to mitigate context loss
- **Strengths**: Excellent document understanding; visual chunking inspection; grounded citations; massive adoption (75K stars)
- **Weaknesses**: Not an agent memory system — it's a document RAG engine; no temporal modeling; no agent integration

---

### 2.4 Search/Retrieval Mechanisms

#### BM25 (Sparse Retrieval)

- **Algorithm**: Term frequency-inverse document frequency scoring with document length normalization
- **BM25F variant**: Extends BM25 to weight multiple text fields differently (used by Weaviate, Elasticsearch)
- **Role in hybrid search**: Excels at exact keyword matching where dense embeddings miss specific terms
- **Performance**: Hybrid (BM25 + dense) shows 15-30% better recall than either alone
- **2025 advances**:
  - **Dynamic Weighted RRF**: Uses query specificity (avg tf-idf) to weight BM25 vs semantic per-query
  - **Three-way retrieval** (BM25 + dense + sparse vectors) shown optimal for RAG
  - **Adaptive fusion**: +2-7.5 pp gains in Precision@1 and MRR@20

#### Hybrid Search Implementations

**Qdrant**:
- Supports dense + sparse vectors natively
- Fusion methods: Reciprocal Rank Fusion (RRF) and Distribution-Based Score Fusion
- First-class sparse vector support with named vector spaces

**Weaviate**:
- BM25F + vector search in parallel, fused via algorithms
- Fusion options: rankedFusion, relativeScoreFusion (default from v1.24)
- Supports structured filters (including temporal) alongside hybrid search

#### Temporal Retrieval

Key formulas and approaches:
- **Exponential decay**: `score *= e^(-lambda * time_elapsed)` — basic recency weighting
- **Ebbinghaus curve**: `strength = importance * e^(-lambda_eff * days) * (1 + recall_count * 0.2)` where reinforcement resets effective age
- **Multi-factor scoring (A-MAC)**: Future utility + factual confidence + semantic novelty + temporal recency + content type prior
- **Field-theoretic approach**: Memory as continuous dynamic field where high-importance regions diffuse/decay more slowly
- **Practical implementation**: Timestamps as metadata + recency weight in retrieval scoring; expiration/eviction policies for auto-cleanup

#### Multi-Hop Retrieval

- Graph traversal chains multiple facts: A -> B -> C without extra scaffolding
- Explicit relationship modeling enables "neighbors-of-neighbors" queries
- Knowledge graphs support contradiction detection across hops
- Modern approach: Hybrid — precise graph traversal + broad vector semantic recall
- GraphRAG consistently outperforms vanilla RAG on complex reasoning tasks

#### Entity Relationships

- **Triplet model**: (Subject, Predicate, Object) with optional temporal bounds
- **Evolving summaries**: Entity descriptions update as new information arrives
- **Provenance**: Each relationship traces back to source episodes/documents
- **Hierarchical**: Community detection groups related entities for summarization

---

### 2.5 Comparison Matrix

| System | Approach | Storage | Stars | Temporal | Graph | Hybrid Search | Agent Integration | Production Ready |
|--------|----------|---------|-------|----------|-------|---------------|-------------------|-----------------|
| **mem0** | Vector + optional graph | Qdrant/Pinecone/22+ | 49.9k | Weak | Optional | No | Yes (SDK) | Yes |
| **Letta** | Tiered (core/archival/recall) | PostgreSQL + vector | 21.6k | No | Optional | No | Native | Yes |
| **Graphiti/Zep** | Temporal knowledge graph | Neo4j/FalkorDB/Kuzu | 23.8k | **Best** | Native | **Yes (BM25+vector+graph)** | Yes (MCP) | Yes |
| **GraphRAG** | Community summaries | Custom | 25k+ | No | Native | No | No | Partial |
| **Cognee** | Graph + vector + relational | Neo4j + vector + SQLite | 14k | Weak | Native | Partial | Yes | Yes |
| **OpenViking** | Filesystem paradigm | Custom Viking protocol | 1.6k | Weak | No | No | Yes | Early |
| **RAGFlow** | Deep doc understanding | Elasticsearch | 75.1k | No | No | Yes (fused re-rank) | No | Yes |
| **nano-graphrag** | Simplified GraphRAG | NetworkX/Neo4j + vector | 3.7k | No | Native | No | No | Partial |
| **FalkorDB** | Graph database | Sparse matrices | 3.7k | Via Graphiti | Native | Via integrations | Via SDK | Yes |
| **LangChain Memory** | Multiple simple types | In-memory/pluggable | N/A | No | KG type only | No | Yes | Deprecated |

---

## Topic 3: Design Direction for maestro-memory

### Gap Analysis — What Existing Systems Miss

1. **mem0** is the market leader but has weak temporal reasoning and no built-in hybrid search (BM25 + vector + graph). Graph memory is an add-on, not core.

2. **Letta** has an elegant tiered model but no temporal awareness, no graph relationships, and depends on the agent's LLM judgment for memory quality.

3. **Graphiti/Zep** has the best temporal model but requires Neo4j/FalkorDB infrastructure — too heavy for a CLI tool. No filesystem-native approach.

4. **GraphRAG** is batch-oriented, expensive, and designed for document corpora, not agent memory.

5. **Cognee** is the closest hybrid but still lacks explicit temporal reasoning and has a complex pipeline.

6. **OpenViking** has an interesting filesystem metaphor but no graph relationships and is very new.

7. **No existing system is designed for CLI-native agents** that work with local files, CLAUDE.md, and development workflows.

### The Gap maestro-memory Should Fill

**A lightweight, CLI-native agent memory system that combines temporal-aware knowledge graphs with hybrid retrieval, designed for developer tool agents (like Claude Code) rather than chatbot conversations.**

Key differentiators:
- **CLI-first**: Designed as a skill/tool for agents working in terminals, not a web service
- **File-aware**: Understands codebases, CLAUDE.md files, project structures
- **Temporal-native**: Every fact has a validity window (like Graphiti) but without requiring Neo4j
- **Hybrid retrieval**: BM25 + embeddings + graph traversal in a single query
- **Lightweight**: SQLite + embedded vector store, no external infrastructure needed
- **Developer workflow integration**: Git-aware, project-scoped, multi-session

### Proposed Architecture

```
┌─────────────────────────────────────────────────┐
│                maestro-memory                    │
├─────────────────────────────────────────────────┤
│  Query Layer                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Natural   │ │ Structured│ │ Temporal         │ │
│  │ Language  │ │ Filters   │ │ "as of date X"   │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
├─────────────────────────────────────────────────┤
│  Retrieval Layer (Hybrid)                        │
│  ┌──────┐ ┌────────────┐ ┌───────────────────┐  │
│  │ BM25 │ │ Embeddings │ │ Graph Traversal   │  │
│  │      │ │ (dense)    │ │ (multi-hop)       │  │
│  └──┬───┘ └─────┬──────┘ └────────┬──────────┘  │
│     └────────────┼─────────────────┘             │
│            ┌─────▼─────┐                         │
│            │ RRF Fusion│ + Temporal Decay Weight  │
│            └───────────┘                         │
├─────────────────────────────────────────────────┤
│  Memory Layer                                    │
│  ┌────────────────────────────────────────────┐  │
│  │ Knowledge Graph (lightweight)              │  │
│  │ - Entities (people, projects, concepts)    │  │
│  │ - Relations with validity windows          │  │
│  │ - Community summaries (lazy, on-demand)    │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ Vector Store (embedded)                    │  │
│  │ - Fact embeddings                          │  │
│  │ - Episode embeddings                       │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ Full-Text Index (BM25)                     │  │
│  │ - Keyword search over facts + episodes     │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │ Provenance Store                           │  │
│  │ - Source episodes -> derived facts         │  │
│  │ - Timestamps (event_time, ingestion_time)  │  │
│  └────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│  Ingestion Layer                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Convo    │ │ File     │ │ Structured       │ │
│  │ Episodes │ │ Changes  │ │ Data (JSON/YAML) │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│           ↓                                      │
│  LLM Extraction: entities, relations, facts      │
│  + Embedding generation                          │
│  + BM25 index update                             │
│  + Temporal metadata (valid_from, valid_until)    │
├─────────────────────────────────────────────────┤
│  Storage: SQLite + sqlite-vss (or usearch)       │
│  Single file per project: .maestro/memory.db     │
└─────────────────────────────────────────────────┘
```

### Storage Backends

**Primary (default — zero-config)**:
- **SQLite** for everything: graph (adjacency tables), full-text (FTS5 for BM25), metadata, provenance
- **sqlite-vss** or **usearch** for vector similarity (embedded, no server)
- Single file: `~/.maestro/memory/{project-hash}/memory.db`

**Optional (scale-up)**:
- **Qdrant** for vector search (when corpus grows large)
- **Neo4j/FalkorDB** for graph (when relationship complexity demands it)
- **PostgreSQL + pgvector** for teams/shared memory

### Query Interface

```
# Natural language (agent-facing)
maestro-memory search "What does the user prefer for commit messages?"

# Structured (programmatic)
maestro-memory search --entity "user" --relation "prefers" --after "2026-01"

# Temporal
maestro-memory search "project deadlines" --as-of "2026-03-01"
maestro-memory search "tech stack" --current  # only facts not yet superseded

# Add memory
maestro-memory add --type feedback "User corrected: do not use emoji in files"
maestro-memory add --type project --source "conversation" "Deadline moved to April 15"

# Graph queries
maestro-memory graph --entity "maestro-fetch" --hops 2
maestro-memory graph --community "authentication"
```

### Memory Types (borrowing from Graphiti's model)

1. **Episodes**: Raw source data (conversation snippets, file diffs, user corrections)
2. **Entities**: Extracted subjects (users, projects, tools, concepts) with evolving summaries
3. **Relations**: Directed links between entities with temporal validity windows
4. **Facts**: Discrete statements derived from episodes, each with:
   - `valid_from` timestamp
   - `valid_until` timestamp (null = still current)
   - `importance` score (0-1)
   - `source_episode_id` for provenance
   - Embedding vector
   - Full text (for BM25)
5. **Communities**: Auto-clustered groups of related entities with LLM-generated summaries (lazy — generated on first query, cached)

### Temporal Handling

Inspired by Graphiti's dual-timestamp model:
- **event_time**: When the fact became true in the real world
- **ingestion_time**: When maestro-memory learned about it
- **valid_until**: When superseded (null = current)
- **Contradiction detection**: New facts that contradict existing ones automatically invalidate the old fact (set valid_until)
- **Decay scoring**: `relevance = base_score * e^(-0.01 * days_since_last_access) * (1 + access_count * 0.1)`

### Relationship Modeling

- Triplet model: `(Entity A) --[relation, valid_from, valid_until]--> (Entity B)`
- Multi-hop traversal via SQL recursive CTEs (no Neo4j needed for moderate graphs)
- Community detection via simple connected-component analysis on the SQLite graph

### Integration as CLI Tool / Skill

maestro-memory should work as:

1. **MCP Server**: Expose `search`, `add`, `graph` as MCP tools for any agent
2. **CLI binary**: `maestro-memory` command for direct use
3. **Claude Code Skill**: `~/.claude/skills/maestro-memory/` with SKILL.md describing capabilities
4. **Python SDK**: `from maestro_memory import Memory` for programmatic use

### What It Borrows from Each System

| From | What maestro-memory takes |
|------|--------------------------|
| **Graphiti/Zep** | Temporal knowledge graph model, dual timestamps, validity windows, fact invalidation |
| **mem0** | LLM-powered fact extraction pipeline (ingest -> extract -> compare -> ADD/UPDATE/DELETE) |
| **Letta** | Tiered memory concept (core context vs archival), agent self-editing pattern |
| **OpenViking** | Hierarchical context loading (L0/L1/L2), observable retrieval |
| **Cognee** | Three-layer hybrid (graph + vector + relational in single system) |
| **Qdrant/Weaviate** | RRF fusion for hybrid search (BM25 + dense) |
| **nano-graphrag** | Simplicity ethos — keep it hackable, ~2000 lines, easy to understand |
| **RAGFlow** | Deep document understanding patterns for ingesting code/docs |

### What maestro-memory Does NOT Do

- Not a chatbot memory layer (mem0's strength)
- Not a document RAG engine (RAGFlow's strength)
- Not a full knowledge graph platform (Neo4j's strength)
- Not a simulation engine (MiroFish's strength)

### What maestro-memory IS

A **lightweight, temporal, hybrid-retrieval memory system for developer tool agents**, stored in a single SQLite file per project, queryable via CLI/MCP/SDK, with first-class support for:
- Facts that change over time
- Entity relationships that evolve
- Hybrid search (keyword + semantic + graph)
- Zero-config local deployment
- Optional scale-up to production databases

---

## Sources

### MiroFish
- [MiroFish GitHub](https://github.com/666ghj/MiroFish)
- [36kr: Post-2000 Kid Programs with AI in 10 Days](https://eu.36kr.com/en/p/3713983582662788)
- [TMTPOST: AI Product Tops GitHub](https://en.tmtpost.com/post/7905996)
- [The Daily Jagran: MiroFish AI Explained](https://www.thedailyjagran.com/technology/mirofish-ai-explained-the-new-multiagent-prediction-engine-trending-on-github-10303504)
- [DEV Community: MiroFish Digital Worlds](https://dev.to/arshtechpro/mirofish-the-open-source-ai-engine-that-builds-digital-worlds-to-predict-the-future-ki8)

### Agent Memory Systems
- [mem0 GitHub](https://github.com/mem0ai/mem0)
- [mem0 Research Paper](https://arxiv.org/abs/2504.19413)
- [mem0 DeepWiki](https://deepwiki.com/mem0ai/mem0)
- [Letta GitHub](https://github.com/letta-ai/letta)
- [Letta: Agent Memory Blog](https://www.letta.com/blog/agent-memory)
- [Letta Docs: Intro to MemGPT](https://docs.letta.com/concepts/memgpt/)
- [OpenViking GitHub](https://github.com/volcengine/OpenViking)
- [OpenViking Official Site](https://openviking.ai/)

### Graph-Based Systems
- [Zep Paper (arXiv)](https://arxiv.org/abs/2501.13956)
- [Graphiti GitHub](https://github.com/getzep/graphiti)
- [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- [GraphRAG Paper (arXiv)](https://arxiv.org/abs/2404.16130)
- [nano-graphrag GitHub](https://github.com/gusye1234/nano-graphrag)
- [FalkorDB GitHub](https://github.com/FalkorDB/FalkorDB)
- [FalkorDB GraphRAG](https://www.falkordb.com/news-updates/data-retrieval-graphrag-ai-agents/)

### Hybrid and Retrieval
- [Cognee GitHub](https://github.com/topoteretes/cognee)
- [Cognee: How It Builds AI Memory](https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory)
- [RAGFlow GitHub](https://github.com/infiniflow/ragflow)
- [Qdrant Hybrid Search](https://qdrant.tech/documentation/concepts/hybrid-queries/)
- [Weaviate Hybrid Search](https://weaviate.io/blog/hybrid-search-explained)
- [Ebbinghaus Forgetting Curve for Agents](https://dev.to/sachit_mishra_686a94d1bb5/i-built-memory-decay-for-ai-agents-using-the-ebbinghaus-forgetting-curve-1b0e)
- [A-MAC: Adaptive Memory Admission Control](https://arxiv.org/html/2603.04549v1)
- [Neo4j: Multi-Hop Reasoning with KGs](https://neo4j.com/blog/genai/knowledge-graph-llm-multi-hop-reasoning/)
