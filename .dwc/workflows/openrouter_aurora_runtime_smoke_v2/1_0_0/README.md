# openrouter_aurora_runtime_smoke_v2 (1.0.0)

## Capability
Return current local date and time in ISO format with a one-line explanation

## Subtasks
- `gather_workflow_grammar`: Collect and document the workflow language grammar and semantics. (tool: `tool_gather_workflow_grammar`)
- `design_ir`: Create an IR that captures all workflow constructs. (tool: `tool_design_ir`)
- `implement_parser`: Build a parser that translates source scripts into the IR. (tool: `tool_implement_parser`)
- `type_check_validation`: Add a type‑checking and validation pass over the IR. (tool: `tool_type_check_validation`)
- `codegen_modules`: Generate code for target platforms such as Docker, Kubernetes, and serverless. (tool: `tool_codegen_modules`)
- `optimization_passes`: Add passes like dead‑code elimination and parallelism extraction. (tool: `tool_optimization_passes`)
- `cli_assembly`: Create a CLI that accepts workflow files and emits compiled artifacts. (tool: `tool_cli_assembly`)
- `testing_deployment`: Write unit/integration tests, documentation, and package the compiler with CI pipelines. (tool: `tool_testing_deployment`)

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
