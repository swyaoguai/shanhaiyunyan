"""
结构化输出协议工具模块

提供结构化输出协议的验证和应用工具
"""

import json
import re
from typing import Dict, List, Any, Optional


class StructuredOutputValidator:
    """结构化输出协议验证器"""
    
    # 禁用的线性流词汇
    LINEAR_FLOW_PATTERNS = [
        r'首先[，,、]',
        r'然后[，,、]',
        r'接着[，,、]',
        r'所以[，,、]',
        r'你可以[，,、]',
        r'接下来[，,、]',
        r'我已经[，,、]',
    ]
    
    # 需要删除的口语化表达
    NOISE_PATTERNS = [
        r'根据搜索结果[，,、]',
        r'总的来说[，,、]',
        r'希望这对您有帮助',
        r'希望对你有帮助',
    ]

    # 正文型模式不应出现的结构化痕迹
    PROSE_STRUCTURE_PATTERNS = [
        (r'^#\s+', "Markdown 一级标题"),
        (r'^\d+\.\s+', "有序列表"),
        (r'^\-\s+', "无序列表"),
        (r'^\>\s+', "引用块"),
        (r'\|[^\n]*\|[^\n]*\|', "Markdown 表格"),
        (r'(?i)润色说明|修改对比|润色分析|章节总结|重要事件|新增角色|下一步建议|自检报告', "元信息说明"),
    ]

    @classmethod
    def check_linear_flow(cls, text: str) -> List[str]:
        """检查是否存在线性流叙事"""
        violations = []
        for pattern in cls.LINEAR_FLOW_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                violations.append(f"发现线性流词汇: {pattern}")
        return violations
    
    @classmethod
    def check_noise(cls, text: str) -> List[str]:
        """检查是否存在口语化噪音"""
        violations = []
        for pattern in cls.NOISE_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                violations.append(f"发现口语化表达: {pattern}")
        return violations
    
    @classmethod
    def check_structure(cls, text: str) -> Dict[str, Any]:
        """检查文本结构"""
        # 检查一级标题数量
        h1_count = len(re.findall(r'^# [^#]', text, re.MULTILINE))
        
        # 检查表格使用
        table_count = len(re.findall(r'\|.*\|.*\|', text))
        
        # 检查列表使用
        ordered_list_count = len(re.findall(r'^\d+\. ', text, re.MULTILINE))
        unordered_list_count = len(re.findall(r'^- ', text, re.MULTILINE))
        
        # 检查加粗使用（核心结论）
        bold_count = len(re.findall(r'\*\*[^*]+\*\*', text))
        
        # 检查引用块使用
        quote_count = len(re.findall(r'^> ', text, re.MULTILINE))
        
        return {
            "h1_count": h1_count,
            "table_count": table_count,
            "ordered_list_count": ordered_list_count,
            "unordered_list_count": unordered_list_count,
            "bold_count": bold_count,
            "quote_count": quote_count,
            "has_structure": h1_count > 0 or table_count > 0 or ordered_list_count > 0
        }
    
    @classmethod
    def validate(cls, text: str) -> Dict[str, Any]:
        """完整验证 Markdown 结构化文本是否符合协议"""
        linear_violations = cls.check_linear_flow(text)
        noise_violations = cls.check_noise(text)
        structure = cls.check_structure(text)
        
        return {
            "mode": "markdown",
            "is_valid": len(linear_violations) == 0 and len(noise_violations) == 0 and structure["has_structure"],
            "linear_flow_violations": linear_violations,
            "noise_violations": noise_violations,
            "structure": structure,
            "suggestions": cls._generate_suggestions(linear_violations, noise_violations, structure)
        }

    @classmethod
    def validate_json_output(
        cls,
        text: str,
        required_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """验证 JSON 型输出是否符合协议。"""
        required_fields = list(required_fields or [])
        violations: List[str] = []
        suggestions: List[str] = []

        raw_text = str(text or "").strip()
        parsed: Any = None
        markdown_leak = bool(re.search(r'^\s*#|^\s*>|^\s*[-*]\s+|^\s*\d+\.\s+|\|[^\n]*\|', raw_text, re.MULTILINE))

        if markdown_leak:
            violations.append("JSON 输出中检测到 Markdown 结构残留")

        try:
            parsed = json.loads(raw_text)
        except Exception as exc:
            violations.append(f"JSON 解析失败: {exc}")
            suggestions.append("确保只输出合法 JSON，不要在外层包裹说明文字或 Markdown")
            return {
                "mode": "json",
                "is_valid": False,
                "violations": violations,
                "missing_fields": required_fields,
                "suggestions": suggestions,
                "parsed_type": None,
            }

        if not isinstance(parsed, (dict, list)):
            violations.append("JSON 顶层必须是对象或数组")

        missing_fields: List[str] = []
        if isinstance(parsed, dict):
            for field in required_fields:
                if field not in parsed:
                    missing_fields.append(field)
            if missing_fields:
                violations.append(f"缺少必填字段: {', '.join(missing_fields)}")

            for field_name in ("suggestions", "issues", "highlights"):
                field_value = parsed.get(field_name)
                if isinstance(field_value, list):
                    for item in field_value:
                        item_text = str(item).strip() if not isinstance(item, dict) else json.dumps(item, ensure_ascii=False)
                        if any(token in item_text for token in ("需要优化", "建议改进", "可进一步完善")):
                            violations.append(f"{field_name} 中存在空泛建议")

        if violations and "确保关键字段齐全，建议具体、可执行、可机读" not in suggestions:
            suggestions.append("确保关键字段齐全，建议具体、可执行、可机读")

        return {
            "mode": "json",
            "is_valid": len(violations) == 0,
            "violations": violations,
            "missing_fields": missing_fields,
            "suggestions": suggestions,
            "parsed_type": type(parsed).__name__,
        }

    @classmethod
    def validate_prose_output(cls, text: str) -> Dict[str, Any]:
        """验证正文型输出是否出现反结构化违规。"""
        raw_text = str(text or "")
        violations: List[str] = []
        for pattern, label in cls.PROSE_STRUCTURE_PATTERNS:
            if re.search(pattern, raw_text, re.MULTILINE):
                violations.append(f"正文中检测到不应出现的{label}")

        return {
            "mode": "prose",
            "is_valid": len(violations) == 0,
            "violations": violations,
            "suggestions": [
                "正文型模式只输出最终正文，不输出表格、列表、标题、说明和元信息"
            ] if violations else [],
        }
    
    @classmethod
    def _generate_suggestions(cls, linear_violations: List[str], noise_violations: List[str], structure: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        if linear_violations:
            suggestions.append("避免使用线性流叙事词汇，改用并列或递进的逻辑关系")
        
        if noise_violations:
            suggestions.append("删除口语化表达，直接陈述核心内容")
        
        if structure["h1_count"] == 0:
            suggestions.append("使用一级标题(#)分隔不同维度")
        
        if structure["table_count"] == 0 and structure["ordered_list_count"] == 0:
            suggestions.append("使用表格或列表提升可读性")
        
        if structure["bold_count"] == 0:
            suggestions.append("用加粗(**文本**)标记核心结论")
        
        return suggestions


class StructuredOutputHelper:
    """结构化输出协议辅助工具"""
    
    @staticmethod
    def format_comparison(items: List[Dict[str, Any]], dimensions: List[str]) -> str:
        """格式化对比数据为表格"""
        if not items or not dimensions:
            return ""
        
        # 构建表头
        headers = ["维度"] + [item.get("name", f"方案{i+1}") for i, item in enumerate(items)]
        header_row = "| " + " | ".join(headers) + " |"
        separator = "|" + "|".join(["---" for _ in headers]) + "|"
        
        # 构建数据行
        rows = []
        for dim in dimensions:
            row_data = [dim]
            for item in items:
                value = item.get(dim, "-")
                row_data.append(str(value))
            rows.append("| " + " | ".join(row_data) + " |")
        
        return "\n".join([header_row, separator] + rows)
    
    @staticmethod
    def format_steps(steps: List[str]) -> str:
        """格式化步骤为有序列表"""
        if not steps:
            return ""
        
        formatted = []
        for i, step in enumerate(steps, 1):
            # 提取关键动作（假设在冒号前）
            if "：" in step or ":" in step:
                parts = re.split(r'[：:]', step, 1)
                action = parts[0].strip()
                detail = parts[1].strip() if len(parts) > 1 else ""
                formatted.append(f"{i}. **{action}**：{detail}")
            else:
                formatted.append(f"{i}. {step}")
        
        return "\n".join(formatted)
    
    @staticmethod
    def format_explanation(items: List[str]) -> str:
        """格式化解释为无序列表"""
        if not items:
            return ""
        
        return "\n".join([f"- {item}" for item in items])
    
    @staticmethod
    def add_conclusion_prefix(title: str, conclusion: str) -> str:
        """为模块添加核心结论前置"""
        return f"# {title}\n\n**{conclusion}**\n\n"
    
    @staticmethod
    def add_warning_block(warnings: List[str]) -> str:
        """添加警告引用块"""
        if not warnings:
            return ""
        
        return "\n".join([f"> {warning}" for warning in warnings])


# 导出
__all__ = [
    'StructuredOutputValidator',
    'StructuredOutputHelper',
]