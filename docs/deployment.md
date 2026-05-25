# 云服务器部署说明

当前部署目标：

- Web 地址：`http://103.236.98.149:8888/`
- SSH：`103.236.98.149:29453`
- 应用目录：`/opt/kol-monitor-trade/current`
- 环境变量：`/etc/kol-monitor-trade/app.env`
- 数据库：云端 MySQL，`kol_monitor_trade`
- systemd 服务：`kol-monitor-trade`

## 自动部署

仓库已加入 GitHub Actions 工作流：`.github/workflows/deploy.yml`。

推送到 `main` 后，工作流会打包代码、上传到服务器，并调用
`deploy/apply-release.sh` 完成发布、依赖安装和服务重启。

需要在 GitHub 仓库 Secrets 中配置：

- `KMT_SSH_HOST`：`103.236.98.149`
- `KMT_SSH_PORT`：`29453`
- `KMT_SSH_USER`：服务器登录用户
- `KMT_SSH_PASSWORD`：服务器登录密码

## 常用检查

```bash
systemctl status kol-monitor-trade --no-pager
journalctl -u kol-monitor-trade -n 120 --no-pager
curl http://127.0.0.1:8000/api/health
```

服务器直连 Telegram 当前可能超时；如果要在云端监听 Telegram，需要在
`/etc/kol-monitor-trade/app.env` 配置服务器可用的 `TELEGRAM_PROXY_URL`。

当前 80 端口外网会返回未备案拦截页；`8888` 已在 Nginx 配好，但还需要在
云服务器安全组或端口映射里放通。

如果要启用 Discord self 模式，还需要让服务器能访问 GitHub，并在发布时设置
`INSTALL_SELFCORD=true`，否则自动部署会跳过这个可选依赖。
