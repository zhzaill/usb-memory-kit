便携 Firefox · 随盘携带记忆库的登录态
======================================

双击 启动记忆浏览器.cmd ：先确保记忆服务在跑，再用本盘自带的 Firefox 打开记忆库页面。

为什么不用系统浏览器：
  部分浏览器（如 Tabbit 1.18）默认启用 Local Network Access 策略，
  页面能打开，但对 127.0.0.1 的 fetch 请求会被直接拒绝（报 Failed to fetch）。
  Firefox 没有这条拦截，插上就能用。

这份配置带着什么（来自本机 Firefox 配置文件的副本）：
  书签、历史（places.sqlite）、已保存的登录（logins.json + key4.db）、
  各站点登录态（cookies.sqlite）、已登录的 Firefox 账号（signedInUser.json）。
  所以插上即是登录状态，联网时会自动同步。

结构：
  firefox\       Firefox 程序本体（不安装，绿色运行）
  profile\       配置与登录资料（含密码库与 cookie，敏感！）
  open-kit.ps1   启动逻辑：确保服务 -> 打开页面

注意：
  * U 盘外借或丢失前，删除 browser\profile 目录（其中含密码库与登录 cookie）。
  * firefox\distribution\policies.json 已关闭自动更新、遥测与首次运行页，
    避免盘上的程序在别人机器上被改动。
  * 换机器后盘符不是 E: 也没关系：启动器按自身位置推算路径。

2026-10-26 部署