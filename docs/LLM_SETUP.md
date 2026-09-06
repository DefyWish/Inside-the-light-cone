# 光锥之内：LLM API 手动接入

后端在启动时读取环境变量。配置必须与 `./scripts/run_demo.sh` 在同一个终端会话中完成；修改变量后需要重启服务。

`LIGHTCONE_RESEARCH_MODE=auto` 会在 Kimi 配置可用时复用同一 API key，通过官方 `moonshot/web-search:latest` Formula 执行研究 Agent 联网检索。设为 `mock` 可强制使用本地研究语料。

## 1. 获取 API key

- OpenAI：在 [API Keys](https://platform.openai.com/api-keys) 创建 key。官方 [Quickstart](https://developers.openai.com/api/docs/quickstart) 使用 Bearer key；`gpt-5.6-sol` 的官方模型页确认支持 `v1/chat/completions`。
- Kimi：在 [Kimi API Keys](https://platform.kimi.com/console/api-keys) 创建 key。官方 [快速开始](https://platform.kimi.com/docs/overview) 给出的 base URL 为 `https://api.moonshot.cn/v1`，模型 ID 为 `kimi-k3`，接口兼容 OpenAI API 格式。

不要把 key 写进代码、提交到 Git 或发到对话里。

## 2. 配置 OpenAI 主 provider

在 macOS Terminal 中执行：

```bash
cd /Users/wangxiuyuan/Documents/AIx_Shenzhen_Hackson
export LIGHTCONE_PROVIDER_MODE=auto
export LIGHTCONE_PRIMARY_BASE_URL=https://api.openai.com/v1
export LIGHTCONE_PRIMARY_MODEL=gpt-5.6-sol
read -s "LIGHTCONE_PRIMARY_API_KEY?OpenAI API Key: "
export LIGHTCONE_PRIMARY_API_KEY
echo
```

只配置 OpenAI 也可以启动。

## 3. 配置 Kimi 备用 provider

继续在同一个 Terminal 中执行：

```bash
export LIGHTCONE_BACKUP_BASE_URL=https://api.moonshot.cn/v1
export LIGHTCONE_BACKUP_MODEL=kimi-k3
read -s "LIGHTCONE_BACKUP_API_KEY?Kimi API Key: "
export LIGHTCONE_BACKUP_API_KEY
echo
```

主、备都配置时，后端先调用 OpenAI；主 provider 请求失败或返回无法解析的动作时，后续动作切换到 Kimi。

## 4. 启动与核验

```bash
./scripts/run_demo.sh
```

另开一个 Terminal 查看运行状态：

```bash
curl -s http://127.0.0.1:18765/health
```

双 provider 配置成功时，返回值中的 `provider` 应包含：

```text
primary:gpt-5.6-sol → backup:kimi-k3
```

页面中的“开始新调查”使用真实 provider。保底重放接口仍保留在后端，不在主界面显示。

## 5. 常用切换

只用 Kimi：不要设置 `LIGHTCONE_PRIMARY_*`，只设置完整的 `LIGHTCONE_BACKUP_*`。

强制本地 Mock：

```bash
export LIGHTCONE_PROVIDER_MODE=mock
./scripts/run_demo.sh
```

清除当前终端里的 key：

```bash
unset LIGHTCONE_PRIMARY_API_KEY LIGHTCONE_BACKUP_API_KEY
```
