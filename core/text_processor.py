import re
import math
import tiktoken


class TextProcessor:
    CHUNK_STRATEGIES = {
        "fixed": "固定大小分块",
        "paragraph": "段落感知分块",
        "semantic": "语义边界分块",
        "recursive": "递归分块",
        "sentence": "句子级分块",
    }

    def __init__(self, chunk_size=512, chunk_overlap=64, strategy="semantic"):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def chunk_text(self, text: str) -> list:
        strategies = {
            "fixed": self._chunk_fixed,
            "paragraph": self._chunk_paragraph,
            "semantic": self._chunk_semantic,
            "recursive": self._chunk_recursive,
            "sentence": self._chunk_sentence,
        }
        func = strategies.get(self.strategy, self._chunk_semantic)
        return func(text)

    def _chunk_fixed(self, text: str) -> list:
        tokens = self.tokenizer.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append({
                "content": chunk_text,
                "token_count": len(chunk_tokens)
            })
            start = end - self.chunk_overlap
            if start >= len(tokens):
                break
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def _chunk_paragraph(self, text: str) -> list:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        chunks = []
        current_tokens = []
        current_count = 0

        for para in paragraphs:
            para_tokens = self.tokenizer.encode(para)
            para_count = len(para_tokens)

            if current_count + para_count > self.chunk_size and current_tokens:
                chunk_text = self.tokenizer.decode(current_tokens)
                chunks.append({
                    "content": chunk_text,
                    "token_count": current_count
                })
                overlap_start = max(0, len(current_tokens) - self.chunk_overlap)
                current_tokens = current_tokens[overlap_start:]
                current_count = len(current_tokens)

            current_tokens.extend(para_tokens)
            current_count += para_count

        if current_tokens:
            chunk_text = self.tokenizer.decode(current_tokens)
            chunks.append({
                "content": chunk_text,
                "token_count": current_count
            })

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def _chunk_semantic(self, text: str) -> list:
        sections = re.split(r'\n(?=#{1,6}\s|\[第?\d+页\]|\[表格\]|\[工作表)', text)
        sections = [s.strip() for s in sections if s.strip()]

        chunks = []
        current_section = ""
        current_count = 0

        for section in sections:
            section_tokens = self.tokenizer.encode(section)
            section_count = len(section_tokens)

            if current_count + section_count > self.chunk_size and current_section:
                chunks.append({
                    "content": current_section,
                    "token_count": current_count
                })
                current_section = ""
                current_count = 0

            if section_count > self.chunk_size:
                if current_section:
                    chunks.append({
                        "content": current_section,
                        "token_count": current_count
                    })
                    current_section = ""
                    current_count = 0
                sub_chunks = self._chunk_fixed(section)
                chunks.extend(sub_chunks)
            else:
                current_section = (current_section + "\n\n" + section).strip() if current_section else section
                current_count += section_count

        if current_section:
            chunks.append({
                "content": current_section,
                "token_count": current_count
            })

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def _chunk_recursive(self, text: str) -> list:
        separators = ["\n\n", "\n", "。", ".", "！", "!", "？", "?", "；", ";", " "]
        return self._recursive_split(text, separators)

    def _recursive_split(self, text: str, separators: list) -> list:
        if not separators:
            return self._chunk_fixed(text)

        sep = separators[0]
        remaining_seps = separators[1:]

        parts = text.split(sep)
        chunks = []
        current = ""
        current_count = 0

        for part in parts:
            part_text = part.strip()
            if not part_text:
                continue

            part_tokens = self.tokenizer.encode(part_text)
            part_count = len(part_tokens)

            if current_count + part_count > self.chunk_size and current:
                if current_count <= self.chunk_size:
                    chunks.append({
                        "content": current,
                        "token_count": current_count
                    })
                else:
                    sub_chunks = self._recursive_split(current, remaining_seps)
                    chunks.extend(sub_chunks)
                current = ""
                current_count = 0

            current = (current + sep + part_text).strip() if current else part_text
            current_count += part_count

        if current:
            if current_count <= self.chunk_size:
                chunks.append({
                    "content": current,
                    "token_count": current_count
                })
            else:
                sub_chunks = self._recursive_split(current, remaining_seps)
                chunks.extend(sub_chunks)

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def _chunk_sentence(self, text: str) -> list:
        sentence_endings = r'(?<=[。！？\.\!\?])\s*'
        sentences = re.split(sentence_endings, text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current_sentences = []
        current_count = 0

        for sent in sentences:
            sent_tokens = self.tokenizer.encode(sent)
            sent_count = len(sent_tokens)

            if current_count + sent_count > self.chunk_size and current_sentences:
                chunk_text = " ".join(current_sentences)
                chunks.append({
                    "content": chunk_text,
                    "token_count": current_count
                })
                overlap_sents = current_sentences[-max(1, len(current_sentences)//4):]
                current_sentences = overlap_sents
                current_count = sum(len(self.tokenizer.encode(s)) for s in current_sentences)

            current_sentences.append(sent)
            current_count += sent_count

        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append({
                "content": chunk_text,
                "token_count": current_count
            })

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
        return chunks

    def extract_keywords(self, text: str, top_n=10) -> list:
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text)
        freq = {}
        for w in words:
            if len(w) > 1:
                freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:top_n]]

    def generate_training_pairs(self, chunks: list, num_questions=3) -> list:
        pairs = []
        for chunk in chunks:
            content = chunk["content"]
            if len(content) < 50:
                continue

            sentences = [s.strip() for s in re.split(r'[。！？\n]', content) if len(s.strip()) > 10]

            if not sentences:
                continue

            summary_a = "。".join(sentences[:3]) + "。" if len(sentences) >= 3 else "。".join(sentences) + "。"
            pairs.append({
                "question": "请总结以下内容的要点：",
                "answer": summary_a,
                "source_chunk_ids": [chunk.get("id")]
            })

            if len(sentences) >= 2:
                pairs.append({
                    "question": "关于%s，主要讲了什么？" % sentences[0][:30],
                    "answer": "。".join(sentences[:2]) + "。",
                    "source_chunk_ids": [chunk.get("id")]
                })

            keywords = self.extract_keywords(content, top_n=5)
            if keywords:
                kw = "、".join(keywords[:3])
                pairs.append({
                    "question": "请解释%s的相关内容" % kw,
                    "answer": summary_a,
                    "source_chunk_ids": [chunk.get("id")]
                })

            if len(sentences) >= 4:
                pairs.append({
                    "question": "请详细说明%s的具体内容" % sentences[0][:20],
                    "answer": "。".join(sentences[:5]) + "。",
                    "source_chunk_ids": [chunk.get("id")]
                })

            if len(sentences) >= 3:
                pairs.append({
                    "question": "这段内容的核心观点是什么？",
                    "answer": "。".join(sentences[:2]) + "。",
                    "source_chunk_ids": [chunk.get("id")]
                })

        return pairs
