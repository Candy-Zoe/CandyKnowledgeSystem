import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingEngine:
    def __init__(self, model_name="BAAI/bge-small-zh-v1.5"):
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True)

    def embed_batch(self, texts: list, batch_size=64) -> np.ndarray:
        return self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=True)

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
