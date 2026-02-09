# Dynamic Workflow Compiler (DWC)

DWC compiles natural language requirements into a custom LangGraph workflow with a verifier-approved tool arsenal.

## Current Journey

1. User provides requirements (or enters interactive plan mode).
2. Planner proposes implementation path; user can refine until approved.
3. Requirements are split into independent subtasks.
4. Tool-builder agent creates one function per subtask.
5. Tool-verifier agent executes each tool in an isolated venv and validates output integrity.
6. Passing tools are added to the workflow arsenal.
7. A workflow folder is generated with:
   - `workflow.py`
   - `tools.py`
   - `README.md`
   - `spec.json`
   - `memory/` snapshot (shared + working memory markdown files)

## Plan Mode

Run without requirements to start plan mode:

```bash
python3 -m dwc.main
```

or explicitly:

```bash
python3 -m dwc.main --plan-mode
```

## Non-Interactive Compile

```bash
python3 -m dwc.main \
  --requirements "Build a workflow that extracts code blocks from a markdown document" \
  --workflow-name code_extractor
```

To stream agent progress checks during compile:

```bash
python3 -m dwc.main --requirements "..." --todo-stream
```

The persisted checklist is written to:
- `.dwc/memory_md/agents/todo_board.md`

## Generated Workflow Run

For general workflows:

```bash
python .dwc/workflows/<workflow_name>/<version>/workflow.py
```

For document workflows:

```bash
python .dwc/workflows/<workflow_name>/<version>/workflow.py --doc ./doc.txt
```

Output is plain text in terminal (not JSON).
