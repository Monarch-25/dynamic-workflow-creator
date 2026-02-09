# smoke_todo_semantic (1.0.0)

## Capability
Search python files for TODO comments and summarize the findings

## Subtasks
- `search_python_files_todo_comments_summarize`: Search python files for TODO comments and summarize the findings (tool: `tool_search_python_files_todo_comments_summarize`)

## Runtime Requirements
- Document required: Yes (`--doc /path/to/file` required unless doc/text passed via JSON).
- Required input fields: doc
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
