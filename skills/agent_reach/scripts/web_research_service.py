"""
网络资料研究服务
整合 Agent-Reach 能力，为小说创作提供资料搜索支持

设计理念：
1. 复用现有的 trends_search 服务
2. 集成 Jina Reader 网页阅读
3. 集成 yt-dlp 视频字幕提取
4. 集成 Agent-Reach 网络搜索能力
5. 提供统一的事件研究和热梗搜索接口
"""
import logging
import json
import time
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
import requests
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class WebResearchConfig:
    """配置类"""
    cache_enabled: bool = True
    cache_ttl: int = 3600  # 1小时
    timeout: int = 30
    max_retries: int = 3
    jina_reader_url: str = "https://r.jina.ai/"
    # Agent-Reach 搜索配置
    search_engine: str = "duckduckgo"  # 默认使用DuckDuckGo
    search_api_key: str = ""
    search_secret_key: str = ""
    # 平台特定配置
    platforms: Dict[str, Any] = field(default_factory=dict)


class WebResearchService:
    """
    网络资料研究服务

    核心功能：
    1. 网页内容阅读（Jina Reader）
    2. 热点搜索（复用 trends_search）
    3. 视频字幕提取（yt-dlp）
    4. 网络搜索（Agent-Reach）
    5. 事件研究（综合多来源）
    6. 网络热梗搜索
    """

    def __init__(self, config: Optional[WebResearchConfig] = None):
        self.config = config or WebResearchConfig()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self._trends_service = None
        self._search_engine = None
        self._cache: Dict[str, Any] = {}
        
        # 加载配置
        self._load_config()

    def _load_config(self):
        """从配置文件加载搜索引擎配置"""
        try:
            config_path = Path(__file__).parent.parent.parent.parent / "novel_agent" / "data" / "skills_config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    skills_config = json.load(f)
                    web_research_config = skills_config.get("skill_configs", {}).get("web_research", {})
                    
                    if web_research_config:
                        self.config.search_engine = web_research_config.get("search_engine", "duckduckgo")
                        self.config.search_api_key = web_research_config.get("api_key", "")
                        self.config.search_secret_key = web_research_config.get("secret_key", "")
                        logger.info(f"已加载web_research配置: engine={self.config.search_engine}")
        except Exception as e:
            logger.warning(f"加载web_research配置失败: {e}")

    def _get_trends_service(self):
        """延迟加载 trends_search 服务"""
        if self._trends_service is None:
            try:
                from skills.trends_search.scripts.trends_service import get_service
                self._trends_service = get_service()
            except ImportError as e:
                logger.warning(f"无法导入 trends_search 服务: {e}")
        return self._trends_service

    def _get_search_engine(self):
        """延迟加载搜索引擎"""
        if self._search_engine is None:
            try:
                engine = self.config.search_engine
                
                if engine == "baidu":
                    from skills.agent_reach.scripts.search_engines.baidu_search import BaiduSearchEngine
                    self._search_engine = BaiduSearchEngine({
                        "api_key": self.config.search_api_key,
                        "secret_key": self.config.search_secret_key,
                        "timeout": self.config.timeout
                    })
                elif engine == "bing":
                    from skills.agent_reach.scripts.search_engines.bing_search import BingSearchEngine
                    self._search_engine = BingSearchEngine({
                        "api_key": self.config.search_api_key,
                        "timeout": self.config.timeout
                    })
                elif engine == "duckduckgo":
                    from skills.agent_reach.scripts.search_engines.duckduckgo_search import DuckDuckGoSearchEngine
                    self._search_engine = DuckDuckGoSearchEngine({
                        "timeout": 15,
                        "max_retries": 3
                    })
                else:
                    logger.warning(f"不支持的搜索引擎: {engine}，使用DuckDuckGo")
                    from skills.agent_reach.scripts.search_engines.duckduckgo_search import DuckDuckGoSearchEngine
                    self._search_engine = DuckDuckGoSearchEngine({
                        "timeout": 15,
                        "max_retries": 3
                    })
                    
                logger.info(f"搜索引擎已初始化: {engine}")
            except ImportError as e:
                logger.error(f"无法导入搜索引擎: {e}")
        return self._search_engine

    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
        """统一的请求方法"""
        retry_count = 0
        last_error = None

        while retry_count <= self.config.max_retries:
            try:
                kwargs.setdefault('timeout', self.config.timeout)
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                last_error = e
                if e.response.status_code in [403, 429]:
                    retry_count += 1
                    time.sleep(2 ** retry_count)
                    continue
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

    def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if not self.config.cache_enabled:
            return None
        cached = self._cache.get(key)
        if cached and time.time() - cached['timestamp'] < self.config.cache_ttl:
            return cached['data']
        return None

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        if self.config.cache_enabled:
            self._cache[key] = {
                'data': data,
                'timestamp': time.time()
            }

    # ==================== 核心方法 ====================

    def web_search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """
        网络搜索（Agent-Reach核心功能）
        
        使用配置的搜索引擎进行真实的网络搜索
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            {
                "success": bool,
                "query": str,
                "data": [{"title", "url", "snippet", "source"}],
                "count": int
            }
        """
        cache_key = f"search:{query}:{max_results}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            search_engine = self._get_search_engine()
            if not search_engine:
                return {"success": False, "error": "搜索引擎未初始化"}
            
            results = search_engine.search(query, max_results=max_results)
            
            result = {
                "success": True,
                "query": query,
                "data": results,
                "count": len(results),
                "engine": self.config.search_engine
            }
            
            self._set_cache(cache_key, result)
            return result
            
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return {"success": False, "error": str(e)}

    def read_webpage(self, url: str) -> Dict[str, Any]:
        """
        阅读网页内容

        使用 Jina Reader 将网页转换为 Markdown 格式
        自动去除广告、导航栏等无关内容

        Args:
            url: 网页URL

        Returns:
            {
                "success": bool,
                "title": "文章标题",
                "content": "正文内容（Markdown）",
                "source": "来源URL"
            }
        """
        cache_key = f"webpage:{url}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            # 使用 Jina Reader
            reader_url = f"{self.config.jina_reader_url}{url}"
            response = self._make_request(reader_url)

            if not response:
                return {"success": False, "error": "请求失败"}

            content = response.text

            # 提取标题（Jina Reader 格式通常第一行是标题）
            lines = content.split('\n')
            title = ""
            for line in lines:
                if line.startswith('Title:'):
                    title = line.replace('Title:', '').strip()
                    break
                elif line.startswith('# '):
                    title = line[2:].strip()
                    break

            result = {
                "success": True,
                "title": title,
                "content": content,
                "source": url,
                "length": len(content)
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"阅读网页失败: {e}")
            return {"success": False, "error": str(e)}

    def search_trends(
        self,
        platform: str = "weibo",
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        搜索热点

        复用 trends_search 服务

        Args:
            platform: 平台名称 (weibo/zhihu/douyin/bilibili/toutiao/baidu/36kr/sspai/ithome/thepaper/tophub)
            limit: 返回条数

        Returns:
            {
                "success": bool,
                "platform": str,
                "data": [{"rank", "title", "hot", "url"}]
            }
        """
        # 平台名称映射
        platform_map = {
            'weibo': 'get_weibo_trending',
            'zhihu': 'get_zhihu_trending',
            'douyin': 'get_douyin_trending',
            'toutiao': 'get_toutiao_trending',
            'baidu': 'get_baidu_trending',
            '36kr': 'get_36kr_trending',
            'sspai': 'get_sspai_trending',
            'ithome': 'get_ithome_trending',
            'thepaper': 'get_thepaper_trending',
            'tophub': 'get_tophub_trending',
        }

        cache_key = f"trends:{platform}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            trends_service = self._get_trends_service()
            if not trends_service:
                return {"success": False, "error": "trends_search 服务不可用"}

            method_name = platform_map.get(platform.lower())
            if not method_name:
                return {
                    "success": False,
                    "error": f"不支持的平台: {platform}",
                    "supported": list(platform_map.keys())
                }

            method = getattr(trends_service, method_name, None)
            if not method:
                return {"success": False, "error": f"方法不存在: {method_name}"}

            result = method(limit=limit)
            result['platform'] = platform

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"搜索热点失败: {e}")
            return {"success": False, "error": str(e)}

    def extract_video_subtitle(self, url: str) -> Dict[str, Any]:
        """
        提取视频字幕

        支持 B站、YouTube 等平台
        需要安装 yt-dlp

        Args:
            url: 视频URL

        Returns:
            {
                "success": bool,
                "title": "视频标题",
                "subtitle": "字幕内容",
                "duration": "视频时长",
                "source": "来源URL"
            }
        """
        try:
            import subprocess

            # 检查 yt-dlp 是否可用
            try:
                subprocess.run(
                    ['yt-dlp', '--version'],
                    capture_output=True,
                    check=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                return {
                    "success": False,
                    "error": "yt-dlp 未安装，请运行: pip install yt-dlp"
                }

            # 获取视频信息
            result = subprocess.run(
                ['yt-dlp', '--dump-json', '--no-download', url],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return {"success": False, "error": f"获取视频信息失败: {result.stderr}"}

            video_info = json.loads(result.stdout)
            title = video_info.get('title', '未知标题')
            duration = video_info.get('duration', 0)

            # 尝试获取字幕
            subtitle_result = subprocess.run(
                [
                    'yt-dlp',
                    '--write-auto-sub',
                    '--sub-lang', 'zh,zh-Hans,zh-Hant,en',
                    '--skip-download',
                    '--print', 'subtitle',
                    url
                ],
                capture_output=True,
                text=True,
                timeout=120
            )

            subtitle = ""
            if subtitle_result.returncode == 0 and subtitle_result.stdout:
                subtitle = subtitle_result.stdout.strip()

            # 如果没有字幕，尝试获取描述作为替代
            if not subtitle:
                subtitle = video_info.get('description', '（无字幕，仅显示视频描述）')

            return {
                "success": True,
                "title": title,
                "subtitle": subtitle,
                "duration": f"{duration // 60}分{duration % 60}秒",
                "source": url
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "视频解析超时"}
        except json.JSONDecodeError:
            return {"success": False, "error": "视频信息解析失败"}
        except Exception as e:
            logger.error(f"提取视频字幕失败: {e}")
            return {"success": False, "error": str(e)}

    def search_memes(
        self,
        keyword: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        搜索网络热梗

        使用网络搜索查找热梗信息

        Args:
            keyword: 热梗关键词（可选）
            limit: 返回条数

        Returns:
            {"success": bool, "data": [...]}
        """
        try:
            if keyword:
                # 使用网络搜索
                search_query = f"{keyword} 网络热梗 含义"
                search_result = self.web_search(search_query, max_results=limit)
                
                if search_result.get("success"):
                    memes = []
                    for item in search_result.get("data", []):
                        memes.append({
                            "term": keyword,
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "url": item.get("url", ""),
                            "source": item.get("source", "web")
                        })
                    
                    return {
                        "success": True,
                        "keyword": keyword,
                        "count": len(memes),
                        "data": memes
                    }

            # 降级：从热搜中过滤
            weibo_result = self.search_trends('weibo', limit)

            memes = []
            if weibo_result.get('success'):
                for item in weibo_result.get('data', []):
                    term = item.get('title', '')
                    if keyword and keyword.lower() not in term.lower():
                        continue
                    memes.append({
                        "term": term,
                        "meaning": "（待查询）",
                        "origin": "微博热搜",
                        "usage": "社交网络讨论",
                        "hot": item.get('hot', ''),
                        "url": item.get('url', ''),
                        "examples": []
                    })

            return {
                "success": True,
                "keyword": keyword,
                "count": len(memes),
                "data": memes[:limit]
            }

        except Exception as e:
            logger.error(f"搜索热梗失败: {e}")
            return {"success": False, "error": str(e)}

    def research_event(
        self,
        query: str,
        depth: str = "quick"
    ) -> Dict[str, Any]:
        """
        事件研究

        使用网络搜索进行事件资料检索

        Args:
            query: 事件关键词
            depth: 研究深度 (quick/deep)

        Returns:
            {
                "success": bool,
                "query": str,
                "timeline": [{"date", "event", "source", "url"}],
                "summary": str,
                "sources": []
            }
        """
        try:
            related_items: List[Dict[str, Any]] = []

            # 网络搜索（主要来源）
            limit = 10 if depth == "deep" else 5
            search_result = self.web_search(query, max_results=limit)
            
            if search_result.get("success"):
                for item in search_result.get("data", []):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    if not title and not url:
                        continue
                    related_items.append({
                        "date": "网络搜索",
                        "event": title or url,
                        "source": "web_research",
                        "url": url,
                        "snippet": item.get("snippet", "")
                    })

            # 热榜补充（如果可用）
            try:
                weibo_result = self.search_trends('weibo', 20)
                if weibo_result.get('success'):
                    for item in weibo_result.get('data', []):
                        title = (item.get('title', '') or '').lower()
                        if query.lower() in title or any(kw in title for kw in query.split()):
                            related_items.append({
                                "date": "当前热搜",
                                "event": item.get('title'),
                                "source": f"微博热搜 #{item.get('rank')}",
                                "url": item.get('url')
                            })

                zhihu_result = self.search_trends('zhihu', 10)
                if zhihu_result.get('success'):
                    for item in zhihu_result.get('data', []):
                        title = (item.get('title', '') or '').lower()
                        if query.lower() in title:
                            related_items.append({
                                "date": "知乎热榜",
                                "event": item.get('title'),
                                "source": "知乎",
                                "url": item.get('url')
                            })
            except Exception:
                # 热榜补充失败不影响主流程
                pass

            timeline = related_items

            summary = f"关于「{query}」的事件研究"
            if timeline:
                summary += f"，共找到 {len(timeline)} 条相关资料/讨论。"
            else:
                summary += "，暂未找到相关资料。"

            return {
                "success": True,
                "query": query,
                "depth": depth,
                "timeline": timeline,
                "summary": summary,
                "sources": list({item.get('source', '') for item in timeline if item.get('source')})
            }

        except Exception as e:
            logger.error(f"事件研究失败: {e}")
            return {"success": False, "error": str(e)}

    def comprehensive_search(
        self,
        query: str,
        sources: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        综合搜索

        从多个来源搜索信息：
        - web：使用网络搜索（真实网络搜索）
        - social/news/trending：使用 trends_search（热点补充）

        Args:
            query: 搜索关键词
            sources: 数据源列表 (默认全部)

        Returns:
            {
                "success": bool,
                "query": str,
                "results": {"web": [], "social": [], "news": [], "trending": []},
                "summary": str
            }
        """
        pass


# 全局服务实例
_service_instance = None

def get_service() -> WebResearchService:
    """获取服务单例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = WebResearchService()
    return _service_instance
