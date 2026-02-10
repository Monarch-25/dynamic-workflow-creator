# openrouter_aurora_runtime_smoke (1.0.0)

## Capability
Return current local date and time in ISO format with a one-line explanation

## Subtasks
- `get_current_iso_timestamp`: Retrieve the current local date and time formatted in ISO 8601. (tool: `tool_get_current_iso_timestamp`)
- `generate_one_line_explanation`: Provide a concise one-line description of the timestamp's purpose. (tool: `tool_generate_one_line_explanation`)
- `gather_workflow_specifications`: Collect detailed workflow specifications and compiler requirements. (tool: `tool_gather_workflow_specifications`)
- `design_ast_structure`: Create the abstract syntax tree (AST) model for the workflow language. (tool: `tool_design_ast_structure`)
- `implement_parsing_modules`: Build parsers to translate workflow definitions into the AST. (tool: `tool_implement_parsing_modules`)
- `develop_codegen_backends`: Create code generation back‑ends for target execution environments. (tool: `tool_develop_codegen_backends`)
- `create_validation_testing_suites`: Develop validation and testing suites to ensure correct compilation. (tool: `tool_create_validation_testing_suites`)
- `deploy_compiler_and_document`: Deploy the compiler with documentation and monitor user feedback. (tool: `tool_deploy_compiler_and_document`)

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
