"""
DuckDuckGo搜索引擎
使用ddgs库（duckduckgo-search的新版本）
"""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class DuckDuckGoSearchEngine:
    """DuckDuckGo搜索引擎"""
    
    def __init__(self, config: Dict):
        self.timeout = config.get('timeout', 15)
        self.max_retries = config.get('max_retries', 3)
        self._ddgs = None
    
    def _get_ddgs(self):
        """延迟导入ddgs"""
        if self._ddgs is None:
            try:
                from ddgs import DDGS
                self._ddgs = DDGS()
            except ImportError:
                logger.error("ddgs未安装，请运行: pip install ddgs")
                raise
        return self._ddgs
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """执行搜索"""
        try:
            ddgs = self._get_ddgs()
            
            # 使用text搜索 - 新版API使用query参数
            results = []
            search_results = ddgs.text(
                query=query,
                region='cn-zh',
                safesearch='moderate',
                max_results=max_results
            )
            
            # search_results是生成器，需要迭代
            for item in search_results:
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('href', ''),
                    'snippet': item.get('body', ''),
                    'source': 'duckduckgo'
                })
                
                if len(results) >= max_results:
                    break
            
            logger.info(f"DuckDuckGo搜索成功，返回 {len(results)} 条结果")
            return results
            
        except ImportError:
            logger.error("ddgs库未安装")
            return []
        except Exception as e:
            logger.error(f"DuckDuckGo搜索失败: {e}")
            return []