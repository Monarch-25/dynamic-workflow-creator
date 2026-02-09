# Dynamic Workflow Compiler (DWC)

DWC compiles natural language workflow requirements into a typed IR, optimizes it, generates LangGraph code, executes in an isolated Python venv, and iteratively refines the workflow using reflection.

## Key Pipeline

1. `SpecGeneratorAgent` turns NL requirements into `WorkflowSpec`.
2. `ClarificationAgent` fills missing deterministic defaults.
3. `OptimizerAgent` applies IR optimization passes.
4. `CodegenAgent` generates executable LangGraph Python.
5. `WorkflowExecutor` runs generated code in a venv sandbox and collects telemetry.
6. `ReflectionAgent` classifies failures and patches the IR for recompilation.
7. Stable artifacts are versioned via `WorkflowVersionManager`.

## Run (CLI)

```bash
python3 -m dwc.main \
  --requirements "Build a workflow that extracts text then proofreads it" \
  --workflow-name proofreading_workflow \
  --max-reflections 5
```

Dry run without execution:

```bash
python3 -m dwc.main \
  --requirements "Build a summarization workflow" \
  --workflow-name summarize_workflow \
  --no-execute
```

## API

Mount `dwc.api.router.router` in a FastAPI app:

```python
from fastapi import FastAPI
from dwc.api.router import router as dwc_router

app = FastAPI()
if dwc_router is not None:
    app.include_router(dwc_router)
```
