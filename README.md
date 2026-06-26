# CandyKnowledgeSystem

基于Python的知识库系统，支持PDF/Word/TXT文件导入，通过RAG检索增强和模型微调实现智能问答。

## 功能特性

- **文档导入**: 支持PDF、Word(.docx)、TXT格式，单个或批量上传
- **自动处理**: 文档解析、分词、向量嵌入自动生成
- **智能问答**: 基于知识库的RAG检索增强问答
- **模型微调**: 使用QLoRA微调Qwen2-1.5B模型
- **数据管理**: 文档管理、训练数据管理、数据库导出/导入
- **Web界面**: Flask + Jinja2，浏览器访问

## 安装

```bash
pip install -r requirements.txt
```

## 启动

```bash
python run.py
```

访问 http://localhost:5000

## 使用流程

1. **上传文件**: 访问 /upload/ 上传PDF/Word/TXT文件
2. **管理文档**: 访问 /documents/ 查看文档处理状态
3. **智能问答**: 访问 /qa/ 基于知识库提问
4. **模型微调**: 访问 /finetune/ 管理训练数据并启动微调

## 批量导入

```bash
python scripts/batch_import.py /path/to/folder
```

## 数据库导出/导入

```bash
# 导出
python scripts/export_db.py

# 导入
python scripts/import_db.py knowledge_base_export.json
```

## 项目结构

```
├── config.py              # 全局配置
├── run.py                 # 启动入口
├── core/                  # 核心业务逻辑
│   ├── database.py        # SQLite数据库管理
│   ├── document_parser.py # 文档解析(PDF/DOCX/TXT)
│   ├── text_processor.py  # 文本分块与分词
│   ├── embedding_engine.py # 向量嵌入与搜索
│   ├── rag_engine.py      # RAG检索增强引擎
│   └── finetune_engine.py # 模型微调引擎
├── web/                   # Web界面
│   ├── app.py             # Flask应用工厂
│   ├── routes/            # 路由蓝图
│   ├── templates/         # Jinja2模板
│   └── static/            # 静态资源
├── scripts/               # 工具脚本
└── data/                  # 运行时数据(自动创建)
```

## 技术栈

- Python 3.10+
- Flask (Web框架)
- SQLite (数据库)
- sentence-transformers (嵌入模型: bge-small-zh-v1.5)
- transformers + peft (微调: Qwen2-1.5B + QLoRA)
- PyMuPDF / python-docx / chardet (文档解析)
