"""
Skills管理API路由模块

提供Skills的配置、启用/禁用、列表查询等功能
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...utils.atomic_write import atomic_write_json

logger = logging.getLogger(__name__)

router = APIRouter()


class SkillConfigRequest(BaseModel):
    """Skill配置请求"""
    skill_name: str
    enabled: bool


class SkillsConfigRequest(BaseModel):
    """批量Skills配置请求"""
    skills: Dict[str, bool]  # skill_name -> enabled


def _get_skills_config_path() -> Path:
    """获取Skills配置文件路径"""
    return Path(__file__).parent.parent.parent / "data" / "skills_config.json"


def _load_skills_config() -> Dict[str, Any]:
    """加载Skills配置"""
    config_path = _get_skills_config_path()
    
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Skills] 加载配置失败: {e}")
    
    return {"enabled_skills": {}}


def _save_skills_config(config: Dict[str, Any]) -> bool:
    """保存Skills配置"""
    config_path = _get_skills_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        old_content = config_path.read_text(encoding="utf-8") if config_path.exists() else None
        atomic_write_json(
            config_path,
            config,
            old_content=old_content,
            ensure_ascii=False,
            indent=2
        )
        logger.info(f"[Skills] 配置已保存: {config}")
        return True
    except Exception as e:
        logger.error(f"[Skills] 保存配置失败: {e}")
        return False


def _discover_skills() -> List[Dict[str, Any]]:
    """自动发现可用的Skills"""
    skills_dir = Path(__file__).parent.parent.parent.parent / "skills"
    discovered_skills = []
    
    if not skills_dir.exists():
        logger.warning(f"[Skills] Skills目录不存在: {skills_dir}")
        return []
    
    for skill_path in skills_dir.iterdir():
        if not skill_path.is_dir():
            continue
        
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            continue
        
        skill_name = skill_path.name
        
        # 读取SKILL.md获取描述
        try:
            content = skill_md.read_text(encoding="utf-8")
            lines = content.split("\n")
            description = ""
            for line in lines:
                if line.startswith("# "):
                    description = line[2:].strip()
                    break
            
            # 检查是否有服务文件
            scripts_dir = skill_path / "scripts"
            has_service = False
            if scripts_dir.exists():
                for f in scripts_dir.glob("*_service.py"):
                    has_service = True
                    break
            
            discovered_skills.append({
                "name": skill_name,
                "display_name": description or skill_name,
                "description": description,
                "path": str(skill_path),
                "available": has_service
            })
        except Exception as e:
            logger.warning(f"[Skills] 读取Skill信息失败 ({skill_name}): {e}")
    
    return discovered_skills


@router.get("/skills")
async def list_skills():
    """获取所有可用的Skills列表"""
    try:
        # 发现所有Skills
        all_skills = _discover_skills()
        
        # 加载配置
        config = _load_skills_config()
        enabled_skills = config.get("enabled_skills", {})
        
        # 合并配置信息
        for skill in all_skills:
            skill["enabled"] = enabled_skills.get(skill["name"], False)
        
        return JSONResponse({
            "success": True,
            "skills": all_skills,
            "count": len(all_skills)
        })
    except Exception as e:
        logger.error(f"[Skills] 获取Skills列表失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "skills": []
        })


@router.get("/skills/{skill_name}")
async def get_skill_info(skill_name: str):
    """获取指定Skill的详细信息"""
    try:
        skills_dir = Path(__file__).parent.parent.parent.parent / "skills"
        skill_path = skills_dir / skill_name
        
        if not skill_path.exists():
            return JSONResponse({
                "success": False,
                "error": f"Skill '{skill_name}' 不存在"
            })
        
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            return JSONResponse({
                "success": False,
                "error": f"Skill '{skill_name}' 缺少SKILL.md文件"
            })
        
        # 读取完整描述
        content = skill_md.read_text(encoding="utf-8")
        
        # 检查可用方法
        scripts_dir = skill_path / "scripts"
        methods = []
        if scripts_dir.exists():
            for f in scripts_dir.glob("*_service.py"):
                try:
                    # 简单解析获取方法列表
                    service_content = f.read_text(encoding="utf-8")
                    import re
                    method_pattern = r'def\s+(\w+)\s*\('
                    found_methods = re.findall(method_pattern, service_content)
                    methods.extend([m for m in found_methods if not m.startswith('_')])
                except Exception as e:
                    logger.warning(f"[Skills] 解析方法列表失败: {e}")
        
        # 加载配置
        config = _load_skills_config()
        enabled = config.get("enabled_skills", {}).get(skill_name, False)
        
        return JSONResponse({
            "success": True,
            "skill": {
                "name": skill_name,
                "description": content,
                "methods": methods,
                "enabled": enabled,
                "path": str(skill_path)
            }
        })
    except Exception as e:
        logger.error(f"[Skills] 获取Skill信息失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@router.post("/skills/toggle")
async def toggle_skill(request: SkillConfigRequest):
    """启用或禁用指定Skill"""
    try:
        config = _load_skills_config()
        
        if "enabled_skills" not in config:
            config["enabled_skills"] = {}
        
        config["enabled_skills"][request.skill_name] = request.enabled
        
        if _save_skills_config(config):
            return JSONResponse({
                "success": True,
                "message": f"Skill '{request.skill_name}' 已{'启用' if request.enabled else '禁用'}",
                "skill_name": request.skill_name,
                "enabled": request.enabled
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "保存配置失败"
            })
    except Exception as e:
        logger.error(f"[Skills] 切换Skill状态失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@router.post("/skills/batch-toggle")
async def batch_toggle_skills(request: SkillsConfigRequest):
    """批量启用或禁用Skills"""
    try:
        config = _load_skills_config()
        
        if "enabled_skills" not in config:
            config["enabled_skills"] = {}
        
        config["enabled_skills"].update(request.skills)
        
        if _save_skills_config(config):
            return JSONResponse({
                "success": True,
                "message": f"已更新 {len(request.skills)} 个Skills配置",
                "updated_skills": request.skills
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "保存配置失败"
            })
    except Exception as e:
        logger.error(f"[Skills] 批量更新Skills失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        })


@router.get("/skills/status")
async def get_skills_status():
    """获取Skills系统状态"""
    try:
        skills_dir = Path(__file__).parent.parent.parent.parent / "skills"
        
        if not skills_dir.exists():
            return JSONResponse({
                "available": False,
                "message": "Skills目录不存在",
                "skills_count": 0
            })
        
        all_skills = _discover_skills()
        config = _load_skills_config()
        enabled_count = sum(1 for s in all_skills if config.get("enabled_skills", {}).get(s["name"], False))
        
        return JSONResponse({
            "available": True,
            "message": f"Skills系统正常，共 {len(all_skills)} 个Skills，已启用 {enabled_count} 个",
            "skills_count": len(all_skills),
            "enabled_count": enabled_count,
            "skills_dir": str(skills_dir)
        })
    except Exception as e:
        logger.error(f"[Skills] 获取状态失败: {e}")
        return JSONResponse({
            "available": False,
            "message": f"获取状态失败: {str(e)}",
            "skills_count": 0
        })


@router.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """删除指定的Skill"""
    try:
        skills_dir = Path(__file__).parent.parent.parent.parent / "skills"
        skill_path = skills_dir / skill_name
        
        if not skill_path.exists():
            return JSONResponse({
                "success": False,
                "error": f"Skill '{skill_name}' 不存在"
            })
        
        # 删除目录及其所有内容
        import shutil
        shutil.rmtree(skill_path)
        
        # 从配置中移除
        config = _load_skills_config()
        if "enabled_skills" in config and skill_name in config["enabled_skills"]:
            del config["enabled_skills"][skill_name]
            _save_skills_config(config)
        
        logger.info(f"[Skills] 已删除Skill: {skill_name}")
        return JSONResponse({
            "success": True,
            "message": f"Skill '{skill_name}' 已删除"
        })
    except Exception as e:
        logger.error(f"[Skills] 删除Skill失败: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        })