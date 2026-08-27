# 知乎桌面采集器集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** 在 `E:\Projects\zhihu` 交付一个仅聚焦知乎的 Tkinter Windows 应用，统一提供 MediaCrawler 知乎采集和 Zhihu-Collection-Downloader 下载能力，并生成可双击使用的目录版 `.exe` 与 `.lnk` 快捷方式。

**Architecture:** 保留两个源项目的知乎实现为受控的 vendor/source 层，在 `src/zhihu_app` 上方建立统一配置、任务模型、后台运行器和 GUI。GUI 只依赖统一任务接口；登录态、输出目录、日志和取消信号由应用层统一管理。PyInstaller 采用 onedir，确保 Playwright、Node 签名脚本和静态资源可用。

**Tech Stack:** Python 3.11+, Tkinter/ttk, asyncio, Playwright, requests, html2text, PyYAML, PyInstaller, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-27-zhihu-desktop-integration-design.md`

## Global Constraints

- 目标平台为 Windows 10/11 x64。
- 仅用于个人/非商业学习研究，不进行大规模爬取、商业用途或规避平台访问控制。
- 必须保留两个源项目的 LICENSE 和来源说明。
- 所有网络任务默认使用保守请求间隔，并支持取消。
- 测试不得访问知乎真实站点；完成标准必须包含真实构建和 GUI 启动 smoke test。

---

### Task 1: 建立项目骨架、许可证和依赖边界

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `LICENSE.MediaCrawler.txt`
- Create: `LICENSE.Apache-2.0.txt`
- Create: `src/zhihu_app/__init__.py`
- Create: `src/zhihu_app/__main__.py`
- Create: `tests/test_project_metadata.py`
- Copy source: `vendor/mediacrawler/` 中仅保留运行知乎适配器所需的模块；`vendor/collection_downloader/Main.py`、`requirements` 和示例配置

**Interfaces:**
- `python -m zhihu_app` 启动 GUI。
- `zhihu_app.__version__` 返回固定应用版本字符串。

- [ ] 写测试，断言版本存在、README 明确四类功能、两个 LICENSE 文件存在且第三方说明包含两个来源。
- [ ] 运行 `python -m pytest tests/test_project_metadata.py -q`，确认因文件不存在失败。
- [ ] 建立 `src`、`tests`、`vendor`、`packaging`、`output` 目录，复制源代码时删除 `__pycache__`、浏览器缓存和其他平台适配器。
- [ ] 添加最小 `pyproject.toml`，声明 Python 版本、运行依赖和 pytest 配置；不把源项目的无关数据库/可视化依赖加入默认安装集。
- [ ] 通过测试并运行 `python -m pytest tests/test_project_metadata.py -q`。

### Task 2: 实现统一配置、URL 分类、任务模型和安全输出路径

**Files:**
- Create: `src/zhihu_app/config/settings.py`
- Create: `src/zhihu_app/engine/models.py`
- Create: `src/zhihu_app/engine/paths.py`
- Create: `tests/test_settings.py`
- Create: `tests/test_models.py`
- Create: `tests/test_paths.py`

**Interfaces:**
- `AppSettings.load(path: Path | None = None) -> AppSettings`
- `AppSettings.save(path: Path | None = None) -> None`
- `class TaskType(Enum)`: `SEARCH`, `QUESTION`, `CREATOR`, `COLLECTION`
- `class ZhihuTask`: `task_type`, `target`, `include_comments`, `max_items`, `interval_seconds`, `proxy`, `output_dir`
- `class TaskResult`: `status`, `items_processed`, `output_dir`, `error_message`
- `class OutputPaths`: `raw_dir`, `markdown_dir`, `image_dir`, `task_dir`
- `classify_target(url: str) -> TaskType`：识别问题、创作者、收藏夹/用户文章；关键词由显式任务类型提供。
- `build_output_paths(root: Path, task_type: TaskType, label: str, now: datetime) -> OutputPaths`：拒绝绝对路径逃逸和 `..` 片段。

- [ ] 先写覆盖默认设置、非法 URL、负数限制、Windows 文件名清洗和路径逃逸的测试。
- [ ] 运行上述测试，确认缺少模块/接口导致失败。
- [ ] 实现 dataclass/Enum、JSON 持久化和安全目录构造；默认输出为项目根 `output`、间隔 1.5 秒、最大数量 50。
- [ ] 重新运行测试直到全部通过；再运行全量 `python -m pytest -q`。

### Task 3: 封装登录态、MediaCrawler 知乎采集和 Collection Downloader

**Files:**
- Create: `src/zhihu_app/auth/session.py`
- Create: `src/zhihu_app/engine/mediacrawler_adapter.py`
- Create: `src/zhihu_app/engine/collection_downloader.py`
- Create: `src/zhihu_app/engine/errors.py`
- Create: `tests/fixtures/zhihu_search.json`
- Create: `tests/fixtures/zhihu_collection.json`
- Create: `tests/test_adapters.py`
- Create: `tests/test_downloader_output.py`

**Interfaces:**
- `SessionManager(profile_dir: Path)`：`async login() -> None`、`async close() -> None`、`cookies_for_requests() -> dict[str, str]`。
- `MediaCrawlerAdapter(settings: AppSettings)`：`async run(task: ZhihuTask, emit: Callable[[str], None], cancel: Event) -> TaskResult`。
- `CollectionDownloader(settings: AppSettings)`：`run(task: ZhihuTask, emit: Callable[[str], None], cancel: Event) -> TaskResult`。
- 两个适配器都不得把 Cookie 或 Authorization 写入日志；取消时返回 `cancelled` 而不是删除已有文件。

- [ ] 使用固定 JSON fixture 写测试，验证搜索/问题/创作者结果统一成 `TaskResult`，收藏夹结果生成 Markdown frontmatter 并按 URL/更新时间跳过重复内容。
- [ ] 运行测试确认适配器接口缺失或行为不完整而失败。
- [ ] 将源项目调用隔离在适配器内部；为 requests 下载器注入 session/transport，使离线测试不发网络请求；将 Playwright 登录态目录固定为 `data/browser_profile`。
- [ ] 对网络异常、登录失效、HTTP 429/403、解析异常映射为 `ZhihuAuthError`、`ZhihuRateLimitError`、`ZhihuParseError` 或 `ZhihuNetworkError`。
- [ ] 运行 `python -m pytest tests/test_adapters.py tests/test_downloader_output.py -q`，确认通过。

### Task 4: 实现后台任务运行器和 Tkinter GUI

**Files:**
- Create: `src/zhihu_app/engine/runner.py`
- Create: `src/zhihu_app/gui/logging.py`
- Create: `src/zhihu_app/gui/forms.py`
- Create: `src/zhihu_app/gui/app.py`
- Modify: `src/zhihu_app/__main__.py`
- Create: `tests/test_forms.py`
- Create: `tests/test_runner.py`

**Interfaces:**
- `TaskRunner.submit(task: ZhihuTask) -> None`
- `TaskRunner.cancel() -> None`
- `TaskRunner.on_log: Callable[[str], None]`
- `TaskRunner.on_done: Callable[[TaskResult], None]`
- `build_task_from_form(values: Mapping[str, str]) -> ZhihuTask`
- `create_app(settings: AppSettings) -> ZhihuApp`

- [ ] 先写表单测试：四种任务可构造，缺目标、数量非整数、间隔小于 0.5 秒时返回明确错误。
- [ ] 先写 runner 测试：任务提交只启动一个后台任务，取消设置事件，完成回调收到 `TaskResult`。
- [ ] 运行测试确认失败。
- [ ] 使用 Tkinter/ttk 建立单窗口：任务类型下拉框、关键词/URL 输入框、评论开关、最大数量、间隔、代理、输出目录、登录按钮、开始/停止按钮、日志区和“打开输出目录”按钮。
- [ ] GUI 主线程只更新控件；爬虫在后台线程/事件循环运行；窗口关闭时取消任务并关闭会话。
- [ ] 登录按钮只启动/复用 Playwright 会话，不在界面或日志显示敏感 Cookie。
- [ ] 运行测试和 `python -m zhihu_app --help`/版本 smoke test，确认无显示器环境下不导入即崩溃。

### Task 5: 配置 PyInstaller、构建脚本和桌面快捷方式

**Files:**
- Create: `packaging/知乎采集器.spec`
- Create: `packaging/build.ps1`
- Create: `packaging/create_shortcut.ps1`
- Create: `packaging/smoke_test.ps1`
- Modify: `README.md`
- Create: `tests/test_packaging_layout.py`

**Interfaces:**
- `packaging/build.ps1 -PythonExe <path> -Clean`：退出码 0 时生成 `dist/知乎采集器/知乎采集器.exe`。
- `packaging/create_shortcut.ps1 -ExePath <path> -ShortcutPath <path>`：创建 `.lnk`，目标为绝对规范化 exe 路径。
- `packaging/smoke_test.ps1 -ExePath <path>`：启动程序、等待窗口进程出现、发送关闭信号并返回退出码。

- [ ] 先写布局测试，断言 spec 包含 `src`、`vendor`、Playwright browser data 和无控制台窗口配置。
- [ ] 运行测试确认文件不存在而失败。
- [ ] 配置 onedir PyInstaller，显式收集 vendor 包、`libs/zhihu.js`、Tkinter 和 Playwright 需要的运行时资源。
- [ ] 构建脚本创建 `.venv`、安装依赖、执行 `python -m playwright install chromium`，然后运行 `pyinstaller --noconfirm packaging/知乎采集器.spec`。
- [ ] 快捷方式脚本使用 WScript.Shell COM 创建桌面快捷方式，不覆盖用户已有非本项目快捷方式；输出发布目录内的 `.lnk` 和桌面副本。
- [ ] 运行布局测试，检查 PowerShell 脚本语法，并更新 README 的构建/使用步骤。

### Task 6: 全量验证和交付审计

**Files:**
- Modify: `README.md`
- Create: `dist/` build artifacts

- [ ] 运行 `python -m pytest -q`，记录通过数和任何警告。
- [ ] 运行 `packaging/build.ps1 -Clean`，确认最终退出码为 0，且 exe 文件存在。
- [ ] 运行 `packaging/create_shortcut.ps1`，确认 `.lnk` 的目标路径指向最终 exe。
- [ ] 运行 `packaging/smoke_test.ps1`，确认 GUI 能打开、显示应用标题/版本并正常关闭。
- [ ] 使用离线 fixture 运行四类任务的核心路径，确认输出 JSON/Markdown/图片目录结构和取消行为。
- [ ] 对照设计规格逐条检查功能、许可证、日志脱敏、构建产物和快捷方式证据；只有全部有命令输出或文件证据时才宣称完成。

