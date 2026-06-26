# CandyKnowledgeSystem 实现计划

## 概述

基于Python搭建知识库系统，支持PDF/Word/TXT文件导入，通过微调本地大模型+RAG实现问答。SQLite存储，Flask Web界面。

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Web框架 | Flask | 轻量，Jinja2模板 |
| 数据库 | SQLite + WAL | 零配置，文件可分享 |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 | 中英文，512维，~100MB |
| 基础LLM | Qwen2-1.5B | 中英文，QLoRA可跑在8GB显存 |
| 微调方式 | QLoRA (4-bit) | 消费级GPU可用 |
| 分块 | 512 tokens, 64 overlap | 平衡上下文与内存 |
| 向量搜索 | numpy余弦相似度 | <100K chunks约10ms |

## 项目结构

```
CandyKnowledgeSystem/
├── config.py                  # 全局配置
├── run.py                     # 启动入口
├── requirements.txt
├── .gitignore
├── core/                      # 核心业务逻辑
│   ├── __init__.py
│   ├── database.py            # SQLite CRUD
│   ├── document_parser.py     # PDF/DOCX/TXT解析
│   ├── text_processor.py      # 分块+分词
│   ├── embedding_engine.py    # 向量生成+搜索
│   ├── rag_engine.py          # RAG检索+生成
│   └── finetune_engine.py     # 微调流水线
├── web/                       # Web界面
│   ├── __init__.py
│   ├── app.py                 # Flask工厂
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── upload.py          # 文件上传
│   │   ├── documents.py       # 文档管理
│   │   ├── qa.py              # 问答
│   │   └── finetune.py        # 微调管理
│   ├── templates/             # Jinja2模板
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── upload.html
│   │   ├── documents.html
│   │   ├── qa.html
│   │   └── finetune.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── data/                      # 运行时数据(gitignore)
│   ├── uploads/
│   ├── models/
│   └── knowledge.db
├── scripts/
│   ├── export_db.py
│   ├── import_db.py
│   └── batch_import.py
└── tests/
```

## 数据库Schema

```sql
-- 文档表
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    total_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 文本分块表
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- 训练数据对表
CREATE TABLE training_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source_chunk_ids TEXT,
    document_id INTEGER,
    is_generated INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

-- 微调任务表
CREATE TABLE finetune_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    base_model TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    training_samples INTEGER,
    epochs INTEGER,
    lora_rank INTEGER,
    output_path TEXT,
    metrics TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 核心流程

### 文档处理流程
1. 上传文件 → 保存到 data/uploads/
2. 解析文档(PyMuPDF/python-docx/chardet) → 提取纯文本
3. 文本分块(tiktoken, 512 tokens/chunk, 64 overlap)
4. 生成嵌入向量(bge-small-zh-v1.5) → 存入chunks表
5. 自动生成训练数据对(模板式QA)

### RAG问答流程
1. 用户提问 → 嵌入查询向量
2. 余弦相似度搜索 → 返回top-5相关chunks
3. 组装上下文 → ChatML格式prompt
4. 微调模型(或基础模型)生成回答
5. 返回答案+来源引用

### 微调流程
1. 从training_pairs表加载训练数据
2. 格式化为ChatML模板 → HuggingFace Dataset
3. 加载Qwen2-1.5B基础模型(4-bit量化)
4. 应用LoRA adapter (r=16, alpha=32)
5. SFTTrainer训练(3 epochs, batch=4, lr=2e-4)
6. 保存adapter到data/models/

## 实现顺序(分7个Phase)

### Phase 1: 基础设施
- config.py, requirements.txt, .gitignore
- core/database.py (完整CRUD)
- 数据库导出/导入功能

### Phase 2: 文档处理
- core/document_parser.py (PDF/DOCX/TXT)
- core/text_processor.py (分块+分词)
- core/embedding_engine.py (嵌入+搜索)

### Phase 3: Web上传与管理
- Flask app + base模板
- 上传页面(单文件+批量)
- 文档列表/删除页面
- 后台异步处理

### Phase 4: RAG问答
- core/rag_engine.py
- 问答聊天界面
- SSE流式输出

### Phase 5: 微调流水线
- core/finetune_engine.py
- 训练数据准备
- QLoRA训练循环
- 模型保存/加载

### Phase 6: 微调Web UI
- 微调仪表板
- 训练数据管理
- 任务触发+状态轮询

### Phase 7: 收尾优化
- 进度指示器
- 错误处理
- 批量导入脚本
- README文档

## 依赖库

```
flask==3.1.0
pymupdf==1.25.3
python-docx==1.1.2
chardet==5.2.0
tiktoken==0.9.0
sentence-transformers==4.1.0
numpy==2.2.6
torch>=2.0.0
transformers>=4.40.0
peft>=0.10.0
datasets>=2.0.0
trl>=0.8.0
accelerate>=0.30.0
bitsandbytes>=0.43.0
tqdm>=4.60.0
python-dotenv>=1.0.0
```

## 验证方案

1. 启动应用: `python run.py`
2. 上传测试文件(PDF/DOCX/TXT) → 检查数据库记录
3. 问答测试: 输入问题 → 验证检索结果和回答质量
4. 微调测试: 生成训练数据 → 启动微调 → 加载微调模型问答
5. 导出/导入测试: 导出SQLite → 在另一环境导入验证

## 关键文件(实现时需修改/创建)

- `config.py` - 全局配置
- `core/database.py` - 数据库管理
- `core/document_parser.py` - 文档解析
- `core/text_processor.py` - 文本处理
- `core/embedding_engine.py` - 嵌入引擎
- `core/rag_engine.py` - RAG引擎
- `core/finetune_engine.py` - 微调引擎
- `web/app.py` - Flask应用
- `web/routes/*.py` - 路由
- `web/templates/*.html` - 模板
- `run.py` - 启动入口
