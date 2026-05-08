"""
配置验证模块

在应用启动时验证必需的配置项，提供清晰的错误提示。
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json

from ..utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """配置验证错误"""
    pass


class ConfigValidator:
    """配置验证器"""

    def __init__(self, app_dir: Optional[Path] = None, project_root: Optional[Path] = None):
        self.app_dir = app_dir or Path(__file__).resolve().parent.parent
        self.project_root = project_root or self.app_dir.parent
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        验证所有配置

        Returns:
            (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # 验证各项配置
        self._validate_paths()
        self._validate_knowledge_base()
        self._validate_llm_config()
        self._validate_skills()
        self._validate_port()

        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings

    def _validate_paths(self):
        """验证必需的路径"""
        from ..config import config

        # 检查输出目录
        if not config.paths.output_dir.exists():
            try:
                config.paths.output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建输出目录: {config.paths.output_dir}")
            except Exception as e:
                self.errors.append(f"无法创建输出目录 {config.paths.output_dir}: {e}")

        # 检查数据目录
        data_dir = self.app_dir / "data"
        if not data_dir.exists():
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建数据目录: {data_dir}")
            except Exception as e:
                self.errors.append(f"无法创建数据目录 {data_dir}: {e}")

    def _validate_knowledge_base(self):
        """验证知识库配置"""
        config_path = self.app_dir / "data" / "knowledge_base_config.json"

        if not config_path.exists():
            self.warnings.append(
                "知识库配置文件不存在。知识库功能将不可用。"
                f"请创建 {config_path} 并配置 SiliconFlow API Key。"
            )
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                kb_config = json.load(f)

            # 检查 API Key
            api_key = kb_config.get("siliconflow_api_key", "")
            if not api_key or api_key == "your_siliconflow_api_key_here":
                self.warnings.append(
                    "知识库 API Key 未配置。知识库功能将不可用。"
                    f"请在 {config_path} 中配置有效的 SiliconFlow API Key。"
                )

            # 检查 ChromaDB
            try:
                import chromadb
                logger.info("ChromaDB 可用")
            except ImportError:
                self.warnings.append(
                    "ChromaDB 未安装。知识库功能将不可用。"
                    "请运行: pip install chromadb"
                )

        except json.JSONDecodeError as e:
            self.errors.append(f"知识库配置文件格式错误: {e}")
        except Exception as e:
            self.warnings.append(f"读取知识库配置失败: {e}")

    def _validate_llm_config(self):
        """验证 LLM 配置"""
        # 不验证 API Key，因为用户需要在 Web UI 中配置
        # API Key 可以在程序启动后通过设置页面配置
        pass

    def _validate_skills(self):
        """验证 Skill 配置"""
        skills_dir = self.project_root / "skills"

        if not skills_dir.exists():
            self.warnings.append(
                f"Skills 目录不存在: {skills_dir}。Skill 功能将不可用。"
            )
            return

        # 检查可用的 Skills
        available_skills = []
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                available_skills.append(skill_dir.name)

                # 检查配置文件
                config_file = skill_dir / "config.json"
                example_config = skill_dir / "config.example.json"

                if not config_file.exists() and example_config.exists():
                    if self._bootstrap_config_from_example(
                        config_file=config_file,
                        example_config=example_config,
                        display_name=f"Skill '{skill_dir.name}'"
                    ):
                        continue

                if not config_file.exists() and example_config.exists():
                    self.warnings.append(
                        f"Skill '{skill_dir.name}' 配置文件不存在。"
                        f"请复制 {example_config} 到 {config_file} 并配置。"
                    )
                elif not config_file.exists():
                    self.warnings.append(
                        f"Skill '{skill_dir.name}' 缺少配置文件，且未提供 config.example.json 模板。"
                    )

        if available_skills:
            logger.info(f"发现 {len(available_skills)} 个 Skills: {', '.join(available_skills)}")
        else:
            self.warnings.append("未发现可用的 Skills。")

    def _validate_port(self):
        """验证端口配置"""
        import socket
        from ..config import config

        # 获取配置的端口
        port = config.server.port

        # 检查端口是否被占用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
        except OSError:
            self.warnings.append(
                f"端口 {port} 已被占用。系统将自动尝试其他端口。"
            )

    def _bootstrap_config_from_example(
        self,
        config_file: Path,
        example_config: Path,
        display_name: str,
    ) -> bool:
        """当配置缺失时，尝试从示例文件自动创建。"""
        try:
            content = example_config.read_text(encoding="utf-8")
            atomic_write_text(config_file, content)
            self.warnings.append(
                f"{display_name} 配置文件缺失，已根据示例自动创建: {config_file}。"
                "请按需补充真实配置。"
            )
            logger.info(f"{display_name} 默认配置已创建: {config_file}")
            return True
        except Exception as e:
            self.warnings.append(
                f"{display_name} 配置文件不存在，且自动创建失败。"
                f"请复制 {example_config} 到 {config_file} 并配置。错误: {e}"
            )
            return False


def validate_startup_config() -> bool:
    """
    验证启动配置

    Returns:
        配置是否有效

    Raises:
        ConfigValidationError: 配置验证失败
    """
    validator = ConfigValidator()
    is_valid, errors, warnings = validator.validate_all()

    # 输出警告
    for warning in warnings:
        logger.warning(f"⚠️  {warning}")

    # 输出错误
    if errors:
        logger.error("❌ 配置验证失败:")
        for error in errors:
            logger.error(f"  - {error}")
        raise ConfigValidationError(
            f"配置验证失败，发现 {len(errors)} 个错误。请检查日志。"
        )

    if warnings:
        logger.info(f"✓ 配置验证通过（{len(warnings)} 个警告）")
    else:
        logger.info("✓ 配置验证通过")

    return is_valid


def print_startup_info():
    """打印启动信息"""
    from ..config import config
    import sys

    try:
        print("\n" + "="*60)
        print("🚀 山海·云烟")
        print("="*60)
        print(f"版本: v1.0")
        print(f"Python: {sys.version.split()[0]}")
        print(f"端口: {config.server.port}")
        print(f"输出目录: {config.paths.output_dir}")
        print("="*60 + "\n")
    except UnicodeEncodeError:
        # Windows 控制台编码问题的回退方案
        print("\n" + "="*60)
        print("山海·云烟 v1.0")
        print("="*60)
        print(f"Python: {sys.version.split()[0]}")
        print(f"Port: {config.server.port}")
        print(f"Output: {config.paths.output_dir}")
        print("="*60 + "\n")
