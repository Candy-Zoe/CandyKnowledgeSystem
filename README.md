# CandyKnowledgeSystem

基于Python的桌面端知识库系统，支持多种文档格式导入，通过RAG检索增强和外部API实现智能问答。

## 功能特性

- **文档导入**: 支持PDF、Word(.docx)、TXT、Markdown、HTML、CSV、Excel格式
- **自动处理**: 文档解析、语义分块、向量嵌入自动生成
- **知识库管理**: 多知识库分类管理
- **智能问答**: 基于知识库的RAG检索增强问答（支持通义千问/OpenAI/DeepSeek等API）
- **批量问答**: 一次性提交多个问题
- **对话历史**: 保存和查看历史对话

## 安装

```bash
pip install -r requirements.txt
```

## 启动

```bash
python CandyTool.py
```

## 使用流程

1. **上传文件**: 点击「上传文档」导入PDF/Word/TXT等文件
2. **管理文档**: 点击「文档管理」查看文档处理状态
3. **知识库管理**: 点击「知识库」创建和管理多个知识库
4. **智能问答**: 点击「智能问答」基于知识库提问（需先配置API密钥）
5. **对话历史**: 点击「对话历史」查看历史对话记录

## 配置API

在「智能问答」页面点击「设置API」，填入：
- **API提供商**: 通义千问 / OpenAI / DeepSeek
- **API密钥**: 你的API密钥
- **模型**: qwen-turbo / gpt-3.5-turbo / deepseek-chat 等

## 项目结构

```
├── CandyTool.py             # 桌面端启动文件
├── config.py              # 全局配置
├── requirements.txt       # Python依赖
├── core/                  # 核心业务逻辑
│   ├── database.py        # SQLite数据库管理
│   ├── document_parser.py # 文档解析(PDF/DOCX/TXT等)
│   ├── pdf_parser.py      # 专用PDF解析器
│   ├── text_processor.py  # 文本分块与分词
│   ├── embedding_engine.py # 向量嵌入与搜索
│   ├── rag_engine.py      # RAG检索增强引擎
│   └── api_client.py      # 外部API客户端
├── gui/                   # 桌面端界面
│   ├── main_window.py     # 主窗口
│   ├── styles.py          # 界面样式
│   ├── pages/             # 功能页面
│   ├── widgets/           # 自定义组件
│   └── workers/           # 后台工作线程
└── data/                  # 运行时数据(自动创建)
```

## 技术栈

- Python 3.10+
- PySide6 (桌面端GUI)
- SQLite (数据库)
- sentence-transformers (嵌入模型: bge-small-zh-v1.5)
- PyMuPDF / pdfplumber / python-docx / chardet (文档解析)
