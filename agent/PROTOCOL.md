# 调查 Agent canonical action protocol

业务循环只接收以下三种 JSON 动作，不直接接收任何厂商的 tool-call 对象。

“停止调查”等控制指令由 investigation 会话 API 处理，不进入本协议，也不成为树的根节点。新问题默认创建独立 investigation；只有用户明确选择“沿本次继续”才沿用原会话。

```json
{"type":"tool_call","motivation":"下一步动机","tool":"search_ancient_samples","arguments":{"individual":"Tianyuan"}}
```

```json
{"type":"narration","text":"第三人称纪录片旁白。"}
```

```json
{"type":"finish","text":"本轮调查总结。"}
```

`tool` 只能取后端公布的六件工具。`arguments` 遵循 `/api/tools` 返回的参数说明。工具结果统一包含 `status`，取值为 `ok`、`no_data`、`no_genotype` 或 `unknown_place`。空结果进入后续推理，不能转换为异常或虚构事实。

OpenAI-compatible adapter 支持两种模型返回：原生 `message.tool_calls` 会被翻译为 `tool_call`；没有原生工具调用的模型按上述 JSON action 输出。模型名、base URL 和 key 只存在于环境配置，调查循环与 SSE 事件不包含厂商专属结构。
