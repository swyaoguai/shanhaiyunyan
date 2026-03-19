"""
Bing搜索API集成
"""

import requests
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class BingSearchEngine:
    """Bing搜索引擎"""
    
    def __init__(self, config: Dict):
        self.api_key = config.get('api_key')
        self.timeout = config.get('timeout', 10)
        self.base_url = "https://api.bing.microsoft.com/v7.0/search"
        self.market = config.get('market', 'zh-CN')
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """执行Bing搜索"""
        try:
            headers = {
                'Ocp-Apim-Subscription-Key': self.api_key
            }
            
            params = {
                'q': query,
                'count': min(max_results, 50),
                'mkt': self.market,
                'responseFilter': 'Webpages'
            }
            
            response = requests.get(
                self.base_url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            web_pages = data.get('webPages', {}).get('value', [])
            
            for item in web_pages[:max_results]:
                results.append({
                    'title': item.get('name', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('snippet', ''),
                    'source': 'bing'
                })
            
            logger.info(f"Bing搜索成功，返回 {len(results)} 条结果")
            return results
            
        except Exception as e:
            logger.error(f"Bing搜索失败: {e}")
            return []