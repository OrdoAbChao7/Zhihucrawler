## 2024-05-24 - File Reading I/O
**Learning:** Checking file metadata within the first few KB is much faster and uses less memory than reading the whole file when parsing front matter.
**Action:** Use chunk reading for front matter checks when dealing with potentially large markdown files.

## 2024-05-24 - Lazy String/Regex Evaluation for Large Data Blocks
**Learning:** In the `CollectionDownloader`, generating unique IDs (`identity`) for markdown items used `_content_preview(item)` eagerly to extract preview text using regex (`re.sub`). If an item has a valid URL or ID (true for 99% of valid crawled records), this expensive parsing is completely unnecessary and wastes CPU cycles, especially since items can have massive HTML bodies.
**Action:** When extracting fallbacks from large text blocks, use short-circuit evaluation (`identity = a or b or expensive_preview()`) so that expensive string or regex operations are only evaluated lazily when strictly necessary as a last resort.
