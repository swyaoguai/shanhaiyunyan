"""
章节标记模块

自动识别和管理章节结构。
支持：
- 章节自动识别
- 章节元数据提取
- 章节导航
"""

import re
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ChapterMark:
    """章节标记"""
    chapter_id: str
    title: str
    chapter_number: Optional[int]
    start_pos: int
    end_pos: int
    content: str
    word_count: int


class ChapterMarker:
    """
    章节标记器
    
    自动识别文本中的章节结构。
    """
    
    # 常见的章节标题模式
    CHAPTER_PATTERNS = [
        # 中文模式
        r'^第[一二三四五六七八九十百千万\d]+章[\s\.:：]*(.*?)$',
        r'^第[一二三四五六七八九十百千万\d]+回[\s\.:：]*(.*?)$',
        r'^第[一二三四五六七八九十百千万\d]+节[\s\.:：]*(.*?)$',
        r'^第[一二三四五六七八九十百千万\d]+卷[\s\.:：]*(.*?)$',
        r'^[一二三四五六七八九十百千万]+[\s、\.:：]+(.*?)$',
        # 英文模式
        r'^Chapter\s+(\d+)[\s\.:：]*(.*?)$',
        r'^CHAPTER\s+(\d+)[\s\.:：]*(.*?)$',
        # 数字模式
        r'^(\d+)[\s\.\):：]+(.*?)$',
    ]
    
    # 中文数字映射
    CHINESE_NUMBERS = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '百': 100, '千': 1000, '万': 10000
    }
    
    def __init__(self, custom_patterns: Optional[list[str]] = None):
        """
        初始化章节标记器
        
        Args:
            custom_patterns: 自定义章节标题正则模式
        """
        self.patterns = custom_patterns or self.CHAPTER_PATTERNS
        self._compiled_patterns = [
            re.compile(p, re.MULTILINE | re.IGNORECASE)
            for p in self.patterns
        ]
    
    def detect_chapters(self, text: str) -> list[ChapterMark]:
        """
        检测文本中的章节
        
        Args:
            text: 待检测的文本
        
        Returns:
            章节标记列表
        """
        if not text:
            return []
        
        # 将文本按行分割，逐行检测章节标题
        lines = text.split('\n')
        chapter_positions = []
        current_pos = 0
        
        for line_idx, line in enumerate(lines):
            stripped_line = line.strip()
            if not stripped_line:
                current_pos += len(line) + 1  # +1 for newline
                continue
            
            # 检查这行是否匹配任何章节模式
            matched_pattern = None
            for pattern in self._compiled_patterns:
                match = pattern.match(stripped_line)
                if match:
                    matched_pattern = pattern
                    break
            
            if matched_pattern and self._is_plausible_chapter_title(stripped_line):
                # 提取章节号和标题
                chapter_number, title = self._parse_chapter_title(stripped_line)
                
                # 计算行在原文中的位置
                line_start = current_pos
                line_end = current_pos + len(line)
                
                chapter_positions.append({
                    'start': line_start,
                    'title_end': line_end,
                    'title': title if title else stripped_line,
                    'chapter_number': chapter_number,
                    'raw_title': stripped_line
                })
            
            current_pos += len(line) + 1  # +1 for newline
        
        # 去除太近的重复章节
        chapter_positions = self._deduplicate_chapters(chapter_positions)
        
        # 构建章节标记
        chapters = []
        for i, pos in enumerate(chapter_positions):
            # 确定章节内容范围：从标题结束到下一章节开始（或文档结束）
            content_start = pos['title_end']
            if i + 1 < len(chapter_positions):
                content_end = chapter_positions[i + 1]['start']
            else:
                content_end = len(text)
            
            content = text[content_start:content_end].strip()
            
            chapter = ChapterMark(
                chapter_id=f"chapter_{i + 1}",
                title=pos['title'] if pos['title'] else pos['raw_title'],
                chapter_number=pos['chapter_number'] if pos['chapter_number'] else (i + 1),
                start_pos=pos['start'],
                end_pos=content_end,
                content=content,
                word_count=self._count_words(content)
            )
            chapters.append(chapter)
        
        logger.info(f"检测到 {len(chapters)} 个章节")
        return chapters
    
    def _parse_chapter_title(self, title_line: str) -> Tuple[Optional[int], Optional[str]]:
        """
        解析章节标题，提取章节号和标题
        
        Args:
            title_line: 章节标题行
        
        Returns:
            (章节号, 标题)
        """
        # 尝试匹配各种模式
        
        # 模式1: 第X章 标题
        match = re.match(r'^第([一二三四五六七八九十百千万\d]+)[章回节卷][\s\.:：]*(.*?)$', title_line)
        if match:
            num_str = match.group(1)
            title = match.group(2).strip()
            chapter_number = self._parse_chinese_number(num_str)
            return chapter_number, title if title else None
        
        # 模式2: Chapter X: Title
        match = re.match(r'^Chapter\s+(\d+)[\s\.:：]*(.*?)$', title_line, re.IGNORECASE)
        if match:
            chapter_number = int(match.group(1))
            title = match.group(2).strip()
            return chapter_number, title if title else None
        
        # 模式3: 纯数字开头
        match = re.match(r'^(\d+)[\s\.\):：]+(.*?)$', title_line)
        if match:
            chapter_number = int(match.group(1))
            title = match.group(2).strip()
            return chapter_number, title if title else None
        
        return None, title_line
    
    def _parse_chinese_number(self, num_str: str) -> int:
        """
        解析中文数字
        
        Args:
            num_str: 中文数字字符串
        
        Returns:
            对应的阿拉伯数字
        """
        # 如果是纯数字，直接返回
        if num_str.isdigit():
            return int(num_str)
        
        # 解析中文数字
        result = 0
        temp = 0
        
        for char in num_str:
            if char in self.CHINESE_NUMBERS:
                val = self.CHINESE_NUMBERS[char]
                if val >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * val
                    temp = 0
                else:
                    temp = val
            elif char.isdigit():
                temp = temp * 10 + int(char)
        
        result += temp
        return result if result > 0 else 1
    
    def _deduplicate_chapters(self, positions: list[dict]) -> list[dict]:
        """
        去除重复的章节标记
        
        只去除在同一行或非常接近的重复章节，保留所有明确的章节标题
        """
        if not positions:
            return []
        
        result = [positions[0]]
        min_distance = 5  # 最小章节间隔（字符数），只去除真正重复的
        
        # 用于检测明确章节格式的模式
        chapter_pattern = r'第[一二三四五六七八九十百千万\d]+[章回节卷]'
        
        for pos in positions[1:]:
            last = result[-1]
            distance = pos['start'] - last['title_end']
            
            # 检查两个是否都是明确的章节格式
            is_pos_chapter = bool(re.search(chapter_pattern, pos['raw_title']))
            is_last_chapter = bool(re.search(chapter_pattern, last['raw_title']))
            
            if is_pos_chapter and is_last_chapter:
                # 两个都是明确的章节格式，都保留
                result.append(pos)
            elif distance < min_distance:
                # 非常近（可能是同一行），选择更像章节标题的
                if self._is_better_chapter_title(pos['raw_title'], last['raw_title']):
                    result[-1] = pos
            else:
                result.append(pos)
        
        return result

    def _is_plausible_chapter_title(self, title_line: str) -> bool:
        """
        判断匹配到的行是否真像章节标题。

        一些正文行会以“第X章正文……”开头，旧正则会把它误判为标题，
        导致导入章节数量翻倍。
        """
        stripped = (title_line or "").strip()
        match = re.match(
            r'^第([一二三四五六七八九十百千万\d]+)([章回节卷])(?P<sep>[\s\.:：]*)(?P<title>.*?)$',
            stripped,
        )
        if not match:
            return True

        separator = match.group("sep") or ""
        title = (match.group("title") or "").strip()
        if not title:
            return True

        if not separator and title.startswith(("正文", "内容")):
            return False

        if len(title) > 40:
            return False

        if re.search(r"[，,。！？!?；;]", title) and len(title) > 8:
            return False

        return True
    
    def _is_better_chapter_title(self, title1: str, title2: str) -> bool:
        """判断title1是否比title2更像章节标题"""
        # 优先选择包含"第X章"格式的
        pattern = r'第[一二三四五六七八九十百千万\d]+[章回节卷]'
        
        has_pattern1 = bool(re.search(pattern, title1))
        has_pattern2 = bool(re.search(pattern, title2))
        
        if has_pattern1 and not has_pattern2:
            return True
        if has_pattern2 and not has_pattern1:
            return False
        
        # 其他情况，选择更短的（可能更像标题）
        return len(title1) < len(title2)
    
    def _count_words(self, text: str) -> int:
        """统计字数"""
        text = re.sub(r'\s+', '', text)
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        non_chinese = len(text) - chinese_chars
        english_words = non_chinese // 5 if non_chinese > 0 else 0
        return chinese_chars + english_words
    
    def create_chapter_id(
        self,
        chapter_number: int,
        prefix: str = "chapter"
    ) -> str:
        """
        创建章节ID
        
        Args:
            chapter_number: 章节序号
            prefix: ID前缀
        
        Returns:
            章节ID
        """
        return f"{prefix}_{chapter_number}"
    
    def parse_chapter_id(self, chapter_id: str) -> Optional[int]:
        """
        从章节ID解析章节序号
        
        Args:
            chapter_id: 章节ID
        
        Returns:
            章节序号，解析失败返回None
        """
        match = re.search(r'_(\d+)$', chapter_id)
        if match:
            return int(match.group(1))
        return None
    
    def validate_chapter_sequence(
        self,
        chapters: list[ChapterMark]
    ) -> list[str]:
        """
        验证章节序列的一致性
        
        Args:
            chapters: 章节列表
        
        Returns:
            问题列表
        """
        issues = []
        
        if not chapters:
            return issues
        
        # 检查章节号是否连续
        expected_number = 1
        for chapter in chapters:
            if chapter.chapter_number != expected_number:
                issues.append(
                    f"章节号不连续: 期望{expected_number}，实际{chapter.chapter_number}"
                )
            expected_number = chapter.chapter_number + 1
        
        # 检查是否有空章节
        for chapter in chapters:
            if not chapter.content or chapter.word_count < 10:
                issues.append(f"章节内容过短: {chapter.title} ({chapter.word_count}字)")
        
        return issues
