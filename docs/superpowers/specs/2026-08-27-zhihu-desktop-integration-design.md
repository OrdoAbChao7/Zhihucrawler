# 知乎桌面采集器集成设计

## 目标

在 `E:\Projects\zhihu` 建立一个仅聚焦知乎的 Windows 桌面应用，整合两个已有项目中的知乎能力：MediaCrawler 的搜索、问题、创作者、内容详情和评论采集，以及 Zhihu-Collection-Downloader 的收藏夹/用户文章批量下载、Markdown 转换、图片本地化和去重。应用应提供图形界面，并能够构建可双击启动的 `.exe` 和桌面快捷方式。

## 约束与使用范围

- 首版目标平台为 Windows 10/11 x64。
- 保留 MediaCrawler 的非商业学习许可和版权声明；集成项目仅用于个人/非商业学习研究，不用于大规模爬取、商业用途或干扰平台运营。
- 保留 Zhihu-Collection-Downloader 的 Apache-2.0 许可和来源说明。
- 只集成知乎平台，不把其他社交平台适配器带入最终应用。
- 使用真实登录态和保守请求间隔；不绕过验证码、访问控制或平台权限。

## 方案

采用“知乎引擎层 + GUI 适配层 + 打包层”的单仓库结构。

1. `src/zhihu_app/engine/` 提供稳定、可测试的任务接口。MediaCrawler 的知乎适配器作为采集引擎，Collection Downloader 的逻辑被整理为独立下载引擎；GUI 不直接调用源项目脚本内部细节。
2. `src/zhihu_app/auth/` 统一管理 Playwright 浏览器上下文和登录态目录。GUI 提供扫码/网页登录入口；两个引擎共享同一个登录态，并为旧版 Cookies.json 提供兼容导入，而不是把 Cookie 明文写入日志。
3. `src/zhihu_app/gui/` 使用 Tkinter/ttk，实现任务类型选择、参数表单、代理/间隔/数量等基础设置、开始/停止、实时日志和输出目录打开。
4. `src/zhihu_app/config/` 负责 JSON 配置、默认路径和输入校验。默认输出根目录为 `output/`，按任务类型、日期和内容标题组织；原始 JSON、Markdown、图片分开保存。
5. `packaging/` 提供 PyInstaller 目录版构建脚本和快捷方式创建脚本。目录版优先保证 Playwright、Node 签名脚本和运行时资源的可用性；构建后生成 `dist/知乎采集器/知乎采集器.exe` 及 `知乎采集器.lnk`。

## 功能与数据流

GUI 启动后读取本地配置，用户选择一种任务：

- 关键词搜索：调用知乎搜索接口，提取回答、文章、视频及可选评论。
- 指定问题：输入问题 URL，分页获取回答及可选评论。
- 创作者内容：输入创作者主页，获取回答、文章、视频。
- 收藏夹/用户文章下载：输入收藏夹或用户文章 URL，分页获取内容，转换为 Markdown，下载图片并按 URL/更新时间去重。

所有任务经过同一层校验和取消控制，运行日志只记录 URL、数量、状态和错误摘要，不记录 Cookie、Authorization 或完整响应敏感字段。网络错误、登录失效、限流和解析错误分别显示可操作提示；任务失败不删除已有输出。

## 文件边界

- `src/zhihu_app/engine/mediacrawler_adapter.py`：封装 MediaCrawler 知乎采集入口。
- `src/zhihu_app/engine/collection_downloader.py`：封装收藏夹/用户文章下载能力。
- `src/zhihu_app/engine/models.py`：统一任务、内容和结果模型。
- `src/zhihu_app/engine/runner.py`：后台线程/异步任务调度、进度和取消。
- `src/zhihu_app/auth/session.py`：登录态目录和浏览器会话管理。
- `src/zhihu_app/config/settings.py`：配置模型、路径和安全默认值。
- `src/zhihu_app/gui/app.py`：主窗口和任务导航。
- `src/zhihu_app/gui/forms.py`：任务表单与校验。
- `src/zhihu_app/gui/logging.py`：线程安全日志转发。
- `tests/`：配置、任务构造、输出去重、引擎适配和 GUI 无头逻辑测试。
- `packaging/build.ps1`：创建虚拟环境、安装依赖、安装 Playwright 浏览器并构建目录版程序。
- `packaging/create_shortcut.ps1`：创建桌面快捷方式并解析相对资源路径。
- `THIRD_PARTY_NOTICES.md`：许可证、来源和集成边界说明。

## 测试与验收

- 单元测试覆盖 URL 类型判断、配置默认值/校验、任务序列化、输出路径安全、Markdown 去重和错误分类。
- 引擎测试使用离线固定响应，不访问知乎真实站点；真实登录和网络运行只作为手工验收步骤。
- 构建验收必须得到最终退出码为 0 的 PyInstaller 构建结果、存在 `.exe` 和 `.lnk`，并通过启动 smoke test 验证 GUI 可打开、可显示版本和可关闭。
- 不以“测试通过”替代实际构建和启动验证。

