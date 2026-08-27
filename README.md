# 知乎采集器

Windows 图形化知乎工具，整合两类能力：

- 关键词搜索：采集回答、文章、视频和可选评论。
- 指定问题：分页采集问题回答和可选评论。
- 创作者：采集创作者的回答、文章和视频。
- 收藏夹：批量下载收藏夹或用户文章为 Markdown，图片本地化并去重。

## 使用

运行源码：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\playwright install chromium
.\.venv\Scripts\python -m zhihu_app
```

首次运行通过“登录知乎”打开浏览器完成登录；窗口会在 Cookie 导出并通过知乎账号接口验证后自动关闭。源码版登录态保存在 `data/browser_profile`，打包版保存在 `%LOCALAPPDATA%\ZhihuCrawler`，因此重新构建不会清除登录。输出分别保存在项目 `output/` 或 `%LOCALAPPDATA%\ZhihuCrawler\output`。

如果出现“知乎触发访问风控（错误码 40362）”，表示登录态仍然有效，但当前账号或网络被知乎暂时限制了该类访问；请暂停一段时间或更换正常网络后再试。请设置合理的请求间隔，仅用于个人/非商业学习研究，并遵守知乎规则。

## 构建 Windows 程序

在 PowerShell 执行：

```powershell
.\packaging\build.ps1 -Clean
.\packaging\create_shortcut.ps1
```

构建结果位于 `dist/知乎采集器/知乎采集器.exe`，同时会生成桌面快捷方式。目录版发布包必须整体保留，不能只复制 exe 文件。

## 来源与许可

知乎采集适配器来自 MediaCrawler，收藏夹下载能力来自 Zhihu-Collection-Downloader；集成边界和许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
