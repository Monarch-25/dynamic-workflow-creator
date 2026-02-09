# smoke_progress3 (1.0.0)

## Capability
Extract key entities from text and summarize them

## Subtasks
- `extract_key_entities_text_summarize_them`: Extract key entities from text and summarize them (tool: `tool_extract_key_entities_text_summarize_them`)

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
