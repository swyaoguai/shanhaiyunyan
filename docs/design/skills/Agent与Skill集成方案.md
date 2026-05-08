# Agent 与 Skill 集成方案

## 一、架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Skill Manager                         │
│              (全局单例，所有 Agent 共享)                  │
└─────────────────────────────────────────────────────────┘
                            ▲
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼──────┐  ┌────────▼────────┐
│  Main Agent    │  │ Sub Agent 1 │  │  Sub Agent 2    │
│  (主 Agent)    │  │ (子 Agent)  │  │  (子 Agent)     │
└────────────────┘  └─────────────┘  └─────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Skill Context │
                    │  (上下文传递)   │
                    └────────────────┘
```

### 1.2 核心原则

1. **全局共享**：SkillManager 作为全局单例，所有 Agent 共享
2. **上下文传递**：主 Agent 可以指定子 Agent 使用哪些 Skills
3. **权限控制**：可以限制某些 Agent 只能使用特定 Skills
4. **状态同步**：Skills 的启用/禁用状态全局同步

## 二、实现方案

### 2.1 全局 Skill 管理器

```python
# novel_agent/skills/global_manager.py
from typing import Optional
from .manager import SkillManager
from pathlib import Path

class GlobalSkillManager:
    """全局 Skill 管理器单例"""
    
    _instance: Optional[SkillManager] = None
    _initialized: bool = False
    
    @classmethod
    def initialize(cls, skills_base_path: Path):
        """初始化全局 Skill 管理器"""
        if not cls._initialized:
            cls._instance = SkillManager(skills_base_path)
            cls._initialized = True
    
    @classmethod
    def get_instance(cls) -> SkillManager:
        """获取全局 Skill 管理器实例"""
        if not cls._initialized:
            raise RuntimeError("GlobalSkillManager not initialized. Call initialize() first.")
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置（主要用于测试）"""
        cls._instance = None
        cls._initialized = False
```

### 2.2 Agent 基类扩展

```python
# novel_agent/agents/base_agent.py
from typing import List, Optional, Dict, Any
from novel_agent.skills.global_manager import GlobalSkillManager
from novel_agent.skills.models import Skill, SkillStatus

class BaseAgent:
    """支持 Skill 的 Agent 基类"""
    
    def __init__(
        self,
        name: str,
        allowed_skills: Optional[List[str]] = None,
        inherit_skills: bool = True,
        **kwargs
    ):
        """
        Args:
            name: Agent 名称
            allowed_skills: 允许使用的 Skills 列表（None 表示全部）
            inherit_skills: 是否继承父 Agent 的 Skills
        """
        self.name = name
        self.allowed_skills = allowed_skills
        self.inherit_skills = inherit_skills
        self._active_skills: List[str] = []
        
        # 获取全局 Skill 管理器
        self.skill_manager = GlobalSkillManager.get_instance()
    
    def get_available_skills(self) -> List[Skill]:
        """获取当前 Agent 可用的 Skills"""
        all_enabled = self.skill_manager.list_skills(status=SkillStatus.ENABLED)
        
        if self.allowed_skills is None:
            # 允许使用所有启用的 Skills
            return all_enabled
        else:
            # 只返回允许的 Skills
            return [s for s in all_enabled if s.metadata.name in self.allowed_skills]
    
    def activate_skill(self, skill_name: str) -> bool:
        """激活一个 Skill（用于当前任务）"""
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return False
        
        # 检查权限
        if self.allowed_skills and skill_name not in self.allowed_skills:
            print(f"Agent {self.name} is not allowed to use skill {skill_name}")
            return False
        
        if skill_name not in self._active_skills:
            self._active_skills.append(skill_name)
        
        return True
    
    def deactivate_skill(self, skill_name: str):
        """停用一个 Skill"""
        if skill_name in self._active_skills:
            self._active_skills.remove(skill_name)
    
    def get_active_skills(self) -> List[Skill]:
        """获取当前激活的 Skills"""
        return [
            self.skill_manager.get_skill(name)
            for name in self._active_skills
            if self.skill_manager.get_skill(name)
        ]
    
    def build_prompt_with_skills(
        self,
        base_prompt: str,
        user_message: str,
        include_all_available: bool = False
    ) -> str:
        """
        构建包含 Skills 的提示词
        
        Args:
            base_prompt: 基础提示词
            user_message: 用户消息
            include_all_available: 是否包含所有可用 Skills 的概览
        """
        prompt_parts = [base_prompt]
        
        # 1. 可用 Skills 概览（可选）
        if include_all_available:
            available_skills = self.get_available_skills()
            if available_skills:
                skills_overview = self._build_skills_overview(available_skills)
                prompt_parts.append(skills_overview)
        
        # 2. 激活的 Skills 完整内容
        active_skills = self.get_active_skills()
        for skill in active_skills:
            skill_content = self.skill_manager.load_skill_full_context(skill.metadata.name)
            if skill_content:
                prompt_parts.append(f"\n# Active Skill: {skill.metadata.name}\n{skill_content}")
        
        # 3. 用户消息
        prompt_parts.append(f"\n# User Request\n{user_message}")
        
        return "\n\n".join(prompt_parts)
    
    def _build_skills_overview(self, skills: List[Skill]) -> str:
        """构建 Skills 概览"""
        lines = ["# Available Skills\n"]
        for skill in skills:
            lines.append(f"- **{skill.metadata.name}**: {skill.metadata.description}")
        return "\n".join(lines)
    
    def detect_and_activate_skills(self, user_message: str) -> List[str]:
        """
        自动检测并激活相关 Skills
        
        Returns:
            激活的 Skill 名称列表
        """
        activated = []
        available_skills = self.get_available_skills()
        
        message_lower = user_message.lower()
        
        for skill in available_skills:
            # 简单的关键词匹配
            if self._should_activate_skill(skill, message_lower):
                if self.activate_skill(skill.metadata.name):
                    activated.append(skill.metadata.name)
        
        return activated
    
    def _should_activate_skill(self, skill: Skill, message_lower: str) -> bool:
        """判断是否应该激活 Skill"""
        # 从 description 中提取关键词
        desc_lower = skill.metadata.description.lower()
        
        # 常见触发词
        trigger_keywords = [
            '小说', '创作', '写作', '世界观', '大纲', '章节',
            '角色', '剧情', '设定', '构建', '规划', '撰写'
        ]
        
        # 检查是否匹配
        for keyword in trigger_keywords:
            if keyword in desc_lower and keyword in message_lower:
                return True
        
        return False
    
    def load_skill_reference(self, skill_name: str, reference_name: str) -> Optional[str]:
        """加载 Skill 的引用文档"""
        return self.skill_manager.load_skill_reference(skill_name, reference_name)
    
    def execute_skill_script(
        self,
        skill_name: str,
        script_name: str,
        args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """执行 Skill 中的脚本"""
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return {'success': False, 'error': 'Skill not found'}
        
        # 查找脚本
        script = None
        for s in skill.scripts:
            if s.name == script_name:
                script = s
                break
        
        if not script:
            return {'success': False, 'error': 'Script not found'}
        
        # 执行
        from novel_agent.skills.executor import SkillExecutor
        executor = SkillExecutor()
        return executor.execute_script(script.path, args)
```

### 2.3 子 Agent 实现

```python
# novel_agent/agents/sub_agent.py
from typing import Optional, List, Dict, Any
from .base_agent import BaseAgent

class SubAgent(BaseAgent):
    """子 Agent - 可以继承父 Agent 的 Skills"""
    
    def __init__(
        self,
        name: str,
        parent_agent: Optional[BaseAgent] = None,
        allowed_skills: Optional[List[str]] = None,
        inherit_skills: bool = True,
        **kwargs
    ):
        """
        Args:
            parent_agent: 父 Agent
            inherit_skills: 是否继承父 Agent 的激活 Skills
        """
        super().__init__(name, allowed_skills, inherit_skills, **kwargs)
        
        self.parent_agent = parent_agent
        
        # 继承父 Agent 的激活 Skills
        if inherit_skills and parent_agent:
            self._inherit_parent_skills()
    
    def _inherit_parent_skills(self):
        """继承父 Agent 的激活 Skills"""
        if self.parent_agent:
            parent_active = self.parent_agent.get_active_skills()
            for skill in parent_active:
                self.activate_skill(skill.metadata.name)
    
    def execute_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        执行任务
        
        Args:
            task: 任务描述
            context: 上下文信息（可包含 Skills 相关信息）
        """
        # 1. 检测并激活相关 Skills
        activated = self.detect_and_activate_skills(task)
        if activated:
            print(f"SubAgent {self.name} activated skills: {activated}")
        
        # 2. 构建提示词
        base_prompt = self._get_base_prompt()
        prompt = self.build_prompt_with_skills(
            base_prompt=base_prompt,
            user_message=task,
            include_all_available=True
        )
        
        # 3. 调用 LLM
        response = self._call_llm(prompt)
        
        # 4. 清理（可选）
        for skill_name in activated:
            self.deactivate_skill(skill_name)
        
        return response
    
    def _get_base_prompt(self) -> str:
        """获取基础提示词"""
        return f"You are {self.name}, a specialized sub-agent."
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（需要实现）"""
        # 这里应该调用实际的 LLM
        pass
```

### 2.4 主 Agent 实现

```python
# novel_agent/agents/main_agent.py
from typing import List, Dict, Any, Optional
from .base_agent import BaseAgent
from .sub_agent import SubAgent

class MainAgent(BaseAgent):
    """主 Agent - 可以创建和管理子 Agent"""
    
    def __init__(self, name: str = "MainAgent", **kwargs):
        super().__init__(name, **kwargs)
        self.sub_agents: Dict[str, SubAgent] = {}
    
    def create_sub_agent(
        self,
        name: str,
        allowed_skills: Optional[List[str]] = None,
        inherit_skills: bool = True
    ) -> SubAgent:
        """
        创建子 Agent
        
        Args:
            name: 子 Agent 名称
            allowed_skills: 允许使用的 Skills
            inherit_skills: 是否继承当前激活的 Skills
        """
        sub_agent = SubAgent(
            name=name,
            parent_agent=self,
            allowed_skills=allowed_skills,
            inherit_skills=inherit_skills
        )
        
        self.sub_agents[name] = sub_agent
        return sub_agent
    
    def delegate_task(
        self,
        sub_agent_name: str,
        task: str,
        skills: Optional[List[str]] = None
    ) -> str:
        """
        委派任务给子 Agent
        
        Args:
            sub_agent_name: 子 Agent 名称
            task: 任务描述
            skills: 指定使用的 Skills（可选）
        """
        # 获取或创建子 Agent
        if sub_agent_name not in self.sub_agents:
            self.create_sub_agent(sub_agent_name)
        
        sub_agent = self.sub_agents[sub_agent_name]
        
        # 如果指定了 Skills，临时激活
        temp_activated = []
        if skills:
            for skill_name in skills:
                if sub_agent.activate_skill(skill_name):
                    temp_activated.append(skill_name)
        
        # 执行任务
        result = sub_agent.execute_task(task)
        
        # 清理临时激活的 Skills
        for skill_name in temp_activated:
            sub_agent.deactivate_skill(skill_name)
        
        return result
    
    def execute_with_skills(
        self,
        task: str,
        skills: List[str],
        use_sub_agent: bool = False
    ) -> str:
        """
        使用指定 Skills 执行任务
        
        Args:
            task: 任务描述
            skills: 要使用的 Skills 列表
            use_sub_agent: 是否使用子 Agent 执行
        """
        # 激活 Skills
        for skill_name in skills:
            self.activate_skill(skill_name)
        
        if use_sub_agent:
            # 使用子 Agent 执行
            result = self.delegate_task("task_executor", task, skills)
        else:
            # 主 Agent 直接执行
            base_prompt = self._get_base_prompt()
            prompt = self.build_prompt_with_skills(
                base_prompt=base_prompt,
                user_message=task,
                include_all_available=False
            )
            result = self._call_llm(prompt)
        
        # 清理
        for skill_name in skills:
            self.deactivate_skill(skill_name)
        
        return result
    
    def _get_base_prompt(self) -> str:
        """获取基础提示词"""
        return "You are the main agent coordinating novel writing tasks."
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（需要实现）"""
        pass
```

## 三、使用示例

### 3.1 初始化

```python
# app.py 或 __init__.py
from pathlib import Path
from novel_agent.skills.global_manager import GlobalSkillManager
from novel_agent.agents.main_agent import MainAgent

# 1. 初始化全局 Skill 管理器
skills_path = Path("./skills_data")
GlobalSkillManager.initialize(skills_path)

# 2. 启用需要的 Skills
skill_manager = GlobalSkillManager.get_instance()
skill_manager.enable_skill("novel-writing-assistant")

# 3. 创建主 Agent
main_agent = MainAgent(name="NovelWritingAgent")
```

### 3.2 主 Agent 使用 Skills

```python
# 主 Agent 直接使用 Skill
task = "帮我设计一个修仙世界观"

# 方式1：自动检测并激活
activated = main_agent.detect_and_activate_skills(task)
print(f"Activated skills: {activated}")

# 方式2：手动指定
result = main_agent.execute_with_skills(
    task=task,
    skills=["novel-writing-assistant"],
    use_sub_agent=False
)
```

### 3.3 子 Agent 使用 Skills

```python
# 创建子 Agent（继承主 Agent 的 Skills）
sub_agent = main_agent.create_sub_agent(
    name="WorldBuilder",
    inherit_skills=True
)

# 子 Agent 执行任务
result = sub_agent.execute_task("创建力量体系")

# 或者通过主 Agent 委派
result = main_agent.delegate_task(
    sub_agent_name="WorldBuilder",
    task="创建力量体系",
    skills=["novel-writing-assistant"]
)
```

### 3.4 限制子 Agent 的 Skills

```python
# 创建只能使用特定 Skills 的子 Agent
restricted_agent = main_agent.create_sub_agent(
    name="ChapterWriter",
    allowed_skills=["novel-writing-assistant"],  # 只能用这个
    inherit_skills=False  # 不继承父 Agent 的 Skills
)

# 尝试使用其他 Skill 会失败
restricted_agent.activate_skill("other-skill")  # 返回 False
```

### 3.5 多层子 Agent

```python
# 主 Agent
main_agent = MainAgent("Main")
main_agent.activate_skill("novel-writing-assistant")

# 一级子 Agent
level1_agent = main_agent.create_sub_agent("Level1", inherit_skills=True)

# 二级子 Agent（继承一级子 Agent 的 Skills）
level2_agent = SubAgent(
    name="Level2",
    parent_agent=level1_agent,
    inherit_skills=True
)

# Level2 也可以使用 novel-writing-assistant
result = level2_agent.execute_task("写第1章")
```

## 四、高级功能

### 4.1 Skill 权限管理

```python
# novel_agent/skills/permissions.py
from typing import Dict, List, Set
from enum import Enum

class SkillPermission(Enum):
    """Skill 权限级别"""
    READ = "read"          # 只能读取 Skill 内容
    EXECUTE = "execute"    # 可以执行 Skill 脚本
    FULL = "full"         # 完全访问

class SkillPermissionManager:
    """Skill 权限管理器"""
    
    def __init__(self):
        self._agent_permissions: Dict[str, Dict[str, SkillPermission]] = {}
    
    def grant_permission(
        self,
        agent_name: str,
        skill_name: str,
        permission: SkillPermission
    ):
        """授予权限"""
        if agent_name not in self._agent_permissions:
            self._agent_permissions[agent_name] = {}
        
        self._agent_permissions[agent_name][skill_name] = permission
    
    def check_permission(
        self,
        agent_name: str,
        skill_name: str,
        required: SkillPermission
    ) -> bool:
        """检查权限"""
        if agent_name not in self._agent_permissions:
            return False
        
        if skill_name not in self._agent_permissions[agent_name]:
            return False
        
        granted = self._agent_permissions[agent_name][skill_name]
        
        # FULL 权限包含所有
        if granted == SkillPermission.FULL:
            return True
        
        # EXECUTE 权限包含 READ
        if granted == SkillPermission.EXECUTE and required == SkillPermission.READ:
            return True
        
        return granted == required
```

### 4.2 Skill 使用统计

```python
# novel_agent/skills/statistics.py
from typing import Dict
from datetime import datetime
from collections import defaultdict

class SkillStatistics:
    """Skill 使用统计"""
    
    def __init__(self):
        self._usage_count: Dict[str, int] = defaultdict(int)
        self._agent_usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._last_used: Dict[str, datetime] = {}
    
    def record_usage(self, agent_name: str, skill_name: str):
        """记录使用"""
        self._usage_count[skill_name] += 1
        self._agent_usage[agent_name][skill_name] += 1
        self._last_used[skill_name] = datetime.now()
    
    def get_most_used_skills(self, top_n: int = 10) -> List[tuple]:
        """获取最常用的 Skills"""
        sorted_skills = sorted(
            self._usage_count.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_skills[:top_n]
    
    def get_agent_usage(self, agent_name: str) -> Dict[str, int]:
        """获取 Agent 的 Skill 使用情况"""
        return dict(self._agent_usage[agent_name])
```

### 4.3 Skill 缓存

```python
# novel_agent/skills/cache.py
from typing import Optional, Dict
from datetime import datetime, timedelta

class SkillCache:
    """Skill 内容缓存"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, tuple] = {}  # {key: (content, timestamp)}
        self.ttl = timedelta(seconds=ttl_seconds)
    
    def get(self, key: str) -> Optional[str]:
        """获取缓存"""
        if key not in self._cache:
            return None
        
        content, timestamp = self._cache[key]
        
        # 检查是否过期
        if datetime.now() - timestamp > self.ttl:
            del self._cache[key]
            return None
        
        return content
    
    def set(self, key: str, content: str):
        """设置缓存"""
        self._cache[key] = (content, datetime.now())
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
```

## 五、完整示例

```python
# example_usage.py
from pathlib import Path
from novel_agent.skills.global_manager import GlobalSkillManager
from novel_agent.agents.main_agent import MainAgent

def main():
    # 1. 初始化
    skills_path = Path("./skills_data")
    GlobalSkillManager.initialize(skills_path)
    
    skill_manager = GlobalSkillManager.get_instance()
    skill_manager.enable_skill("novel-writing-assistant")
    
    # 2. 创建主 Agent
    main_agent = MainAgent("NovelAgent")
    
    # 3. 场景1：主 Agent 使用 Skill
    print("=== 场景1：主 Agent 创作世界观 ===")
    result1 = main_agent.execute_with_skills(
        task="设计一个修仙世界观",
        skills=["novel-writing-assistant"]
    )
    print(result1)
    
    # 4. 场景2：创建子 Agent 处理章节
    print("\n=== 场景2：子 Agent 撰写章节 ===")
    chapter_writer = main_agent.create_sub_agent(
        name="ChapterWriter",
        inherit_skills=True
    )
    result2 = chapter_writer.execute_task("写第1章")
    print(result2)
    
    # 5. 场景3：委派任务给子 Agent
    print("\n=== 场景3：委派大纲规划任务 ===")
    result3 = main_agent.delegate_task(
        sub_agent_name="OutlinePlanner",
        task="规划前10章大纲",
        skills=["novel-writing-assistant"]
    )
    print(result3)
    
    # 6. 场景4：多个子 Agent 协作
    print("\n=== 场景4：多 Agent 协作 ===")
    
    # 世界观构建 Agent
    world_builder = main_agent.create_sub_agent("WorldBuilder")
    world_result = world_builder.execute_task("构建世界观")
    
    # 角色创建 Agent
    character_creator = main_agent.create_sub_agent("CharacterCreator")
    char_result = character_creator.execute_task("创建主角")
    
    # 大纲规划 Agent
    outliner = main_agent.create_sub_agent("Outliner")
    outline_result = outliner.execute_task("规划大纲")
    
    # 章节撰写 Agent
    writer = main_agent.create_sub_agent("Writer")
    chapter_result = writer.execute_task("写第1章")
    
    print("协作完成！")

if __name__ == "__main__":
    main()
```

## 六、总结

### 优势

✅ **全局共享**：所有 Agent 共享同一个 SkillManager，避免重复加载  
✅ **灵活继承**：子 Agent 可以继承父 Agent 的 Skills  
✅ **权限控制**：可以限制特定 Agent 只能使用特定 Skills  
✅ **按需激活**：Skills 可以动态激活和停用  
✅ **上下文传递**：Skills 的状态在 Agent 之间传递  
✅ **统计监控**：可以追踪 Skills 的使用情况  

### 使用场景

1. **主 Agent 直接使用**：处理简单任务
2. **子 Agent 继承使用**：复杂任务分解
3. **多 Agent 协作**：不同 Agent 使用不同 Skills
4. **权限隔离**：限制某些 Agent 的 Skill 访问

这个方案让你的整个 Agent 系统都能无缝使用 Skills！