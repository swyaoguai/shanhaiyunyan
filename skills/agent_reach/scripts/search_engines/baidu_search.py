"""
百度搜索API集成
"""

import requests
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class BaiduSearchEngine:
    """百度搜索引擎"""
    
    def __init__(self, config: Dict):
        self.api_key = config.get('api_key')
        self.secret_key = config.get('secret_key')
        self.timeout = config.get('timeout', 10)
        self.base_url = "https://aip.baidubce.com/rest/2.0/search/v1/web"
        self.access_token = None
    
    def _get_access_token(self) -> str:
        """获取访问令牌"""
        if self.access_token:
            return self.access_token
        
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }
        
        try:
            response = requests.post(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            self.access_token = result.get('access_token')
            return self.access_token
        except Exception as e:
            logger.error(f"获取百度访问令牌失败: {e}")
            raise
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """执行百度搜索"""
        try:
            access_token = self._get_access_token()
            
            params = {
                "access_token": access_token,
                "query": query,
                "pn": 0,
                "rn": min(max_results, 50)
            }
            
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('error_code'):
                logger.error(f"百度搜索API错误: {data.get('error_msg')}")
                return []
            
            results = []
            for item in data.get('results', [])[:max_results]:
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('abstract', ''),
                    'source': 'baidu'
                })
            
            logger.info(f"百度搜索成功，返回 {len(results)} 条结果")
            return results
            
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return []