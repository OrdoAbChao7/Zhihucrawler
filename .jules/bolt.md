## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.
