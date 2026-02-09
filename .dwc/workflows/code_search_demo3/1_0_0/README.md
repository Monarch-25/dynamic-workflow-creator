# code_search_demo3 (1.0.0)

## Capability
Search python source code with ripgrep for class definitions

## Subtasks
- `task_1`: Search python source code with ripgrep for class definitions (tool: `tool_task_1`)

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
