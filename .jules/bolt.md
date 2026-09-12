## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.

## 2024-06-12 - Short-circuit Evaluation in Data Parsing
**Learning:** Eagerly calling functions that perform heavy string/regex processing (like HTML stripping in `_content_preview`) causes unnecessary CPU overhead if the result is only used as a fallback identifier.
**Action:** Use short-circuit evaluation (`a or b or expensive_call()`) to lazily evaluate expensive operations only when needed, especially in loops processing large data structures.