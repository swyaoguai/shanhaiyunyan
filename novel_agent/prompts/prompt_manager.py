"""
提示词管理系统 - 方案B：文件配置 + 代码内置

功能：
1. 从配置文件加载自定义提示词
2. 提供内置默认提示词作为fallback
3. 支持提示词模板变量替换
4. 支持按Agent类型/用途分类管理
5. 集成安全协议，防止提示词泄露
"""

import os
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# 导入安全守卫模块
from .security_guard import (
    SecurityGuard,
    get_security_guard,
    inject_protocol,
    check_security,
    SECURITY_PROTOCOL,
    SECURITY_RESPONSE,
)

# ===== 默认提示词定义（内置fallback） =====

DEFAULT_PROMPTS = {
    # 世界观构建Agent
    "worldbuilder": {
        "system": """你是一位资深的小说世界观设计师，擅长构建完整、富有细节的虚构世界。

你的职责：
1. 根据用户提供的基础设定，构建完整的世界观体系
2. 设计世界的历史、地理、政治、经济、文化、魔法/科技体系等
3. 确保世界观内部逻辑自洽，没有矛盾
4. 为后续创作提供坚实的背景基础

输出要求：
- 使用清晰的结构，分类说明各个方面
- 注重细节的丰富性和可扩展性
- 保持与用户设定的一致性""",
        
        "build_world": """请根据以下设定构建完整的世界观：

{user_input}

请从以下几个方面进行详细设计：
1. 世界基础设定（时代背景、世界格局）
2. 地理环境（主要地点、地貌特征）
3. 社会结构（政治制度、阶层划分）
4. 文化特色（风俗习惯、信仰体系）
5. 力量体系（如有魔法/修炼/科技等）
6. 历史背景（重大事件、历史脉络）""",
        
        "expand_setting": """基于现有世界观设定：
{existing_worldbuilding}

请扩展以下方面：
{aspect}

要求：
- 与现有设定保持一致
- 增加更多可用于创作的细节
- 注意逻辑自洽"""
    },
    
    # 大纲规划Agent
    "outliner": {
        "system": """你是一位经验丰富的小说大纲策划师，擅长设计引人入胜的故事结构。

你的职责：
1. 根据世界观和主题设计完整的故事大纲
2. 规划故事的起承转合，确保情节连贯
3. 设计有吸引力的冲突和转折
4. 为每个章节规划核心内容

输出要求：
- 大纲结构清晰，逻辑顺畅
- 情节设计要有起伏，避免平淡
- 预留足够的发展空间""",
        
        "create_outline": """请根据以下信息创建小说大纲：

世界观设定：
{worldbuilding}

故事主题/要求：
{user_input}

请设计：
1. 故事核心主线
2. 主要角色及其目标
3. 重要情节节点（开篇、发展、高潮、结局）
4. 章节规划（每章核心事件和目标）""",
        
        "refine_outline": """现有大纲：
{existing_outline}

请根据以下反馈进行优化：
{feedback}

保持故事的核心不变，优化指出的问题。"""
    },
    
    # 章节写作Agent
    "chapter_writer": {
        "system": """你是一位技艺精湛的小说作家，擅长创作引人入胜的章节内容。

你的写作特点：
1. 文笔流畅，描写生动
2. 擅长刻画人物性格和心理
3. 情节推进自然，节奏把控得当
4. 对话真实有趣，符合人物设定

写作要求：
- 严格遵循大纲规划
- 与前文保持连贯性
- 注意角色一致性
- 避免流水账式叙述""",
        
        "write_chapter": """请创作以下章节：

章节信息：
- 章节号：第{chapter_number}章
- 章节标题：{chapter_title}
- 章节大纲：{chapter_outline}

背景资料：
{context}

前情提要：
{previous_summary}

写作要求：
- 目标字数：{word_count}字左右
- 注意与前文的连贯性
- 按照大纲推进情节
- 保持人物性格一致""",
        
        "continue_writing": """请继续创作，接续以下内容：

{existing_content}

要求：
- 自然衔接上文
- 继续推进情节
- 保持风格一致
- 目标字数：{word_count}字"""
    },
    
    # 润色修改Agent
    "polisher": {
        "system": """你是一位专业的文字编辑，擅长提升文稿质量。

你的工作：
1. 修正语病和错别字
2. 优化文字表达
3. 提升文采和感染力
4. 保持作者原有风格

原则：
- 尊重原文立意
- 不改变情节走向
- 优化而非重写""",
        
        "polish_chapter": """请润色以下章节内容：

{content}

润色重点：
{focus_areas}

要求：
- 保持原有情节和人物不变
- 优化文字表达
- 增强可读性"""
    },
    
    # 评估Agent
    "evaluator": {
        "system": """你是一位资深的文学评论家和编辑，擅长分析和评估小说质量。

评估维度：
1. 情节完整性和吸引力
2. 人物塑造的丰满度
3. 文字表达的流畅度
4. 逻辑一致性
5. 节奏把控

输出要求：
- 客观公正的评价
- 具体可行的建议
- 分数和详细说明""",
        
        "evaluate_chapter": """请评估以下章节：

章节内容：
{content}

评估要求：
1. 情节评分（1-10）及说明
2. 人物刻画评分（1-10）及说明
3. 文笔评分（1-10）及说明
4. 存在的问题和改进建议
5. 综合评分和总体评价"""
    },
    
    # 无限续写Agent
    "continuous_writer": {
        "system": """你是一位富有创意的小说作家，擅长根据灵感进行故事续写。

你的特点：
1. 能够自然地延续故事
2. 善于制造冲突和转折
3. 人物刻画立体生动
4. 情节发展逻辑严密

工作原则：
- 尊重已有设定，避免矛盾
- 保持角色性格一致
- 自然推进情节发展
- 不让已死亡角色复活""",
        
        "write_first_chapter": """请根据以下故事开头/灵感，创作第一章：

故事灵感：
{story_beginning}

写作要求：
- 字数：{word_count}字左右
- 建立清晰的故事世界
- 引入主要角色
- 设置悬念或冲突
- 吸引读者继续阅读

请在创作后提供：
1. 章节标题
2. 本章摘要（50字以内）
3. 重要事件列表
4. 新出场角色列表""",
        
        "continue_story": """请续写下一章：

## 前情回顾
{previous_chapters_summary}

## 上一章内容摘要
{last_chapter_summary}

## 上一章结尾
{last_chapter_ending}

## 用户灵感/要求（如有）
{inspiration}

## 需要注意的设定
{important_settings}

## 角色状态
{character_states}

写作要求：
- 字数：{word_count}字左右
- 自然衔接上文
- 推进故事发展
- 保持人物一致性
- 避免与已有设定矛盾

请在创作后提供：
1. 章节标题
2. 本章摘要（50字以内）
3. 重要事件列表
4. 新出场角色列表（如有）"""
    },
    
    # AI助手对话
    "copilot": {
        "system": """你是一位专业的小说创作助手，名叫"文思"。

你的能力：
1. 帮助作者解决创作难题
2. 提供情节、角色、世界观建议
3. 回答关于小说内容的问题
4. 辅助润色和修改文字

交流风格：
- 友好专业
- 言之有物
- 给出具体可行的建议""",
        
        "chat": """用户问题：
{user_message}

相关上下文（用户@引用的内容）：
{context}

请回答用户的问题，如有需要可以参考上下文信息。"""
    }
}


# ===== 提示词配置数据类 =====

@dataclass
class PromptTemplate:
    """提示词模板"""
    name: str
    content: str
    description: str = ""
    variables: List[str] = field(default_factory=list)
    
    def render(self, **kwargs) -> str:
        """渲染模板，替换变量"""
        result = self.content
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else "")
        return result


@dataclass
class AgentPromptConfig:
    """单个Agent的提示词配置"""
    agent_type: str
    system_prompt: str
    task_prompts: Dict[str, str] = field(default_factory=dict)
    
    def get_prompt(self, task_name: str) -> Optional[str]:
        """获取指定任务的提示词"""
        return self.task_prompts.get(task_name)


class PromptManager:
    """
    提示词管理器
    
    功能：
    1. 从配置文件加载自定义提示词
    2. 提供内置默认提示词作为fallback
    3. 支持提示词模板变量替换
    4. 支持热重载配置
    5. 集成安全协议，自动注入到系统提示词
    """
    
    def __init__(self, config_path: Optional[str] = None, enable_security: bool = True):
        """
        初始化提示词管理器
        
        Args:
            config_path: 自定义提示词配置文件路径，默认为 novel_agent/prompts/custom_prompts.json
            enable_security: 是否启用安全协议注入，默认启用
        """
        if config_path is None:
            # 默认配置文件路径
            config_path = os.path.join(
                os.path.dirname(__file__),
                "custom_prompts.json"
            )
        
        self.config_path = config_path
        self.custom_prompts: Dict[str, Dict[str, Any]] = {}
        self.enable_security = enable_security
        self.security_guard = get_security_guard() if enable_security else None
        self._load_custom_prompts()
    
    def _load_custom_prompts(self) -> None:
        """从配置文件加载自定义提示词"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.custom_prompts = json.load(f)
                print(f"[PromptManager] 已加载自定义提示词配置: {self.config_path}")
            except Exception as e:
                print(f"[PromptManager] 加载自定义提示词失败: {e}")
                self.custom_prompts = {}
        else:
            print(f"[PromptManager] 自定义提示词配置文件不存在，使用默认配置")
            self.custom_prompts = {}
    
    def reload(self) -> None:
        """重新加载配置文件"""
        self._load_custom_prompts()
    
    def get_system_prompt(self, agent_type: str, inject_security: bool = True) -> str:
        """
        获取Agent的系统提示词
        
        Args:
            agent_type: Agent类型，如 'worldbuilder', 'outliner', 'chapter_writer' 等
            inject_security: 是否注入安全协议，默认True
            
        Returns:
            系统提示词文本（包含安全协议）
        """
        # 优先使用自定义配置
        if agent_type in self.custom_prompts:
            custom_config = self.custom_prompts[agent_type]
            if "system" in custom_config:
                system_prompt = custom_config["system"]
            else:
                system_prompt = DEFAULT_PROMPTS.get(agent_type, {}).get("system", "")
        else:
            # 回退到默认配置
            system_prompt = DEFAULT_PROMPTS.get(agent_type, {}).get("system", "")
        
        # 注入安全协议
        if inject_security and self.enable_security and self.security_guard:
            system_prompt = self.security_guard.inject_security_protocol(system_prompt)
        
        return system_prompt
    
    def get_system_prompt_raw(self, agent_type: str) -> str:
        """
        获取Agent的原始系统提示词（不含安全协议）
        
        Args:
            agent_type: Agent类型
            
        Returns:
            原始系统提示词文本
        """
        return self.get_system_prompt(agent_type, inject_security=False)
    
    def check_user_input(self, user_input: str) -> Tuple[bool, str]:
        """
        检查用户输入是否安全
        
        Args:
            user_input: 用户输入
            
        Returns:
            Tuple[bool, str]: (是否安全, 处理后的消息或安全回复)
        """
        if not self.enable_security or not self.security_guard:
            return True, user_input
        
        return check_security(user_input)
    
    def detect_threat(self, user_input: str) -> Tuple[bool, Optional[str]]:
        """
        检测用户输入是否包含安全威胁
        
        Args:
            user_input: 用户输入
            
        Returns:
            Tuple[bool, Optional[str]]: (是否检测到威胁, 威胁类型描述)
        """
        if not self.enable_security or not self.security_guard:
            return False, None
        
        return self.security_guard.detect_threat(user_input)
    
    def get_task_prompt(self, agent_type: str, task_name: str) -> str:
        """
        获取指定任务的提示词模板
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称，如 'build_world', 'write_chapter' 等
            
        Returns:
            任务提示词模板文本
        """
        # 优先使用自定义配置
        if agent_type in self.custom_prompts:
            custom_config = self.custom_prompts[agent_type]
            if task_name in custom_config:
                return custom_config[task_name]
        
        # 回退到默认配置
        if agent_type in DEFAULT_PROMPTS:
            return DEFAULT_PROMPTS[agent_type].get(task_name, "")
        
        return ""
    
    def render_prompt(self, agent_type: str, task_name: str, **variables) -> str:
        """
        渲染提示词模板，替换变量
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称
            **variables: 要替换的变量
            
        Returns:
            渲染后的提示词文本
        """
        template = self.get_task_prompt(agent_type, task_name)
        if not template:
            return ""
        
        result = template
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else "")
        
        return result
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的Agent类型及其信息
        
        Returns:
            Agent类型列表，每个包含name、description、tasks、task_count、has_custom等
        """
        agents = set(DEFAULT_PROMPTS.keys())
        # 过滤掉以_开头的元数据键（如_说明、_示例等）
        agents.update(k for k in self.custom_prompts.keys() if not k.startswith('_'))
        
        # Agent显示名称映射
        display_names = {
            'worldbuilder': '世界观构建器',
            'outliner': '大纲生成器',
            'chapter_writer': '章节写作器',
            'polisher': '内容润色器',
            'evaluator': '质量评估器',
            'continuous_writer': '无限续写器',
            'copilot': 'AI写作助手'
        }
        
        result = []
        for agent_type in sorted(agents):
            tasks = self.list_tasks(agent_type)
            description = ""
            # 尝试从系统提示词提取描述
            system_prompt = self.get_system_prompt_raw(agent_type)
            if system_prompt:
                # 取第一行或前100字符作为描述
                first_line = system_prompt.split('\n')[0].strip()
                description = first_line[:100] if len(first_line) > 100 else first_line
            
            # 检查是否有任何自定义提示词
            has_custom = agent_type in self.custom_prompts and bool(self.custom_prompts[agent_type])
            
            result.append({
                "name": agent_type,
                "display_name": display_names.get(agent_type, agent_type),
                "description": description,
                "tasks": tasks,
                "task_count": len(tasks),
                "has_custom": has_custom
            })
        
        return result
    
    def list_tasks(self, agent_type: str) -> List[Dict[str, Any]]:
        """
        列出指定Agent的所有可用任务
        
        Args:
            agent_type: Agent类型
            
        Returns:
            任务列表，每个包含name、display_name、description、prompt和is_custom
        """
        # 检查agent_type是否有效（不是元数据键）
        if agent_type.startswith('_'):
            return []
        
        tasks = set()
        
        if agent_type in DEFAULT_PROMPTS:
            tasks.update(k for k in DEFAULT_PROMPTS[agent_type].keys() if k != "system")
        
        if agent_type in self.custom_prompts:
            # 过滤掉以_开头的元数据键
            tasks.update(k for k in self.custom_prompts[agent_type].keys() if k != "system" and not k.startswith('_'))
        
        # 任务显示名称映射
        task_display_names = {
            'build_world': '构建世界观',
            'expand_setting': '扩展设定',
            'create_outline': '创建大纲',
            'refine_outline': '优化大纲',
            'write_chapter': '写作章节',
            'continue_writing': '续写内容',
            'polish_chapter': '润色章节',
            'evaluate_chapter': '评估章节',
            'write_first_chapter': '写作首章',
            'continue_story': '续写故事',
            'chat': '对话交互'
        }
        
        result = []
        for task_name in sorted(tasks):
            is_custom = self.has_custom_prompt(agent_type, task_name)
            prompt = self.get_task_prompt(agent_type, task_name)
            # 取前80字符作为描述
            description = prompt[:80] + "..." if len(prompt) > 80 else prompt
            
            result.append({
                "name": task_name,
                "display_name": task_display_names.get(task_name, task_name),
                "description": description,
                "prompt": prompt,
                "is_custom": is_custom
            })
        
        return result
    
    def has_custom_prompt(self, agent_type: str, task_name: str) -> bool:
        """
        检查是否有自定义提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称
            
        Returns:
            是否存在自定义提示词
        """
        return (
            agent_type in self.custom_prompts and
            task_name in self.custom_prompts[agent_type]
        )
    
    def get_default_prompt(self, agent_type: str, task_name: str) -> str:
        """
        获取默认提示词（忽略自定义配置）
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称
            
        Returns:
            默认提示词内容
        """
        if task_name == "system":
            return DEFAULT_PROMPTS.get(agent_type, {}).get("system", "")
        return DEFAULT_PROMPTS.get(agent_type, {}).get(task_name, "")
    
    def save_custom_prompt(self, agent_type: str, task_name: str, content: str) -> None:
        """
        保存自定义提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称（'system' 表示系统提示词）
            content: 提示词内容
        """
        if agent_type not in self.custom_prompts:
            self.custom_prompts[agent_type] = {}
        
        self.custom_prompts[agent_type][task_name] = content
        
        # 保存到文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.custom_prompts, f, ensure_ascii=False, indent=2)
            print(f"[PromptManager] 已保存自定义提示词: {agent_type}.{task_name}")
        except Exception as e:
            print(f"[PromptManager] 保存自定义提示词失败: {e}")
    
    def delete_custom_prompt(self, agent_type: str, task_name: Optional[str] = None) -> bool:
        """
        删除自定义提示词
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称，为None时删除整个Agent的配置
            
        Returns:
            是否删除成功
        """
        if agent_type not in self.custom_prompts:
            return False
        
        if task_name is None:
            del self.custom_prompts[agent_type]
        elif task_name in self.custom_prompts[agent_type]:
            del self.custom_prompts[agent_type][task_name]
            if not self.custom_prompts[agent_type]:
                del self.custom_prompts[agent_type]
        else:
            return False
        
        # 保存到文件
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.custom_prompts, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[PromptManager] 保存失败: {e}")
            return False
    
    def reset_to_default(self, agent_type: str, task_name: Optional[str] = None) -> None:
        """
        重置为默认提示词（删除自定义配置）
        
        Args:
            agent_type: Agent类型
            task_name: 任务名称，为None时重置整个Agent
        """
        self.delete_custom_prompt(agent_type, task_name)
    
    def export_all_prompts(self) -> Dict[str, Dict[str, str]]:
        """
        导出所有提示词（包括默认和自定义）
        
        Returns:
            完整的提示词配置字典
        """
        result = {}
        
        # 先添加默认配置
        for agent_type, prompts in DEFAULT_PROMPTS.items():
            result[agent_type] = dict(prompts)
        
        # 用自定义配置覆盖
        for agent_type, prompts in self.custom_prompts.items():
            if agent_type not in result:
                result[agent_type] = {}
            result[agent_type].update(prompts)
        
        return result
    
    def get_prompt_info(self, agent_type: str, task_name: str) -> Dict[str, Any]:
        """
        获取提示词的详细信息
        
        Returns:
            包含提示词内容、是否自定义、变量列表等信息
        """
        is_custom = (
            agent_type in self.custom_prompts and 
            task_name in self.custom_prompts[agent_type]
        )
        
        content = self.get_task_prompt(agent_type, task_name) if task_name != "system" else self.get_system_prompt(agent_type)
        
        # 提取变量
        import re
        variables = re.findall(r'\{(\w+)\}', content)
        
        return {
            "agent_type": agent_type,
            "task_name": task_name,
            "content": content,
            "is_custom": is_custom,
            "variables": list(set(variables)),
            "char_count": len(content)
        }


# ===== 全局单例 =====

_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """获取提示词管理器单例"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def reload_prompts() -> None:
    """重新加载提示词配置"""
    global _prompt_manager
    if _prompt_manager is not None:
        _prompt_manager.reload()
    else:
        _prompt_manager = PromptManager()


# ===== 便捷函数 =====

def get_system_prompt(agent_type: str) -> str:
    """获取Agent的系统提示词"""
    return get_prompt_manager().get_system_prompt(agent_type)


def get_task_prompt(agent_type: str, task_name: str) -> str:
    """获取任务提示词模板"""
    return get_prompt_manager().get_task_prompt(agent_type, task_name)


def render_prompt(agent_type: str, task_name: str, **variables) -> str:
    """渲染提示词模板"""
    return get_prompt_manager().render_prompt(agent_type, task_name, **variables)


def check_user_input_security(user_input: str) -> Tuple[bool, str]:
    """
    检查用户输入的安全性
    
    Args:
        user_input: 用户输入
        
    Returns:
        Tuple[bool, str]: (是否安全, 处理后的消息或安全回复)
    """
    return get_prompt_manager().check_user_input(user_input)


def get_security_response() -> str:
    """获取安全拦截的标准回复"""
    return SECURITY_RESPONSE