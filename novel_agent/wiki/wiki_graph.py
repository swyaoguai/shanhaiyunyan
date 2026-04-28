"""
Wiki 知识图谱构建器

基于 4 信号相关性模型构建知识图谱：
1. 直接链接（×3.0）：[[wikilink]] 关系
2. 来源重叠（×4.0）：共享同一原始来源
3. Adamic-Adar（×1.5）：共享邻居（按度数加权）
4. 类型亲和度（×1.0）：同类型页面加分

支持：
- 图谱构建和更新
- 相关性计算
- 图谱扩展检索（2跳遍历+衰减）
- 孤立页面检测
- 桥接节点检测
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .wiki_types import (
    PageType,
    WikiGraph,
    WikiGraphEdge,
    WikiGraphNode,
    WikiPage,
)

logger = logging.getLogger(__name__)

# 信号权重
WEIGHT_DIRECT_LINK = 3.0
WEIGHT_SOURCE_OVERLAP = 4.0
WEIGHT_ADAMIC_ADAR = 1.5
WEIGHT_TYPE_AFFINITY = 1.0


class WikiGraphBuilder:
    """
    知识图谱构建器
    
    从 wiki 页面集合构建知识图谱，计算页面间的相关性。
    """

    def __init__(self):
        self._graph = WikiGraph()

    @property
    def graph(self) -> WikiGraph:
        return self._graph

    # ------------------------------------------------------------------
    #  图谱构建
    # ------------------------------------------------------------------

    def build_from_pages(self, pages: List[WikiPage]) -> WikiGraph:
        """
        从页面列表构建完整的知识图谱
        
        Args:
            pages: wiki 页面列表
            
        Returns:
            构建好的知识图谱
        """
        self._graph = WikiGraph()
        
        # 1. 创建节点
        for page in pages:
            node = WikiGraphNode(
                title=page.title,
                page_type=page.page_type,
                sources=list(page.sources),
                tags=list(page.tags),
            )
            self._graph.nodes[page.title] = node
        
        # 2. 收集链接关系
        link_map: Dict[str, Set[str]] = defaultdict(set)  # source → {targets}
        for page in pages:
            targets = page.extract_wikilinks()
            for target in targets:
                if target in self._graph.nodes:
                    link_map[page.title].add(target)
                    # 双向
                    link_map[target].add(page.title)
        
        # 3. 收集来源关系
        source_map: Dict[str, Set[str]] = defaultdict(set)  # source_file → {page_titles}
        for page in pages:
            for src in page.sources:
                source_map[src].add(page.title)
        
        # 4. 计算 4 信号相关性并创建边
        edges_set: Set[Tuple[str, str]] = set()
        
        for page_a in pages:
            for page_b in pages:
                if page_a.title >= page_b.title:
                    continue  # 避免重复
                
                pair = (page_a.title, page_b.title)
                if pair in edges_set:
                    continue
                
                signals: Dict[str, float] = {}
                
                # 信号1: 直接链接
                if page_b.title in link_map.get(page_a.title, set()):
                    signals["direct_link"] = WEIGHT_DIRECT_LINK
                
                # 信号2: 来源重叠
                shared_sources = set(page_a.sources) & set(page_b.sources)
                if shared_sources:
                    signals["source_overlap"] = len(shared_sources) * WEIGHT_SOURCE_OVERLAP
                
                # 信号3: Adamic-Adar
                common_neighbors = link_map.get(page_a.title, set()) & link_map.get(page_b.title, set())
                if common_neighbors:
                    aa_score = 0.0
                    for neighbor in common_neighbors:
                        degree = len(link_map.get(neighbor, set()))
                        if degree > 1:
                            aa_score += WEIGHT_ADAMIC_ADAR / math.log(degree)
                    if aa_score > 0:
                        signals["adamic_adar"] = aa_score
                
                # 信号4: 类型亲和度
                if page_a.page_type == page_b.page_type:
                    signals["type_affinity"] = WEIGHT_TYPE_AFFINITY
                
                # 只有存在至少一个信号时才创建边
                total_weight = sum(signals.values())
                if total_weight > 0:
                    edge = WikiGraphEdge(
                        source=page_a.title,
                        target=page_b.title,
                        weight=total_weight,
                        signals=signals,
                    )
                    self._graph.edges.append(edge)
                    edges_set.add(pair)
        
        # 5. 更新节点度数
        for edge in self._graph.edges:
            if edge.source in self._graph.nodes:
                self._graph.nodes[edge.source].degree += 1
            if edge.target in self._graph.nodes:
                self._graph.nodes[edge.target].degree += 1
        
        logger.info(
            f"[WikiGraph] 构建完成: {len(self._graph.nodes)} 节点, "
            f"{len(self._graph.edges)} 边"
        )
        
        return self._graph

    # ------------------------------------------------------------------
    #  图谱扩展检索
    # ------------------------------------------------------------------

    def expand_from_seeds(
        self,
        seed_titles: List[str],
        hops: int = 2,
        decay: float = 0.5,
        max_results: int = 20,
    ) -> List[Tuple[str, float]]:
        """
        从种子节点出发，通过图谱扩展检索相关页面
        
        Args:
            seed_titles: 种子页面标题列表
            hops: 跳数（默认2跳）
            decay: 每跳衰减系数
            max_results: 最大返回数
            
        Returns:
            [(页面标题, 相关性分数)] 列表，按分数降序
        """
        scores: Dict[str, float] = {}
        visited: Set[str] = set()
        
        # 种子节点初始分数为 1.0
        frontier = {title: 1.0 for title in seed_titles if title in self._graph.nodes}
        
        for hop in range(hops):
            next_frontier: Dict[str, float] = {}
            
            for title, current_score in frontier.items():
                if title in visited:
                    continue
                visited.add(title)
                
                # 累加分数
                scores[title] = scores.get(title, 0.0) + current_score
                
                # 获取邻居
                for edge in self._graph.edges:
                    neighbor = None
                    edge_weight = edge.weight
                    
                    if edge.source == title and edge.target not in visited:
                        neighbor = edge.target
                    elif edge.target == title and edge.source not in visited:
                        neighbor = edge.source
                    
                    if neighbor:
                        # 衰减后的分数
                        neighbor_score = current_score * decay * (edge_weight / 5.0)
                        if neighbor_score > 0.01:  # 阈值过滤
                            next_frontier[neighbor] = max(
                                next_frontier.get(neighbor, 0.0),
                                neighbor_score
                            )
            
            frontier = next_frontier
        
        # 排序并返回
        sorted_results = sorted(scores.items(), key=lambda x: -x[1])
        return sorted_results[:max_results]

    # ------------------------------------------------------------------
    #  分析
    # ------------------------------------------------------------------

    def get_isolated_pages(self) -> List[str]:
        """获取孤立页面（度数 ≤ 1）"""
        return self._graph.get_isolated_pages()

    def get_bridge_nodes(self, min_clusters: int = 3) -> List[str]:
        """获取桥接节点"""
        return self._graph.get_bridge_nodes(min_clusters)

    def get_surprising_connections(self) -> List[Dict[str, any]]:
        """
        检测意外连接
        
        意外连接 = 跨类型、跨来源的高权重边
        """
        surprising = []
        
        for edge in self._graph.edges:
            source_node = self._graph.nodes.get(edge.source)
            target_node = self._graph.nodes.get(edge.target)
            
            if not source_node or not target_node:
                continue
            
            # 计算意外度
            surprise_score = 0.0
            reasons = []
            
            # 跨类型连接更意外
            if source_node.page_type != target_node.page_type:
                surprise_score += 2.0
                reasons.append("跨类型")
            
            # 高权重但没有直接链接（通过其他信号连接）
            if edge.weight >= 3.0 and "direct_link" not in edge.signals:
                surprise_score += edge.weight
                reasons.append("非直接链接的强相关")
            
            # 来源重叠但类型不同
            if "source_overlap" in edge.signals and source_node.page_type != target_node.page_type:
                surprise_score += 1.5
                reasons.append("跨类型来源重叠")
            
            if surprise_score >= 2.0:
                surprising.append({
                    "source": edge.source,
                    "target": edge.target,
                    "weight": edge.weight,
                    "surprise_score": surprise_score,
                    "reasons": reasons,
                })
        
        surprising.sort(key=lambda x: -x["surprise_score"])
        return surprising

    def get_knowledge_gaps(self) -> List[Dict[str, any]]:
        """
        检测知识缺口
        
        包括：
        - 孤立页面（度数 ≤ 1）
        - 稀疏社区（内部连接少）
        - 桥接节点（连接多个社区）
        """
        gaps = []
        
        # 孤立页面
        for title in self.get_isolated_pages():
            node = self._graph.nodes.get(title)
            if node:
                gaps.append({
                    "type": "isolated",
                    "title": title,
                    "page_type": node.page_type.value,
                    "degree": node.degree,
                    "suggestion": f"为 [[{title}]] 添加更多链接",
                })
        
        # 桥接节点
        for title in self.get_bridge_nodes():
            gaps.append({
                "type": "bridge",
                "title": title,
                "page_type": self._graph.nodes[title].page_type.value,
                "degree": self._graph.nodes[title].degree,
                "suggestion": f"[[{title}]] 是关键连接点，考虑补充内容",
            })
        
        return gaps

    # ------------------------------------------------------------------
    #  统计
    # ------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, any]:
        """获取图谱统计信息"""
        if not self._graph.nodes:
            return {"nodes": 0, "edges": 0}
        
        degrees = [node.degree for node in self._graph.nodes.values()]
        weights = [edge.weight for edge in self._graph.edges]
        
        return {
            "nodes": len(self._graph.nodes),
            "edges": len(self._graph.edges),
            "avg_degree": sum(degrees) / len(degrees) if degrees else 0,
            "max_degree": max(degrees) if degrees else 0,
            "min_degree": min(degrees) if degrees else 0,
            "avg_weight": sum(weights) / len(weights) if weights else 0,
            "isolated_count": len(self.get_isolated_pages()),
            "bridge_count": len(self.get_bridge_nodes()),
        }