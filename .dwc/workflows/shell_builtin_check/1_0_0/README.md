# shell_builtin_check (1.0.0)

## Capability
Create a workflow tool that runs shell commands only after user confirmation, and supports modify or skip based on the user message.

## Subtasks
- `task_1`: Create a workflow tool that runs shell commands only after user confirmation, and supports modify or skip based on the user message (tool: `tool_task_1`)

## Runtime Requirements
- Document required: No.
- Required input fields: none
- Optional input fields: query
- Supported document extensions: .txt, .md, .pdf, .docx, .doc

## Run
Default:
```bash
python workflow.py
```

With query:
```bash
python workflow.py --query "Your question here"
```

With document:
```bash
python workflow.py --doc ./input.txt
```

## Output
- The script prints plain-text final answer to terminal.
- No JSON is emitted by default.

## Notes
- `tools.py` contains verifier-approved tool functions.
- `spec.json` stores the compiled workflow spec.
- `memory/` snapshot mirrors shared task + working memories used during build.
- Any tool that calls `safe_cli` requires command approval (`execute` / `modify:<cmd>` / `skip`).
- Non-interactive control: `DWC_SAFE_CLI_MODE=allow|deny|prompt` and optional `DWC_SAFE_CLI_USER_MESSAGE`.
