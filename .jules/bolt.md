## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.

## 2026-09-08 - Lazy Evaluation of Expensive HTML Parsing
**Learning:** Unconditional calls to functions performing expensive string/regex operations on large data blocks (like HTML stripping for preview generation) cause unnecessary CPU overhead, especially when their output is only used as a fallback.
**Action:** Use short-circuit evaluation (e.g., `a or b or expensive_call()`) when possible to prevent executing heavy operations unless necessary.
