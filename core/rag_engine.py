import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from peft import PeftModel
from threading import Thread
from core.embedding_engine import EmbeddingEngine
from core.api_client import APIClient
from core.database import DatabaseManager
import config


class RAGEngine:
    def __init__(self, db, embedding_engine, model_path=None):
        self.db = db
        self.embedding_engine = embedding_engine
        self.model = None
        self.tokenizer = None
        self.model_path = None
        self.model_type = None
        self.api_client = None
        self.settings = config.load_settings()
        self.retrieval_mode = self.settings.get("retrieval_mode", config.RETRIEVAL_MODE)
        if model_path:
            self.load_model(model_path)

    def load_settings(self, settings):
        self.settings = settings
        self.retrieval_mode = settings.get("retrieval_mode", "hybrid")
        if settings.get("model_source") == "api":
            self._init_api_client(settings)

    def _init_api_client(self, settings):
        self.api_client = APIClient(
            provider=settings.get("api_provider", "qwen"),
            api_key=settings.get("api_key", ""),
            base_url=settings.get("api_base_url", ""),
            model=settings.get("api_model", ""),
        )

    def load_model(self, model_path, model_type="finetuned"):
        model_path = str(model_path)
        self.api_client = None

        if model_type == "custom":
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
            )
        else:
            base_model_name = config.DEFAULT_BASE_MODEL
            self.tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_name, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
            )
            self.model = PeftModel.from_pretrained(base_model, model_path)

        self.model.eval()
        self.model_path = model_path
        self.model_type = model_type

    def unload_model(self):
        self.model = None
        self.tokenizer = None
        self.model_path = None
        self.model_type = None
        self.api_client = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def is_model_loaded(self):
        return self.model is not None or self.api_client is not None

    def get_model_status(self):
        if self.api_client:
            return {
                "loaded": True,
                "type": "api",
                "provider": self.api_client.provider,
                "model": self.api_client.model,
            }
        if self.model is None:
            return {"loaded": False, "message": "未加载模型"}
        return {
            "loaded": True,
            "path": self.model_path,
            "type": self.model_type,
            "device": str(self.model.device),
        }

    def retrieve(self, query, top_k=5):
        chunks = self.db.get_all_chunks_with_embeddings()
        if not chunks:
            return []

        if self.retrieval_mode == "bm25":
            return self.embedding_engine.search_bm25(query, chunks, top_k)
        elif self.retrieval_mode == "hybrid":
            return self.embedding_engine.search_hybrid(
                query, chunks, top_k,
                vector_weight=self.settings.get("vector_weight", 0.7),
                bm25_weight=self.settings.get("bm25_weight", 0.3),
            )
        else:
            query_emb = self.embedding_engine.embed_text(query)
            return self.embedding_engine.search_similar(
                query_emb, chunks, top_k=top_k,
                threshold=self.settings.get("similarity_threshold", 0.3),
            )

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
        return "根据知识库检索到以下相关内容：\n\n%s\n\n（提示：未加载模型，仅展示检索结果。）" % context

    def generate_answer(self, query, context_chunks, history=None):
        if self.api_client:
            messages = self._build_prompt(query, context_chunks, history)
            try:
                return self.api_client.chat(
                    messages,
                    temperature=self.settings.get("temperature", 0.7),
                    max_tokens=self.settings.get("max_tokens", 1024),
                )
            except Exception as e:
                return "API调用失败: %s" % str(e)

        if not self.model:
            return self._get_no_model_msg(context_chunks)

        messages = self._build_prompt(query, context_chunks, history)
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.settings.get("max_tokens", 1024),
                temperature=self.settings.get("temperature", 0.7),
                top_p=0.9, do_sample=True, repetition_penalty=1.1,
            )
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response.strip()

    def generate_answer_stream(self, query, context_chunks, history=None):
        if self.api_client:
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
            return

        if not self.model:
            yield self._get_no_model_msg(context_chunks)
            return

        messages = self._build_prompt(query, context_chunks, history)
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = {
            **inputs,
            "max_new_tokens": self.settings.get("max_tokens", 1024),
            "temperature": self.settings.get("temperature", 0.7),
            "top_p": 0.9, "do_sample": True, "repetition_penalty": 1.1,
            "streamer": streamer,
        }
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        for text_chunk in streamer:
            yield text_chunk
        thread.join()

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
