"""
文本分块模块

将长文本按照配置策略切分成知识片段。
支持：
- 多种分割策略
- 块重叠
- 保持语义完整性
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass

from ..config import ChunkingConfig

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """文本块"""
    text: str
    index: int
    start_pos: int
    end_pos: int
    word_count: int
    
    def __len__(self) -> int:
        return len(self.text)


class TextChunker:
    """
    文本分块器
    
    将长文本切分成适合向量检索的片段。
    """
    
    def __init__(self, config: Optional[ChunkingConfig] = None):
        """
        初始化分块器
        
        Args:
            config: 分块配置
        """
        self.config = config or ChunkingConfig()
    
    def chunk(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None
    ) -> list[TextChunk]:
        """
        将文本切分成块
        
        Args:
            text: 待切分的文本
            chunk_size: 每块大小（字符数），默认使用配置
            chunk_overlap: 块重叠大小，默认使用配置
        
        Returns:
            文本块列表
        """
        if not text or not text.strip():
            return []
        
        chunk_size = chunk_size or self.config.chunk_size
        chunk_overlap = chunk_overlap or self.config.chunk_overlap
        
        # 首先按分隔符切分
        segments = self._split_by_separators(text)
        
        # 合并小段落，切分大段落
        chunks = self._merge_and_split(segments, chunk_size, chunk_overlap)
        
        # 构建结果
        results = []
        current_pos = 0
        
        for i, chunk_text in enumerate(chunks):
            # 查找在原文中的位置
            start_pos = text.find(chunk_text[:50], current_pos)  # 用前50字符定位
            if start_pos == -1:
                start_pos = current_pos
            end_pos = start_pos + len(chunk_text)
            current_pos = end_pos - chunk_overlap  # 考虑重叠
            
            chunk = TextChunk(
                text=chunk_text,
                index=i,
                start_pos=start_pos,
                end_pos=end_pos,
                word_count=self._count_words(chunk_text)
            )
            results.append(chunk)
        
        logger.debug(f"文本分块完成: 原文{len(text)}字符 -> {len(results)}个块")
        return results
    
    def _split_by_separators(self, text: str) -> list[str]:
        """
        按分隔符切分文本
        
        优先按段落分割，保持语义完整性
        """
        segments = []
        current_text = text
        
        # 按分隔符优先级尝试切分，使用第一个有效的分隔符
        for separator in self.config.separators:
            if separator in current_text:
                # 使用当前分隔符切分
                parts = current_text.split(separator)
                for part in parts:
                    part = part.strip()
                    if part:
                        segments.append(part)
                break
        
        # 如果没有找到任何分隔符，按句子切分
        if not segments:
            # 尝试按句子切分
            sentence_pattern = r'([。！？.!?]+)'
            parts = re.split(sentence_pattern, text)
            
            i = 0
            while i < len(parts):
                sentence = parts[i].strip()
                # 如果下一个是标点符号，合并
                if i + 1 < len(parts) and re.match(r'^[。！？.!?]+$', parts[i + 1]):
                    sentence += parts[i + 1]
                    i += 2
                else:
                    i += 1
                if sentence:
                    segments.append(sentence)
        
        # 如果仍然没有分段，返回整个文本
        if not segments:
            stripped = text.strip()
            if stripped:
                segments.append(stripped)
        
        return segments
    
    def _merge_and_split(
        self,
        segments: list[str],
        chunk_size: int,
        chunk_overlap: int
    ) -> list[str]:
        """
        合并小段落，切分大段落
        
        确保每个块的大小在合理范围内
        """
        if not segments:
            return []
        
        chunks = []
        current_chunk = ""
        
        for segment in segments:
            # 如果当前段落本身就超过chunk_size，需要进一步切分
            if len(segment) > chunk_size:
                # 先保存当前累积的块
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # 切分大段落
                sub_chunks = self._split_large_segment(segment, chunk_size, chunk_overlap)
                chunks.extend(sub_chunks)
                continue
            
            # 尝试合并到当前块
            if not current_chunk:
                current_chunk = segment
            elif len(current_chunk) + len(segment) + 1 <= chunk_size:
                current_chunk = current_chunk + "\n" + segment
            else:
                # 当前块已满，保存并开始新块
                chunks.append(current_chunk)
                # 保留重叠部分
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    overlap_text = current_chunk[-chunk_overlap:]
                    current_chunk = overlap_text + "\n" + segment
                else:
                    current_chunk = segment
        
        # 保存最后一个块
        if current_chunk:
            chunks.append(current_chunk)
        
        # 如果只有一个块，直接返回
        if len(chunks) <= 1:
            return chunks
        
        # 过滤太小的块，但确保至少保留足够数量的块
        min_size = self.config.min_chunk_size
        filtered_chunks = [c for c in chunks if len(c) >= min_size]
        
        # 如果过滤后块太少，尝试合并小块到相邻块
        if len(filtered_chunks) < 2 and len(chunks) > 1:
            # 直接返回原始块，不做过滤
            return chunks
        
        return filtered_chunks if filtered_chunks else chunks
    
    def _split_large_segment(
        self,
        text: str,
        chunk_size: int,
        chunk_overlap: int
    ) -> list[str]:
        """
        切分大段落
        
        尝试在句子边界处切分，保持语义完整
        """
        chunks = []
        
        # 先按句子切分
        sentences = self._split_sentences(text)
        
        current_chunk = ""
        for sentence in sentences:
            if len(sentence) > chunk_size:
                # 句子本身就太长，强制按字符切分
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                for i in range(0, len(sentence), chunk_size - chunk_overlap):
                    sub_chunk = sentence[i:i + chunk_size]
                    if sub_chunk:
                        chunks.append(sub_chunk)
                continue
            
            if not current_chunk:
                current_chunk = sentence
            elif len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk = current_chunk + sentence
            else:
                chunks.append(current_chunk)
                # 重叠处理
                if chunk_overlap > 0:
                    overlap_start = max(0, len(current_chunk) - chunk_overlap)
                    current_chunk = current_chunk[overlap_start:] + sentence
                else:
                    current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_sentences(self, text: str) -> list[str]:
        """
        按句子切分文本
        
        支持中英文标点
        """
        # 使用正则表达式匹配句子结束符
        pattern = r'([。！？.!?]+)'
        parts = re.split(pattern, text)
        
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            sentence = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
            sentence = sentence.strip()
            if sentence:
                sentences.append(sentence)
        
        # 处理最后一个不以标点结尾的部分
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1].strip())
        
        return sentences
    
    def _count_words(self, text: str) -> int:
        """
        统计字数
        
        中文按字符计数，英文按单词计数
        """
        # 移除空白字符
        text = re.sub(r'\s+', '', text)
        
        # 计算中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        
        # 计算英文单词（简单估算：非中文字符数 / 5）
        non_chinese = len(text) - chinese_chars
        english_words = non_chinese // 5 if non_chinese > 0 else 0
        
        return chinese_chars + english_words
    
    def estimate_chunks(self, text: str) -> int:
        """
        估算文本会产生多少个块
        
        Args:
            text: 文本内容
        
        Returns:
            预计的块数量
        """
        if not text:
            return 0
        
        text_len = len(text)
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        
        if text_len <= chunk_size:
            return 1
        
        # 考虑重叠的估算
        effective_chunk_size = chunk_size - overlap
        return max(1, (text_len - overlap) // effective_chunk_size + 1)