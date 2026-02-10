# Current Task Description

_updated: 2026-02-09T20:59:39.473241+00:00_

User Requirements:
Extract python code blocks from markdown text and provide a concise summary

Approved Plan:
1. Load the markdown file or input string.  
2. Scan the text for fenced code blocks using the pattern ```python … ```.  
3. Capture the content between each matching pair of fences.  
4. Store each extracted snippet in a list or temporary file.  
5. For each snippet, parse the abstract syntax tree (AST) to identify top‑level definitions (functions, classes, imports).  
6. Generate a brief description for each snippet, e.g., “Defines function `foo` that …” or “Imports `numpy` and uses `np.array`”.  
7. Compile the descriptions into a concise summary, grouping similar snippets if appropriate.  
8. Output the extracted code blocks and the summary in the desired format.

Intent Summary:
The user wants a tool that processes a markdown document, finds all fenced Python code blocks (```python … ```), extracts each snippet, analyzes its AST to locate top‑level definitions such as functions, classes, and imports, and then creates brief natural‑language descriptions of those snippets (e.g., “defines function foo”, “imports numpy”). The extracted code and the generated descriptions should be compiled into a concise summary, grouping similar snippets when appropriate, and presented in a clear format.
