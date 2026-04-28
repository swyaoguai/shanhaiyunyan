# Local Performance Smoke Report

- Generated at: 2026-04-10T16:36:38.099325+00:00
- Scope: 本地编排与会话层开销，不包含真实 LLM 网络耗时

| Scenario | Runs | Avg ms | P50 ms | P95 ms | Min ms | Max ms | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| create_chat_session_burst | 20 | 0.04 | 0.03 | 0.05 | 0.03 | 0.10 | unique_session_ids=20, requested=20 |
| same_session_chat_sequential | 50 | 0.08 | 0.06 | 0.09 | 0.05 | 0.89 | saved_states=50 |
| same_session_chat_concurrent | 20 | 0.07 | 0.06 | 0.13 | 0.06 | 0.17 | saved_states=20 |
| multi_session_chat_concurrent | 20 | 0.08 | 0.07 | 0.14 | 0.06 | 0.20 | unique_sessions=20, saved_states=20 |
| multi_session_mixed_ops | 30 | 0.04 | 0.03 | 0.07 | 0.03 | 0.11 | workers=12, resets=6, saved_states=24 |
| formal_create_route_smoke | 10 | 123.82 | 123.89 | 128.87 | 117.46 | 128.87 | avg_sse_chunks=3.0, task_pool_source=contract_confirmation |

## Notes
- 这些数据用于观察最近重构是否显著放大本地 orchestration overhead。
- 如需真实性能结论，下一步应在真实 API / 前端 / 多 session 环境下做端到端压测。