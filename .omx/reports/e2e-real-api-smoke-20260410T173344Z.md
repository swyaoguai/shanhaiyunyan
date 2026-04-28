# Real API E2E Smoke Report

- Generated at: 2026-04-10T17:33:44.812119+00:00
- Base URL: http://127.0.0.1:65208
- Timeout: 180s

- project_count_before: 3
- project_count_after: 5
- created_projects: ['213b9744', '5cdee869']
- create_completed: True
- create_timed_out: False
- create_error: 
- create_duration_seconds: 21.96
- sse_chunk_count: 7

## Final Workflow
```json
{
  "run_id": "",
  "session_id": "realapi_1775842400",
  "project_id": "5cdee869",
  "command": "",
  "status": "idle",
  "target_agent": "",
  "current_agent": "",
  "stage": "",
  "last_progress": "",
  "last_error": "",
  "output_dir": "",
  "focus_module": "",
  "focus_chapter": 0,
  "started_at": "",
  "updated_at": "",
  "created_files": [],
  "updated_files": [],
  "reused_files": []
}
```

## WebSocket Preview
```json
[
  {
    "type": "connected",
    "payload_keys": [
      "client_id",
      "message"
    ]
  },
  {
    "type": "stage_change",
    "payload_keys": [
      "type",
      "stage",
      "agent",
      "task_type",
      "title",
      "message"
    ]
  },
  {
    "type": "stage_change",
    "payload_keys": [
      "type",
      "stage",
      "agent",
      "task_type",
      "title",
      "message"
    ]
  },
  {
    "type": "progress",
    "payload_keys": [
      "type",
      "agent",
      "message",
      "progress",
      "data"
    ]
  },
  {
    "type": "progress",
    "payload_keys": [
      "type",
      "agent",
      "message",
      "progress",
      "data"
    ]
  },
  {
    "type": "notification",
    "payload_keys": [
      "message"
    ]
  },
  {
    "type": "stage_change",
    "payload_keys": [
      "type",
      "stage",
      "agent",
      "task_type",
      "title",
      "error",
      "message"
    ]
  },
  {
    "type": "stage_change",
    "payload_keys": [
      "type",
      "stage",
      "agent",
      "task_type",
      "title",
      "error",
      "message"
    ]
  }
]
```