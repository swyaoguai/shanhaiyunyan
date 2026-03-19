# Skill 系统集成技术方案

## 一、系统架构设计

### 1.1 整体架构

```
novel_agent/
├── skills/                          # Skills 管理系统
│   ├── __init__.py
│   ├── manager.py                   # Skill 管理器
│   ├── loader.py                    # Skill 加载器
│   ├── parser.py                    # SKILL.md 解析器
│   ├── registry.py                  # Skill 注册表
│   ├── executor.py                  # Skill 执行器
│   └── models.py                    # Skill 数据模型
├── skills_data/                     # Skills 存储目录
│   ├── official/                    # 官方 Skills
│   │   ├── novel-writing-assistant/
│   │   └── ...
│   └── custom/                      # 自定义 Skills
│       └── ...
├── prompts/                         # 现有提示词系统
│   └── skill_integration.md         # Skill 集成提示词
└── ...
```

### 1.2 核心组件

```python
# skills/models.py
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path
from enum import Enum

class SkillStatus(Enum):
    """Skill 状态"""
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"

@dataclass
class SkillMetadata:
    """Skill 元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    author: Optional[str] = None
    compatibility: Optional[List[str]] = None
    
@dataclass
class SkillReference:
    """引用文档"""
    path: Path
    title: str
    content: Optional[str] = None
    
@dataclass
class SkillScript:
    """脚本文件"""
    path: Path
    name: str
    executable: bool = True
    
@dataclass
class Skill:
    """完整的 Skill 对象"""
    metadata: SkillMetadata
    skill_path: Path
    content: str  # SKILL.md 主体内容
    references: List[SkillReference]
    scripts: List[SkillScript]
    assets: List[Path]
    status: SkillStatus
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'name': self.metadata.name,
            'description': self.metadata.description,
            'version': self.metadata.version,
            'status': self.status.value,
            'path': str(self.skill_path),
            'references': [str(r.path) for r in self.references],
            'scripts': [str(s.path) for s in self.scripts]
        }
```

## 二、核心功能实现

### 2.1 Skill 解析器

```python
# skills/parser.py
import re
import yaml
from pathlib import Path
from typing import Tuple, Dict

class SkillParser:
    """解析 SKILL.md 文件"""
    
    def __init__(self):
        self.frontmatter_pattern = re.compile(
            r'^---\s*\n(.*?)\n---\s*\n(.*)$',
            re.DOTALL
        )
    
    def parse_skill_file(self, skill_path: Path) -> Tuple[SkillMetadata, str]:
        """
        解析 SKILL.md 文件
        
        Returns:
            (metadata, content): 元数据和主体内容
        """
        skill_file = skill_path / "SKILL.md"
        
        if not skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_path}")
        
        with open(skill_file, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        # 解析 YAML frontmatter
        match = self.frontmatter_pattern.match(raw_content)
        if not match:
            raise ValueError("Invalid SKILL.md format: missing frontmatter")
        
        frontmatter_str = match.group(1)
        content = match.group(2)
        
        # 解析 YAML
        metadata_dict = yaml.safe_load(frontmatter_str)
        
        # 验证必需字段
        if 'name' not in metadata_dict:
            raise ValueError("Missing required field: name")
        if 'description' not in metadata_dict:
            raise ValueError("Missing required field: description")
        
        metadata = SkillMetadata(
            name=metadata_dict['name'],
            description=metadata_dict['description'],
            version=metadata_dict.get('version', '1.0.0'),
            author=metadata_dict.get('author'),
            compatibility=metadata_dict.get('compatibility')
        )
        
        return metadata, content
    
    def scan_references(self, skill_path: Path) -> List[SkillReference]:
        """扫描 references 目录"""
        references = []
        ref_dir = skill_path / "references"
        
        if ref_dir.exists():
            for ref_file in ref_dir.glob("*.md"):
                references.append(SkillReference(
                    path=ref_file,
                    title=ref_file.stem
                ))
        
        return references
    
    def scan_scripts(self, skill_path: Path) -> List[SkillScript]:
        """扫描 scripts 目录"""
        scripts = []
        script_dir = skill_path / "scripts"
        
        if script_dir.exists():
            for script_file in script_dir.glob("*"):
                if script_file.is_file():
                    scripts.append(SkillScript(
                        path=script_file,
                        name=script_file.name,
                        executable=script_file.suffix in ['.py', '.sh', '.js']
                    ))
        
        return scripts
    
    def scan_assets(self, skill_path: Path) -> List[Path]:
        """扫描 assets 目录"""
        assets = []
        asset_dir = skill_path / "assets"
        
        if asset_dir.exists():
            for asset_file in asset_dir.rglob("*"):
                if asset_file.is_file():
                    assets.append(asset_file)
        
        return assets
```

### 2.2 Skill 加载器

```python
# skills/loader.py
from pathlib import Path
from typing import Optional
from .parser import SkillParser
from .models import Skill, SkillStatus

class SkillLoader:
    """加载和验证 Skills"""
    
    def __init__(self):
        self.parser = SkillParser()
    
    def load_skill(self, skill_path: Path) -> Optional[Skill]:
        """
        加载单个 Skill
        
        Args:
            skill_path: Skill 目录路径
            
        Returns:
            Skill 对象，如果加载失败返回 None
        """
        try:
            # 解析 SKILL.md
            metadata, content = self.parser.parse_skill_file(skill_path)
            
            # 扫描资源
            references = self.parser.scan_references(skill_path)
            scripts = self.parser.scan_scripts(skill_path)
            assets = self.parser.scan_assets(skill_path)
            
            # 创建 Skill 对象
            skill = Skill(
                metadata=metadata,
                skill_path=skill_path,
                content=content,
                references=references,
                scripts=scripts,
                assets=assets,
                status=SkillStatus.INSTALLED
            )
            
            return skill
            
        except Exception as e:
            print(f"Failed to load skill from {skill_path}: {e}")
            return None
    
    def load_all_skills(self, base_path: Path) -> Dict[str, Skill]:
        """
        加载目录下所有 Skills
        
        Args:
            base_path: Skills 基础目录
            
        Returns:
            {skill_name: Skill} 字典
        """
        skills = {}
        
        # 扫描所有子目录
        for skill_dir in base_path.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                skill = self.load_skill(skill_dir)
                if skill:
                    skills[skill.metadata.name] = skill
        
        return skills
    
    def validate_skill(self, skill: Skill) -> Tuple[bool, List[str]]:
        """
        验证 Skill 完整性
        
        Returns:
            (is_valid, errors): 是否有效和错误列表
        """
        errors = []
        
        # 检查必需文件
        if not (skill.skill_path / "SKILL.md").exists():
            errors.append("Missing SKILL.md")
        
        # 检查元数据
        if not skill.metadata.name:
            errors.append("Missing skill name")
        if not skill.metadata.description:
            errors.append("Missing skill description")
        
        # 检查内容长度（建议 <500 行）
        if skill.content:
            lines = skill.content.count('\n')
            if lines > 500:
                errors.append(f"SKILL.md too long: {lines} lines (recommended <500)")
        
        return len(errors) == 0, errors
```

### 2.3 Skill 管理器

```python
# skills/manager.py
from pathlib import Path
from typing import Dict, List, Optional
from .loader import SkillLoader
from .registry import SkillRegistry
from .models import Skill, SkillStatus

class SkillManager:
    """Skill 管理器 - 核心管理类"""
    
    def __init__(self, skills_base_path: Path):
        self.skills_base_path = Path(skills_base_path)
        self.official_path = self.skills_base_path / "official"
        self.custom_path = self.skills_base_path / "custom"
        
        # 确保目录存在
        self.official_path.mkdir(parents=True, exist_ok=True)
        self.custom_path.mkdir(parents=True, exist_ok=True)
        
        self.loader = SkillLoader()
        self.registry = SkillRegistry()
        
        # 加载所有 Skills
        self.reload_all()
    
    def reload_all(self):
        """重新加载所有 Skills"""
        # 加载官方 Skills
        official_skills = self.loader.load_all_skills(self.official_path)
        for name, skill in official_skills.items():
            self.registry.register(name, skill, is_official=True)
        
        # 加载自定义 Skills
        custom_skills = self.loader.load_all_skills(self.custom_path)
        for name, skill in custom_skills.items():
            self.registry.register(name, skill, is_official=False)
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取指定 Skill"""
        return self.registry.get(name)
    
    def list_skills(self, status: Optional[SkillStatus] = None) -> List[Skill]:
        """列出所有 Skills"""
        return self.registry.list_all(status=status)
    
    def enable_skill(self, name: str) -> bool:
        """启用 Skill"""
        skill = self.registry.get(name)
        if skill:
            skill.status = SkillStatus.ENABLED
            return True
        return False
    
    def disable_skill(self, name: str) -> bool:
        """禁用 Skill"""
        skill = self.registry.get(name)
        if skill:
            skill.status = SkillStatus.DISABLED
            return True
        return False
    
    def install_skill(self, source_path: Path, is_official: bool = False) -> bool:
        """
        安装新 Skill
        
        Args:
            source_path: Skill 源目录
            is_official: 是否为官方 Skill
        """
        try:
            # 加载 Skill
            skill = self.loader.load_skill(source_path)
            if not skill:
                return False
            
            # 验证 Skill
            is_valid, errors = self.loader.validate_skill(skill)
            if not is_valid:
                print(f"Skill validation failed: {errors}")
                return False
            
            # 复制到目标目录
            target_path = self.official_path if is_official else self.custom_path
            target_skill_path = target_path / skill.metadata.name
            
            if target_skill_path.exists():
                print(f"Skill {skill.metadata.name} already exists")
                return False
            
            # 复制文件
            import shutil
            shutil.copytree(source_path, target_skill_path)
            
            # 重新加载
            skill = self.loader.load_skill(target_skill_path)
            if skill:
                self.registry.register(skill.metadata.name, skill, is_official)
                return True
            
            return False
            
        except Exception as e:
            print(f"Failed to install skill: {e}")
            return False
    
    def uninstall_skill(self, name: str) -> bool:
        """卸载 Skill"""
        skill = self.registry.get(name)
        if not skill:
            return False
        
        try:
            import shutil
            shutil.rmtree(skill.skill_path)
            self.registry.unregister(name)
            return True
        except Exception as e:
            print(f"Failed to uninstall skill: {e}")
            return False
    
    def get_enabled_skills_context(self) -> str:
        """
        获取所有启用的 Skills 的上下文
        用于注入到 LLM 提示词中
        """
        enabled_skills = self.registry.list_all(status=SkillStatus.ENABLED)
        
        if not enabled_skills:
            return ""
        
        context_parts = ["# Available Skills\n"]
        
        for skill in enabled_skills:
            context_parts.append(f"\n## {skill.metadata.name}")
            context_parts.append(f"**Description**: {skill.metadata.description}\n")
            
            # 只包含元数据，主体内容按需加载
            if skill.references:
                context_parts.append(f"**References**: {len(skill.references)} documents available")
            if skill.scripts:
                context_parts.append(f"**Scripts**: {len(skill.scripts)} tools available")
        
        return "\n".join(context_parts)
    
    def load_skill_full_context(self, name: str) -> Optional[str]:
        """
        加载 Skill 的完整上下文（包括主体内容）
        当 Skill 被触发时调用
        """
        skill = self.registry.get(name)
        if not skill or skill.status != SkillStatus.ENABLED:
            return None
        
        context_parts = [
            f"# {skill.metadata.name}",
            f"\n{skill.metadata.description}\n",
            "\n---\n",
            skill.content
        ]
        
        return "\n".join(context_parts)
    
    def load_skill_reference(self, skill_name: str, reference_name: str) -> Optional[str]:
        """
        按需加载 Skill 的引用文档
        """
        skill = self.registry.get(skill_name)
        if not skill:
            return None
        
        for ref in skill.references:
            if ref.title == reference_name or ref.path.stem == reference_name:
                if not ref.content:
                    # 懒加载
                    with open(ref.path, 'r', encoding='utf-8') as f:
                        ref.content = f.read()
                return ref.content
        
        return None
```

### 2.4 Skill 注册表

```python
# skills/registry.py
from typing import Dict, List, Optional
from .models import Skill, SkillStatus

class SkillRegistry:
    """Skill 注册表"""
    
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._official_skills: set = set()
    
    def register(self, name: str, skill: Skill, is_official: bool = False):
        """注册 Skill"""
        self._skills[name] = skill
        if is_official:
            self._official_skills.add(name)
    
    def unregister(self, name: str):
        """注销 Skill"""
        if name in self._skills:
            del self._skills[name]
        if name in self._official_skills:
            self._official_skills.remove(name)
    
    def get(self, name: str) -> Optional[Skill]:
        """获取 Skill"""
        return self._skills.get(name)
    
    def list_all(self, status: Optional[SkillStatus] = None) -> List[Skill]:
        """列出所有 Skills"""
        skills = list(self._skills.values())
        if status:
            skills = [s for s in skills if s.status == status]
        return skills
    
    def is_official(self, name: str) -> bool:
        """检查是否为官方 Skill"""
        return name in self._official_skills
    
    def search(self, keyword: str) -> List[Skill]:
        """搜索 Skills"""
        results = []
        keyword_lower = keyword.lower()
        
        for skill in self._skills.values():
            if (keyword_lower in skill.metadata.name.lower() or
                keyword_lower in skill.metadata.description.lower()):
                results.append(skill)
        
        return results
```

### 2.5 Skill 执行器

```python
# skills/executor.py
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

class SkillExecutor:
    """执行 Skill 中的脚本"""
    
    def execute_script(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        执行脚本
        
        Returns:
            {
                'success': bool,
                'stdout': str,
                'stderr': str,
                'returncode': int
            }
        """
        try:
            # 根据文件类型选择执行方式
            if script_path.suffix == '.py':
                cmd = ['python', str(script_path)]
            elif script_path.suffix == '.sh':
                cmd = ['bash', str(script_path)]
            elif script_path.suffix == '.js':
                cmd = ['node', str(script_path)]
            else:
                return {
                    'success': False,
                    'error': f'Unsupported script type: {script_path.suffix}'
                }
            
            if args:
                cmd.extend(args)
            
            # 执行
            result = subprocess.run(
                cmd,
                cwd=cwd or script_path.parent,
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Script execution timeout'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
```

## 三、集成到现有系统

### 3.1 在 LLM 适配器中集成

```python
# novel_agent/llm_adapters/base_with_skills.py
from pathlib import Path
from novel_agent.skills.manager import SkillManager

class LLMAdapterWithSkills:
    """带 Skill 支持的 LLM 适配器基类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 初始化 Skill 管理器
        skills_path = Path(__file__).parent.parent.parent / "skills_data"
        self.skill_manager = SkillManager(skills_path)
    
    def build_prompt_with_skills(self, user_message: str, **kwargs) -> str:
        """构建包含 Skills 的提示词"""
        
        # 1. 获取启用的 Skills 概览
        skills_context = self.skill_manager.get_enabled_skills_context()
        
        # 2. 检测是否需要触发特定 Skill
        triggered_skill = self._detect_skill_trigger(user_message)
        
        # 3. 构建完整提示词
        prompt_parts = []
        
        # 系统提示词
        prompt_parts.append(self._get_system_prompt())
        
        # Skills 概览（始终包含）
        if skills_context:
            prompt_parts.append(skills_context)
        
        # 触发的 Skill 完整内容
        if triggered_skill:
            skill_content = self.skill_manager.load_skill_full_context(triggered_skill)
            if skill_content:
                prompt_parts.append(f"\n# Active Skill\n{skill_content}")
        
        # 用户消息
        prompt_parts.append(f"\n# User Request\n{user_message}")
        
        return "\n\n".join(prompt_parts)
    
    def _detect_skill_trigger(self, message: str) -> Optional[str]:
        """
        检测用户消息是否触发某个 Skill
        
        简单实现：关键词匹配
        高级实现：可以用 LLM 判断
        """
        message_lower = message.lower()
        
        # 获取所有启用的 Skills
        enabled_skills = self.skill_manager.list_skills(status=SkillStatus.ENABLED)
        
        for skill in enabled_skills:
            # 检查 description 中的关键词
            desc_lower = skill.metadata.description.lower()
            
            # 简单的关键词匹配
            keywords = self._extract_keywords(desc_lower)
            for keyword in keywords:
                if keyword in message_lower:
                    return skill.metadata.name
        
        return None
    
    def _extract_keywords(self, description: str) -> List[str]:
        """从描述中提取关键词"""
        # 简单实现：提取常见触发词
        trigger_words = [
            '小说', '创作', '写作', '世界观', '大纲', '章节',
            '角色', '剧情', '设定', '构建', '规划'
        ]
        return [w for w in trigger_words if w in description]
```

### 3.2 在 Web API 中集成

```python
# novel_agent/web/skills_routes.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from novel_agent.skills.manager import SkillManager

router = APIRouter(prefix="/api/skills", tags=["skills"])

# 初始化 Skill 管理器
skills_path = Path(__file__).parent.parent.parent / "skills_data"
skill_manager = SkillManager(skills_path)

@router.get("/list")
async def list_skills():
    """列出所有 Skills"""
    skills = skill_manager.list_skills()
    return {
        "skills": [skill.to_dict() for skill in skills]
    }

@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """获取 Skill 详情"""
    skill = skill_manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return skill.to_dict()

@router.post("/{skill_name}/enable")
async def enable_skill(skill_name: str):
    """启用 Skill"""
    success = skill_manager.enable_skill(skill_name)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"message": f"Skill {skill_name} enabled"}

@router.post("/{skill_name}/disable")
async def disable_skill(skill_name: str):
    """禁用 Skill"""
    success = skill_manager.disable_skill(skill_name)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"message": f"Skill {skill_name} disabled"}

@router.post("/install")
async def install_skill(source_path: str, is_official: bool = False):
    """安装 Skill"""
    success = skill_manager.install_skill(Path(source_path), is_official)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to install skill")
    
    return {"message": "Skill installed successfully"}

@router.delete("/{skill_name}")
async def uninstall_skill(skill_name: str):
    """卸载 Skill"""
    success = skill_manager.uninstall_skill(skill_name)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return {"message": f"Skill {skill_name} uninstalled"}

@router.get("/{skill_name}/reference/{ref_name}")
async def get_skill_reference(skill_name: str, ref_name: str):
    """获取 Skill 的引用文档"""
    content = skill_manager.load_skill_reference(skill_name, ref_name)
    if not content:
        raise HTTPException(status_code=404, detail="Reference not found")
    
    return {"content": content}
```

## 四、使用示例

### 4.1 基本使用

```python
from pathlib import Path
from novel_agent.skills.manager import SkillManager

# 初始化
skills_path = Path("./skills_data")
manager = SkillManager(skills_path)

# 列出所有 Skills
skills = manager.list_skills()
for skill in skills:
    print(f"{skill.metadata.name}: {skill.metadata.description}")

# 启用 Skill
manager.enable_skill("novel-writing-assistant")

# 获取启用的 Skills 上下文
context = manager.get_enabled_skills_context()
print(context)

# 加载完整 Skill 内容
full_content = manager.load_skill_full_context("novel-writing-assistant")
print(full_content)

# 加载引用文档
ref_content = manager.load_skill_reference(
    "novel-writing-assistant",
    "worldbuilding-schema"
)
print(ref_content)
```

### 4.2 在创作流程中使用

```python
from novel_agent.llm_adapters.factory import create_adapter_with_skills

# 创建带 Skill 的适配器
adapter = create_adapter_with_skills("moonshot")

# 用户请求
user_message = "帮我设计一个修仙世界观"

# 构建提示词（自动检测并加载相关 Skill）
prompt = adapter.build_prompt_with_skills(user_message)

# 调用 LLM
response = adapter.generate(prompt)
print(response)
```

## 五、配置文件

### 5.1 Skills 配置

```yaml
# config/skills.yaml
skills:
  base_path: "./skills_data"
  
  auto_load:
    official: true
    custom: true
  
  default_enabled:
    - novel-writing-assistant
  
  trigger_detection:
    method: "keyword"  # keyword | llm | hybrid
    confidence_threshold: 0.7
  
  execution:
    script_timeout: 300
    max_reference_size: 1048576  # 1MB
```

### 5.2 加载配置

```python
# novel_agent/skills/config.py
import yaml
from pathlib import Path
from dataclasses import dataclass

@dataclass
class SkillsConfig:
    base_path: Path
    auto_load_official: bool
    auto_load_custom: bool
    default_enabled: List[str]
    trigger_method: str
    confidence_threshold: float
    script_timeout: int
    max_reference_size: int

def load_skills_config(config_path: Path) -> SkillsConfig:
    """加载 Skills 配置"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    skills_config = config['skills']
    
    return SkillsConfig(
        base_path=Path(skills_config['base_path']),
        auto_load_official=skills_config['auto_load']['official'],
        auto_load_custom=skills_config['auto_load']['custom'],
        default_enabled=skills_config['default_enabled'],
        trigger_method=skills_config['trigger_detection']['method'],
        confidence_threshold=skills_config['trigger_detection']['confidence_threshold'],
        script_timeout=skills_config['execution']['script_timeout'],
        max_reference_size=skills_config['execution']['max_reference_size']
    )
```

## 六、测试

### 6.1 单元测试

```python
# tests/test_skills.py
import pytest
from pathlib import Path
from novel_agent.skills.manager import SkillManager
from novel_agent.skills.models import SkillStatus

@pytest.fixture
def skill_manager(tmp_path):
    """创建临时 Skill 管理器"""
    return SkillManager(tmp_path)

def test_load_skill(skill_manager, tmp_path):
    """测试加载 Skill"""
    # 创建测试 Skill
    skill_path = tmp_path / "custom" / "test-skill"
    skill_path.mkdir(parents=True)
    
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

This is a test skill.
""")
    
    # 重新加载
    skill_manager.reload_all()
    
    # 验证
    skill = skill_manager.get_skill("test-skill")
    assert skill is not None
    assert skill.metadata.name == "test-skill"
    assert skill.status == SkillStatus.INSTALLED