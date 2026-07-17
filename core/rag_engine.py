"""
RAG 引擎 - 检索增强生成

支持两种模式：
1. 仅检索模式 (local): 不使用LLM，直接返回知识库检索结果并格式化
2. LLM模式: 将检索结果作为上下文，调用云端/本地LLM生成回答
"""
import logging
from core.database import DatabaseManager
from core.embedding_engine import EmbeddingEngine
from core.api_client import APIClient

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self, db: DatabaseManager, embed_engine: EmbeddingEngine,
                 api_client: APIClient, top_k=5, retrieval_mode="hybrid"):
        self.db = db
        self.embed_engine = embed_engine
        self.api_client = api_client
        self.top_k = top_k
        self.retrieval_mode = retrieval_mode

    def retrieve(self, query: str):
        """检索相关文档片段"""
        chunks = self.db.get_all_chunks_with_embeddings()
        if not chunks:
            logger.warning("知识库为空，没有可检索的chunk")
            return []

        chunk_texts = [row["content"] for row in chunks]
        chunk_ids = [row["id"] for row in chunks]

        if self.retrieval_mode == "bm25":
            results = self.embed_engine.search_bm25(query, chunk_texts, chunk_ids, self.top_k)
        elif self.retrieval_mode == "hybrid":
            results = self.embed_engine.search_hybrid(
                query, chunk_texts, chunk_ids, self.top_k,
                vector_weight=0.7, bm25_weight=0.3
            )
        else:
            results = self.embed_engine.search_similar(query, chunk_texts, chunk_ids, self.top_k)

        sources = []
        for r in results:
            chunk_id = r["chunk_id"]
            score = r["score"]
            # 找到对应的完整chunk信息
            chunk_info = None
            for row in chunks:
                if row["id"] == chunk_id:
                    chunk_info = row
                    break

            if chunk_info:
                sources.append({
                    "chunk_id": chunk_id,
                    "score": round(score, 4),
                    "content": chunk_info["content"],
                    "document_id": chunk_info.get("document_id", ""),
                    "file_type": chunk_info.get("file_type", ""),
                    "file_path": chunk_info.get("file_path", ""),
                    "original_name": chunk_info.get("original_name", "未知文件"),
                    "chunk_index": chunk_info.get("chunk_index", 0),
                    "total_chunks": chunk_info.get("total_chunks", 0),
                })

        logger.info(f"检索完成: query='{query[:30]}...', 找到{len(sources)}个结果")
        return sources

    def query(self, question: str) -> dict:
        """完整问答流程（同步）"""
        sources = self.retrieve(question)
        if not sources:
            return {
                "answer": "未在知识库中找到相关内容。请先上传相关文档到知识库中。",
                "sources": [],
            }

        if self.api_client.is_local:
            answer = self._format_local_answer(question, sources)
        else:
            context = self._build_context(sources)
            messages = self._build_messages(question, context)
            answer = self.api_client.chat(messages)

        return {"answer": answer, "sources": sources}

    def query_stream(self, question: str):
        """完整问答流程（流式）"""
        sources = self.retrieve(question)
        if not sources:
            yield from self._yield_text("未在知识库中找到相关内容。请先上传相关文档到知识库中。")
            return

        if self.api_client.is_local:
            for chunk in self._format_local_answer_stream(question, sources):
                yield chunk
        else:
            context = self._build_context(sources)
            messages = self._build_messages(question, context)
            for chunk in self.api_client.chat(messages, stream=True):
                yield chunk

    def _build_context(self, sources: list) -> str:
        """构建上下文文本"""
        parts = []
        for i, s in enumerate(sources, 1):
            filename = s.get("original_name", "未知")
            parts.append(f"[来源{i}] 文件: {filename}\n{s['content']}")
        return "\n\n".join(parts)

    def _build_messages(self, question: str, context: str) -> list:
        """构建LLM消息"""
        system_prompt = (
            "你是一个知识库问答助手。请根据以下参考资料回答用户的问题。\n"
            "要求：\n"
            "1. 如果参考资料中有答案，请基于参考资料进行回答，并在回答中引用相关来源（如'[来源1]'）\n"
            "2. 如果参考资料不足以回答问题，请诚实说明\n"
            "3. 回答要简洁、准确、有条理\n"
            "4. 使用中文回答"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"参考资料：\n{context}\n\n问题：{question}"},
        ]

    def _format_local_answer(self, question: str, sources: list) -> str:
        """仅检索模式：格式化检索结果为回答"""
        lines = []
        lines.append(f"🔍 **关于「{question}」的检索结果**\n")
        lines.append(f"共找到 {len(sources)} 个相关片段：\n")

        for i, s in enumerate(sources, 1):
            filename = s.get("original_name", "未知")
            score = s.get("score", 0)
            chunk_idx = s.get("chunk_index", 0)
            total = s.get("total_chunks", 0)
            content = s.get("content", "")

            relevance = "★★★★★" if score >= 0.8 else "★★★★☆" if score >= 0.6 else "★★★☆☆" if score >= 0.4 else "★★☆☆☆"

            lines.append(f"---")
            lines.append(f"### 📄 来源{i}：{filename}  (片段 {chunk_idx+1}/{total})")
            lines.append(f"📊 相关度: {relevance} ({score:.2%})")
            lines.append(f"")
            lines.append(f"{content}")
            lines.append(f"")

        lines.append(f"---")
        lines.append(f"💡 **提示**: 这是基于关键词匹配+语义相似度从知识库中检索到的原始内容。")
        lines.append(f"如需AI总结，请切换到云端API或安装Ollama本地模型。")

        return "\n".join(lines)

    def _format_local_answer_stream(self, question: str, sources: list):
        """仅检索模式：流式输出格式化结果"""
        lines = self._format_local_answer(question, sources).split("\n")
        for line in lines:
            yield line + "\n"

    def _yield_text(self, text: str):
        """将文本逐字yield（模拟流式效果）"""
        for i in range(0, len(text), 3):
            yield text[i:i+3]

    def generate_answer(self, question: str, sources: list):
        """使用LLM基于检索结果生成回答"""
        if self.api_client.is_local:
            return self._format_local_answer(question, sources)
        context = self._build_context(sources)
        messages = self._build_messages(question, context)
        return self.api_client.chat(messages)

    def generate_answer_stream(self, question: str, sources: list):
        if self.api_client.is_local:
            for chunk in self._format_local_answer_stream(question, sources):
                yield chunk
        else:
            context = self._build_context(sources)
            messages = self._build_messages(question, context)
            for chunk in self.api_client.chat(messages, stream=True):
                yield chunk