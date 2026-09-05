from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


FilterAction = Literal["allow", "reject", "clarify"]


@dataclass(frozen=True)
class QueryDecision:
    action: FilterAction
    code: str
    message: str

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


_UNSAFE = (
    re.compile(r"忽略.{0,12}(指令|规则|提示词|system|developer)", re.I),
    re.compile(r"(系统提示词|开发者指令|system prompt|developer message|越狱|jailbreak)", re.I),
    re.compile(r"(读取|泄露|显示|输出).{0,10}(密钥|api.?key|环境变量|系统文件|提示词)", re.I),
    re.compile(r"(执行|运行).{0,8}(shell|终端|命令|代码)", re.I),
)

_IMPLAUSIBLE = (
    re.compile(r"(外星人|外星文明|火星人|et\b|穿越时空|魔法世界|修仙|霍格沃茨|漫威宇宙)", re.I),
    re.compile(r"(征服|统治|远征|迁徙到|出生于|死于).{0,8}(火星|月球|银河系|木星|土星)", re.I),
)

_PROCEDURAL_OFF_TOPIC = (
    re.compile(r"(菜谱|食谱)", re.I),
    re.compile(r"(红烧肉|炒菜|做饭|烹饪).{0,10}(做法|怎么做|教程|步骤|配方)", re.I),
    re.compile(r"(写|生成|调试|修复).{0,8}(代码|程序|网页|脚本|bug)", re.I),
    re.compile(r"(股票|基金|加密货币|比特币).{0,10}(买|卖|价格|行情|推荐|预测)", re.I),
    re.compile(r"(天气|天气预报|空气质量|比分|赛程|游戏攻略|彩票|星座运势)", re.I),
    re.compile(r"(诊断|处方|用药建议|治疗方案|法律建议|贷款建议)", re.I),
    re.compile(r"(写一首歌|写首歌|讲个笑话|写情书|写广告|翻译成)", re.I),
)

_HISTORICAL_SCOPE = re.compile(
    r"(历史|生平|年谱|年表|编年|家族|氏族|宗族|皇族|族群|民族|部族|王朝|朝代|政权|"
    r"迁徙|迁移|流徙|贬谪|任官|仕途|战争|战役|政治|治理|作品|诗词|文学|思想|后世影响|"
    r"考古|遗址|墓葬|陵墓|古尸|干尸|木乃伊|文物|出土|发掘|测年|古基因|基因组|古.?dna|"
    r"正史|史书|文献|方志|地方志|著录|善本|古籍|作品集|回忆录|谱系|世系|血缘|亲缘|"
    r"先秦|春秋战国|秦汉|魏晋|南北朝|隋唐|五代十国|北宋|南宋|辽金|元代|明代|清代|民国)",
    re.I,
)

_ENTITY_LIKE = re.compile(r"^[\u3400-\u9fffA-Za-z0-9·・\-—\s]{2,24}$")
_QUESTION_SHAPE = re.compile(r"(为何|为什么|如何|怎样|怎么|是谁|什么关系|有何影响|路线|身份|真伪|起源|兴衰|演变)")
_EMPTY_OR_GENERIC = re.compile(r"^(你好|您好|谢谢|测试|试试|随便|不知道|哈哈+|呵呵+|帮我看看|说点什么)[！!。.?？\s]*$", re.I)


def screen_question(question: str, *, context: str | None = None) -> QueryDecision:
    text = " ".join(question.strip().split())
    if not text:
        return QueryDecision("clarify", "empty_query", "请输入要调查的历史对象或问题。")
    if len(text) > 300:
        return QueryDecision("reject", "query_too_long", "问题过长，请用一句话说明调查对象和核心问题。")
    if any(pattern.search(text) for pattern in _UNSAFE):
        return QueryDecision("reject", "unsafe_request", "请求包含与历史策展无关的系统操作，已停止。")
    if any(pattern.search(text) for pattern in _IMPLAUSIBLE):
        return QueryDecision(
            "reject",
            "implausible_premise",
            "问题包含无法建立可信证据链的虚构设定，请改问可核验的历史对象或事件。",
        )
    if any(pattern.search(text) for pattern in _PROCEDURAL_OFF_TOPIC):
        return QueryDecision(
            "reject",
            "out_of_scope",
            "该问题超出历史策展范围，请改问人物、家族、族群、遗址、文献、考古或古基因组。",
        )
    if context:
        return QueryDecision("allow", "contextual_followup", "")
    if _HISTORICAL_SCOPE.search(text):
        return QueryDecision("allow", "historical_scope", "")
    if _ENTITY_LIKE.fullmatch(text) and not _EMPTY_OR_GENERIC.fullmatch(text):
        return QueryDecision("allow", "historical_entity", "")
    if _QUESTION_SHAPE.search(text) and len(text) <= 100:
        return QueryDecision("allow", "historical_question", "")
    return QueryDecision(
        "clarify",
        "scope_unclear",
        "请说明要调查的历史人物、家族、族群、遗址、文献或古基因组对象。",
    )
