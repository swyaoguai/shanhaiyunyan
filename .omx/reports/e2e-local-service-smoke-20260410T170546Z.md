# Local Service E2E Smoke Report

- Generated at: 2026-04-10T17:05:46.023696+00:00
- Scope: 真实 FastAPI 服务 + HTTP + WebSocket 联调，不包含真实浏览器自动化

| Name | Method | Path | Status | Duration ms | OK | Notes |
|---|---|---|---:|---:|---|---|
| root_html | GET | / | 200 | 2.57 | ✅ | content_length=11182 |
| status | GET | /api/v1/status | 200 | 40.70 | ✅ | keys=['project', 'workflow_state', 'checkpoint', 'world', 'characters', 'contexts'] |
| projects | GET | /api/v1/projects | 200 | 15.28 | ✅ | keys=['projects', 'current_project_id'] |
| chat_sessions | GET | /api/v1/chat/sessions | 200 | 20.22 | ✅ | keys=['project_id', 'sessions', 'count'], count=7 |
| create_chat_session | POST | /api/v1/chat/sessions | 200 | 8.36 | ✅ | keys=['session_id', 'project_id', 'created'] |
| chat_history | GET | /api/v1/chat/history?session_id=copilot_1775840745973 | 200 | 3.18 | ✅ | keys=['session_id', 'history', 'count', 'restored'], count=0 |
| chat_workflow_status | GET | /api/v1/chat/workflow-status?session_id=copilot_1775840745973 | 200 | 3.66 | ✅ | keys=['workflow', 'reply'] |
| reset_chat | POST | /api/v1/chat/reset?session_id=copilot_1775840745973 | 200 | 5.21 | ✅ | keys=['success', 'session_id', 'cleared'] |

## WebSocket
- connected: True
- first_message_type: connected
- first_payload_keys: ['client_id', 'message']