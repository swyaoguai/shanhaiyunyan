# 测试失败问题分析报告

## 一、已修复的问题

### 1. test_coordinator_trends.py (2个测试)
**问题**: `fake_use_skill` 函数签名缺少 `self` 参数

**根因**: monkeypatch 时 `fake_use_skill(skill_name, method, **kwargs)` 被绑定到实例方法，但实例方法第一个参数是 `self`，导致调用时传递了3个参数但函数只接受2个。

```python
# 修复前
def fake_use_skill(skill_name: str, method: str, **kwargs):

# 修复后
def fake_use_skill(self, skill_name: str, method: str, **kwargs):
```

**涉及测试**:
- `test_coordinator_search_trends_balances_multi_platforms`
- `test_coordinator_search_trends_fallbacks_to_legacy_tool_name`

---

### 2. test_supervised_collab_foundation.py (9个测试)

#### 2.1 递归溢出死循环
**问题**: `ProjectReadyTaskExecutor.execute_next_batch` 循环调用自身导致栈溢出

**根因**: `execute_next_batch` 调用 `coordinator._execute_project_ready_batch`，而 `_execute_project_ready_batch` 又创建新的 executor 并调用 `execute_next_batch`，形成无限递归。

```python
# 修复: execute_next_batch 直接调用自身的 _execute_project_ready_batch
async def execute_next_batch(self, ...):
    return await self._execute_project_ready_batch(...)  # 不再经过 coordinator
```

#### 2.2 缺少 `chapter_tasks_executed` 字段
**问题**: 返回结果缺少 `chapter_tasks_executed` 字段，测试断言失败

**根因**: `_execute_project_ready_batch` 返回字典未包含该字段

**修复**: 在返回字典中添加 `"chapter_tasks_executed": chapter_tasks_executed`

#### 2.3 `summary_orchestrate` 任务缺少 `chapters` 上下文
**问题**: `ContextValidationError: Missing required context keys: chapters`

**根因**: `_execute_summary_orchestrate` 未传递 `chapters` 到 context，但 `routing_policy` 的 `RouteRule` 要求 `summary_orchestrate` 必须有 `chapters` 字段

**修复**: 添加 `outline_rows = coordinator.project_manager.load_project_data("outline")` 并传入 context

#### 2.4 `_persist_project_stage_summary_result` 参数错误
**问题**: `TypeError: ... takes 2 positional arguments but 3 were given`

**根因**: 调用时传递了2个参数 `run_result.get("result", {})` 和 `run_result.get("result", {}).get("summary", "")`，但方法只接受1个参数

**修复**: 移除多余的 `summary` 参数

---

### 3. test_router_intents.py (2个测试)

#### 3.1 缺少 "角色卡" token
**问题**: `"请帮我生成主角角色卡：林渡，少年剑修，宗门遗孤"` 返回 `general_chat`

**根因**: mock fixture 的 token 列表缺少 `"角色卡"`

**修复**: 在条件判断中添加 `"角色卡"` token

#### 3.2 测试期望旧的规则回退行为
**问题**: `test_intent_analysis_falls_back_to_rules_when_llm_payload_invalid` 期望 LLM 失败时回退到规则

**根因**: 用户已明确要求彻底废弃规则兜底，但测试仍期望旧行为

**修复**: 改为 `test_intent_analysis_raises_when_llm_returns_invalid_json`，期望抛出 RuntimeError

---

### 4. test_plot_thread_state_machine.py (1个测试)

#### 4.1 `__init__` 参数顺序错误导致快照恢复失败
**问题**: `PlotThreadStateMachine(snapshot)` 将 dict 作为 `project_dir` 传入，`state` 参数为 None

**根因**: `__init__(self, project_dir=None, state=None)` — 当传入单个 dict 时，被当作 `project_dir`，真正的 `state` 却成了 None

```python
# 修复: 检测并兼容 dict 作为 state
def __init__(self, project_dir=None, state=None):
    if isinstance(project_dir, dict):
        state = project_dir
        project_dir = None
    ...
```

---

### 5. test_library_service.py (2个测试)

#### 5.1 `_apply_obsidian_link_metadata` 链接提取逻辑错误
**问题**: `links_out` 只从 `relations` 提取，忽略了 `links_out` 自身和文本内容中的 `[[...]]` 链接

**根因**: 原逻辑只从 `entry.relations` 获取链接，即使 `entry.links_out` 有值也不使用

```python
# 原逻辑
links = list(dict.fromkeys([str(link).strip() for link in (entry.relations or []) if str(link).strip()]))
if not links:  # 只有 relations 为空时才从文本提取
    links = re.findall(r"\[\[([^\]]+)\]\]", text)
```

**修复**: 合并 `relations` + `links_out` + `text_links` 三者一起去重

---

## 二、仍存在问题的测试

### 1. test_chapter_summary_entries_roundtrip_as_knowledge_nodes
**问题**: `vector_text` 缺少前缀 "第3章摘要 "

**根因**: 测试期望格式为 `"第3章摘要 和[[林渡]]..."`，但实际只包含 `"和[[林渡]]..."`。可能和 `content_structured.vector_text` 被写入但未被正确使用有关。

---

### 2. test_characters_post_preserves_structured_fields
**问题**: `IndexError: list index out of range` — `payload["data"][0]` 不存在

**根因**: POST 字符数据后，GET 请求返回的 `data` 为空列表。可能是因为：
- 字符数据保存后没有正确索引
- 或者 GET API 读取的位置不正确

---

### 3. test_chat_routing_execution.py (多个测试)
**问题**: 测试挂起/超时

**根因**: 测试中 mock 了 `send_task` 方法，但 `CommunicatorAgent` 可能通过其他方式（如 `send_task_stream`）发送消息，导致 mock 未生效，测试在等待实际的网络调用超时。

---

## 三、编码问题说明

在测试输出中看到大量 `[?]`, `[[ֶ]]`, `[[]]` 等乱码，这是 **Windows 终端 GBK 编码** 与 **Python 源代码 UTF-8** 之间的显示冲突，并非实际数据损坏。

验证方法：
```python
# 写入文件后以 UTF-8 读取，数据是正确的
s = '[[林渡]]'
p.write_text(s, encoding='utf-8')
content = p.read_text(encoding='utf-8')
# content == s 为 True，说明数据未损坏
```

修复后的代码在保存/读取 JSON 时使用 UTF-8 编码，数据完整性有保证。

---

## 四、修复文件汇总

| 文件 | 修改内容 |
|------|----------|
| `novel_agent/tests/test_coordinator_trends.py` | 添加 `self` 参数到两个 `fake_use_skill` 函数 |
| `novel_agent/workflow/project_ready.py` | 修复递归调用、添加字段、添加上下文、修正参数 |
| `novel_agent/tests/test_router_intents.py` | 添加 token、修改测试名称/断言 |
| `novel_agent/workflow/plot_thread_state.py` | `__init__` 兼容 dict 形式的 state 参数 |
| `novel_agent/library_service.py` | 重写 `_apply_obsidian_link_metadata` 链接提取逻辑 |