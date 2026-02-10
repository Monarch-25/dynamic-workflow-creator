# openrouter_aurora_compile_test (1.0.0)

## Capability
Extract python code blocks from markdown text and provide a concise summary

## Subtasks
- `load_markdown_input`: Read the markdown file or input string containing the content to be processed. (tool: `tool_load_markdown_input`)
- `find_python_code_blocks`: Search the markdown for fenced code blocks that start with ```python and end with ```. (tool: `tool_find_python_code_blocks`)
- `extract_code_snippets`: Capture the inner text of each identified Python code block and store them in a list. (tool: `tool_extract_code_snippets`)
- `parse_ast_for_definitions`: For each snippet, build an abstract syntax tree to locate top‑level functions, classes, and import statements. (tool: `tool_parse_ast_for_definitions`)
- `generate_snippet_description`: Compose a brief natural‑language description of the snippet based on the AST findings. (tool: `tool_generate_snippet_description`)
- `group_similar_snippets`: Cluster snippets that share comparable functionality or imports for more concise summarisation. (tool: `tool_group_similar_snippets`)
- `compile_concise_summary`: Combine the individual descriptions into a short overall summary, preserving key details. (tool: `tool_compile_concise_summary`)
- `output_results`: Emit the list of extracted code blocks together with the generated summary in the required format. (tool: `tool_output_results`)

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
