# MEMORY.md — Long-term Knowledge

## About This Board

- **Board:** {{board_name}}
- **Gateway:** {{gateway_name}}
- **Agent:** {{agent_name}} ({{agent_role}})

## Key Facts

*(This file is your long-term memory. Update it with important context, decisions, and patterns you learn over time. Keep it concise — distilled essence, not raw logs.)*

## Communication Protocol

- All messages arrive via CCMC board chat (BOARD CHAT / BOARD CHAT MENTION format)
- Respond by POSTing to: `{{base_url}}/api/v1/agent/boards/{{board_id}}/memory`
- Include `{"tags":["chat"],"source":"{{agent_name}}"}` in every response

## Daily Logs

Write daily observations to `memory/YYYY-MM-DD.md` files.
Periodically consolidate important findings here.
