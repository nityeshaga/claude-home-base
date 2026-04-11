#!/usr/bin/env python3
"""
Luoji Search — hybrid FTS5 + vector search over local files.

Usage:
    python luoji_search.py index          # Index all configured directories
    python luoji_search.py search "query" # Search across all indexed content
    python luoji_search.py search "query" --source diary  # Filter by source
    python luoji_search.py status         # Show index stats
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import sqlite_vec
import yaml


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    cfg["database"] = os.path.expanduser(cfg["database"])
    for d in cfg["directories"]:
        d["path"] = os.path.expanduser(d["path"])
    return cfg


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db(cfg):
    db_path = cfg["database"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.execute("PRAGMA journal_mode=WAL")
    _create_tables(db)
    return db


def _create_tables(db):
    # Main documents table
    db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT,
            chunk_index INTEGER DEFAULT 0,
            content TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            metadata TEXT
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_path
        ON documents(file_path, chunk_index)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_source
        ON documents(source)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_hash
        ON documents(file_hash)
    """)

    # FTS5 virtual table
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
        USING fts5(title, content, content=documents, content_rowid=id)
    """)

    # Triggers to keep FTS in sync
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END
    """)
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            INSERT INTO documents_fts(documents_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO documents_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)

    # Vector table — 384 dimensions for bge-small-en-v1.5
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_vec
        USING vec0(embedding float[384])
    """)

    db.commit()


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping chunks by character count."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
                # Look for sentence break
                sent_break = text.rfind(". ", start + chunk_size // 2, end)
                if sent_break > start:
                    end = sent_break + 2

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def file_hash(path):
    """Quick hash of file content for change detection."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def extract_markdown(path):
    """Extract title and content from a markdown file."""
    with open(path, "r", errors="replace") as f:
        text = f.read()

    # Extract title from first heading or filename
    title = Path(path).stem
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:].strip()

    return title, text


def extract_jsonl_conversations(path):
    """Extract conversations from a Claude Code JSONL session file."""
    docs = []
    messages = []
    session_id = Path(path).stem

    try:
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = entry.get("type", "")

                # Extract human messages
                if msg_type == "queue-operation":
                    content = entry.get("content", "")
                    if content:
                        messages.append(f"Human: {content}")

                # Extract assistant messages
                elif msg_type == "assistant":
                    message = entry.get("message", {})
                    if isinstance(message, dict):
                        content_parts = message.get("content", [])
                        if isinstance(content_parts, list):
                            text_parts = []
                            for part in content_parts:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text_parts.append(part.get("text", ""))
                            if text_parts:
                                messages.append(f"Assistant: {' '.join(text_parts)}")

    except Exception as e:
        print(f"  Warning: error reading {path}: {e}")
        return []

    if not messages:
        return []

    # Combine all messages into one document per session
    full_text = "\n\n".join(messages)
    timestamp = None
    try:
        with open(path, "r") as f:
            first_line = f.readline()
            first_entry = json.loads(first_line)
            timestamp = first_entry.get("timestamp", "")
    except Exception:
        pass

    title = f"Conversation {session_id[:8]}"
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            title = f"Conversation {dt.strftime('%Y-%m-%d %H:%M')}"
        except Exception:
            pass

    return [(title, full_text, json.dumps({"session_id": session_id, "timestamp": timestamp}))]


def should_exclude(path, excludes):
    """Check if a file path matches any exclusion patterns."""
    parts = Path(path).parts
    for exc in excludes:
        if exc in parts:
            return True
    return False


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_model = None


def get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        print("Loading embedding model...")
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def embed_texts(texts, batch_size=64):
    """Generate embeddings for a list of texts."""
    model = get_model()
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = list(model.embed(batch))
        all_embeddings.extend(embeddings)
    return all_embeddings


def serialize_vec(vec):
    """Pack a numpy array into bytes for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

def index_all(cfg, force=False):
    """Index all configured directories."""
    db = get_db(cfg)
    chunk_size = cfg.get("chunk_size", 1000)
    chunk_overlap = cfg.get("chunk_overlap", 200)

    total_new = 0
    total_skipped = 0
    total_errors = 0

    for dir_cfg in cfg["directories"]:
        dir_path = dir_cfg["path"]
        source = dir_cfg["name"]
        file_type = dir_cfg["type"]
        excludes = dir_cfg.get("exclude", [])

        if not os.path.exists(dir_path):
            print(f"Skipping {source}: {dir_path} does not exist")
            continue

        print(f"\nIndexing [{source}] from {dir_path}")

        if file_type == "markdown":
            files = []
            for root, dirs, filenames in os.walk(dir_path):
                # Filter excluded dirs in-place
                dirs[:] = [d for d in dirs if d not in excludes]
                for fn in filenames:
                    if fn.endswith((".md", ".txt")):
                        full_path = os.path.join(root, fn)
                        if not should_exclude(full_path, excludes):
                            files.append(full_path)

            for fpath in files:
                try:
                    fhash = file_hash(fpath)
                    if not force:
                        existing = db.execute(
                            "SELECT file_hash FROM documents WHERE file_path = ? LIMIT 1",
                            (fpath,)
                        ).fetchone()
                        if existing and existing[0] == fhash:
                            total_skipped += 1
                            continue

                    # Remove old entries for this file
                    _delete_file_entries(db, fpath)

                    title, text = extract_markdown(fpath)
                    if not text.strip():
                        continue

                    chunks = chunk_text(text, chunk_size, chunk_overlap)
                    texts_to_embed = []
                    rows = []

                    for i, chunk in enumerate(chunks):
                        rows.append((fpath, source, title, i, chunk, fhash,
                                     datetime.now().isoformat(), None))
                        texts_to_embed.append(chunk)

                    # Insert document rows
                    doc_ids = []
                    for row in rows:
                        cursor = db.execute(
                            """INSERT INTO documents
                               (file_path, source, title, chunk_index, content, file_hash, indexed_at, metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            row
                        )
                        doc_ids.append(cursor.lastrowid)

                    # Generate and insert embeddings
                    embeddings = embed_texts(texts_to_embed)
                    for doc_id, emb in zip(doc_ids, embeddings):
                        db.execute(
                            "INSERT INTO documents_vec(rowid, embedding) VALUES (?, ?)",
                            (doc_id, serialize_vec(emb))
                        )

                    db.commit()
                    total_new += len(chunks)
                    print(f"  + {Path(fpath).name} ({len(chunks)} chunks)")

                except Exception as e:
                    total_errors += 1
                    print(f"  ! Error indexing {fpath}: {e}")

        elif file_type == "jsonl":
            files = [os.path.join(dir_path, f) for f in os.listdir(dir_path)
                     if f.endswith(".jsonl")]

            for fpath in files:
                try:
                    fhash = file_hash(fpath)
                    if not force:
                        existing = db.execute(
                            "SELECT file_hash FROM documents WHERE file_path = ? LIMIT 1",
                            (fpath,)
                        ).fetchone()
                        if existing and existing[0] == fhash:
                            total_skipped += 1
                            continue

                    _delete_file_entries(db, fpath)

                    conversations = extract_jsonl_conversations(fpath)
                    for title, text, metadata in conversations:
                        if not text.strip():
                            continue

                        chunks = chunk_text(text, chunk_size, chunk_overlap)
                        texts_to_embed = []
                        rows = []

                        for i, chunk in enumerate(chunks):
                            rows.append((fpath, source, title, i, chunk, fhash,
                                         datetime.now().isoformat(), metadata))
                            texts_to_embed.append(chunk)

                        doc_ids = []
                        for row in rows:
                            cursor = db.execute(
                                """INSERT INTO documents
                                   (file_path, source, title, chunk_index, content, file_hash, indexed_at, metadata)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                row
                            )
                            doc_ids.append(cursor.lastrowid)

                        embeddings = embed_texts(texts_to_embed)
                        for doc_id, emb in zip(doc_ids, embeddings):
                            db.execute(
                                "INSERT INTO documents_vec(rowid, embedding) VALUES (?, ?)",
                                (doc_id, serialize_vec(emb))
                            )

                        db.commit()
                        total_new += len(chunks)

                    print(f"  + {Path(fpath).name}")

                except Exception as e:
                    total_errors += 1
                    print(f"  ! Error indexing {fpath}: {e}")

    print(f"\nDone! {total_new} chunks indexed, {total_skipped} unchanged files skipped, {total_errors} errors")
    db.close()


def _delete_file_entries(db, file_path):
    """Remove all entries for a file (before re-indexing)."""
    ids = db.execute("SELECT id FROM documents WHERE file_path = ?", (file_path,)).fetchall()
    for (doc_id,) in ids:
        db.execute("DELETE FROM documents_vec WHERE rowid = ?", (doc_id,))
    db.execute("DELETE FROM documents WHERE file_path = ?", (file_path,))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(cfg, query, source=None, limit=10):
    """Hybrid search: FTS5 (BM25) + vector similarity, merged."""
    db = get_db(cfg)

    source_filter = ""
    source_params = ()
    if source:
        source_filter = "AND d.source = ?"
        source_params = (source,)

    # --- FTS5 search ---
    fts_results = {}
    try:
        fts_query = _build_fts_query(query)
        rows = db.execute(f"""
            SELECT d.id, d.file_path, d.source, d.title, d.chunk_index,
                   snippet(documents_fts, 1, '>>>', '<<<', '...', 40) as snippet,
                   bm25(documents_fts) as score
            FROM documents_fts f
            JOIN documents d ON d.id = f.rowid
            WHERE documents_fts MATCH ?
            {source_filter}
            ORDER BY score
            LIMIT ?
        """, (fts_query, *source_params, limit * 2)).fetchall()

        for row in rows:
            doc_id = row[0]
            fts_results[doc_id] = {
                "id": doc_id,
                "file_path": row[1],
                "source": row[2],
                "title": row[3],
                "chunk_index": row[4],
                "snippet": row[5],
                "fts_score": -row[6],  # BM25 returns negative scores
            }
    except Exception as e:
        print(f"FTS search error: {e}")

    # --- Vector search ---
    vec_results = {}
    try:
        query_embedding = embed_texts([query])[0]
        query_bytes = serialize_vec(query_embedding)

        rows = db.execute(f"""
            SELECT v.rowid, v.distance,
                   d.file_path, d.source, d.title, d.chunk_index,
                   substr(d.content, 1, 300) as snippet
            FROM documents_vec v
            JOIN documents d ON d.id = v.rowid
            WHERE embedding MATCH ?
            AND k = ?
            {source_filter}
            ORDER BY distance
        """, (query_bytes, limit * 2, *source_params)).fetchall()

        for row in rows:
            doc_id = row[0]
            vec_results[doc_id] = {
                "id": doc_id,
                "distance": row[1],
                "file_path": row[2],
                "source": row[3],
                "title": row[4],
                "chunk_index": row[5],
                "snippet": row[6],
                "vec_score": 1 - row[1],  # Convert distance to similarity
            }
    except Exception as e:
        print(f"Vector search error: {e}")

    # --- Merge results ---
    all_ids = set(fts_results.keys()) | set(vec_results.keys())
    merged = []

    # Normalize scores
    max_fts = max((r["fts_score"] for r in fts_results.values()), default=1) or 1
    max_vec = max((r["vec_score"] for r in vec_results.values()), default=1) or 1

    for doc_id in all_ids:
        fts = fts_results.get(doc_id, {})
        vec = vec_results.get(doc_id, {})

        fts_norm = fts.get("fts_score", 0) / max_fts
        vec_norm = vec.get("vec_score", 0) / max_vec

        # Weighted combination: slight preference for vector similarity
        combined = 0.4 * fts_norm + 0.6 * vec_norm

        result = {
            "id": doc_id,
            "file_path": fts.get("file_path") or vec.get("file_path"),
            "source": fts.get("source") or vec.get("source"),
            "title": fts.get("title") or vec.get("title"),
            "chunk_index": fts.get("chunk_index") or vec.get("chunk_index", 0),
            "snippet": fts.get("snippet") or vec.get("snippet", ""),
            "combined_score": combined,
            "fts_score": fts.get("fts_score", 0),
            "vec_score": vec.get("vec_score", 0),
            "match_type": _match_type(fts, vec),
        }
        merged.append(result)

    merged.sort(key=lambda x: x["combined_score"], reverse=True)
    db.close()
    return merged[:limit]


def _build_fts_query(query):
    """Build an FTS5 query from natural language — OR between terms for recall."""
    words = re.findall(r'\w+', query.lower())
    if not words:
        return query
    return " OR ".join(words)


def _match_type(fts, vec):
    if fts and vec:
        return "hybrid"
    elif fts:
        return "keyword"
    else:
        return "semantic"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status(cfg):
    db = get_db(cfg)
    total = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    sources = db.execute(
        "SELECT source, COUNT(*) FROM documents GROUP BY source ORDER BY source"
    ).fetchall()
    files = db.execute("SELECT COUNT(DISTINCT file_path) FROM documents").fetchone()[0]
    vec_count = db.execute("SELECT COUNT(*) FROM documents_vec").fetchone()[0]

    print(f"Luoji Search Index Status")
    print(f"{'='*40}")
    print(f"Total chunks:  {total}")
    print(f"Total files:   {files}")
    print(f"Vector count:  {vec_count}")
    print(f"\nBy source:")
    for source, count in sources:
        file_count = db.execute(
            "SELECT COUNT(DISTINCT file_path) FROM documents WHERE source = ?",
            (source,)
        ).fetchone()[0]
        print(f"  {source:20s} {count:5d} chunks from {file_count} files")

    db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_results(results):
    """Pretty-print search results."""
    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        score_parts = []
        if r["fts_score"]:
            score_parts.append(f"kw:{r['fts_score']:.2f}")
        if r["vec_score"]:
            score_parts.append(f"vec:{r['vec_score']:.3f}")
        scores = ", ".join(score_parts)

        print(f"\n{'─'*60}")
        print(f"[{i}] {r['title']}  ({r['match_type']})")
        print(f"    Source: {r['source']} | Score: {r['combined_score']:.3f} ({scores})")
        print(f"    File: {r['file_path']}")
        snippet = r['snippet'].replace('\n', ' ')[:200]
        print(f"    {snippet}")


def main():
    parser = argparse.ArgumentParser(description="Luoji Search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Index command
    idx_parser = subparsers.add_parser("index", help="Index configured directories")
    idx_parser.add_argument("--force", action="store_true", help="Re-index all files")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search indexed content")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--source", "-s", help="Filter by source name")
    search_parser.add_argument("--limit", "-n", type=int, default=10, help="Max results")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Status command
    subparsers.add_parser("status", help="Show index stats")

    args = parser.parse_args()
    cfg = load_config()

    if args.command == "index":
        index_all(cfg, force=args.force)
    elif args.command == "search":
        results = search(cfg, args.query, source=args.source, limit=args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            format_results(results)
    elif args.command == "status":
        show_status(cfg)


if __name__ == "__main__":
    main()
