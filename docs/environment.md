# Environment

## 首版必需

- Python 3.11+
- Git

## 推荐

- `uv`：Python 项目管理。
- `pytest`：规则回归测试。

## 平台接入可选

- `TIANGONG_SUPABASE_URL`：天工平台使用的 Supabase 地址。
- `TIANGONG_SUPABASE_ANON_KEY`：平台公开的 publishable key。
- `TIANGONG_ADMIN_ACCESS_TOKEN`、`TIANGONG_ADMIN_EMAIL`、`TIANGONG_ADMIN_PASSWORD`：
  主账号配置，用于读取管理员队列和执行经确认的分配操作。`ACCESS_TOKEN` 可填写从网页复制的临时通行证。
- `TIANGONG_MEMBER_ACCESS_TOKEN`、`TIANGONG_MEMBER_EMAIL`、`TIANGONG_MEMBER_PASSWORD`：
  副账号配置，用于读取审核员队列和执行经确认的二次审核提交。`ACCESS_TOKEN` 可填写从网页复制的临时通行证。
- `TIANGONG_API_ALLOW_WRITES`：默认必须为 `false`。
- 审核管理员和审核员账号权限。

从 `.env.example` 复制出本地 `.env` 后填写配置，客户端会自动读取当前目录中的
`.env`。账号、token、API key 和 `.env` 不得提交到仓库，也不得粘贴到聊天或案件
记录。

每个账号都支持两种认证方式并可同时配置：

```env
TIANGONG_ADMIN_ACCESS_TOKEN=<主账号网页临时通行证，可留空>
TIANGONG_ADMIN_EMAIL=main@example.com
TIANGONG_ADMIN_PASSWORD=...
TIANGONG_MEMBER_ACCESS_TOKEN=<副账号网页临时通行证，可留空>
TIANGONG_MEMBER_EMAIL=second@example.com
TIANGONG_MEMBER_PASSWORD=...
```

客户端会优先使用对应账号的 `ACCESS_TOKEN`。未填写令牌，或令牌失效并收到 HTTP 401
时，如果已填写该账号的邮箱和密码，客户端会自动登录、获取新令牌并把原请求重试一次。

命令行可显式选择登录账号。`fetch-tasks --role admin` 默认使用 `admin` 账号；
`fetch-tasks --role member` 默认使用 `member` 账号。`fetch-dataset` 需要按任务所属账号
显式加 `--account-role admin` 或 `--account-role member`。`submit-result` 默认使用
`member` 账号。

建议为程序创建权限受限的审核专用账号，不要使用个人主账号。自动登录不会自动开启
写操作，`TIANGONG_API_ALLOW_WRITES=false` 仍然生效。
