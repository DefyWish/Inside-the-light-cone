from __future__ import annotations

import asyncio
import http.client
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


REMOTE_HTTP_LOCK = threading.RLock()


def _build_ssl_context() -> ssl.SSLContext:
    # macOS conda 环境自带 openssl 证书目录常为空，urllib 默认上下文找不到 CA 根；
    # 统一改用 certifi 的 CA 包，缺失时退回系统默认。
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CONTEXT = _build_ssl_context()

# 部分中转站（Cloudflare）按 UA 封禁 Python-urllib，统一伪装浏览器 UA
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class ClaimLink(BaseModel):
    target: str
    predicate: Literal[
        "supports", "contradicts", "kin", "same_site",
        "contemporaneous", "part_of", "derived_from",
    ]
    note: str | None = None


class CurationEventDraft(BaseModel):
    event_id: str | None = None
    subject_ids: list[str] = Field(default_factory=list)
    title: str
    summary: str
    branch: str
    event_type: str
    event_year_start: int | None = None
    event_year_end: int | None = None
    date_text: str | None = None
    time_precision: Literal["exact", "year", "range", "circa", "period", "unknown"] = "unknown"
    historical_place: str | None = None
    modern_place: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_precision: str | None = None
    epistemic_status: Literal["fact", "view", "disputed", "gap"] = "fact"
    source_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    movement: dict[str, Any] | None = None


class AgentAction(BaseModel):
    type: Literal["tool_call", "narration", "finish", "claim", "plan", "curation_event"]
    motivation: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None
    lines: list[str] = Field(default_factory=list)
    line_status: list[dict[str, Any]] = Field(default_factory=list)
    line: str | None = None
    claim: str | None = None
    claim_id: str | None = None
    status: Literal["open", "strengthened", "challenged", "dropped"] | None = None
    evidence_level: Literal["fact_genomic", "fact_archaeology", "fact_documentary", "view_model"] | None = None
    event_year_start: int | None = None
    event_year_end: int | None = None
    links: list[ClaimLink] = Field(default_factory=list)
    event: CurationEventDraft | None = None


@dataclass
class InvestigationState:
    question: str
    observations: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    curation_events: list[dict[str, Any]] = field(default_factory=list)
    provider_cursor: int = 0
    provider_scenario: str | None = None


class LLMProvider(ABC):
    """Provider-neutral boundary consumed by the investigation loop."""

    name: str

    @abstractmethod
    async def next_action(self, state: InvestigationState) -> AgentAction:
        raise NotImplementedError


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(self, fixture_path: Path) -> None:
        payload = json.loads(fixture_path.read_text())
        self.scenarios = payload["scenarios"]

    def _select_scenario(self, question: str) -> dict[str, Any]:
        normalized = question.casefold()
        for scenario in self.scenarios:
            terms = scenario.get("match_contains", [])
            if terms and any(term.casefold() in normalized for term in terms):
                return scenario
        return next(scenario for scenario in self.scenarios if not scenario.get("match_contains"))

    @staticmethod
    def _render(value: Any, question: str) -> Any:
        if isinstance(value, str):
            return value.replace("{{question}}", question)
        if isinstance(value, list):
            return [MockLLM._render(item, question) for item in value]
        if isinstance(value, dict):
            return {key: MockLLM._render(item, question) for key, item in value.items()}
        return value

    async def next_action(self, state: InvestigationState) -> AgentAction:
        scenario = self._select_scenario(state.question)
        state.provider_scenario = scenario["id"]
        actions = scenario["actions"]
        if state.provider_cursor >= len(actions):
            return AgentAction(type="finish", text="调查循环已完成。")
        payload = self._render(actions[state.provider_cursor], state.question)
        state.provider_cursor += 1
        return AgentAction.model_validate(payload)


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    api_key: str
    model: str
    provider_name: str
    timeout_seconds: float = 90.0


SYSTEM_PROMPT = """你是光锥之内的调查与策展 Agent。每轮只输出一个动作。
动作使用 provider-neutral JSON：
1. 拆解计划：{"type":"plan","lines":["主线1","主线2","主线3","主线4"]} —— 调查早期必须先把问题拆成4-8条调查主线
2. 调工具：{"type":"tool_call","motivation":"为什么查","tool":"工具名","arguments":{}}
3. 形成判断：{"type":"claim","claim":"一个可被证据支撑的判断","line":"所属主线（与计划文字一致）","evidence_level":"fact_genomic|fact_archaeology|fact_documentary|view_model","event_year_start":整数或null,"event_year_end":整数或null,"links":[{"target":"既有claim编号或证据名称","predicate":"supports|contradicts|kin|same_site|contemporaneous|part_of|derived_from","note":"可选"}]}
4. 主线了断：{"type":"plan","line_status":[{"line":"主线文字","status":"covered|gap","note":"简述"}]} —— covered 表示该线已有带外部证据的claim，gap 表示该线确无证据
5. 生成策展节点：{"type":"curation_event","event":{"title":"短标题","summary":"故事摘要","branch":"由本轮问题动态形成的主题枝","event_type":"迁徙|任职|作品|思想|战争|亲缘|考古|文献|影响|争议|其他","subject_ids":["对象名或权威ID"],"event_year_start":整数或null,"event_year_end":整数或null,"date_text":"原始年代文字或null","time_precision":"exact|year|range|circa|period|unknown","historical_place":"历史地名或null","modern_place":"现代地名或null","latitude":数字或null,"longitude":数字或null,"place_precision":"地点精度说明或null","epistemic_status":"fact|view|disputed|gap","source_ids":["来源ID"],"claim_ids":["c1"],"evidence_ids":["证据ID"],"movement":{"kind":"赴任|贬谪|迁居|征战|其他","from":{"name":"地点","latitude":数字,"longitude":数字},"to":{"name":"地点","latitude":数字,"longitude":数字}}或null}}
6. 纪录片旁白：{"type":"narration","text":"第三人称、带证据边界的叙述"}
7. 收束：{"type":"finish","text":"本轮总结"}
只输出一个 JSON 对象，不要 Markdown。
工作方式：先拆解，再逐线调查。收束的硬条件：每一条主线都必须了断（covered 或 gap），少一条都会被驳回。单条主线的漂亮叙事不是情报，是摘要。
证据检索采用本地优先：先查询 search_curated_sources、search_literature 与本地 AADR 工具，充分复用策展主题包和 research_staging 既有成果；本地返回 no_data、unknown_place 或明确证据缺口后，再等待研究 Agent 联网补证。不得为了重复确认本地已有材料而反复外派。
claim 是情报网的节点：每条 claim 必须属于一条主线，并尽量与**其他主线的** claim 连线——跨线的 supports/contradicts/derived_from 才是网络，同线串联只是目录。
curation_event 是地图、生命树、时间轴共享的投影节点。它必须来自本轮实际检索到的证据或 claim，引用 source_ids、claim_ids、evidence_ids 中至少一种；不得按人物姓名套用预设路线、预设故事或固定分支。branch 依据用户问题与本轮计划动态命名。同一资料在不同问题下可以生成不同的节点与分支。每个带坐标的节点只填写与该坐标对应的一个历史地点和一个现代地点，禁止把出发地与目的地合写在地点字段。只有证据明确支持真实位移时才填写 movement；movement 的 from/to 分别保存起点与终点，节点自身地点和坐标使用终点。带坐标的普通事件只落点，不连成迁徙线。区域深时背景、对照人群、阴性结果、尚未与调查对象直接对应的样本和证据缺口只保留在调查报告的证据边界中，不生成地图点、时间轴节点或迁徙线。已取得且与对象直接相关的证据都应保留为策展叶片，最终收束只更新和补充节点，不删减早期证据。后世影响沿时间轴继续展开。年代或地点未知时保留 unknown/gap，禁止补造。
历史、考古与数字人文问题的候选主线：人物生平、迁徙与任职、作品与思想、文献记载、考古证据、古基因组证据、族群与亲缘、地名沿革、争议与反方、后世影响。按问题现场裁剪，不必全用。
同一历史事件在史传、当事人记述、地方记忆、考古材料和遗传研究中出现的矛盾解释是高价值证据，必须分别成 claim 并以 contradicts 相连。
claim 带明暗状态：新生成时 status=open（暗线/待证）；证据充分时更新为 strengthened；遭遇反证时 challenged；被证伪时 dropped。更新方式：{"type":"claim","claim_id":"既有编号","status":"新状态","motivation":"为什么"}。
暗线嗅觉：调查途中特别留意四类异常——①同一事件不同主体给出互相矛盾的解释；②权利、归属或主导权发生突变；③长期沉寂的对象在某项条件变化后重新活跃；④表面无关的实体共享关键人物、机构或来源。撞到异常即形成 open 状态的 claim，继续追。
策展别名卡是线索不是证据（始终为 view_model）：其内容必须经工具检索到外部来源核实后才能支撑 claim；不得仅凭别名卡就形成并收束 claim。
研究 Agent 返回的 claim 是历史事件或判断，event_year_start/event_year_end 是该事件的时间，relation_to_question 是它与主问题的关系，narrative_role 是它在故事中的位置。规划下一步时沿这些关系追问，避免重复搜索同一消息。
历史人物、历史事件或墓葬问题优先查文献与考古；没有该人物本人的已发表古 DNA 证据时，不得把同一地区其他时代的古样本挂到人物名下。
按地点扩大古样本范围时，必须忠于用户明确提出的空间与时间范围；用户没有要求时，不得擅自从历史时期扩展到史前时期。
研究 Agent 的 pending 表示联网搜索仍在进行，此时不得用无关的宽泛查询填补等待时间。
停止、终止、退出等控制指令不属于调查对象。无数据是正常结果；不得编造人物、关系、年代、引文、身份、血缘或成分百分比。古基因组事实、考古事实和研究模型必须保持原有证据层级。
收束文本要形成连续叙事：从问题的历史起点进入，说明各主线上的关键事件、证据转折、跨线的连接与矛盾，最后落到仍未解决的缺口。不要逐条复述链接标题。"""


class OpenAICompatibleLLM(LLMProvider):
    def __init__(self, config: OpenAICompatibleConfig, tools: list[dict[str, Any]]) -> None:
        self.config = config
        self.tools = tools
        self.native_tools = self._native_tool_definitions(tools)
        self.name = config.provider_name

    @staticmethod
    def _native_tool_definitions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for tool in tools:
            properties: dict[str, Any] = {
                "motivation": {
                    "type": "string",
                    "description": "本轮调用怎样推进证据脉络",
                }
            }
            required = ["motivation"]
            for name, declared_type in tool.get("arguments", {}).items():
                optional = str(declared_type).endswith("?")
                value_type = str(declared_type).removesuffix("?")
                if value_type == "number":
                    schema = {"type": "number"}
                elif value_type == "integer":
                    schema = {"type": "integer"}
                elif value_type == "all_periods":
                    schema = {"type": "string", "enum": ["all_periods"]}
                else:
                    schema = {"type": "string"}
                properties[name] = schema
                if not optional:
                    required.append(name)
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": str(tool.get("description") or tool["name"]),
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    },
                }
            )
        definitions.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "update_plan",
                        "description": "拆解调查主线（调查早期必须）或了断主线状态。收束前每条主线都必须 covered 或 gap。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "lines": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "调查主线清单（4-8条），仅在拆解时提供",
                                },
                                "line_status": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "line": {"type": "string"},
                                            "status": {"type": "string", "enum": ["covered", "gap"]},
                                            "note": {"type": "string"},
                                        },
                                        "required": ["line", "status"],
                                    },
                                },
                            },
                            "required": [],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "record_claim",
                        "description": "形成一个可被证据支撑的历史判断（claim），并可用 links 连接证据或其他 claim。收束前至少要有一个 claim 或明确缺口。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "claim": {"type": "string", "description": "历史判断的陈述；更新状态时留空"},
                                "line": {"type": "string", "description": "所属调查主线（与计划文字一致）"},
                                "claim_id": {"type": "string", "description": "要更新状态的既有 claim 编号（如 c1）；新建时留空"},
                                "status": {
                                    "type": "string",
                                    "enum": ["open", "strengthened", "challenged", "dropped"],
                                    "description": "明暗状态：open 待证/暗线，strengthened 升格明线，challenged 遇反证，dropped 证伪",
                                },
                                "evidence_level": {
                                    "type": "string",
                                    "enum": ["fact_genomic", "fact_archaeology", "fact_documentary", "view_model"],
                                },
                                "event_year_start": {"type": ["integer", "null"]},
                                "event_year_end": {"type": ["integer", "null"]},
                                "links": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "target": {"type": "string", "description": "既有 claim 编号或证据名称"},
                                            "predicate": {
                                                "type": "string",
                                                "enum": [
                                                    "supports", "contradicts", "kin",
                                                    "same_site", "contemporaneous",
                                                    "part_of", "derived_from",
                                                ],
                                            },
                                            "note": {"type": "string"},
                                        },
                                        "required": ["target", "predicate"],
                                    },
                                },
                                "motivation": {"type": "string"},
                            },
                            "required": [],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "record_curation_event",
                        "description": "把已检索证据与判断投影成地图、生命树和时间轴共享的策展节点。主题枝由当前问题动态产生。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "event": {
                                    "type": "object",
                                    "properties": {
                                        "event_id": {"type": "string"},
                                        "subject_ids": {"type": "array", "items": {"type": "string"}},
                                        "title": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "branch": {"type": "string"},
                                        "event_type": {"type": "string"},
                                        "event_year_start": {"type": ["integer", "null"]},
                                        "event_year_end": {"type": ["integer", "null"]},
                                        "date_text": {"type": ["string", "null"]},
                                        "time_precision": {"type": "string", "enum": ["exact", "year", "range", "circa", "period", "unknown"]},
                                        "historical_place": {"type": ["string", "null"]},
                                        "modern_place": {"type": ["string", "null"]},
                                        "latitude": {"type": ["number", "null"]},
                                        "longitude": {"type": ["number", "null"]},
                                        "place_precision": {"type": ["string", "null"]},
                                        "epistemic_status": {"type": "string", "enum": ["fact", "view", "disputed", "gap"]},
                                        "source_ids": {"type": "array", "items": {"type": "string"}},
                                        "claim_ids": {"type": "array", "items": {"type": "string"}},
                                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                                        "movement": {"type": ["object", "null"]}
                                    },
                                    "required": ["title", "summary", "branch", "event_type", "subject_ids", "time_precision", "epistemic_status", "source_ids", "claim_ids", "evidence_ids"]
                                }
                            },
                            "required": ["event"],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "narrate_investigation",
                        "description": "发布一段连接既有证据的第三人称阶段叙述。",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "finish_investigation",
                        "description": "证据链已经形成或已明确留下缺口时，输出连续的最终叙事并结束调查。",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                },
            ]
        )
        return definitions

    @property
    def uses_native_tools(self) -> bool:
        model = self.config.model.casefold()
        return model.startswith(("kimi", "gpt-"))

    @property
    def chat_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _messages(self, state: InvestigationState) -> list[dict[str, str]]:
        tool_text = json.dumps(self.tools, ensure_ascii=False, separators=(",", ":"))
        observations = json.dumps(
            state.observations[-12:],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        lines_text = json.dumps(
            [{"line": line["line"], "status": line["status"]} for line in state.lines],
            ensure_ascii=False,
        )
        native_instruction = (
            "\n当前 adapter 已提供原生函数。每轮只调用一个函数；调查完成时调用 finish_investigation。"
            if self.uses_native_tools
            else ""
        )
        return [
            {
                "role": "system",
                "content": f"{SYSTEM_PROMPT}{native_instruction}\n可用工具：{tool_text}",
            },
            {
                "role": "user",
                "content": (
                    f"调查问题：{state.question}\n"
                    f"已执行步数：{state.provider_cursor}\n"
                    f"调查主线及其状态：{lines_text}\n"
                    f"已形成的 claim：{json.dumps([{'id': c['claim_id'], 'line': c.get('line'), 'status': c.get('status'), 'text': c['text'][:40]} for c in state.claims[-10:]], ensure_ascii=False)}\n"
                    f"已形成的关系数：{len(state.relations)}\n"
                    f"已生成的策展节点：{json.dumps([{'id': e['event_id'], 'branch': e['branch'], 'title': e['title']} for e in state.curation_events[-12:]], ensure_ascii=False)}\n"
                    f"最近工具结果：{observations}\n"
                    "选择下一动作。"
                ),
            },
        ]

    def _request(self, state: InvestigationState) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with REMOTE_HTTP_LOCK:
                    request_body: dict[str, Any] = {
                        "model": self.config.model,
                        "messages": self._messages(state),
                    }
                    if self.config.model.casefold().startswith("kimi-k3"):
                        request_body["reasoning_effort"] = "high"
                    if self.uses_native_tools:
                        request_body["tools"] = self.native_tools
                    payload = json.dumps(
                        request_body,
                        ensure_ascii=False,
                    ).encode("utf-8")
                    request = urllib.request.Request(
                        self.chat_url,
                        data=payload,
                        headers={
                            "Authorization": f"Bearer {self.config.api_key}",
                            "Content-Type": "application/json",
                            "User-Agent": HTTP_USER_AGENT,
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=self.config.timeout_seconds, context=SSL_CONTEXT) as response:
                        return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                last_error = error
                if attempt == 0 and (error.code == 429 or error.code >= 500):
                    time.sleep(1)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as error:
                last_error = error
                if attempt == 0:
                    time.sleep(1)
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("remote provider request failed")

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict)
            )
        return ""

    @staticmethod
    def _parse_json_action(text: str) -> AgentAction:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("provider response does not contain a JSON action")
        return AgentAction.model_validate(json.loads(cleaned[start : end + 1]))

    @classmethod
    def _translate_message(cls, message: dict[str, Any]) -> AgentAction:
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            function = tool_calls[0].get("function", {})
            raw_arguments = function.get("arguments", {})
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
            arguments = dict(arguments or {})
            name = function.get("name")
            if name == "update_plan":
                return AgentAction(
                    type="plan",
                    lines=arguments.get("lines") or [],
                    line_status=arguments.get("line_status") or [],
                )
            if name == "record_claim":
                return AgentAction(
                    type="claim",
                    claim=str(arguments.pop("claim", "")) or None,
                    line=arguments.pop("line", None) or None,
                    claim_id=arguments.pop("claim_id", None) or None,
                    status=arguments.pop("status", None) or None,
                    evidence_level=arguments.pop("evidence_level", None) or None,
                    event_year_start=arguments.pop("event_year_start", None),
                    event_year_end=arguments.pop("event_year_end", None),
                    links=arguments.pop("links", []) or [],
                    motivation=str(arguments.pop("motivation", "")) or None,
                )
            if name == "record_curation_event":
                return AgentAction(type="curation_event", event=arguments.get("event"))
            if name == "narrate_investigation":
                return AgentAction(type="narration", text=str(arguments.get("text") or ""))
            if name == "finish_investigation":
                return AgentAction(type="finish", text=str(arguments.get("text") or "调查完成。"))
            return AgentAction(
                type="tool_call",
                motivation=str(arguments.pop("motivation", "")) or None,
                tool=name,
                arguments=arguments,
            )
        return cls._parse_json_action(cls._content_text(message.get("content")))

    async def next_action(self, state: InvestigationState) -> AgentAction:
        response = await asyncio.to_thread(self._request, state)
        message = response["choices"][0]["message"]
        action = self._translate_message(message)
        state.provider_cursor += 1
        state.provider_scenario = self.name
        return action


class FailoverLLMProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.active_index = 0
        self.name = " → ".join(provider.name for provider in providers)

    async def next_action(self, state: InvestigationState) -> AgentAction:
        errors: list[str] = []
        for index in range(self.active_index, len(self.providers)):
            provider = self.providers[index]
            try:
                action = await provider.next_action(state)
                self.active_index = index
                return action
            except Exception as error:
                errors.append(f"{provider.name}: {type(error).__name__}: {error}")
                self.active_index = min(index + 1, len(self.providers) - 1)
        raise RuntimeError("all configured LLM providers failed: " + " | ".join(errors))


def _provider_setting(name: str, default: str = "") -> str:
    return os.getenv(f"LIGHTCONE_{name}", os.getenv(f"JIALUO_{name}", default))


def provider_from_environment(
    fixture_path: Path,
    tools: list[dict[str, Any]],
) -> LLMProvider:
    mode = _provider_setting("PROVIDER_MODE", "auto").strip().casefold()
    if mode == "mock":
        return MockLLM(fixture_path)

    configured: list[LLMProvider] = []
    for slot, default_name in (("PRIMARY", "gpt-5.6-sol"), ("BACKUP", "kimi-k3")):
        base_url = _provider_setting(f"{slot}_BASE_URL").strip()
        api_key = _provider_setting(f"{slot}_API_KEY").strip()
        model = _provider_setting(f"{slot}_MODEL", default_name).strip()
        if base_url and api_key and model:
            configured.append(
                OpenAICompatibleLLM(
                    OpenAICompatibleConfig(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        provider_name=f"{slot.casefold()}:{model}",
                    ),
                    tools,
                )
            )
    if not configured:
        return MockLLM(fixture_path)
    if len(configured) == 1:
        return configured[0]
    return FailoverLLMProvider(configured)
