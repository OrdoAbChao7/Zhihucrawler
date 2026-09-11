## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.
## 2024-05-24 - Short-circuit Evaluation
**Learning:** Eagerly evaluating fallback values for string fields by doing regex operations on large content payloads uses unnecessary CPU overhead.
**Action:** Use short-circuit evaluation (e.g., `a or b or expensive_call()`) to lazily evaluate functions performing expensive string/regex operations.
