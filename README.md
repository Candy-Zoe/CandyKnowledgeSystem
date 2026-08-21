# CandyKnowledgeSystem

一个本地桌面端知识库工具，核心目标是：用项目内的解析代码读取各种文件内容，导入 SQLite 知识库，再通过关键词快速定位原文。

## 当前核心功能

1. **自研文档解析工具集**
   - 统一入口：`core/parser_toolkit.py`
   - 解析调度：`core/document_parser.py`
   - 格式解析器：`core/parsers/`
   - 支持 PDF、DOCX/DOC、TXT/Markdown、XLSX/XLS、PPTX/PPT、EPUB、RTF、OpenDocument、MHTML、CSV/TSV、JSON/XML/YAML/TOML、代码文件、字幕、ZIP、图片 OCR、音视频元数据等。
   - DOCX、XLSX、PPTX、EPUB、RTF、OpenDocument、MHTML 等优先使用项目内代码解析。PDF 已调整为纯 Python 解析优先，第三方库只作为兼容回退。
   - 容器类文档会扫描内嵌图片、音频、视频资源，并把资源清单写入索引文本。

2. **SQLite 知识库**
   - 上传文件后自动解析、分块、写入 `data/knowledge.db`。
   - 支持一次选择多个文件批量导入。
   - 支持多个知识库分类管理。
   - 文档记录、分块内容、全文检索索引都保存在 SQLite。

3. **关键词检索与原文预览**
   - 在“内容检索”页输入一个或多个关键词。
   - 可选择“全部关键词”或“任一关键词”。
   - 搜索结果按文件和片段列出。
   - 双击结果或点击“查看原文”，可以查看命中片段及前后上下文。

## 启动

```bash
pip install -r requirements.txt
python CandyTool.py
```

## 项目结构

```text
CandyTool.py                 桌面应用入口
config.py                    本地配置
core/
  parser_toolkit.py          解析工具统一入口
  document_parser.py         文件类型调度与嵌入资源扫描
  parsers/                   各格式解析器集合
  database.py                SQLite 知识库与检索
  text_processor.py          文本分块
gui/
  main_window.py             主窗口
  pages/
    upload_page.py           导入文件生成知识库
    search_page.py           关键词检索与原文预览
    documents_page.py        文档管理
    knowledge_bases_page.py  知识库管理
  workers/                   后台导入/编辑任务
data/
  knowledge.db               SQLite 数据库
```
