import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from core.embedding_engine import EmbeddingEngine
from core.database import DatabaseManager
import config


class RAGEngine:
    def __init__(self, db, embedding_engine, model_path=None):
        self.db = db
        self.embedding_engine = embedding_engine
        self.model = None
        self.tokenizer = None
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path):
        base_model_name = config.DEFAULT_BASE_MODEL
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        self.model = PeftModel.from_pretrained(base_model, model_path)
        self.model.eval()

    def retrieve(self, query, top_k=5):
        chunks = self.db.get_all_chunks_with_embeddings()
        if not chunks:
            return []
        query_emb = self.embedding_engine.embed_text(query)
        results = self.embedding_engine.search_similar(query_emb, chunks, top_k=top_k, threshold=config.SIMILARITY_THRESHOLD)
        return results

    def generate_answer(self, query, context_chunks):
        if not self.model:
            context = "\n".join(["[%d] %s" % (i+1, c['chunk']['content']) for i, c in enumerate(context_chunks)])
            return "根据知识库检索到以下相关内容：\n\n%s\n\n（提示：未加载微调模型，仅展示检索结果。请先微调模型以获得AI生成的回答。）" % context

        context = "\n".join(["[%d] %s" % (i+1, c['chunk']['content'][:500]) for i, c in enumerate(context_chunks)])
        messages = [
            {"role": "system", "content": "你是一个知识库助手，请根据提供的参考资料回答用户的问题。如果参考资料中没有相关信息，请说明。"},
            {"role": "user", "content": "参考资料：\n%s\n\n问题：%s" % (context, query)}
        ]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=512, temperature=0.3, do_sample=True)
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

    def query(self, query, top_k=5):
        results = self.retrieve(query, top_k)
        if not results:
            return {"answer": "未找到相关知识，请尝试其他问题。", "sources": []}
        answer = self.generate_answer(query, results)
        sources = []
        for r in results:
            chunk = r["chunk"]
            sources.append({
                "chunk_id": chunk["id"],
                "document": chunk.get("original_name", "Unknown"),
                "content_preview": chunk["content"][:300],
                "score": round(r["score"], 4)
            })
        return {"answer": answer, "sources": sources}
