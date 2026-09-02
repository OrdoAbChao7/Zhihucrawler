<div align="center">
  <h1>知乎采集器 ZhihuCrawler</h1>
  <b>English</b> | <a href="./README.md"><b>中文</b></a>
</div>
<br>

# Zhihu Crawler

A Windows graphical Zhihu (知乎) tool that combines two kinds of capabilities:

- Keyword search: collect answers, articles, videos, and optional comments.
- Specific questions: collect question answers page by page, with optional comments.
- Creators: collect a creator's answers, articles, and videos.
- Collections: batch-download collections or a user's articles as Markdown, with local deduplicated images.

## Usage

Run from source:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\playwright install chromium
.\.venv\Scripts\python -m zhihu_app
```

On first run, use "Log in to Zhihu" to open the browser and complete login; the window closes automatically once cookies are exported and verified through the Zhihu account API. For the source version, login state is stored in `data/browser_profile`; for the packaged version, in `%LOCALAPPDATA%\ZhihuCrawler`, so rebuilding does not clear the login. Output goes to the project's `output/` or `%LOCALAPPDATA%\ZhihuCrawler\output` respectively.

If you see "Zhihu triggered access risk control (error code 40362)", your login state is still valid but the account or network is temporarily restricted by Zhihu for that type of access; pause for a while or switch to a normal network and retry. Set reasonable request intervals, use it only for personal/non-commercial study and research, and follow Zhihu's rules.

## Building the Windows app

In PowerShell:

```powershell
.\packaging\build.ps1 -Clean
.\packaging\create_shortcut.ps1
```

The build lands in `dist/知乎采集器/知乎采集器.exe` and a desktop shortcut is created. The directory-based release package must be kept intact — do not copy the exe alone.

## Origin and licensing

The Zhihu collection adapters come from MediaCrawler; the collection-download capability comes from Zhihu-Collection-Downloader. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for integration boundaries and licenses.
