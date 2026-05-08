# 多 Key 与 ONNX 语义召回改造审计记录

## API Key 配置链路

- `novel_agent/agent_config.py` 是全局与 Agent 生效配置的核心入口，原先 `APIConfigItem`、`GlobalAPIConfig`、`AgentModelConfig` 都以单个 `api_key` 为兼容字段。
- `novel_agent/agents/llm_client.py` 集中处理 `openai_chat`、`openai_responses`、`anthropic` 三类调用，是多 key 轮询最适合的统一接入点。
- `novel_agent/agents/base_agent.py` 仍保留 `openai_chat` 直连调用路径，需要与 `LLMClient` 使用同一个轮询服务，避免老 Agent 绕过 key 池。
- `novel_agent/web/routes/settings.py` 与 `novel_agent/web/models/requests.py` 负责多 API 配置的保存、更新、列表输出；读接口必须继续只返回 masked key。

## Embedding 初始化链路

- `novel_agent/knowledge_base/config.py` 管理 `KnowledgeBaseConfig`，原先 provider 主要是 `siliconflow` 与 `nvidia`。
- `novel_agent/knowledge_base/knowledge_base.py` 在 `_init_components()` 中实例化 embedding service，再传给 `HybridSearch`、`KnowledgeAPI`、`UnifiedStore`。
- `novel_agent/knowledge_base/logic_layer/embeddings.py` 已有 `EmbeddingService`、`NVIDIAEmbeddingService`、`MockEmbeddingService` 三个同形接口，可直接加入 `LocalOnnxEmbeddingService`。
- `novel_agent/knowledge_base/application_layer/knowledge_api.py` 是章节分块入库处，适合补充 `embedding_provider`、`embedding_model`、`embedding_dim` 与 `content_hash` metadata。

## 写作召回链路

- `novel_agent/agents/chapter_writer.py` 已在写作前调用 `_get_kb_context()`，并在写作后通过 `save_chapter_to_knowledge_base()` 入库。
- `novel_agent/workflow/coordinator.py` 在章节执行前已经聚合 `world`、`characters`、`eventlines`、`plot_thread`、`chapter_planning` 等上下文。
- 语义召回首版放在 `ChapterWriterAgent` 内部，输入上述上下文字段构造查询，召回失败只 warning，不阻断章节生成。

## 测试落点

- API key 池模型与状态机：`novel_agent/tests/test_api_key_rotation.py`
- LLM 调用轮询：`novel_agent/tests/test_llm_client_key_rotation.py`
- 本地 ONNX pooling/normalize：`novel_agent/knowledge_base/tests/test_local_onnx_embeddings.py`
- 章节语义召回查询与 prompt 注入：`novel_agent/tests/test_chapter_semantic_recall.py`
