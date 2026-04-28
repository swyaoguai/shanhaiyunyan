# Deep Interview Spec: library-auto-save-toggle

## Metadata
- Profile: standard
- Rounds: 5
- Final ambiguity: 0.18
- Threshold: 0.20
- Context type: brownfield
- Context snapshot: `.omx/context/library-auto-save-gating-20260416T234654Z.md`
- Transcript: `.omx/interviews/library-auto-save-toggle-20260417T000300Z.md`

## Clarity Breakdown
| Dimension | Score |
|---|---:|
| Intent Clarity | 0.94 |
| Outcome Clarity | 0.88 |
| Scope Clarity | 0.88 |
| Constraint Clarity | 0.72 |
| Success Criteria Clarity | 0.70 |
| Context Clarity | 0.96 |

## Intent
用户希望把“是否自动创建/保存文件”的行为从当前分散在不同生成链路中的隐式规则，提升为聊天界面中一个明确、可控、可预期的开关，并避免 LLM 或模糊规则在自定义分类上擅自落盘。

## Desired Outcome
在聊天界面新增一个“自动保存/自动创建文件”开关：
- 开启时：对内置资料库分类及章节正文等受支持输出，生成后自动创建/写入对应文件。
- 关闭时：保留当前系统里原本就存在的内置自动落盘行为，但不要把新的自动保存能力扩展到本来不自动保存的内容。
- 对非内置/用户自定义分类：无论开关状态如何，都不能直接自动存，必须先由用户手动选择分类。

## In-Scope
- 聊天界面可见、可操作的自动保存开关
- 对“内置资料库分类”的识别与范围校验
- 对现有角色卡 draft/save 行为与新开关的交互定义
- 对章节正文等文件型输出与开关的交互定义
- 对用户自定义分类的保护性分流（要求手选）

## Out-of-Scope / Non-goals
- 不把“开关关闭”定义为全局禁止一切自动写文件
- 不允许非内置/用户自定义分类由 LLM 自动猜测后直接落盘
- 不在 deep-interview 阶段直接实现代码修改

## Decision Boundaries
OMX may decide without further confirmation:
- 内置分类名单应从后端实际支持的 builtin project-data 类型中提取/校验，而不是只依赖前端文案。
- 开关默认文案、提示文案、辅助说明可由实现阶段决定。
- 关闭开关时，当前已经存在的 built-in auto-persist 流程可以继续保留。

OMX must NOT decide without confirmation:
- 不能把非内置/用户自定义分类纳入自动保存。
- 不能让 LLM 自行选择某个自定义分类并自动落盘。
- 不能把“关闭开关”改造成全局只草稿不落盘。

## Constraints
- 需要检查并区分“内置资料库分类”与“用户自定义分类/aux-memory 分类”的真实代码来源。
- 现有 built-in project-data 后端路径由 `project_manager.get_project_data_path()` 限定。
- 自定义知识分类当前并非统一后端 project-data 类型，存在前端 localStorage 分类与 aux-memory 分类两套来源。

## Testable Acceptance Criteria
1. 聊天界面存在明确开关，用于控制“新增的自动保存能力”。
2. 开关开启时，内置分类相关生成结果可自动保存到对应后端文件位置。
3. 开关开启时，章节正文等受支持输出可自动写入对应文件位置。
4. 若目标属于非内置/用户自定义分类，系统不得自动保存，而必须要求用户手动选择分类。
5. 开关关闭时，当前原本已自动落盘的内置链路保持原行为；新引入的自动保存能力不应生效。
6. 角色卡等当前需要显式保存的链路，在开关关闭时不得被意外升级为自动落盘。

## Assumptions Exposed + Resolutions
- Assumption: “资料库分类”是统一的一套后端分类。  
  Resolution: 否。代码显示 builtin project-data、自定义知识分类、aux-memory 分类并不统一。
- Assumption: 目前所有生成内容都不会自动保存。  
  Resolution: 否。世界观、大纲、事件线、细纲、章纲、章节正文等很多链路已自动落盘，角色卡是主要例外。

## Pressure-pass Findings
- Revisited earlier assumption that “关闭开关”应等于“完全禁止自动写文件”。用户明确否定，并进一步限定为：仅阻止新增自动保存能力，保留现有 built-in 自动落盘行为。

## Brownfield Evidence vs Inference
### Evidence
- Built-in auto-persist exists for worldbuilding/outline/project-data/chapters in router pipelines.
- Character cards currently use draft/save split.
- Custom knowledge categories and aux-memory categories are separate storage concepts.

### Inference
- The safest implementation boundary is to make the new switch govern only newly-expanded auto-save behavior and to keep non-builtin destinations behind explicit user choice.

## Technical Context Findings
- Built-in backend project-data types: `outline`, `worldbuilding`, `characters`, `items`, `eventlines`, `outline_settings`, `detail_settings`, `chapter_settings`
- Chapter正文文件走 `chapters/` 目录单独落盘
- 自定义知识分类需要额外映射策略，当前无统一自动保存后端路径

## Condensed Transcript
- User: 希望解决“明确要求保存到资料库却不会自动保存”的不一致问题。
- Interview: 改为聊天界面开关而不是仅凭 LLM 保存权限。
- User: 需要全局开关，并覆盖资料库分类与章节正文等输出。
- Interview: 自定义分类怎么处理？
- User: 非内置分类必须手动选，不能自动存。
- Interview: 开关关闭是否全禁写？
- User: 不是。
- Interview: 关闭时是保留现状还是更严格？
- User: 选 B——保留现有 built-in 自动保存，但新接入的自动保存能力关闭后不生效。
