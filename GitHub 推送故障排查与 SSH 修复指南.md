# GitHub 推送故障排查与 SSH 修复指南

本文档记录一次典型的 `git push` 失败（HTTPS 443 连接超时）场景的排查与修复流程，并给出推荐的稳定做法：切换到 SSH remote。

## 适用场景

当你执行：

```bash
git push
```

出现类似错误：

- `Failed to connect to github.com port 443 ... Couldn't connect to server`
- 或长时间卡住后超时

通常代表：本机到 GitHub 的 **HTTPS 443** 链路不可达或被代理/防火墙影响。

## 目标

- 识别是“整体网络不可达”还是“Git 代理配置问题”。
- 在网络受限时，通过 **SSH** 完成 `git push`。

## 步骤 1：确认是否整体 HTTPS 不通

执行：

```bash
curl -I https://github.com
```

判读：

- 如果 `curl` 也长时间无响应/超时：多半是网络侧问题（公司内网策略、代理、VPN、DNS、防火墙等）。
- 如果 `curl` 正常但 `git push` 不行：更可能是 Git 的代理配置或证书链问题。

说明：如果 `curl` 卡住，你可以用 `Ctrl + C` 中断（不会产生副作用）。

## 步骤 2：检查 Git 是否配置了代理

执行：

```bash
git config --global --get http.proxy
git config --global --get https.proxy
git config --system --get http.proxy
git config --system --get https.proxy
```

以及检查环境变量：

```bash
env | grep -i proxy
```

判读：

- 如果存在代理配置，但当前网络环境不需要代理或代理不可用，Git 可能会因为走错误代理导致连接失败。

可选修复（仅在你确认“不需要代理”时）：

```bash
git config --global --unset http.proxy
git config --global --unset https.proxy
```

> 注意：在公司内网可能必须使用公司代理；如果不确定，先不要取消代理，优先咨询网络/IT 策略。

## 步骤 3：推荐修复——切换到 SSH 推送

当 HTTPS 443 不稳定或被限制时，推荐把 remote 从 HTTPS 切换到 SSH。

### 3.1 查看当前 remote

```bash
git remote -v
```

### 3.2 设置 origin 为 SSH 地址

```bash
git remote set-url origin git@github.com:surdring/GangQing.git
```

> 将 `surdring/GangQing` 替换为你的实际仓库路径。

### 3.3 验证 SSH 鉴权是否正常

```bash
ssh -T git@github.com
```

预期输出（示例）：

- `Hi <username>! You've successfully authenticated, but GitHub does not provide shell access.`

这是 **成功** 的标志：

- 说明 SSH key 认证成功
- GitHub 不提供 shell 登录，因此会提示不提供 shell access（属于正常信息）

### 3.4 再次确认 remote 指向

```bash
git remote -v
git remote show origin
```

预期现象：

- fetch/push 地址都是 `git@github.com:...`
- 本地分支与远程分支跟踪关系正常

## 步骤 4：推送

```bash
git push
```

如果你想更明确地推送当前分支，也可以：

```bash
git push -u origin HEAD
```

## 常见失败与定位方法

### A) 权限/仓库不存在

常见报错：

- `ERROR: Repository not found.`
- `Permission denied (publickey).`

处理：

- 确认你当前 SSH key 对应的 GitHub 账号对该仓库有写权限。
- 确认 `origin` 指向的仓库路径正确。

### B) 分支非快进（远端已有更新）

常见报错：

- `rejected (non-fast-forward)`

处理（谨慎使用，遵循团队策略）：

```bash
git pull --rebase
git push
```

### C) 需要更详细网络日志

当问题难以判断时，可以打开 Git 网络诊断输出：

```bash
GIT_CURL_VERBOSE=1 GIT_TRACE=1 git push
```

将关键报错片段提供给排查人员（注意不要泄露 token/敏感信息）。

## 参考：本次实际修复链路（复盘）

- 现象：`git push` 通过 HTTPS 报 443 连接超时。
- 动作：`curl -I https://github.com` 验证 HTTPS 链路不通/不稳定。
- 动作：把 `origin` 切换为 SSH：`git remote set-url origin git@github.com:surdring/GangQing.git`。
- 验证：`ssh -T git@github.com` 返回成功认证提示。
- 结果：`git push` 推送成功。
