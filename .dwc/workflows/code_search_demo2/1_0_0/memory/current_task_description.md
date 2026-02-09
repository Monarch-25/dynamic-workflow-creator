# Current Task Description

_updated: 2026-02-09T17:26:53.610240+00:00_

User Requirements:
Search python source code with ripgrep for class definitions

Approved Plan:
1. Parse requirements and lock the current task description in shared memory.
2. Split the task into independent subtasks for tool construction.
3. Build one tool function per subtask via tool-builder agents.
4. Verify each tool in a venv with execution-based integrity checks.
5. Iterate tool fixes until verifier passes or fallback tool is selected.
6. Assemble a LangGraph workflow that runs subtasks and synthesizes results.
7. Emit workflow folder with workflow.py, tools.py, README.md, and memory snapshot.
8. Validate generated code and return user run instructions.

Intent Summary:
Build a general-purpose workflow generator from natural language requirements. User context: Search python source code with ripgrep for class definitions Execution path: 1. Parse requirements and lock the current task description in shared memory. 2. Split the task into independent subtasks for tool construction. 3. Build one tool function per subtask via tool-builder agents. 4. Verify each tool in a venv with execution-based integrity checks. 5. Iterate tool fix...
