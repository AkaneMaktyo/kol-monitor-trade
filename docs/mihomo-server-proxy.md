# Mihomo 服务器代理

服务器代理建议使用 `mihomo`，不要安装 Clash Verge。Clash Verge 是桌面 GUI 客户端，云服务器没有桌面环境时维护成本高；`mihomo` 是 Clash.Meta 系内核，更适合以 systemd 后台服务运行。

## 推荐方式

订阅地址属于敏感信息，默认不要放进 GitHub。推荐在服务器本地生成或放置 `/etc/mihomo/config.yaml`，再启动 mihomo。

如果只有订阅 URI 列表而不是 Clash YAML，需要先转换成 mihomo 配置。当前服务器已按这个方式生成配置。

## GitHub Actions 备用安装

当服务器上已经存在 `/etc/mihomo/config.yaml` 时，可以在 GitHub Actions 手动运行 `Install mihomo proxy` 来重装 mihomo。工作流只复用现有部署 secrets：

- `KMT_SSH_HOST`
- `KMT_SSH_PORT`
- `KMT_SSH_USER`
- `KMT_SSH_PASSWORD`

安装完成后，服务器会有：

- `mihomo.service`
- `/etc/mihomo/config.yaml`
- 本地代理端口 `127.0.0.1:7897`
- `TRADING_PROXY_URL=http://127.0.0.1:7897`
- `TELEGRAM_PROXY_URL=socks5://127.0.0.1:7897`

## 手动安装

如果已经 SSH 到服务器，并且要临时用订阅地址生成配置，也可以直接执行：

```bash
MIHOMO_CONFIG_URL='你的订阅地址' bash /root/kol-monitor-deploy/install-mihomo.sh
```

## 验收

在服务器上检查：

```bash
systemctl status mihomo --no-pager
curl --proxy http://127.0.0.1:7897 https://api.bitget.com/api/v2/public/time
curl http://127.0.0.1:8000/api/account/overview
```

如果 Bitget 私有接口不再返回 `Connection reset by peer`，线上账户页就不会再因为实时查询失败显示 0。
