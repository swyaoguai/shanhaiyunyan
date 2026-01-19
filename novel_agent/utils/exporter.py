"""
小说导出模块
支持多种格式导出：TXT, Markdown, HTML, EPUB, PDF
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod
import zipfile
import uuid

logger = logging.getLogger(__name__)


@dataclass
class NovelMetadata:
    """小说元数据"""
    title: str
    author: str = "AI创作"
    description: str = ""
    genre: str = ""
    language: str = "zh-CN"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    word_count: int = 0
    chapter_count: int = 0
    cover_image: Optional[str] = None


@dataclass
class Chapter:
    """章节数据"""
    number: int
    title: str
    content: str
    word_count: int = 0
    
    def __post_init__(self):
        if self.word_count == 0:
            self.word_count = len(self.content)


@dataclass
class Novel:
    """小说数据"""
    metadata: NovelMetadata
    chapters: List[Chapter] = field(default_factory=list)
    
    @property
    def total_words(self) -> int:
        return sum(ch.word_count for ch in self.chapters)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Novel':
        """从字典创建"""
        metadata = NovelMetadata(
            title=data.get("title", "未命名"),
            author=data.get("author", "AI创作"),
            description=data.get("description", ""),
            genre=data.get("genre", data.get("novel_type", "")),
            word_count=data.get("word_count", 0),
            chapter_count=data.get("chapter_count", 0)
        )
        
        chapters = []
        for ch_data in data.get("chapters", []):
            chapters.append(Chapter(
                number=ch_data.get("number", len(chapters) + 1),
                title=ch_data.get("title", f"第{len(chapters)+1}章"),
                content=ch_data.get("content", ""),
                word_count=ch_data.get("word_count", 0)
            ))
        
        return cls(metadata=metadata, chapters=chapters)


class BaseExporter(ABC):
    """导出器基类"""
    
    def __init__(self, output_dir: Optional[Path] = None):
        from ..constants import PATH_DEFAULTS
        self.output_dir = output_dir or Path(PATH_DEFAULTS.EXPORTS_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    def export(self, novel: Novel, filename: Optional[str] = None) -> Path:
        """导出小说"""
        pass
    
    def _sanitize_filename(self, name: str) -> str:
        """清理文件名"""
        # 移除不安全字符
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        return name[:100]  # 限制长度


class TxtExporter(BaseExporter):
    """TXT格式导出器"""
    
    def export(self, novel: Novel, filename: Optional[str] = None) -> Path:
        """导出为TXT"""
        filename = filename or self._sanitize_filename(novel.metadata.title)
        output_path = self.output_dir / f"{filename}.txt"
        
        lines = []
        
        # 标题页
        lines.append(f"{'=' * 50}")
        lines.append(f"《{novel.metadata.title}》")
        lines.append(f"{'=' * 50}")
        lines.append(f"作者：{novel.metadata.author}")
        lines.append(f"类型：{novel.metadata.genre}")
        lines.append(f"字数：{novel.total_words:,}")
        lines.append(f"章节：{len(novel.chapters)}")
        lines.append(f"{'=' * 50}")
        lines.append("")
        
        # 简介
        if novel.metadata.description:
            lines.append("【简介】")
            lines.append(novel.metadata.description)
            lines.append("")
            lines.append(f"{'-' * 50}")
            lines.append("")
        
        # 目录
        lines.append("【目录】")
        for ch in novel.chapters:
            lines.append(f"  {ch.title}")
        lines.append("")
        lines.append(f"{'=' * 50}")
        lines.append("")
        
        # 正文
        for ch in novel.chapters:
            lines.append(f"\n{ch.title}\n")
            lines.append(ch.content)
            lines.append(f"\n{'-' * 30}\n")
        
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"TXT exported: {output_path}")
        
        return output_path


class MarkdownExporter(BaseExporter):
    """Markdown格式导出器"""
    
    def export(self, novel: Novel, filename: Optional[str] = None) -> Path:
        """导出为Markdown"""
        filename = filename or self._sanitize_filename(novel.metadata.title)
        output_path = self.output_dir / f"{filename}.md"
        
        lines = []
        
        # 标题
        lines.append(f"# {novel.metadata.title}")
        lines.append("")
        
        # 元数据
        lines.append("---")
        lines.append(f"author: {novel.metadata.author}")
        lines.append(f"genre: {novel.metadata.genre}")
        lines.append(f"words: {novel.total_words}")
        lines.append(f"chapters: {len(novel.chapters)}")
        lines.append(f"created: {novel.metadata.created_at}")
        lines.append("---")
        lines.append("")
        
        # 简介
        if novel.metadata.description:
            lines.append("## 简介")
            lines.append("")
            lines.append(novel.metadata.description)
            lines.append("")
        
        # 目录
        lines.append("## 目录")
        lines.append("")
        for ch in novel.chapters:
            lines.append(f"- [{ch.title}](#{ch.title.replace(' ', '-')})")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # 正文
        for ch in novel.chapters:
            lines.append(f"## {ch.title}")
            lines.append("")
            # 分段处理
            paragraphs = ch.content.split('\n')
            for para in paragraphs:
                if para.strip():
                    lines.append(para)
                    lines.append("")
            lines.append("")
        
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Markdown exported: {output_path}")
        
        return output_path


class HtmlExporter(BaseExporter):
    """HTML格式导出器"""
    
    def __init__(self, output_dir: Optional[Path] = None, include_style: bool = True):
        super().__init__(output_dir)
        self.include_style = include_style
    
    def _get_style(self) -> str:
        """获取CSS样式"""
        return """
        <style>
            body {
                font-family: 'Noto Serif SC', serif, 'Times New Roman';
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                line-height: 1.8;
                color: #333;
                background: #fafafa;
            }
            h1 { 
                text-align: center; 
                border-bottom: 2px solid #333;
                padding-bottom: 20px;
            }
            h2 { 
                border-left: 4px solid #333;
                padding-left: 10px;
                margin-top: 40px;
            }
            .metadata {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
            }
            .toc {
                background: #f0f0f0;
                padding: 20px;
                border-radius: 5px;
                margin: 20px 0;
            }
            .toc ul { list-style: none; padding-left: 0; }
            .toc li { padding: 5px 0; }
            .toc a { color: #333; text-decoration: none; }
            .toc a:hover { text-decoration: underline; }
            .chapter { margin-top: 50px; }
            .chapter-content { 
                text-indent: 2em;
                text-align: justify;
            }
            .chapter-content p { margin: 1em 0; }
            .divider { 
                text-align: center; 
                margin: 30px 0;
                color: #999;
            }
            .description {
                font-style: italic;
                background: #f9f9f9;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
            }
        </style>
        """
    
    def export(self, novel: Novel, filename: Optional[str] = None) -> Path:
        """导出为HTML"""
        filename = filename or self._sanitize_filename(novel.metadata.title)
        output_path = self.output_dir / f"{filename}.html"
        
        html = []
        html.append("<!DOCTYPE html>")
        html.append('<html lang="zh-CN">')
        html.append("<head>")
        html.append('<meta charset="UTF-8">')
        html.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        html.append(f"<title>{novel.metadata.title}</title>")
        
        if self.include_style:
            html.append(self._get_style())
        
        html.append("</head>")
        html.append("<body>")
        
        # 标题
        html.append(f"<h1>{novel.metadata.title}</h1>")
        
        # 元数据
        html.append('<div class="metadata">')
        html.append(f"<p>作者：{novel.metadata.author} | 类型：{novel.metadata.genre}</p>")
        html.append(f"<p>字数：{novel.total_words:,} | 章节：{len(novel.chapters)}</p>")
        html.append("</div>")
        
        # 简介
        if novel.metadata.description:
            html.append('<div class="description">')
            html.append(f"<p>{novel.metadata.description}</p>")
            html.append("</div>")
        
        # 目录
        html.append('<div class="toc">')
        html.append("<h3>目录</h3>")
        html.append("<ul>")
        for i, ch in enumerate(novel.chapters):
            html.append(f'<li><a href="#chapter-{i+1}">{ch.title}</a></li>')
        html.append("</ul>")
        html.append("</div>")
        
        # 正文
        for i, ch in enumerate(novel.chapters):
            html.append(f'<div class="chapter" id="chapter-{i+1}">')
            html.append(f"<h2>{ch.title}</h2>")
            html.append('<div class="chapter-content">')
            
            # 分段处理
            paragraphs = ch.content.split('\n')
            for para in paragraphs:
                if para.strip():
                    html.append(f"<p>{para}</p>")
            
            html.append("</div>")
            html.append('<div class="divider">◇ ◇ ◇</div>')
            html.append("</div>")
        
        html.append("</body>")
        html.append("</html>")
        
        output_path.write_text("\n".join(html), encoding="utf-8")
        logger.info(f"HTML exported: {output_path}")
        
        return output_path


class EpubExporter(BaseExporter):
    """EPUB格式导出器"""
    
    def export(self, novel: Novel, filename: Optional[str] = None) -> Path:
        """导出为EPUB"""
        filename = filename or self._sanitize_filename(novel.metadata.title)
        output_path = self.output_dir / f"{filename}.epub"
        
        # EPUB是一个ZIP文件
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as epub:
            # mimetype (必须是第一个文件，不压缩)
            epub.writestr('mimetype', 'application/epub+zip', 
                         compress_type=zipfile.ZIP_STORED)
            
            # container.xml
            container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
            epub.writestr('META-INF/container.xml', container)
            
            # content.opf
            book_id = str(uuid.uuid4())
            manifest_items = []
            spine_items = []
            
            # 添加章节
            for i, ch in enumerate(novel.chapters):
                item_id = f"chapter{i+1}"
                manifest_items.append(
                    f'    <item id="{item_id}" href="{item_id}.xhtml" '
                    f'media-type="application/xhtml+xml"/>'
                )
                spine_items.append(f'    <itemref idref="{item_id}"/>')
            
            content_opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{novel.metadata.title}</dc:title>
    <dc:creator>{novel.metadata.author}</dc:creator>
    <dc:language>{novel.metadata.language}</dc:language>
    <dc:subject>{novel.metadata.genre}</dc:subject>
    <meta property="dcterms:modified">{datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="style.css" media-type="text/css"/>
{chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    <itemref idref="nav"/>
{chr(10).join(spine_items)}
  </spine>
</package>'''
            epub.writestr('OEBPS/content.opf', content_opf)
            
            # toc.ncx
            nav_points = []
            for i, ch in enumerate(novel.chapters):
                nav_points.append(f'''    <navPoint id="navpoint{i+1}" playOrder="{i+1}">
      <navLabel><text>{ch.title}</text></navLabel>
      <content src="chapter{i+1}.xhtml"/>
    </navPoint>''')
            
            toc_ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
  </head>
  <docTitle><text>{novel.metadata.title}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>'''
            epub.writestr('OEBPS/toc.ncx', toc_ncx)
            
            # nav.xhtml
            nav_items = [
                f'      <li><a href="chapter{i+1}.xhtml">{ch.title}</a></li>'
                for i, ch in enumerate(novel.chapters)
            ]
            nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>目录</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <nav epub:type="toc">
    <h1>目录</h1>
    <ol>
{chr(10).join(nav_items)}
    </ol>
  </nav>
</body>
</html>'''
            epub.writestr('OEBPS/nav.xhtml', nav_xhtml)
            
            # style.css
            style_css = '''body {
    font-family: serif;
    line-height: 1.6;
    margin: 1em;
}
h1, h2 { text-align: center; }
p { text-indent: 2em; margin: 0.5em 0; }
'''
            epub.writestr('OEBPS/style.css', style_css)
            
            # 章节文件
            for i, ch in enumerate(novel.chapters):
                paragraphs = [
                    f"<p>{p}</p>" for p in ch.content.split('\n') if p.strip()
                ]
                chapter_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{ch.title}</title>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <h2>{ch.title}</h2>
  {chr(10).join(paragraphs)}
</body>
</html>'''
                epub.writestr(f'OEBPS/chapter{i+1}.xhtml', chapter_xhtml)
        
        logger.info(f"EPUB exported: {output_path}")
        return output_path


class NovelExporter:
    """
    统一导出器
    
    支持格式：txt, md, html, epub
    """
    
    EXPORTERS = {
        "txt": TxtExporter,
        "md": MarkdownExporter,
        "markdown": MarkdownExporter,
        "html": HtmlExporter,
        "epub": EpubExporter
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        from ..constants import PATH_DEFAULTS
        self.output_dir = output_dir or Path(PATH_DEFAULTS.EXPORTS_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export(
        self, 
        novel: Novel, 
        format: str = "txt",
        filename: Optional[str] = None
    ) -> Path:
        """
        导出小说
        
        Args:
            novel: 小说数据
            format: 导出格式 (txt, md, html, epub)
            filename: 文件名（不含扩展名）
            
        Returns:
            导出文件路径
        """
        format = format.lower()
        
        if format not in self.EXPORTERS:
            raise ValueError(f"Unsupported format: {format}. "
                           f"Supported: {list(self.EXPORTERS.keys())}")
        
        exporter = self.EXPORTERS[format](self.output_dir)
        return exporter.export(novel, filename)
    
    def export_all(
        self, 
        novel: Novel, 
        formats: Optional[List[str]] = None,
        filename: Optional[str] = None
    ) -> Dict[str, Path]:
        """
        导出为多种格式
        
        Args:
            novel: 小说数据
            formats: 格式列表，默认全部
            filename: 文件名
            
        Returns:
            格式到文件路径的映射
        """
        formats = formats or ["txt", "md", "html", "epub"]
        results = {}
        
        for fmt in formats:
            try:
                path = self.export(novel, fmt, filename)
                results[fmt] = path
            except Exception as e:
                logger.error(f"Failed to export {fmt}: {e}")
                results[fmt] = None
        
        return results
    
    @staticmethod
    def get_supported_formats() -> List[str]:
        """获取支持的格式列表"""
        return list(NovelExporter.EXPORTERS.keys())


# 模块职责说明：提供多格式小说导出功能，支持TXT、Markdown、HTML和EPUB格式。