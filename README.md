# honk-geoip

自维护的 v2ray 格式 `geoip.dat`，给 [honk](https://github.com/daeuniverse/honk)（dae 系透明代理）的 `dip(geoip:xxx)` 规则用。

思路：**以官方 cn+private 数据为底，追加/覆盖自定义码**。CI 每天重新拉一次底包，所以你只维护 `sets/*.txt` 里的 CIDR 列表，CN 段不会过期。

## 目录

```
sets/*.txt              自定义 CIDR 集合，文件名即 code（telegram.txt -> TELEGRAM）
scripts/build_geoip.py  构建脚本：base + sets -> geoip.dat
dist/geoip.dat          构建产物（CI 自动提交，别手改）
dist/geoip.dat.sha256sum  校验文件，对应 honk 的 checksum: true
```

## 在 honk 里用

`/etc/honk/config.dae` 的 `global` 块里加（注意：`assets.geodata.*` 任何改动都要**重启** honk 才生效）：

```dae
global {
  assets {
    geodata {
      geoip: 'https://raw.githubusercontent.com/<USER>/honk-geoip/main/dist/geoip.dat'
      checksum: true
      auto_update: true
      cron: '0 3 * * *'
    }
  }
}
```

然后：

```sh
ssh root@192.168.2.1 '/etc/init.d/honk restart'
```

`checksum: true` 时 honk 会去拉 `<url>.sha256sum`，本仓库已生成；若该文件 404，honk 会接受未校验的文件。

之后 `route.dae` 里就能直接写：

```dae
dip(geoip:telegram) -> proxy
```

（code 大小写不敏感，`CN`/`cn` 都行。）

### 拉不到 raw.githubusercontent.com 时

honk 的 `geodata.route` 默认是 `routing`，即按路由规则下载；如果 fallback 走代理，raw 通常没问题。若想直连 CDN，可改用 jsDelivr：

```
https://cdn.jsdelivr.net/gh/<USER>/honk-geoip@main/dist/geoip.dat
```

jsDelivr 对分支有缓存（最长约 12h），日更数据可以接受；raw 无缓存、永远最新。

## 维护

- **加集合**：新建 `sets/myproxy.txt`（每行一个 CIDR，`#` 注释），push 即触发 CI，生成 code `MYPROXY`。
- **改集合**：直接改文件 push。
- **同名冲突**：若 sets 里的 code 与底包同名（如 `cn`），会用你的集合**整体替换**底包里的这一项。
- **定时**：CI 每天 02:30 CST 重建，02:30–03:00 之间完成提交，赶在 honk 03:00 的拉取窗口前。

## 本地构建

```sh
python3 scripts/build_geoip.py \
  --base https://cdn.jsdelivr.net/gh/Loyalsoldier/geoip@release/geoip-only-cn-private.dat \
  --out dist/geoip.dat
```

`--base` 也可以是本地文件（如路由器上的 `/etc/honk/geoip.dat`）。脚本会打印每个 code 的 CIDR 数、文件大小和 sha256，并做一次回读自检。
