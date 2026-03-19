# Coordinator 世界观保存问题修复方案

## 问题描述
用户要求创建世界观后，世界观内容没有保存到当前项目目录中。

## 根本原因
1. WorldManager 在 Coordinator 初始化时设置了 project_dir
2. 但在 create_novel 创建新项目后，没有更新 WorldManager 的 project_dir
3. 导致世界观保存到了错误的目录

## 修复方案

### 方案1：在创建项目后同步项目目录（推荐）

在 `create_novel` 方法中，创建项目后立即同步所有管理器的项目目录：

```python
async def create_novel(self, ...):
    # 创建项目
    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 使用 ProjectManager 创建项目
    pm_project = self.project_manager.create_project(
        name=f"{novel_type}小说_{project_id}",
        description=f"类型：{novel_type}"
    )
    
    # 切换到新项目
    self.project_manager.switch_project(pm_project.id)
    
    # 获取新项目的实际目录
    new_project_dir = self.project_manager._get_project_dir(pm_project.id)
    
    # 同步所有管理器的项目目录
    self.context_manager = ContextManager(new_project_dir)
    self.character_manager = CharacterManager(new_project_dir)
    self.world_manager = WorldManager(new_project_dir)
    
    # 更新 Coordinator 的 project_dir
    self.project_dir = new_project_dir
    
    # 继续后续流程...
```

### 方案2：使用 ProjectManager 统一管理路径

修改所有管理器，让它们从 ProjectManager 动态获取当前项目目录：

```python
class WorldManager:
    def __init__(self, project_manager=None):
        self.project_manager = project_manager
        self.world = None
        # ...
    
    def _get_project_dir(self) -> Optional[Path]:
        """动态获取当前项目目录"""
        if self.project_manager and self.project_manager.current_project_id:
            return self.project_manager._get_project_dir(
                self.project_manager.current_project_id
            )
        return None
    
    def _save_world(self) -> None:
        """保存世界观到当前项目"""
        project_dir = self._get_project_dir()
        if not project_dir:
            logger.warning("No active project, cannot save world")
            return
        
        project_dir.mkdir(parents=True, exist_ok=True)
        world_file = project_dir / "worldbuilding.json"
        # ... 保存逻辑
```

### 方案3：添加项目切换钩子

在 Coordinator 中添加项目切换方法：

```python
def switch_to_project(self, project_id: str) -> bool:
    """切换到指定项目并同步所有管理器"""
    if not self.project_manager.switch_project(project_id):
        return False
    
    # 获取新项目目录
    new_project_dir = self.project_manager._get_project_dir(project_id)
    
    # 重新初始化所有管理器
    self.context_manager = ContextManager(new_project_dir)
    self.character_manager = CharacterManager(new_project_dir)
    self.world_manager = WorldManager(new_project_dir)
    self.project_dir = new_project_dir
    
    # 重新加载检查点
    self._load_checkpoint()
    self._load_plot_thread_state()
    
    logger.info(f"Switched to project {project_id}")
    return True
```

## 推荐实施步骤

1. **立即修复**：在 `create_novel` 方法中添加项目目录同步（方案1）
2. **中期重构**：让所有管理器使用 ProjectManager 动态获取路径（方案2）
3. **长期优化**：统一项目切换接口（方案3）

## 测试验证

修复后需要验证：
1. 创建新小说时，世界观正确保存到新项目目录
2. 切换项目后，加载正确的世界观数据
3. 多个项目之间的世界观数据不会混淆
4. 所有文件（world, outline, characters）都保存到正确位置