# Agent Project

This project demonstrates a Claude Agent using the Agent SDK with
runtime behavior switching.

## Key Features

- Single persistent ClaudeSDKClient session
- Runtime prompt injection via hooks
- Resolution mode triggered by tool failures (422)
- Resolution implemented as prompts, not a skill
- Claude Code built-in tools locked down by default

## Hooks

### PostToolUseFailure
Detects tool failures and switches the agent into resolution mode.
Current SDK payloads expose `error`, `tool_name`, and `tool_input`.

### UserPromptSubmit
Injects prompts depending on the current mode:
- Entry prompt
- Steady resolution prompt
- Exit prompt

## Modes

### Normal
Default agent behavior.

### Resolution
Guided troubleshooting flow triggered by 422 errors.
