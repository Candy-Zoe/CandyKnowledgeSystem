import sqlite3
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
        cursor.execute(
            """INSERT OR IGNORE INTO document_knowledge_bases (document_id, kb_id)
               SELECT d.id, d.kb_id
               FROM documents d
               JOIN knowledge_bases k ON d.kb_id=k.id"""
        )
        cursor.execute(
            """INSERT OR IGNORE INTO document_knowledge_bases (document_id, kb_id)
               SELECT d.id, 1
               FROM documents d
               WHERE NOT EXISTS (
                   SELECT 1 FROM document_knowledge_bases dkb WHERE dkb.document_id=d.id
               )"""
        )
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
        target_kb_id = kb_id or 1
        cursor.execute(
            "INSERT OR IGNORE INTO document_knowledge_bases (document_id, kb_id) VALUES (?, ?)",
            (doc_id, target_kb_id),
        )
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
        where = ""
        params = []
        if status:
            where = "WHERE d.status=?"
            params.append(status)
        rows = conn.execute(
            f"""SELECT d.*,
                       GROUP_CONCAT(k.id) AS kb_ids,
                       GROUP_CONCAT(k.name, ', ') AS kb_names
                FROM documents d
                LEFT JOIN document_knowledge_bases dkb ON d.id=dkb.document_id
                LEFT JOIN knowledge_bases k ON dkb.kb_id=k.id
                {where}
                GROUP BY d.id
                ORDER BY d.created_at DESC""",
            params,
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_documents_by_knowledge_base(self, kb_id: int) -> list:
        conn = self.get_connection()
        rows = conn.execute(
            """SELECT d.*,
                      GROUP_CONCAT(k.id) AS kb_ids,
                      GROUP_CONCAT(k.name, ', ') AS kb_names
               FROM documents d
               JOIN document_knowledge_bases selected ON d.id=selected.document_id
               LEFT JOIN document_knowledge_bases dkb ON d.id=dkb.document_id
               LEFT JOIN knowledge_bases k ON dkb.kb_id=k.id
               WHERE selected.kb_id=?
               GROUP BY d.id
               ORDER BY d.created_at DESC""",
            (kb_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_document_chunks(self, doc_id) -> bool:
        """删除文档的所有分块（保留文档记录本身）"""
        conn = self.get_connection()
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        conn.commit()
        conn.close()
        return True

    def delete_document(self, doc_id) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM document_knowledge_bases WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
        conn.close()
        return True

    def create_chunks(self, document_id, chunks: list) -> list:
        conn = self.get_connection()
        cursor = conn.cursor()
        ids = []
        for chunk in chunks:
            cursor.execute(
                "INSERT INTO chunks (document_id, chunk_index, content, token_count) VALUES (?, ?, ?, ?)",
                (document_id, chunk["chunk_index"], chunk["content"], chunk.get("token_count", 0))
            )
            ids.append(cursor.lastrowid)
        conn.commit()
        conn.close()
        return ids

    def get_chunks_by_document(self, doc_id) -> list:
        conn = self.get_connection()
        rows = conn.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY chunk_index", (doc_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_content(self, keywords: str, kb_id=None, match_mode="all", limit=500) -> list:
        """按一个或多个关键词检索知识库分块。

        Args:
            keywords: 用户输入的关键词，支持空格、逗号、分号分隔。
            kb_id: 限定知识库ID，None 表示全部知识库。
            match_mode: all=所有关键词都出现，any=任一关键词出现。
            limit: 最大返回条数。
        """
        terms = [
            t.strip()
            for t in str(keywords).replace("，", " ").replace(",", " ").replace("；", " ").replace(";", " ").split()
            if t.strip()
        ]
        if not terms:
            return []

        operator = " AND " if match_mode == "all" else " OR "
        fts_query = operator.join([self._escape_fts_term(t) for t in terms])
        like_operator = " AND " if match_mode == "all" else " OR "
        like_clause = like_operator.join(["c.content LIKE ?" for _ in terms])

        conn = self.get_connection()
        rows = []
        try:
            params = [fts_query]
            kb_clause = ""
            if kb_id:
                kb_clause = " AND EXISTS (SELECT 1 FROM document_knowledge_bases dkb WHERE dkb.document_id=d.id AND dkb.kb_id=?)"
                params.append(kb_id)
            params.append(limit)
            rows = conn.execute(
                f"""SELECT c.*, d.original_name, d.file_type, d.file_path, d.kb_id, d.total_chunks
                    FROM chunks c
                    JOIN documents d ON c.document_id=d.id
                    WHERE c.id IN (SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?)
                    {kb_clause}
                    ORDER BY d.original_name, c.chunk_index
                    LIMIT ?""",
                params,
            ).fetchall()
        except Exception:
            rows = []

        if not rows:
            params = [f"%{t}%" for t in terms]
            kb_clause = ""
            if kb_id:
                kb_clause = " AND EXISTS (SELECT 1 FROM document_knowledge_bases dkb WHERE dkb.document_id=d.id AND dkb.kb_id=?)"
                params.append(kb_id)
            params.append(limit)
            rows = conn.execute(
                f"""SELECT c.*, d.original_name, d.file_type, d.file_path, d.kb_id, d.total_chunks
                    FROM chunks c
                    JOIN documents d ON c.document_id=d.id
                    WHERE ({like_clause}) {kb_clause}
                    ORDER BY d.original_name, c.chunk_index
                    LIMIT ?""",
                params,
            ).fetchall()
        conn.close()

        result = []
        for r in rows:
            item = dict(r)
            item["matched_terms"] = [t for t in terms if t.lower() in item["content"].lower()]
            item["snippet"] = self._make_snippet(item["content"], terms)
            result.append(item)
        return result

    def get_chunk_context(self, chunk_id: int, radius=1) -> dict:
        """返回命中分块及前后相邻分块，供原文预览使用。"""
        conn = self.get_connection()
        row = conn.execute(
            """SELECT c.*, d.original_name, d.file_type, d.file_path, d.total_chunks
               FROM chunks c JOIN documents d ON c.document_id=d.id
               WHERE c.id=?""",
            (chunk_id,),
        ).fetchone()
        if not row:
            conn.close()
            return {}

        chunk = dict(row)
        start = max(0, chunk["chunk_index"] - radius)
        end = chunk["chunk_index"] + radius
        rows = conn.execute(
            """SELECT * FROM chunks
               WHERE document_id=? AND chunk_index BETWEEN ? AND ?
               ORDER BY chunk_index""",
            (chunk["document_id"], start, end),
        ).fetchall()
        conn.close()
        chunk["context"] = [dict(r) for r in rows]
        return chunk

    @staticmethod
    def _escape_fts_term(term: str) -> str:
        escaped = str(term).replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _make_snippet(content: str, terms: list, window=90) -> str:
        text = content or ""
        lower = text.lower()
        positions = [lower.find(t.lower()) for t in terms if t and lower.find(t.lower()) >= 0]
        if not positions:
            return text[: window * 2] + ("..." if len(text) > window * 2 else "")
        pos = min(positions)
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return prefix + text[start:end].strip() + suffix

    def get_document_content(self, doc_id) -> str:
        chunks = self.get_chunks_by_document(doc_id)
        return "\n\n".join([c["content"] for c in chunks])

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
        conn.execute("DELETE FROM document_knowledge_bases WHERE kb_id=?", (kb_id,))
        conn.execute("DELETE FROM knowledge_bases WHERE id=?", (kb_id,))
        conn.commit()
        conn.close()
        return True

    def add_document_to_knowledge_base(self, doc_id: int, kb_id: int) -> bool:
        conn = self.get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO document_knowledge_bases (document_id, kb_id) VALUES (?, ?)",
            (doc_id, kb_id),
        )
        conn.commit()
        conn.close()
        return True

    def move_document_to_knowledge_base(self, doc_id: int, kb_id: int) -> bool:
        conn = self.get_connection()
        conn.execute("DELETE FROM document_knowledge_bases WHERE document_id=?", (doc_id,))
        conn.execute(
            "INSERT OR IGNORE INTO document_knowledge_bases (document_id, kb_id) VALUES (?, ?)",
            (doc_id, kb_id),
        )
        conn.execute("UPDATE documents SET kb_id=? WHERE id=?", (kb_id, doc_id))
        conn.commit()
        conn.close()
        return True

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

CREATE TABLE IF NOT EXISTS document_knowledge_bases (
    document_id INTEGER NOT NULL,
    kb_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, kb_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_kbs_document_id ON document_knowledge_bases(document_id);
CREATE INDEX IF NOT EXISTS idx_document_kbs_kb_id ON document_knowledge_bases(kb_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_kb_id ON documents(kb_id);

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
