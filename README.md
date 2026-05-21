# 新闻简报助手 (News Digest Assistant)

这是一个每日新闻聚合与中文翻译系统，主要用于自动收集半导体行业（特别是安世半导体 Nexperia）以及宠物/动物克隆与基因编辑相关的全球最新动态，并生成中文精简摘要。

## 系统架构与文件结构

* `fetcher.py`: 每天早晨 6:30 自动执行的新闻抓取与翻译引擎，解析 RSS 订阅，通过 `googlenewsdecoder` 解密原始链接，抓取网页 meta 摘要并调用 `deep-translator` 进行翻译，最终存入 SQLite。
* `server.py`: 基于 FastAPI 的本地服务器，提供数据 API，处理文章保存，并在本地编译生成 Markdown 文档。
* `templates/index.html`: 高质量、全动态的毛玻璃暗黑风格（Glassmorphism）Web Dashboard，用以展示新闻，供用户勾选和阅读。
* `run_fetcher.sh`: 用于 Cron 定时器的 Shell 脚本包裹层。
* `start_dashboard.sh`: 桌面启动器，一键开启服务并自动打开浏览器。
* `digest.db`: 本地 SQLite 数据库。
* `briefings/`: 存放用户打勾保存的每日简报文档（Markdown 格式，以日期命名）。

## 快速使用说明

### 1. 本地启动 Dashboard 界面

直接运行启动器脚本：
```bash
./start_dashboard.sh
```
该脚本会自动启动本地 Web 服务，并在您的默认浏览器中打开：`http://127.0.0.1:8000/`。

### 2. 界面操作

1. **查看与阅读**：在左侧边栏切换分类。右侧会显示新闻的中文标题与翻译后的摘要。
2. **中英对照**：如果文章来源于英文或荷兰文等欧洲语系，卡片右上角会有**“对照原文”**按钮，点击可展开原文标题和摘要对照。
3. **勾选保存**：将感兴趣的条目打勾，点击右上角的 **“保存选中的简报”**。系统会将其写入本地简报库，并自动在 `briefings/` 目录下生成/更新以今天日期命名的 Markdown 简报文件。
4. **看完关闭**：阅读完后，点击右上角的 **“看完并关闭”**。系统将把所有未保存的资讯自动标记为已读（下次不再重复显示），同时优雅地停掉后台数据库服务并安全关闭浏览器标签页。

### 3. 配置每天 6:30 自动抓取

请参阅同目录下的 [crontab_setup.txt](file:///home/allenxu/news/crontab_setup.txt) 获取配置步骤。

---
*Powered by DeepMind Advanced Agentic Coding - Antigravity*
