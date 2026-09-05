# 光锥之内

当前进度：M1–M6 的本地工程路径已完成。系统包含真实 AADR 数据制品、六件证据工具、双 Agent、SSE、React + Canvas“落叶归树”、观众改方向、OpenAI-compatible 主备 provider 和显式本地保底重放。外部模型实 key 尚未提供，因此真实远程模型调用仍待验收。

## 启动演示

```bash
./scripts/run_demo.sh
```

打开 `http://127.0.0.1:5173/`。没有 API key 时自动使用 MockLLM；“启动本地保底重放”按钮始终通过 `/api/replays` 使用同一套调查 fixture，不依赖外网。

## 配置真实模型

完整手动步骤见 `docs/LLM_SETUP.md`，配置字段见 `.env.example`。在启动前导出主、备 provider 的 base URL、API key 和账号实际可调用的模型 ID。主 provider 对应 `gpt-5.6-sol` 配置位，备 provider 对应 `kimi-k3` 配置位；任一完整配置即可运行，两个都配置时按主到备自动切换。业务循环只读取 `agent/PROTOCOL.md` 定义的 canonical JSON action。

## 验证

```bash
envs/kalpatower/bin/python scripts/verify_m1.py
envs/kalpatower/bin/python -m unittest discover -s backend/tests -v
cd frontend
npm test
npm run build
```

M6 验收结果：20 项后端测试、1 项前端回归测试和 Vite 生产构建通过；本地 OpenAI-compatible HTTP 模拟服务验证了 JSON action、原生 `tool_calls` 翻译与主备切换；显式重放完成 20 个连续 SSE 事件。外部 provider 的真实联网调用等待 key。

## 数据制品

M1 使用 AADR v66.p1 真实公开数据。`artifacts/catalog.sqlite` 包含 21,433 个人物、23,089 条遗传数据表示、4,031 个遗址、23,089 条测年记录、709 条文献索引和 67,611 条外部 ID 映射。`artifacts/numeric/` 包含现代 Human Origins 建轴、古样本投影、共同观测 SNP 距离、重叠位点数与 TopN 近邻。

当前真实数值基准采用 256 个现代 HO 参考、64 个古样本和 20,000 个经 QC/LD pruning 的 SNP。它用于工具链复算与 smartpca 对照，不代表首发区域或最终展示内容。Mock 数值 fixture 保留为开发测试入口，不进入真实演示。
