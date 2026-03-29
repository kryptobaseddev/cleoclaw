# HEARTBEAT.md — Periodic Check-in Tasks

When running heartbeat check-ins, perform these tasks:

## Board Health Check

1. Check if there are any pending tasks on the board that need attention
2. Check if any board chat messages are unanswered
3. Report status back to CCMC:

```bash
curl -X POST "{{base_url}}/api/v1/agent/boards/{{board_id}}/memory" \
  -H "Content-Type: application/json" \
  -d '{"content":"Heartbeat: all systems operational.","tags":["heartbeat"]}'
```

## Memory Maintenance

- Review `memory/` files for the day
- Consolidate important findings into `MEMORY.md`
- Clean up stale or redundant memory entries
