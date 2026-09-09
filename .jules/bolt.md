## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.

## 2026-09-09 - Short-Circuit Evaluation for Expensive Fallbacks
**Learning:** Unconditionally evaluating fallback variables (like extracting plain text from large HTML strings for identity fallbacks) introduces unnecessary CPU overhead when the primary keys (`url` or `id`) are usually present.
**Action:** Use short-circuit evaluation (e.g., `a or b or expensive_call()`) to lazily evaluate functions performing expensive string/regex operations on large data blocks when the output is only used as a fallback.
