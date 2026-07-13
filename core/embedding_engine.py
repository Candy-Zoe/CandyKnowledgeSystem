import re
import math
import numpy as np
from collections import Counter
from sentence_transformers import SentenceTransformer
from core.logger import log


class BM25:
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs = []
        self.idf = {}
        self.doc_lens = []
        self.avg_doc_len = 0
        self.documents = []

    def _tokenize(self, text):
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+', text.lower())
        return words

    def fit(self, documents):
        self.documents = documents
        self.doc_lens = []
        self.doc_freqs = []
        df = {}

        for doc in documents:
            tokens = self._tokenize(doc)
            self.doc_lens.append(len(tokens))
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            for word in set(tokens):
                df[word] = df.get(word, 0) + 1

        self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 0
        n = len(documents)
        self.idf = {}
        for word, freq in df.items():
            self.idf[word] = math.log((n - freq + 0.5) / (freq + 0.5) + 1)

    def search(self, query, top_k=5):
        query_tokens = self._tokenize(query)
        if not query_tokens or not self.doc_freqs:
            return []

        scores = []
        avg_len = self.avg_doc_len if self.avg_doc_len > 0 else 1

        for i, doc_freq in enumerate(self.doc_freqs):
            score = 0
            doc_len = self.doc_lens[i]
            for token in query_tokens:
                if token in doc_freq:
                    tf = doc_freq[token]
                    idf = self.idf.get(token, 0)
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / avg_len)
                    score += idf * numerator / denominator
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class Reranker:
    def __init__(self, model_name="BAAI/bge-reranker-base"):
        self.model = None
        self.model_name = model_name

    def load(self):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(self.model_name)

    def rerank(self, query, documents, top_k=5):
        if not self.model:
            return documents[:top_k]

        pairs = [(query, doc["content"]) for doc in documents]
        scores = self.model.predict(pairs)

        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return [{"chunk": doc, "rerank_score": float(score)} for doc, score in ranked[:top_k]]


class EmbeddingEngine:
    def __init__(self, model_name="BAAI/bge-small-zh-v1.5", torch_threads=0, batch_size=16):
        """
        Args:
            model_name: 嵌入模型名称
            torch_threads: PyTorch 线程数，0=使用默认值
            batch_size: 嵌入生成批次大小
        """
        # 限制 PyTorch 线程数，降低 CPU 占用
        if torch_threads > 0:
            import torch
            torch.set_num_threads(torch_threads)
            torch.set_num_interop_threads(min(torch_threads, torch.get_num_interop_threads()))
            log.info(f"PyTorch 线程数限制为: {torch_threads}")

        self.batch_size = batch_size
        log.info(f"加载嵌入模型: {model_name}")
        try:
            self.model = SentenceTransformer(model_name)
            log.info(f"嵌入模型加载成功: {model_name}")
        except Exception as e:
            log.error(f"嵌入模型加载失败: {model_name} - {e}")
            raise
        self.bm25 = BM25()
        self.reranker = None

    def embed_text(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list, batch_size=None) -> np.ndarray:
        bs = batch_size or self.batch_size
        return self.model.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=True)

    def serialize_embedding(self, embedding) -> bytes:
        return embedding.astype(np.float32).tobytes()

    def deserialize_embedding(self, data: bytes) -> np.ndarray:
        return np.frombuffer(data, dtype=np.float32)

    def search_similar(self, query_emb, chunk_embeddings, top_k=5, threshold=0.3):
        if not chunk_embeddings:
            return []

        matrix = np.array([c["embedding"] for c in chunk_embeddings])
        query = query_emb.astype(np.float32)

        similarities = np.dot(matrix, query)

        valid_indices = np.where(similarities >= threshold)[0]
        if len(valid_indices) == 0:
            return []

        top_indices = valid_indices[np.argsort(similarities[valid_indices])[::-1][:top_k]]

        results = []
        for idx in top_indices:
            results.append({
                "chunk": chunk_embeddings[idx],
                "score": float(similarities[idx])
            })
        return results

    def search_bm25(self, query, chunks, top_k=5):
        if not chunks:
            return []

        documents = [c["content"] for c in chunks]
        self.bm25.fit(documents)
        results = self.bm25.search(query, top_k)

        return [{"chunk": chunks[idx], "score": score} for idx, score in results if score > 0]

    def search_hybrid(self, query, chunks, top_k=5, vector_weight=0.7, bm25_weight=0.3):
        if not chunks:
            return []

        query_emb = self.embed_text(query)
        vector_results = self.search_similar(query_emb, chunks, top_k=top_k * 2, threshold=0.1)
        bm25_results = self.search_bm25(query, chunks, top_k=top_k * 2)

        scores = {}
        max_vector = max([r["score"] for r in vector_results], default=1)
        max_bm25 = max([r["score"] for r in bm25_results], default=1)

        for r in vector_results:
            chunk_id = r["chunk"]["id"]
            norm_score = r["score"] / max_vector if max_vector > 0 else 0
            scores[chunk_id] = scores.get(chunk_id, 0) + norm_score * vector_weight

        for r in bm25_results:
            chunk_id = r["chunk"]["id"]
            norm_score = r["score"] / max_bm25 if max_bm25 > 0 else 0
            scores[chunk_id] = scores.get(chunk_id, 0) + norm_score * bm25_weight

        chunk_map = {c["id"]: c for c in chunks}
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [{"chunk": chunk_map[cid], "score": score} for cid, score in ranked if score > 0]

    def rerank_results(self, query, results, top_k=5):
        if not self.reranker:
            self.reranker = Reranker()
            try:
                self.reranker.load()
            except Exception:
                return results[:top_k]

        chunks = [r["chunk"] for r in results]
        return self.reranker.rerank(query, chunks, top_k)
