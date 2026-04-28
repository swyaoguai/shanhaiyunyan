"""
热点搜索服务
基于 TrendRadar 项目实现多平台热点数据获取
"""
import logging
import requests
from typing import List, Dict, Any, Optional
import json
import re
import time
import random

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    BeautifulSoup = None

logger = logging.getLogger(__name__)


class TrendsSearchService:
    """热点搜索服务类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        self.timeout = 15
        self.max_retries = 2

    def _build_soup(self, html: str, platform_name: str):
        """按需构建 HTML 解析器，缺少依赖时返回明确错误。"""
        if BeautifulSoup is None:
            raise RuntimeError(
                f"{platform_name} 依赖 beautifulsoup4，当前环境未安装；"
                "JSON 平台（如 toutiao/douyin）仍可正常使用"
            )
        return BeautifulSoup(html, "html.parser")
    
    def _make_request(self, url: str, method: str = 'GET', headers: Optional[Dict] = None, **kwargs) -> Optional[requests.Response]:
        """统一的请求方法"""
        retry_count = 0
        last_error = None
        
        while retry_count <= self.max_retries:
            try:
                kwargs.setdefault('timeout', self.timeout)
                
                if headers:
                    request_headers = self.session.headers.copy()
                    request_headers.update(headers)
                    kwargs['headers'] = request_headers
                
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                
                # 确保正确的编码
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = 'utf-8'
                
                if not response.content:
                    logger.warning(f"空响应: {url}")
                    return None
                
                return response
                
            except requests.exceptions.HTTPError as e:
                last_error = e
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden: {url}, 尝试 {retry_count + 1}/{self.max_retries + 1}")
                    retry_count += 1
                    if retry_count <= self.max_retries:
                        time.sleep(random.uniform(1, 2))
                    continue
                else:
                    logger.error(f"HTTP错误 {url}: {e}")
                    return None
                    
            except requests.exceptions.Timeout:
                logger.error(f"请求超时 {url}")
                return None
                
            except Exception as e:
                logger.error(f"请求失败 {url}: {e}")
                return None
        
        logger.error(f"请求失败 {url}: {last_error}")
        return None
    
    def _safe_json_parse(self, response: requests.Response, url: str) -> Optional[Dict]:
        """安全解析JSON"""
        try:
            # 尝试使用response.json()，它会自动处理编码
            return response.json()
        except json.JSONDecodeError as e:
            # 如果失败，尝试手动解码
            try:
                text = response.content.decode('utf-8')
                return json.loads(text)
            except Exception as e2:
                logger.error(f"JSON解析失败 {url}: {e}")
                logger.error(f"Content-Type: {response.headers.get('Content-Type')}")
                logger.error(f"Encoding: {response.encoding}")
                logger.error(f"响应长度: {len(response.content)} bytes")
                # 尝试显示前200字节的十六进制
                logger.error(f"前50字节(hex): {response.content[:50].hex()}")
                return None
    
    def get_weibo_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取微博热搜"""
        try:
            url = "https://weibo.com/ajax/side/hotSearch"
            headers = {'Referer': 'https://weibo.com/', 'X-Requested-With': 'XMLHttpRequest'}
            response = self._make_request(url, headers=headers)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            data = self._safe_json_parse(response, url)
            if not data:
                return {"success": False, "error": "JSON解析失败"}
            
            hot_list = data.get('data', {}).get('realtime', [])
            results = []
            for idx, item in enumerate(hot_list[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get('word', ''),
                    "hot": item.get('num', 0),
                    "url": f"https://s.weibo.com/weibo?q=%23{item.get('word', '')}%23"
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取微博热搜失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_zhihu_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取知乎热榜"""
        try:
            url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
            params = {"limit": limit}
            headers = {'Referer': 'https://www.zhihu.com/', 'X-Requested-With': 'XMLHttpRequest'}
            response = self._make_request(url, params=params, headers=headers)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            data = self._safe_json_parse(response, url)
            if not data:
                return {"success": False, "error": "JSON解析失败"}
            
            hot_list = data.get('data', [])
            results = []
            for idx, item in enumerate(hot_list[:limit], 1):
                target = item.get('target', {})
                results.append({
                    "rank": idx,
                    "title": target.get('title', ''),
                    "hot": item.get('detail_text', ''),
                    "url": target.get('url', '')
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取知乎热榜失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_baidu_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取百度热搜"""
        try:
            url = "https://top.baidu.com/board?tab=realtime"
            response = self._make_request(url)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            soup = self._build_soup(response.text, "百度热搜")
            items = soup.select('.category-wrap_iQLoo .c-single-text-ellipsis')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title = item.get_text(strip=True)
                parent = item.find_parent('a')
                url_link = parent.get('href', '') if parent else ''
                results.append({"rank": idx, "title": title, "hot": "", "url": url_link})
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取百度热搜失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_douyin_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取抖音热点"""
        try:
            url = "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"
            headers = {'Referer': 'https://www.douyin.com/'}
            response = self._make_request(url, headers=headers)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            data = self._safe_json_parse(response, url)
            if not data:
                return {"success": False, "error": "JSON解析失败"}
            
            hot_list = data.get('word_list', [])
            results = []
            for idx, item in enumerate(hot_list[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get('word', ''),
                    "hot": item.get('hot_value', 0),
                    "url": f"https://www.douyin.com/search/{item.get('word', '')}"
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取抖音热点失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_toutiao_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取今日头条热榜"""
        try:
            url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
            headers = {'Referer': 'https://www.toutiao.com/'}
            
            logger.info(f"请求今日头条: {url}")
            response = self._make_request(url, headers=headers)
            
            if not response:
                logger.error("今日头条请求失败: 无响应")
                return {"success": False, "error": "请求失败"}
            
            logger.info(f"今日头条响应: status={response.status_code}, encoding={response.encoding}, length={len(response.content)}")
            
            data = self._safe_json_parse(response, url)
            if not data:
                logger.error("今日头条JSON解析失败")
                return {"success": False, "error": "JSON解析失败"}
            
            hot_list = data.get('data', [])
            logger.info(f"今日头条获取到 {len(hot_list)} 条数据")
            
            results = []
            for idx, item in enumerate(hot_list[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get('Title', ''),
                    "hot": item.get('HotValue', 0),
                    "url": item.get('Url', '')
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取今日头条热榜失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def get_36kr_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取36氪快讯"""
        try:
            url = "https://36kr.com/api/newsflash"
            response = self._make_request(url)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            data = self._safe_json_parse(response, url)
            if not data:
                return {"success": False, "error": "JSON解析失败"}
            
            items = data.get('data', {}).get('items', [])
            results = []
            for idx, item in enumerate(items[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get('title', ''),
                    "hot": "",
                    "url": f"https://36kr.com/newsflashes/{item.get('id', '')}"
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取36氪快讯失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_sspai_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取少数派热门"""
        try:
            url = "https://sspai.com/api/v1/article/tag/page/get"
            params = {"limit": limit, "offset": 0, "sort": "hot", "tag": "热门"}
            response = self._make_request(url, params=params)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            data = self._safe_json_parse(response, url)
            if not data:
                return {"success": False, "error": "JSON解析失败"}
            
            items = data.get('data', [])
            results = []
            for idx, item in enumerate(items[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get('title', ''),
                    "hot": item.get('like_count', 0),
                    "url": f"https://sspai.com/post/{item.get('id', '')}"
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取少数派热门失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_ithome_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取IT之家热榜"""
        try:
            url = "https://www.ithome.com/"
            response = self._make_request(url)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            soup = self._build_soup(response.text, "IT之家热榜")
            items = soup.select('.hot-list ul li a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get_text(strip=True),
                    "hot": "",
                    "url": item.get('href', '')
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取IT之家热榜失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_thepaper_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取澎湃新闻热榜"""
        try:
            url = "https://www.thepaper.cn/load_index.jsp"
            response = self._make_request(url)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            soup = self._build_soup(response.text, "澎湃新闻热榜")
            items = soup.select('.news_li h2 a')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                results.append({
                    "rank": idx,
                    "title": item.get_text(strip=True),
                    "hot": "",
                    "url": f"https://www.thepaper.cn/{item.get('href', '')}"
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取澎湃新闻热榜失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_tophub_trending(self, limit: int = 10) -> Dict[str, Any]:
        """获取今日热榜"""
        try:
            url = "https://tophub.today/"
            response = self._make_request(url)
            
            if not response:
                return {"success": False, "error": "请求失败"}
            
            soup = self._build_soup(response.text, "今日热榜")
            items = soup.select('.cc-dc .cc-dc-content .cc-dc-content-item')
            
            results = []
            for idx, item in enumerate(items[:limit], 1):
                title_elem = item.select_one('.t')
                link_elem = item.select_one('a')
                hot_elem = item.select_one('.e')
                
                results.append({
                    "rank": idx,
                    "title": title_elem.get_text(strip=True) if title_elem else '',
                    "hot": hot_elem.get_text(strip=True) if hot_elem else '',
                    "url": link_elem.get('href', '') if link_elem else ''
                })
            
            return {"success": True, "data": results, "count": len(results)}
        except Exception as e:
            logger.error(f"获取今日热榜失败: {e}")
            return {"success": False, "error": str(e)}


_service_instance = None


def get_service() -> TrendsSearchService:
    """获取服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = TrendsSearchService()
    return _service_instance
