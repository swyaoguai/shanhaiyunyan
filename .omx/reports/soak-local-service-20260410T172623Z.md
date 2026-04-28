# Local Service Soak Report

- Generated at: 2026-04-10T17:26:23.693249+00:00
- Base URL: http://127.0.0.1:56264
- Target duration: 600s
- Actual uptime observed: 609.98s

| Operation | Count | Failures | Avg ms | Max ms |
|---|---:|---:|---:|---:|
| chat_history | 2308 | 0 | 2.07 | 51.77 |
| chat_reset | 2308 | 0 | 1.85 | 22.97 |
| chat_session_create | 2308 | 0 | 2.45 | 31.05 |
| chat_sessions_list | 2308 | 0 | 3.32 | 69.92 |
| chat_workflow_status | 2308 | 0 | 1.95 | 22.88 |
| projects | 594 | 0 | 1.71 | 12.22 |
| status | 594 | 0 | 2.61 | 69.70 |
| websocket_connect | 298 | 0 | 4.72 | 67.66 |

## Notes
- 本脚本只覆盖真实本地服务的稳定性，不触发真实 LLM 网络调用。
- 若要继续推进，应在更宽松权限下做真实浏览器与真实 API 的长时端到端压测。