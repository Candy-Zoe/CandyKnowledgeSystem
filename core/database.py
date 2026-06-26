import sqlite3
import json
import numpy as np
from pathlib import Path
from datetime import datetime


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = self.get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()
        cursor.executescript(SCHEMA)
        has_default_kb = cursor.execute("SELECT COUNT(*) FROM knowledge_bases WHERE id=1").fetchone()[0]
        if not has_default_kb:
            cursor.execute("INSERT OR IGNORE INTO knowledge_bases (id, name, description) VALUES (1, '默认知识库', '默认知识库')")
        conn.commit()
        conn.close()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_document(self, filename, original_name, file_type, file_size, file_path, kb_id=None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        if kb_id:
            cursor.execute(
                "INSERT INTO documents (filename, original_name, file_type, file_size, file_path, kb_id) VALUES (?, ?, ?, ?, ?, ?)",
                (filename, original_name, file_type, file_size, file_path, kb_id)
            )
        else:
            cursor.execute(
                "INSERT INTO documents (filename, original_name, file_type, file_size, file_path) VALUES (?, ?, ?, ?, ?)",
                (filename, original_name, file_type, file_size, file_path)
            )
        doc_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return doc_id

    def update_document_status(self, doc_id, status, error_message=None):
        conn = self.get_connection()
        conn.execute(
            "UPDATE documents SET status=?, error_message=?, updated_at=? WHERE id=?",
            (status, error_message, datetime.now().isoformat(), doc_id)
        )
        conn.commit()
        conn.close()

    def update_document_chunks(self, doc_id, total_chunks):
        conn = self.get_connection()
        conn.execute(
            "UPDATE documents SET total_chunks=?, updated_at=? WHERE id=?",
            (total_chunks, datetime.now().isoformat(), doc_id)
        )
        conn.commit()
        conn.close()

    def get_document(self, doc_id) -> dict:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_documents(self, status=None) -> list:
        conn = self.get_connection()
        if status:
            rows = conn.execute("SELECT * FROM documents WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_document(self, doc_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM training_pairs WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        return True

    def create_chunks(self, document_id, chunks: list) -> list:
        conn = self.get_connection()
        cursor = conn.cursor()
        ids = []
        for chunk in chunks:
            embedding_blob = None
            if chunk.get("embedding") is not None:
                embedding_blob = chunk["embedding"].astype(np.float32).tobytes()
            cursor.execute(
                "INSERT INTO chunks (document_id, chunk_index, content, token_count, embedding) VALUES (?, ?, ?, ?, ?)",
                (document_id, chunk["chunk_index"], chunk["content"], chunk.get("token_count", 0), embedding_blob)
            )
            ids.append(cursor.lastrowid)
        conn.commit()
        conn.close()
        return ids

    def get_chunks_by_document(self, doc_id) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY chunk_index", (doc_id,)).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d["embedding"]:
                d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
            result.append(d)
        return result

    def get_all_chunks_with_embeddings(self) -> list:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT c.*, d.original_name FROM chunks c JOIN documents d ON c.document_id=d.id WHERE c.embedding IS NOT NULL"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
            result.append(d)
        return result

    def search_chunks_by_ids(self, chunk_ids: list) -> list:
        if not chunk_ids:
            return []
        conn = self.get_connection()
        placeholders = ",".join("?" * len(chunk_ids))
        rows = conn.execute(f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d["embedding"]:
                d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
            result.append(d)
        return result

    def create_training_pair(self, question, answer, source_chunk_ids=None, document_id=None, is_generated=False) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO training_pairs (question, answer, source_chunk_ids, document_id, is_generated) VALUES (?, ?, ?, ?, ?)",
            (question, answer, json.dumps(source_chunk_ids) if source_chunk_ids else None, document_id, int(is_generated))
        )
        pair_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return pair_id

    def list_training_pairs(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM training_pairs ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_training_pair(self, pair_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM training_pairs WHERE id=?", (pair_id,))
        conn.commit()
        conn.close()
        return True

    def create_finetune_job(self, model_name, base_model, training_samples, epochs, lora_rank) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO finetune_jobs (model_name, base_model, training_samples, epochs, lora_rank) VALUES (?, ?, ?, ?, ?)",
            (model_name, base_model, training_samples, epochs, lora_rank)
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id

    def update_finetune_job(self, job_id, **kwargs):
        conn = self.get_connection()
        sets = []
        values = []
        for k, v in kwargs.items():
            sets.append(f"{k}=?")
            values.append(v)
        values.append(job_id)
        conn.execute(f"UPDATE finetune_jobs SET {','.join(sets)} WHERE id=?", values)
        conn.commit()
        conn.close()

    def list_finetune_jobs(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM finetune_jobs ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def export_to_json(self, output_path: str):
        conn = self.get_connection()
        data = {}
        for table in ["documents", "chunks", "training_pairs", "finetune_jobs"]:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(r) for r in rows]
        conn.close()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def export_to_sql(self, output_path: str):
        conn = self.get_connection()
        with open(output_path, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()

    def import_from_json(self, json_path: str):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        conn = self.get_connection()
        for table, rows in data.items():
            if not rows:
                continue
            for row in rows:
                cols = list(row.keys())
                placeholders = ",".join("?" * len(cols))
                vals = [row[c] for c in cols]
                conn.execute(f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        conn.close()

    def search_chunks(self, keyword: str, doc_id=None) -> list:
        conn = self.get_connection()
        try:
            if doc_id:
                rows = conn.execute(
                    """SELECT c.*, d.original_name FROM chunks c
                    JOIN documents d ON c.document_id=d.id
                    WHERE c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?) AND c.document_id=?
                    ORDER BY c.chunk_index""",
                    (keyword, doc_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT c.*, d.original_name FROM chunks c
                    JOIN documents d ON c.document_id=d.id
                    WHERE c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?)
                    ORDER BY c.document_id, c.chunk_index""",
                    (keyword,)
                ).fetchall()
        except Exception:
            if doc_id:
                rows = conn.execute(
                    "SELECT c.*, d.original_name FROM chunks c JOIN documents d ON c.document_id=d.id WHERE c.content LIKE ? AND c.document_id=? ORDER BY c.chunk_index",
                    (f"%{keyword}%", doc_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT c.*, d.original_name FROM chunks c JOIN documents d ON c.document_id=d.id WHERE c.content LIKE ? ORDER BY c.document_id, c.chunk_index",
                    (f"%{keyword}%",)
                ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d["embedding"]:
                d["embedding"] = np.frombuffer(d["embedding"], dtype=np.float32)
            result.append(d)
        return result

    def get_document_content(self, doc_id) -> str:
        chunks = self.get_chunks_by_document(doc_id)
        return "\n\n".join([c["content"] for c in chunks])

    def get_stats(self, kb_id=None) -> dict:
        conn = self.get_connection()
        if kb_id:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE kb_id=?", (kb_id,)).fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks c JOIN documents d ON c.document_id=d.id WHERE d.kb_id=?", (kb_id,)).fetchone()[0]
            total_size = conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM documents WHERE kb_id=?", (kb_id,)).fetchone()[0]
        else:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            total_size = conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM documents").fetchone()[0]
        pair_count = conn.execute("SELECT COUNT(*) FROM training_pairs").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM documents WHERE status='completed'").fetchone()[0]
        conv_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        api_count = conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
        conn.close()
        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "training_pair_count": pair_count,
            "completed_documents": completed,
            "conversation_count": conv_count,
            "message_count": msg_count,
            "api_call_count": api_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }

    def create_knowledge_base(self, name, description="") -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO knowledge_bases (name, description) VALUES (?, ?)", (name, description))
        kb_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return kb_id

    def list_knowledge_bases(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM knowledge_bases ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_knowledge_base(self, kb_id) -> bool:
        conn = self.get_connection()
        conn.execute("UPDATE documents SET kb_id=NULL WHERE kb_id=?", (kb_id,))
        conn.execute("DELETE FROM knowledge_bases WHERE id=?", (kb_id,))
        conn.commit()
        conn.close()
        return True

    def create_conversation(self, title="新对话", kb_id=None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO conversations (title, kb_id) VALUES (?, ?)", (title, kb_id))
        conv_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return conv_id

    def list_conversations(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id) -> dict:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_conversation(self, conv_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        conn.commit()
        conn.close()
        return True

    def add_message(self, conversation_id, role, content, sources=None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        import json
        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content, sources) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, json.dumps(sources) if sources else None)
        )
        msg_id = cursor.lastrowid
        conn.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conversation_id,))
        conn.commit()
        conn.close()
        return msg_id

    def get_messages(self, conversation_id) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,)).fetchall()
        conn.close()
        import json
        result = []
        for r in rows:
            d = dict(r)
            if d["sources"]:
                d["sources"] = json.loads(d["sources"])
            result.append(d)
        return result

    def log_api_call(self, endpoint, method, status_code, response_time=None):
        conn = self.get_connection()
        conn.execute(
            "INSERT INTO api_calls (endpoint, method, status_code, response_time) VALUES (?, ?, ?, ?)",
            (endpoint, method, status_code, response_time)
        )
        conn.commit()
        conn.close()

    def get_api_stats(self) -> dict:
        conn = self.get_connection()
        total = conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM api_calls WHERE date(created_at)=date('now')").fetchone()[0]
        by_endpoint = conn.execute("SELECT endpoint, COUNT(*) as cnt FROM api_calls GROUP BY endpoint ORDER BY cnt DESC LIMIT 10").fetchall()
        conn.close()
        return {
            "total_calls": total,
            "today_calls": today,
            "by_endpoint": [{"endpoint": r["endpoint"], "count": r["cnt"]} for r in by_endpoint]
        }

    def get_hot_questions(self, limit=10) -> list:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT content, COUNT(*) as cnt FROM messages WHERE role='user' GROUP BY content ORDER BY cnt DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"question": r["content"], "count": r["cnt"]} for r in rows]

    def save_summary(self, doc_id, summary) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO document_summaries (document_id, summary) VALUES (?, ?)",
            (doc_id, summary)
        )
        sid = cursor.lastrowid
        conn.commit()
        conn.close()
        return sid

    def get_summary(self, doc_id) -> str:
        conn = self.get_connection()
        row = conn.execute("SELECT summary FROM document_summaries WHERE document_id=?", (doc_id,)).fetchone()
        conn.close()
        return row["summary"] if row else None

    def save_batch_result(self, batch_id, question, answer, sources=None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        import json
        cursor.execute(
            "INSERT INTO batch_results (batch_id, question, answer, sources) VALUES (?, ?, ?, ?)",
            (batch_id, question, answer, json.dumps(sources) if sources else None)
        )
        rid = cursor.lastrowid
        conn.commit()
        conn.close()
        return rid

    def get_batch_results(self, batch_id) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM batch_results WHERE batch_id=? ORDER BY id", (batch_id,)).fetchall()
        conn.close()
        import json
        result = []
        for r in rows:
            d = dict(r)
            if d["sources"]:
                d["sources"] = json.loads(d["sources"])
            result.append(d)
        return result

    def save_ocr_result(self, image_path, text, doc_id=None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ocr_results (image_path, extracted_text, document_id) VALUES (?, ?, ?)",
            (image_path, text, doc_id)
        )
        rid = cursor.lastrowid
        conn.commit()
        conn.close()
        return rid

    def create_user(self, username, password_hash, role="user") -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role)
        )
        uid = cursor.lastrowid
        conn.commit()
        conn.close()
        return uid

    def get_user(self, username) -> dict:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_users(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_user(self, user_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        return True

    def create_scheduled_task(self, name, folder_path, interval_minutes=60) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO scheduled_tasks (name, folder_path, interval_minutes) VALUES (?, ?, ?)",
            (name, folder_path, interval_minutes)
        )
        tid = cursor.lastrowid
        conn.commit()
        conn.close()
        return tid

    def list_scheduled_tasks(self) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_scheduled_task(self, task_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM scheduled_tasks WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        return True

    def update_scheduled_task(self, task_id, **kwargs):
        conn = self.get_connection()
        sets = []
        values = []
        for k, v in kwargs.items():
            sets.append(f"{k}=?")
            values.append(v)
        values.append(task_id)
        conn.execute(f"UPDATE scheduled_tasks SET {','.join(sets)} WHERE id=?", values)
        conn.commit()
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id INTEGER DEFAULT 1,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    total_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS training_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_chunk_ids TEXT,
    document_id INTEGER,
    is_generated INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS finetune_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    base_model TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    training_samples INTEGER,
    epochs INTEGER,
    lora_rank INTEGER,
    output_path TEXT,
    metrics TEXT,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT DEFAULT '新对话',
    kb_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER UNIQUE NOT NULL,
    summary TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS batch_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    sources TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER,
    response_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    extracted_text TEXT,
    document_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    interval_minutes INTEGER DEFAULT 60,
    enabled INTEGER DEFAULT 1,
    last_run TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks(id);
CREATE INDEX IF NOT EXISTS idx_training_pairs_document_id ON training_pairs(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_kb_id ON documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_batch_results_batch_id ON batch_results(batch_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, document_id, content=chunks, content_rowid=id);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content, document_id) VALUES (new.id, new.content, new.document_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, document_id) VALUES('delete', old.id, old.content, old.document_id);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, document_id) VALUES('delete', old.id, old.content, old.document_id);
    INSERT INTO chunks_fts(rowid, content, document_id) VALUES (new.id, new.content, new.document_id);
END;
"""
