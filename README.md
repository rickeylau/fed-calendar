# Fed Calendar

从 Federal Reserve Board 月度日历生成 ICS，时间按 America/New_York 解析，输出 UTC。

1. 新建公开 GitHub 仓库 fed-calendar，把三个文件保持原路径上传（包括隐藏目录 .github）。
2. Actions → Update Fed Calendar → Run workflow，选择 main。
3. 成功后订阅 https://raw.githubusercontent.com/你的用户名/fed-calendar/refs/heads/main/fed.ics 。
4. 每小时第 17 分钟自动触发（GitHub 可能延迟）。Google Calendar 有自己的刷新周期。

覆盖上月、本月及未来两个月已发布的官方日历。包含 Fed Board 讲话、讨论、听证、FOMC 和 Beige Book；不保证覆盖地区联储主席的活动。若与经济日历重复，修改 fed_calendar.py 中 INCLUDE_FOMC / INCLUDE_BEIGE_BOOK 为 False。

事件显示长度为 15 分钟，不代表官方时长。无 API Key。数据源： https://www.federalreserve.gov/newsevents/calendar.htm 。如果解析失败，工作流不会发布新日历。实际运行后请检查官方日期和时间。
