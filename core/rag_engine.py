from core.embedding_engine import EmbeddingEngine
from core.api_client import APIClient
from core.database import DatabaseManager
from core.logger import log
import config


class RAGEngine:
    def __init__(self, db, embedding_engine):
        self.db = db
        self.embedding_engine = embedding_engine
        self.api_client = None
        self.settings = config.load_settings()
        self.retrieval_mode = self.settings.get("retrieval_mode", config.RETRIEVAL_MODE)
        log.info(f"RAG引擎初始化，检索模式: {self.retrieval_mode}")

    def load_settings(self, settings):
        self.settings = settings
        self.retrieval_mode = settings.get("retrieval_mode", "hybrid")
        if settings.get("api_key"):
            self._init_api_client(settings)
            log.info(f"API客户端已配置: {settings.get('api_provider')}")

    def _init_api_client(self, settings):
        self.api_client = APIClient(
            provider=settings.get("api_provider", "qwen"),
            api_key=settings.get("api_key", ""),
            base_url=settings.get("api_base_url", ""),
            model=settings.get("api_model", ""),
        )

    def is_model_loaded(self):
        return self.api_client is not None

    def get_model_status(self):
        if self.api_client:
            return {
                "loaded": True,
                "type": "api",
                "provider": self.api_client.provider,
                "model": self.api_client.model,
            }
        return {"loaded": False, "message": "未配置API，请在设置中填写API密钥"}

    def retrieve(self, query, top_k=5):
        log.info(f"检索: query='{query[:50]}...' top_k={top_k} mode={self.retrieval_mode}")
        chunks = self.db.get_all_chunks_with_embeddings()
        if not chunks:
            log.warning("知识库为空，无法检索")
            return []

        if self.retrieval_mode == "bm25":
            results = self.embedding_engine.search_bm25(query, chunks, top_k)
        elif self.retrieval_mode == "hybrid":
            results = self.embedding_engine.search_hybrid(
                query, chunks, top_k,
                vector_weight=self.settings.get("vector_weight", 0.7),
                bm25_weight=self.settings.get("bm25_weight", 0.3),
            )
        else:
            query_emb = self.embedding_engine.embed_text(query)
            results = self.embedding_engine.search_similar(
                query_emb, chunks, top_k=top_k,
                threshold=self.settings.get("similarity_threshold", 0.3),
            )
        
        log.info(f"检索完成: 找到 {len(results)} 个结果")
        return results

    def set_retrieval_mode(self, mode):
        if mode in ("vector", "bm25", "hybrid"):
            self.retrieval_mode = mode
            return True
        return False

    def _build_prompt(self, query, context_chunks, history=None):
        context = "\n\n".join(["[%d] %s" % (i+1, c['chunk']['content'][:800]) for i, c in enumerate(context_chunks)])
        system_msg = "你是一个知识库助手，请根据提供的参考资料准确回答用户的问题。回答要完整、有条理。如果参考资料中没有相关信息，请说明。"
        messages = [{"role": "system", "content": system_msg}]
        if history:
            for h in history[-6:]:
                messages.append({"role": "user", "content": h["user"]})
                messages.append({"role": "assistant", "content": h["assistant"]})
        user_msg = "参考资料：\n%s\n\n问题：%s" % (context, query)
        messages.append({"role": "user", "content": user_msg})
        return messages

    def _get_no_model_msg(self, context_chunks):
        context = "\n".join(["[%d] %s" % (i+1, c['chunk']['content'][:200]) for i, c in enumerate(context_chunks)])
        return "根据知识库检索到以下相关内容：\n\n%s\n\n（提示：未配置API，请在设置中填写API密钥以启用智能回答。）" % context

    def generate_answer(self, query, context_chunks, history=None):
        if not self.api_client:
            log.warning("未配置API，返回检索结果")
            return self._get_no_model_msg(context_chunks)

        messages = self._build_prompt(query, context_chunks, history)
        try:
            log.info(f"调用API生成回答: {self.api_client.provider}/{self.api_client.model}")
            answer = self.api_client.chat(
                messages,
                temperature=self.settings.get("temperature", 0.7),
                max_tokens=self.settings.get("max_tokens", 1024),
            )
            log.info(f"API回答生成完成: {len(answer)} 字符")
            return answer
        except Exception as e:
            log.error(f"API调用失败: {e}")
            return "API调用失败: %s" % str(e)

    def generate_answer_stream(self, query, context_chunks, history=None):
        if not self.api_client:
            yield self._get_no_model_msg(context_chunks)
            return

        messages = self._build_prompt(query, context_chunks, history)
        try:
            for chunk in self.api_client.chat(
                messages,
                temperature=self.settings.get("temperature", 0.7),
                max_tokens=self.settings.get("max_tokens", 1024),
                stream=True,
            ):
                yield chunk
        except Exception as e:
            yield "API调用失败: %s" % str(e)

    def query(self, query, top_k=5, history=None):
        results = self.retrieve(query, top_k)
        if not results:
            return {"answer": "未找到相关知识，请尝试其他问题。", "sources": []}
        answer = self.generate_answer(query, results, history)
        sources = []
        for r in results:
            chunk = r["chunk"]
            sources.append({
                "chunk_id": chunk["id"],
                "document": chunk.get("original_name", "Unknown"),
                "content_preview": chunk["content"][:300],
                "score": round(r["score"], 4),
            })
        return {"answer": answer, "sources": sources, "retrieval_mode": self.retrieval_mode}

    def query_stream(self, query, top_k=5, history=None):
        results = self.retrieve(query, top_k)
        if not results:
            yield {"type": "answer", "content": "未找到相关知识，请尝试其他问题。"}
            yield {"type": "sources", "content": []}
            return
        sources = []
        for r in results:
            chunk = r["chunk"]
            sources.append({
                "chunk_id": chunk["id"],
                "document": chunk.get("original_name", "Unknown"),
                "content_preview": chunk["content"][:300],
                "score": round(r["score"], 4),
            })
        yield {"type": "sources", "content": sources}
        for chunk in self.generate_answer_stream(query, results, history):
            yield {"type": "answer", "content": chunk}
