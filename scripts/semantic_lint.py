#!/usr/bin/env python3
"""Build and lint a surface-independent bilingual prompt program.

V7-07 does not translate arbitrary scene prose. It requires a hash-bound
English/zh-Hans catalog carrying a human-attestation declaration, validates semantic
coverage, and emits provenance units that later surface rendering cannot
silently reorder or drop.  Structural parity is machine checked; translation
quality remains a separately reviewed human judgment.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Support both ``python scripts/...`` and package imports.
    from . import reference_planner
    from . import render_surface_bindings as bindings
    from . import scene_ir_check
except ImportError:  # pragma: no cover - exercised by CLI tests
    import reference_planner
    import render_surface_bindings as bindings
    import scene_ir_check


CATALOG_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/"
    "schemas/prompt-realization-catalog.schema.json"
)
PROGRAM_SCHEMA_URI = (
    "https://github.com/Emily2040/seedance-2.0/schemas/prompt-program.schema.json"
)
CATALOG_KEYS = {
    "$schema", "schema_version", "scene_ir_sha256", "attestation", "entries"
}
ATTESTATION_KEYS = {"method", "linguistic_equivalence", "locales"}
ENTRY_KEYS = {"semantic_key", "source_sha256", "en", "zh_hans"}
LINT_REQUEST_KEYS = {"schema_version", "reference_manifest", "scene_ir", "realization_catalog"}

MAX_CATALOG_ENTRIES = 512
MAX_REALIZATION_TEXT = 1000
MAX_COMPILER_INPUT_BYTES = 64 * 1024 * 1024
SAFE_SEMANTIC_KEY = re.compile(r"^[a-z][a-z0-9._-]{2,255}$")
ENTITY_TOKEN = re.compile(r"\{entity:([a-z][a-z0-9._-]{0,63})\}")
REFERENCE_SKELETON = re.compile(
    r"@(?:image|video|audio)\s*[0-9]+"
    r"|(?:^|[^a-z0-9_])(?:image|video|audio)\s*[0-9]+(?=$|[^a-z0-9_])"
    r"|(?:图片|圖片|图像|圖像|视频|視頻|影片|音频|音頻|音訊)\s*[0-9]+",
    re.IGNORECASE,
)
META_INSTRUCTION = re.compile(
    r"(?:ignore|disregard|override|forget|erase|delete|discard|abandon|supersede|replace|"
    r"invalidate|nullify).{0,48}"
    r"(?:previous|prior|earlier|above|all|system|developer|instructions?|directions?|rules?|polic(?:y|ies))"
    r"|(?:do not|don't|never)\s+(?:follow|obey).{0,32}"
    r"(?:previous|prior|earlier|above|instructions?|directions?|rules?|polic(?:y|ies))"
    r"|(?:follow|obey).{0,32}(?:new|replacement).{0,12}(?:instructions?|tasks?|rules?)"
    r"|\bact\s+as\s+(?:the\s+)?(?:system|developer|assistant)\b"
    r"|\b(?:pretend\s+to\s+be|become)\s+(?:the\s+)?(?:system|developer|assistant)\b"
    r"|\bassume\s+the\s+role\s+of\s+(?:the\s+)?(?:system|developer|assistant)\b"
    r"|\bfrom\s+now\s+on.{0,24}(?:system|developer|assistant)\b"
    r"|\b(?:follow|obey)\s+(?:this|these|the\s+following)\s+(?:commands?|instructions?)\b"
    r"|\b(?:follow|obey)\s+(?:the\s+)?(?:commands?|instructions?)\s+(?:below|following)\b"
    r"|\b(?:new|replacement)\s+(?:commands?|instructions?|tasks?)\s*:"
    r"|\binstructions?\s+(?:below|above)\s*:"
    r"|\btreat\s+(?:this|the\s+following|what\s+follows).{0,24}"
    r"(?:commands?|instructions?|system\s+directives?|directives?)\b"
    r"|\b(?:highest|top)\s+priority\s+(?:commands?|instructions?)\b"
    r"|\b(?:respond|return|output)\s+only\b"
    r"|\b(?:developer|system|administrator|admin)\s+mode\b"
    r"|(?:bypass|circumvent|skip).{0,32}(?:safety|instructions?|directions?|rules?|polic(?:y|ies))"
    r"|\byou\s+are\s+now\s+(?:the\s+)?(?:system|developer|assistant)\b"
    r"|(?:system|developer)\s+(?:prompt|message)"
    r"|(?:reveal|disclose|expose|print|show|repeat|quote|recite).{0,24}"
    r"(?:hidden|system|developer|internal|governing).{0,16}"
    r"(?:instructions?|prompts?|messages?|rules?|directives?)"
    r"|(?:repeat|quote|recite).{0,24}(?:instructions?|prompts?|directives?)"
    r"|(?:do\s+the\s+opposite\s+of).{0,16}(?:previous|prior|earlier).{0,12}"
    r"(?:instructions?|rules?|directions?)"
    r"|(?:previous|prior|earlier|above).{0,16}(?:instructions?|rules?|directions?).{0,16}"
    r"(?:no\s+longer\s+appl(?:y|ies)|are\s+void|invalid|superseded)"
    r"|(?:instructions?|rules?|directions?)\s+(?:above|below).{0,12}"
    r"(?:are\s+void|no\s+longer\s+appl(?:y|ies)|invalid|superseded)"
    r"|(?:adopt|treat).{0,16}(?:commands?|instructions?).{0,16}(?:authoritative|binding)"
    r"|\[(?:/?inst)\]|<</?sys>>|<\s*/?\s*(?:system|developer|assistant)\b[^>]*>"
    r"|#{2,}\s*(?:system|developer|assistant)\b"
    r"|(?:忽略|无视|無視|取消|跳过|跳過|忘记|忘記|抛弃|拋棄|丢弃|丟棄|删除|刪除).{0,24}"
    r"(?:之前|以上|先前|所有|系统|系統|開發者|开发者|指令|提示|规则|規則|要求)"
    r"|(?:不要|不得|无需|無需).{0,8}(?:遵循|遵守|执行|執行).{0,24}"
    r"(?:之前|以上|先前|系统|系統|指令|提示|规则|規則)"
    r"|(?:系统|系統|开发者|開發者)(?:提示|消息|訊息|指令)"
    r"|(?:泄露|洩露|透露|显示|顯示|输出|輸出).{0,16}"
    r"(?:隐藏|隱藏|系统|系統|开发者|開發者|内部|內部).{0,12}(?:指令|提示|消息|訊息|规则|規則)"
    r"|(?:切换|切換|进入|進入).{0,8}(?:开发者|開發者|系统|系統|管理员|管理員)模式"
    r"|(?:服从|服從|遵循|执行|執行).{0,8}(?:以下|下列|此)(?:命令|指令|要求)"
    r"|把.{0,12}(?:以下|下列|此).{0,12}当作.{0,12}"
    r"(?:最高|最高优先级|最高優先級).{0,8}(?:指令|命令)"
    r"|(?:假装|假裝|扮演|成为|成為).{0,8}(?:系统|系統|开发者|開發者|助手)"
    r"|从现在开始.{0,16}(?:系统|系統|开发者|開發者|助手)"
    r"|(?:视为|視為|当作|當作|作为|作為).{0,12}(?:系统|系統)?(?:命令|指令|要求)"
    r"|(?:最高优先级|最高優先級).{0,8}(?:命令|指令)"
    r"|(?:以下|下面|下列).{0,4}(?:命令|指令)"
    r"|(?:先前|之前|以上).{0,12}(?:规则|規則|指令|要求).{0,12}"
    r"(?:作废|作廢|不再生效|失效|无效|無效)"
    r"|(?:改写|改寫|取代|替换|替換).{0,16}(?:系统|系統|原有|先前).{0,8}"
    r"(?:约束|約束|规则|規則|指令)"
    r"|(?:用|以).{0,8}(?:下列|以下).{0,4}(?:要求|指令|命令).{0,8}"
    r"(?:取代|替换|替換).{0,8}(?:原|先前).{0,4}(?:规则|規則|指令|要求)"
    r"|(?:复述|復述|引用|重复|重複).{0,16}(?:内部|內部|隐藏|隱藏|系统|系統).{0,8}"
    r"(?:提示|指令|命令)"
    r"|只(?:回复|回覆|输出|輸出)",
    re.IGNORECASE | re.DOTALL,
)
SECRET_TEXT = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}\b"
    r"|\bgh[pousr]_[A-Za-z0-9]{16,}\b"
    r"|\bgithub_pat_[A-Za-z0-9_]{16,}\b"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    r"|\bAIza[0-9A-Za-z_-]{35}\b"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}\b"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bbearer\s+\S+|\bapi[_ -]?key\s*[:=])",
    re.IGNORECASE,
)
STRICT_TIME_RANGE = re.compile(
    r"(?:\b\d{1,2}:\d{2}(?::\d{2})?\b)"
    r"|(?:\b\d+(?:\.\d+)?\s*[- ]?\s*(?:µs|μs|us|microseconds?|ms|milliseconds?|s|sec|secs|seconds?|frames?)\b)"
    r"|(?:\bframes?\s+#?\s*\d+\b)"
    r"|(?:\b(?:after|in|at|for)\s+(?:an?\s+)?"
    r"(?:half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+"
    r"(?:µs|μs|us|microseconds?|ms|milliseconds?|s|sec|secs|seconds?|minutes?|mins?|hours?|hrs?|frames?)\b)"
    r"|(?:\b(?:half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one\s+hundred)"
    r"[ -](?:microsecond|millisecond|second|sec|minute|min|hour|hr|frame)\b)"
    r"|(?:\b(?:half|quarter)(?:\s+of)?\s+a?\s*(?:microseconds?|milliseconds?|seconds?|minutes?|hours?|frames?)\b)"
    r"|(?:\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one\s+hundred)"
    r"\s+(?:microseconds?|milliseconds?|secs?|seconds?|minutes?|mins?|hours?|hrs?|frames?)\b)"
    r"|(?:\b(?:after|in|at|for)\s+(?:an?\s+)?"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one\s+hundred)\s+"
    r"(?:microseconds?|milliseconds?|secs?|seconds?|minutes?|mins?|hours?|hrs?|frames?)\b)"
    r"|(?:\b(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one\s+hundred)\s+"
    r"(?:microseconds?|milliseconds?|secs?|seconds?|minutes?|mins?|hours?|hrs?|frames?)\s+later\b)"
    r"|(?:\b(?:a\s+)?couple\s+of\s+(?:microseconds?|milliseconds?|seconds?|minutes?|hours?|frames?)\b)"
    r"|(?:\b(?:microseconds?|milliseconds?|seconds?|minutes?|hours?|frames?)\s+"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b)"
    r"|(?:\b\d+(?:st|nd|rd|th)\s+(?:microsecond|millisecond|second|minute|hour|frame)s?\b)"
    r"|(?:\b\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?)\b)"
    r"|(?:\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
    r"nineteenth|twentieth)\s+(?:microsecond|millisecond|second|minute|hour|frame)s?\b)"
    r"|(?:\b(?:one|two|three|four|five|six|seven|eight|nine|ten)[ -]"
    r"(?:half|third|quarter|fourth|fifth|sixth|seventh|eighth|ninth|tenth)s?\s+of\s+"
    r"(?:an?\s+)?(?:microsecond|millisecond|second|minute|hour|frame)\b)"
    r"|(?:\b\d+\s*/\s*\d+\s*(?:microseconds?|milliseconds?|seconds?|minutes?|hours?|frames?)\b)"
    r"|(?:\d+(?:\.\d+)?\s*(?:微秒|毫秒|秒|帧|幀))"
    r"|(?:\d+(?:\.\d+)?\s*(?:分钟|分鐘|小时|小時))"
    r"|(?:半个?(?:小时|小時|分钟|分鐘)(?:后|後|时|時)?)"
    r"|(?:(?:第)?[零〇一二三四五六七八九十百两兩半]+"
    r"(?:微秒|毫秒|秒|帧|幀|分钟|分鐘|小时|小時)(?:后|後|时|時)?)",
    re.IGNORECASE,
)
URI_LOCATOR = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]*://\S+|\bdata:[^\s,]+,)",
    re.IGNORECASE,
)
RELATIVE_LOCATOR = re.compile(
    r"(?:\\\\[^\\/\s]+[\\/][^\s]+|(?:^|[\s(' \" ])(?:\.\.|~|\.)[\\/][^\s]*)"
)
EN_PRONOUN = re.compile(
    r"\b(?:he|she|him|her|his|hers|himself|herself|they|them|their|theirs|"
    r"themselves|it|its|itself)\b|\bthe\s+(?:former|latter)\b|"
    r"\b(?:this|that|each)\s+one\b|\b(?:said|aforementioned)\s+"
    r"(?:object|subject|entity|character|product)\b|\bthe\s+same\s+"
    r"(?:one|object|subject|entity|character|product)\b",
    re.I,
)
ZH_PRONOUN = re.compile(
    r"(?:他们|她们|它们|他們|她們|它們|"
    r"其(?:面部|脸部|臉部|外观|外觀|外形|服装|服裝|动作|動作|位置|状态|狀態|"
    r"声音|聲音|表面|颜色|顏色|形状|形狀|运动|運動|主体|主體)|该主体|該主體|"
    r"本身|自身|自己|前者|后者|後者|该物体|該物體|上述物体|上述物體|此物|彼者)"
)
ZH_STANDALONE_PRONOUN = re.compile(r"(?<![吉其])[他她它]")
EN_AUDIO_IN_CAMERA = re.compile(
    r"\b(?:audio|sound|noise|soundtrack|silence|ambience|music(?!\s+box\b)|voice|dialogue|"
    r"speech|audible|heard)\b|\brings?\s+out\b|\bclick(?:s|\s+occurs?)\b",
    re.I,
)
ZH_AUDIO_IN_CAMERA = re.compile(
    r"(?:音频|音訊|声音|聲音|声响|聲響|音乐(?!盒)|音樂(?!盒)|人声|人聲|对白|對白|"
    r"台词|台詞|听见|聽見|听到|聽到|可闻|可聞|传来|傳來|环境声|環境聲|静音|靜音|"
    r"响起|響起|环境氛围|環境氛圍)"
)
EN_CAMERA_IN_AUDIO = re.compile(
    r"\b(?:camera|shot|viewpoint|view|field\s+of\s+view|framing|composition).{0,32}\b"
    r"(?:pans?|tilts?|zooms?|dollies?|tracks?|moves?|pushes?|reframes?|changes?|shifts?|"
    r"widens?|tightens?|narrows?)\b"
    r"|\b(?:lens|frame|perspective|image|focus).{0,20}\b"
    r"(?:advances?|zooms?|moves?|shifts?|tightens?|widens?|narrows?|cuts?)\b"
    r"|\b(?:push[- ]?in|pull[- ]?out|dolly[- ]?(?:in|out)|zoom[- ]?(?:in|out)|rack focus)\b"
    r"|\b(?:slow|fast|gentle|controlled)\s+(?:pan|tilt|zoom|dolly)\b"
    r"|\b(?:close[- ]?up|medium|wide|establishing|overhead|handheld)\s+shot\b",
    re.I,
)
ZH_CAMERA_IN_AUDIO = re.compile(
    r"(?:(?:镜头|鏡頭|摄影机|攝影機).{0,6}(?:移动|移動|推进|推進|拉远|拉遠|"
    r"摇动|搖動|跟随|跟隨|变化|變化)|(?:构图|構圖|景别|景別).{0,4}(?:变化|變化|改变|改變)|"
    r"推镜|推鏡|推近|拉镜|拉鏡|拉远|拉遠|摇镜|搖鏡|跟拍|运镜|運鏡|"
    r"(?:视角|視角|画面|畫面).{0,12}(?:推进|推進|推近|拉远|拉遠|收窄|变窄|變窄|"
    r"变为|變為|切换|切換|移动|移動).{0,6}(?:特写|特寫|近景|中景|远景|遠景)?|"
    r"(?:视点|視點|焦点|焦點|画幅|畫幅|透视|透視).{0,12}"
    r"(?:移动|移動|推进|推進|转移|轉移|收紧|收緊|变化|變化))"
)
EN_ENDPOINT_ONGOING = re.compile(
    r"\b(?:(?:continue|continues|continuing)\s+(?:moving|rolling|sliding|falling|spinning|"
    r"rotating|drifting|traveling|travelling|translating|gliding|coasting|cruising|orbiting|"
    r"tumbling)|(?:glides?|gliding|coasts?|coasting|cruises?|cruising|orbits?|orbiting|"
    r"tumbles?|tumbling|translates?|translating|revolves?|revolving|falls?|falling|rolls?|"
    r"rolling|slides?|sliding|moves?|moving|drifts?|drifting|crawls?|advances?|proceeds?)|"
    r"keeps? moving|still moving|still rolling|still spins?|"
    r"ongoing|remains? in motion|"
    r"(?:holds?|holding|maintains?|maintaining|retains?|retaining|keeps?|keeping|"
    r"sustains?|sustaining|remains?)\s+(?:(?:in|at|with)\s+)?"
    r"(?:(?:a|an|its|the)\s+)?(?:(?:constant|steady|fixed|uniform|positive|terminal|"
    r"forward|backward|linear|angular|rotational|translational|continuous|continued|"
    r"perpetual|residual|remaining|periodic|slow|lateral|non\s*(?:-\s*)?zero)\s+){0,4}"
    r"(?:speed|ground\s+speed|airspeed|velocity|momentum|kinetic\s+energy|angular\s+rate|"
    r"rate\s+of\s+(?:travel|displacement)|motion|"
    r"translation(?!\s+(?:offset|matrix|alignment|parameter|transform|vector|coordinate|quaternion))|"
    r"rotation(?!\s+(?:angle|matrix|offset|alignment|parameter|transform|axis|coordinate|quaternion))|"
    r"acceleration|vibration|oscillation|wobble|roll|glide|transit|drift|slide|"
    r"spin|precession|tremor)|"
    r"(?:is |keeps? |remains? )?(?:rolling|spinning)|"
    r"(?:remains?|still|keeps?)\s+(?:drifting|falling|sliding|moving|rolling|spinning|"
    r"bouncing|swinging|rotating)|still\s+(?:falls?|drifts?|slides?|moves?|rolls?|spins?))\b",
    re.I,
)
ZH_ENDPOINT_ONGOING = re.compile(
    r"(?:(?:继续|繼續).{0,4}(?:移动|移動|滚动|滾動|滑行|下落|旋转|旋轉)|"
    r"仍在移动|仍在移動|持续运动|持續運動|尚未停|保持滚动|保持滾動|"
    r"(?:继续|繼續|持续|持續|仍在)(?:自转|自轉|公转|公轉|摆动|擺動|前行|前进|前進|"
    r"滑翔|翻滚|翻滾|平移|振荡|振盪)|(?:滑翔|翻滚|翻滾|匀速前进|勻速前進|下落|"
    r"坠落|墜落|滚动|滾動|公转|公轉|自转|自轉)|"
    r"持续滚动|持續滾動|"
    r"(?:保持|维持|維持|保有|具有)(?:(?:恒定|恆定|稳定|穩定|固定|均匀|均勻|"
    r"不变|不變|正向|正|非\s*(?:-\s*)?零|向前|前向|线性|線性|角|平移|旋转|旋轉|持续|持續|"
    r"剩余|剩餘|残余|殘餘|周期|週期|缓慢|緩慢)){0,4}"
    r"(?:速度|速率|转速|轉速|匀速|勻速|巡航速度|地速|角频率|角頻率|"
    r"每分钟转数|每分鐘轉數|每(?:分钟|分鐘)[一二三四五六七八九十百零〇0-9]+(?:转|轉)|"
    r"动量|動量|动能|動能|运动|運動|"
    r"平移(?!偏移|矩阵|矩陣|对齐|對齊|参数|參數|变换|變換|向量|坐标|座標|四元数|四元數)|"
    r"(?:旋转|旋轉)(?!角|矩阵|矩陣|偏移|对齐|對齊|参数|參數|变换|變換|轴|軸|"
    r"坐标|座標|四元数|四元數)|"
    r"滑动|滑動|滑行|漂移|加速度|振动|振動|震颤|震顫|振荡|振盪|"
    r"摇摆|搖擺|晃动|晃動|进动|進動)|"
    r"重新(?:开始|開始)?(?:移动|移動|滚动|滾動|摇晃|搖晃)|"
    r"(?:之后|之後).{0,8}(?:重新|再次).{0,8}(?:移动|移動|滚动|滾動|摇晃|搖晃))"
)
EN_ENDPOINT_NEGATED = re.compile(
    r"\b(?:(?:does not|doesn't|never|cannot|can't|fails? to)\s+"
    r"(?:fully\s+|completely\s+|entirely\s+)?(?:stop|settle|rest|remain|hold|end)"
    r"|not\s+(?:fully\s+|completely\s+|entirely\s+)?(?:stopped|settled|still))\b",
    re.I,
)
ZH_ENDPOINT_NEGATED = re.compile(
    r"(?:(?:没有|沒有|未|尚未|不)(?:再)?(?:完全)?(?:停|停止|停稳|停穩|静止|靜止|落定).{0,8}"
    r"(?:移动|移動|运动|運動)?|并非(?:完全)?(?:静止|靜止|停稳|停穩))"
)
EN_ENDPOINT_INCOMPLETE = re.compile(
    r"\b(?:(?:will|about to|nearly|almost|eventually).{0,24}"
    r"(?:stops?|stopped|settles?|settled|rests?|rested|remains?|holds?|held|ends?|ended|"
    r"becomes? still)|(?:stops?|stopped|settles?|settled|rests?|rested|ends?|ended).{0,12}later)\b",
    re.I,
)
EN_ENDPOINT_RESUMES = re.compile(
    r"\b(?:(?:move|moves|moving|roll|rolls|rolling|drift|drifts|drifting|shake|shakes|shaking)\s+again"
    r"|before\s+(?:it\s+)?(?:moves?|moving|rolls?|rolling|drifts?|drifting|shakes?|shaking)"
    r"|(?:resumes?|resuming|restarts?|restarting)\s+(?:moving|motion|rolling|drifting|shaking|vibrating|"
    r"wobbling|translating|translation|rotating|rotation|gliding|coasting|accelerating)"
    r"|(?:ends?|rests?|settles?|stops?).{0,32}\b"
    r"(?:while|and|only\s+to|before|yet|subsequently|despite)\s+"
    r"(?:still\s+)?(?:keeps?\s+)?(?:moving|rolling|drifting|sliding|coasting|traveling|"
    r"travelling|skidding|slipping|creeping|inching|falling|spinning|rotating|rocking|"
    r"precessing|shaking|vibrating|wobbling|accelerating)"
    r"|(?:then|and(?:\s+then)?|but|until|only\s+to|before|yet|subsequently|"
    r"afterward|afterwards|after\s+that|after\s+which|thereafter|later|followed\s+by|"
    r"nevertheless).{0,24}"
    r"(?:moves?|moving|starts?\s+moving|will\s+move|slides?|sliding|rolls?|rolling|"
    r"drifts?|drifting|spins?|spinning|rotates?|rotating|falls?|falling|bounces?|bouncing|"
    r"swings?|swinging|travels?|traveling|travelling|coasts?|coasting|glides?|gliding|"
    r"translates?|translating|oscillates?|oscillating|revolves?|revolving|proceeds?|"
    r"proceeding|advances?|advancing|crawls?|crawling|conveyed|skids?|skidding|"
    r"slips?|slipping|creeps?|creeping|inches?|inching|rocks?|rocking|precesses?|"
    r"precessing|accelerates?|accelerating|acceleration(?:\s+(?:starts?|begins?|resumes?))?|"
    r"renewed\s+(?:motion|movement|translation|rotation)|"
    r"begins?.{0,12}(?:another|new|second).{0,8}"
    r"(?:motion|fall|slide|roll)|resumes?|restarts?|vibrates?|vibrating|wobbles?|wobbling|"
    r"shakes?|shaking)"
    r"|(?:with|while|but|despite)\b.{0,18}(?:(?:residual|persistent)\s+)?"
    r"(?:motion|moving|vibration|vibrating|wobble|wobbling|shaking|tremor|trembling|"
    r"rocking|precession|precessing|oscillation|oscillating|momentum|kinetic\s+energy|"
    r"acceleration|gliding|coasting|translating|revolving|proceeding|advancing|crawling|"
    r"conveyed|"
    r"(?:non\s*(?:-\s*)?zero\s+)?(?:linear|angular|translational)?\s*velocity))\b"
    r"|\b(?:enters?|settles?\s+into|remains?\s+in).{0,16}"
    r"(?:free[- ]fall|accelerating\s+motion|translation|translational\s+motion|"
    r"linear\s+motion|rotation|rotational\s+motion|sliding\s+motion|rolling\s+motion|motion)\b",
    re.I,
)
EN_ENDPOINT_TEMPORARY = re.compile(
    r"\b(?:(?:temporary|brief|briefly|momentary|momentarily).{0,16}"
    r"(?:rest|rests|settle|settles|stop|stops)"
    r"|(?:rest|rests|settle|settles|stop|stops).{0,16}"
    r"(?:briefly|temporarily|momentarily|for now|for a moment)"
    r"|(?:temporarily|momentarily|for now|for a moment))\b",
    re.I,
)
ZH_ENDPOINT_TEMPORARY = re.compile(
    r"(?:(?:短暂|短暫|暂时|暫時|暂且|暫且|片刻|一度).{0,8}"
    r"(?:停|停稳|停穩|静止|靜止)"
    r"|(?:停|停稳|停穩|静止|靜止).{0,8}"
    r"(?:一会儿|一會兒|片刻|暂时|暫時|一下|一瞬间|一瞬間)"
    r"|短暂|短暫|暂时|暫時|暂且|暫且|片刻|一会儿|一會兒|一瞬间|一瞬間)"
)
ZH_ENDPOINT_RESUMES = re.compile(
    r"(?:(?:停|停稳|停穩|静止|靜止).{0,8}(?:后|後).{0,8}(?:再次|重新).{0,8}"
    r"(?:移动|移動|滚动|滾動|滑动|滑動|滑走|滑行|晃动|晃動|摇晃|搖晃|振动|振動|加速)"
    r"|(?:停|停稳|停穩|静止|靜止).{0,12}"
    r"(?:但|随后|隨後|然后|然後|接着|接著|继而|繼而|旋即).{0,8}"
    r"(?:仍|继续|繼續|持续|持續|缓慢|緩慢)?(?:移动|移動|运动|運動|滚动|滾動|"
    r"翻滚|翻滾|滑动|滑動|滑走|滑行|滑翔|漂移|平移|前进|前進|公转|公轉|"
    r"振荡|振盪|滑落|爬移|进动|進動|晃动|晃動|摇晃|搖晃|振动|振動|加速)"
    r"|(?:结束|結束|停止平移).{0,12}(?:仍在|仍有|仍).{0,8}"
    r"(?:移动|移動|滑行|下落|自由落体|自由落體|加速|进动|進動|晃动|晃動|"
    r"摇晃|搖晃|振动|振動)"
    r"|(?:后|後|随后|隨後|但|直到|并|並|而).{0,12}"
    r"(?:又|再次|重新|仍|还会|還會|开始|開始|继续|繼續|持续|持續).{0,8}"
    r"(?:动起来|動起來|移动|移動|运动|運動|滚动|滾動|翻滚|翻滾|滑动|滑動|"
    r"滑走|滑行|滑翔|漂移|平移|前进|前進|公转|公轉|振荡|振盪|晃动|晃動|"
    r"摇晃|搖晃|振动|振動|加速)"
    r"|(?:仍在|仍有|保持).{0,8}(?:缓慢|緩慢)?"
    r"(?:移动|移動|滑行|下落|自由落体|自由落體|加速|进动|進動|晃动|晃動|"
    r"摇晃|搖晃|振动|振動)"
    r"|(?:进入|進入|处于|處於|保持).{0,10}(?:加速运动|加速運動|自由落体|自由落體)"
    r"|(?:稳定|穩定)(?:进入|進入).{0,40}(?:平移|移动|移動|滚动|滾動|滑行|旋转|旋轉)"
    r"|(?:之后|之後|随后|隨後|然后|然後|接下来|接下來).{0,12}"
    r"(?:加速|继续|繼續|恢复|恢復|重新|公转|公轉|自转|自轉|移动|移動|运动|運動|"
    r"平移|滚动|滾動|滑行|振荡|振盪)"
    r"|(?:仍|还|還).{0,6}(?:保有|保持|具有).{0,6}(?:动能|動能))"
)
ZH_ENDPOINT_INCOMPLETE = re.compile(
    r"(?:(?:即将|即將|将|將|稍后|稍後|接近|几乎|幾乎).{0,12}"
    r"(?:停|停止|停稳|停穩|静止|靜止|落定))"
)
EN_ENDPOINT_COMPLETE = re.compile(
    r"\b(?:stop|stops|stopped|settle|settles|settled|rest|rests|remain|remains|still|"
    r"motionless|stationary|hold|holds)\b",
    re.I,
)
ZH_ENDPOINT_COMPLETE = re.compile(r"(?:停|稳|穩|静止|靜止|保持|落定)")
EN_ENDPOINT_ZERO_OR_ABSENT = re.compile(
    r"\b(?:(?:(?<!non-)(?<!non )(?<!non - )zero|no)\s+"
    r"(?:(?:residual|remaining|linear|angular|rotational|"
    r"translational)\s+){0,3}(?:speed|velocity|momentum|kinetic\s+energy|(?:net|resultant)\s+"
    r"force|torque|motion|translation|rotation|vibration|oscillation|wobble|precession|tremor)"
    r"|(?:an?\s+)?absence\s+of\s+(?:(?:residual|remaining)\s+)?"
    r"(?:motion|speed|velocity|momentum|vibration|oscillation|wobble|tremor)"
    r"|neither\s+(?:motion|speed|velocity|momentum|vibration)\s+nor\s+"
    r"(?:motion|speed|velocity|momentum|vibration)"
    r"|(?:speed|velocity|momentum|kinetic\s+energy|(?:net|resultant)\s+force|torque|"
    r"angular\s+rate|rpm|"
    r"rate\s+of\s+(?:travel|displacement)|motion|"
    r"translation|rotation|vibration|oscillation|wobble|precession|tremor)\s*"
    r"(?:(?:is|at|of|equals?|equal\s+to|stays?(?:\s+at)?|remains?(?:\s+at)?|"
    r"holds?(?:\s+at)?|reaches?|drops?\s+to|falls?\s+to|becomes?|=)\s+)?"
    r"(?:exactly\s+|precisely\s+)?(?:zero|0(?:\.0+)?))\b",
    re.I,
)
ZH_ENDPOINT_ZERO_OR_ABSENT = re.compile(
    r"(?:(?<!非)(?<!非 )(?<!非-)(?<!非 - )零(?:速度|速率|转速|轉速|动量|動量|动能|動能|"
    r"合力|净力|淨力|扭矩|运动|運動|"
    r"平移|旋转|旋轉|振动|振動|震颤|震顫|振荡|振盪|摇摆|搖擺)"
    r"|(?:速度|速率|转速|轉速|动量|動量|动能|動能|合力|净力|淨力|扭矩|"
    r"运动|運動|平移|旋转|旋轉|"
    r"振动|振動|震颤|震顫|振荡|振盪|摇摆|搖擺)\s*"
    r"(?:(?:始终|始終|最终|最終|已经|已經)\s*)?"
    r"(?:(?:为|為|等于|等於|等同于|等同於|保持在|降至|归于|歸於|归|歸|=)\s*)?"
    r"(?:零|0(?:\.0+)?)"
    r"|(?:没有|沒有|无|無)(?:剩余|剩餘|残余|殘餘)?(?:速度|动量|動量|动能|動能|"
    r"运动|運動|平移|旋转|旋轉|振动|振動|震颤|震顫|振荡|振盪|摇摆|搖擺))"
)
EN_ENDPOINT_PERSISTING_DYNAMICS = re.compile(
    r"\b(?:motion|translation(?!\s+(?:offset|matrix|alignment|transform|vector|coordinate|quaternion))|"
    r"rotation(?!\s+(?:angle|matrix|offset|alignment|transform|axis|coordinate|quaternion))|"
    r"acceleration|vibration|oscillation|wobble|roll|"
    r"glide|drift|slide|spin|precession|tremor)\b.{0,12}\b"
    r"(?:persists?|continues?|ongoing|remains?|resumes?|follows?)\b",
    re.I,
)
ZH_ENDPOINT_PERSISTING_DYNAMICS = re.compile(
    r"(?:运动|運動|平移|旋转|旋轉|加速|振动|振動|震颤|震顫|振荡|振盪|摇摆|搖擺|"
    r"晃动|晃動|滑动|滑動|漂移|进动|進動|动量|動量|动能|動能).{0,8}"
    r"(?:持续|持續|继续|繼續|仍在|存在|仍有剩余|仍有剩餘)"
)
EN_ENDPOINT_NONZERO_KINEMATICS = re.compile(
    r"\b(?:(?:non\s*(?:-\s*)?zero|positive|negative|uniform|terminal)\s+"
    r"(?:(?:linear|angular|rotational|translational)\s+)?"
    r"(?:speed|ground\s+speed|airspeed|velocity|momentum|kinetic\s+energy|acceleration|"
    r"angular\s+rate|rotational\s+frequency|rate\s+of\s+displacement)"
    r"|(?:speed|ground\s+speed|airspeed|velocity|momentum|kinetic\s+energy|acceleration|"
    r"angular\s+rate|rotational\s+frequency|rate\s+of\s+displacement)\s*"
    r"(?:(?:is|stays?|remains?|equals?|is\s+equal\s+to)\s+)?"
    r"(?:clearly\s+|measurably\s+|strictly\s+)?(?:non\s*(?:-\s*)?zero|positive|negative|"
    r"(?:not\s+(?:equal\s+to\s+)?|above\s+|below\s+|greater\s+than\s+|"
    r"less\s+than\s+)(?:zero|0(?:\.0+)?)|(?:unequal\s+to\s+|exceeds?\s+)"
    r"(?:zero|0(?:\.0+)?))"
    r"|(?:speed|ground\s+speed|airspeed|velocity|momentum|kinetic\s+energy|acceleration|"
    r"angular\s+rate|rotational\s+frequency|rate\s+of\s+displacement)\s*"
    r"(?:!=|<>|>|<|≠)\s*"
    r"0(?:\.0+)?)\b",
    re.I,
)
EN_ENDPOINT_MEASURED_KINEMATICS = re.compile(
    r"\b(?:[1-9][0-9]*(?:\.[0-9]+)?|(?:one|two|three|four|five|six|seven|eight|nine|ten))\s*"
    r"(?:rpm|revolutions?\s+per\s+minute|(?:metres?|meters?|radians?|degrees?)\s+per\s+second|"
    r"m/s|km/h|hz)\b|\b(?:angular\s+rate|rate\s+of\s+(?:travel|displacement))\s*"
    r"(?:(?:is|remains?|stays?)\s+)?(?:non\s*(?:-\s*)?zero|positive|negative)",
    re.I,
)
ZH_ENDPOINT_NONZERO_KINEMATICS = re.compile(
    r"(?:(?:非\s*(?:-\s*)?零|正向|正)(?:线性|線性|角|旋转|旋轉|平移)?"
    r"(?:速度|速率|转速|轉速|动量|動量|动能|動能|加速度)"
    r"|(?:速度|速率|转速|轉速|动量|動量|动能|動能|加速度)\s*"
    r"(?:为|為|等于|等於|保持|仍为|仍為)?(?:非\s*(?:-\s*)?零|正|负|負|正值|负值|負值|不为零|不為零|"
    r"不等于零|不等於零|不是零|并非零|並非零|并不是零|並不是零|并非为零|並非為零|"
    r"未归零|未歸零|没有归零|沒有歸零|不等同于零|不等同於零|大于零|大於零|"
    r"高于零|高於零|"
    r"小于零|小於零|低于零|低於零)"
    r"|(?:速度|速率|转速|轉速|动量|動量|动能|動能|加速度)\s*(?:!=|<>|>|<|≠)\s*"
    r"0(?:\.0+)?)"
)
EN_ENDPOINT_UNBALANCED_DYNAMICS = re.compile(
    r"\b(?:(?:non\s*(?:-\s*)?zero\s+(?:net|resultant)|unbalanced(?:\s+(?:net|resultant))?)"
    r"\s+(?:force|torque)"
    r"|non\s*(?:-\s*)?zero\s+(?:net\s+)?torque"
    r"|(?:(?:net|resultant)\s+(?:force|torque))\s*"
    r"(?:(?:is|stays?|remains?|equals?)\s+)?(?:non\s*(?:-\s*)?zero|positive|negative|"
    r"unbalanced|(?:not\s+(?:equal\s+to\s+)?|above\s+|below\s+|greater\s+than\s+|"
    r"less\s+than\s+)(?:zero|0(?:\.0+)?)|persists?|continues?)"
    r"|(?:force|torque)\s+(?:(?:that\s+)?(?:is|remains?|stays?)\s+)?(?:unbalanced|unopposed)"
    r"|unopposed\s+(?:force|torque)(?:\s+(?:persists?|continues?))?"
    r"|(?:(?:net|resultant)\s+(?:force|torque))\s*(?:!=|<>|>|<|≠)\s*0(?:\.0+)?"
    r"|non\s*(?:-\s*)?zero\s+(?:(?:linear|angular|rotational|translational)\s+)?acceleration)\b",
    re.I,
)
ZH_ENDPOINT_UNBALANCED_DYNAMICS = re.compile(
    r"(?:(?:非\s*(?:-\s*)?零|不为零|不為零)(?:合力|合外力|净力|淨力|净外力|淨外力|"
    r"净扭矩|淨扭矩|扭矩|线加速度|線加速度|角加速度)|(?:合力|合外力|净力|淨力|"
    r"净外力|淨外力|净扭矩|淨扭矩|扭矩|"
    r"线加速度|線加速度|角加速度)\s*(?:为|為|等于|等於|仍为|仍為)?"
    r"(?:非\s*(?:-\s*)?零|不为零|不為零|不等于零|不等於零|不是零|大于零|大於零|高于零|"
    r"高於零|小于零|小於零|低于零|低於零|持续存在|持續存在|为正|為正)"
    r"|(?:合力|合外力|净力|淨力|净外力|淨外力|扭矩).{0,6}"
    r"(?:处于|處於|保持)(?:不平衡状态|不平衡狀態)"
    r"|不平衡(?:合力|力|扭矩))"
)
EN_ENDPOINT_DISSIPATED = re.compile(
    r"(?:(?:residual|remaining)\s+)?(?:momentum|kinetic\s+energy|vibration|tremor|"
    r"oscillation)\s+(?:(?:is|was|has\s+been|had\s+been)\s+)?"
    r"(?:fully\s+|completely\s+|entirely\s+)?"
    r"(?:transferred|absorbed|dissipated|damped|lost|zeroed)"
    r"|kinetic\s+energy\s+(?:(?:is|was|has\s+been)\s+)?"
    r"(?:fully\s+|completely\s+|entirely\s+)?converted\s+"
    r"(?:fully\s+|completely\s+|entirely\s+)?to\s+(?:heat|thermal\s+energy)",
    re.I,
)
ZH_ENDPOINT_DISSIPATED = re.compile(
    r"(?:残余|殘餘|剩余|剩餘)?(?:动量|動量|动能|動能|振动|振動|震颤|震顫)\s*"
    r"(?:(?:已经|已經|已)\s*)?(?:(?:被[^未不]{0,8})|(?:为|為))?\s*"
    r"(?:完全|全部)?(?:传递|傳遞|吸收|消散|衰减|衰減|归零|歸零)"
    r"|(?:动能|動能)\s*(?:(?:已经|已經|已)\s*)?(?:完全|全部)?"
    r"(?:转化|轉化|转换|轉換)(?:为|為)(?:热能|熱能)"
)
EN_ENDPOINT_FORCE_RESOLVED = re.compile(
    r"\b(?:(?:unbalanced|unopposed)\s+(?:force|torque)|"
    r"non\s*(?:-\s*)?zero\s+(?:net|resultant)\s+(?:force|torque))\s+"
    r"(?:(?:is|was|has\s+been|had\s+been)\s+)?(?:fully\s+|completely\s+)?"
    r"(?:removed|balanced|cancelled|canceled|resolved|neutralized|zeroed)\b",
    re.I,
)
ZH_ENDPOINT_FORCE_RESOLVED = re.compile(
    r"(?:此前|先前)?(?:不平衡(?:合力|力|扭矩)|非\s*(?:-\s*)?零(?:合力|净力|淨力|扭矩))"
    r"\s*(?:(?:已经|已經|已)\s*)?(?:完全|全部)?"
    r"(?:移除|平衡|抵消|消除|归零|歸零)"
)
EN_ENDPOINT_UNRESOLVED_DYNAMICS = re.compile(
    r"\b(?:(?:momentum|kinetic\s+energy|vibration|tremor|oscillation)\s+"
    r"(?:(?:is|was|remains?|has\s+been)\s+)?(?:not|never|isn't|wasn't)\s+"
    r"(?:fully\s+|completely\s+|entirely\s+)?"
    r"(?:transferred|absorbed|dissipated|damped|lost|zeroed)"
    r"|(?:speed|velocity|momentum|kinetic\s+energy)\s+"
    r"(?:rises?|increases?|grows?|accelerates?)\s+from\s+(?:zero|0(?:\.0+)?)"
    r"|(?:transferred|absorbed|dissipated|damped|lost|zeroed).{0,24}"
    r"(?:only\s+briefly|temporarily|for\s+now|before.{0,8}(?:returning|resuming|reappearing)"
    r"|(?:then|later|afterward|afterwards).{0,12}(?:(?:momentum|energy|vibration)\s+)?"
    r"(?:returns?|resumes?|reappears?)))\b",
    re.I,
)
ZH_ENDPOINT_UNRESOLVED_DYNAMICS = re.compile(
    r"(?:(?:动量|動量|动能|動能|振动|振動|震颤|震顫).{0,6}"
    r"(?:尚未|未被|没有|沒有|并未|並未|不再?)(?:完全|全部)?"
    r"(?:传递|傳遞|吸收|消散|衰减|衰減|归零|歸零)"
    r"|(?:速度|速率|动量|動量|动能|動能).{0,6}(?:从|從)(?:零|0)(?:开始|開始)?"
    r"(?:增加|上升|恢复|恢復|加速)"
    r"|(?:传递|傳遞|吸收|消散|衰减|衰減|归零|歸零).{0,12}"
    r"(?:仅短暂|僅短暫|暂时|暫時|后|後|之后|之後|随后|隨後).{0,8}"
    r"(?:又|再次|重新)?(?:恢复|恢復|返回|出现|出現))"
)


class SemanticLintError(bindings.BindingError):
    """Stable, non-echoing semantic compiler boundary failure."""


def _fail(code: str, pointer: str = "/") -> None:
    raise SemanticLintError(code, pointer)


def _object(value: object, keys: set[str], pointer: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("TYPE_OBJECT_REQUIRED", pointer)
    if set(value) != keys:
        _fail("OBJECT_FIELDS_INVALID", pointer)
    return value


def _array(value: object, pointer: str, *, minimum: int = 0, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        _fail("ARRAY_LENGTH_INVALID", pointer)
    return value


def _source_hash(value: str) -> str:
    return bindings.sha256_bytes(value.encode("utf-8"))


def _comparison_skeleton(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _guard_default_ignorables(value: str, pointer: str) -> None:
    bindings._guard_default_ignorables(value, pointer, "PRM013_UNICODE_UNSAFE")


def _contains_locator(value: str, skeleton: str) -> bool:
    return any(
        pattern.search(candidate)
        for pattern in (
            reference_planner.LOCATOR_LIKE,
            URI_LOCATOR,
            RELATIVE_LOCATOR,
        )
        for candidate in (value, skeleton)
    )


def _guard_payload(
    value: str,
    pointer: str,
    *,
    allow_reference_tokens: bool = False,
    allow_structured_frame_terms: bool = False,
) -> None:
    skeleton = re.sub(r"\s+", " ", _comparison_skeleton(value))
    if not allow_reference_tokens and REFERENCE_SKELETON.search(skeleton):
        _fail("PRM009_BINDING_CORE_MISMATCH", pointer)
    if META_INSTRUCTION.search(skeleton):
        _fail("PRM011_META_INSTRUCTION", pointer)
    if SECRET_TEXT.search(skeleton) or _contains_locator(value, skeleton):
        _fail("PRM012_SECRET_OR_LOCATOR", pointer)
    time_view = (
        re.sub(r"\b(?:first|last)\s+frames?\b", "structured-frame-role", skeleton)
        if allow_structured_frame_terms
        else skeleton
    )
    if STRICT_TIME_RANGE.search(time_view):
        _fail("PRM008_TIME_RANGE_UNEVIDENCED", pointer)


def _safe_text(value: object, pointer: str, *, source: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REALIZATION_TEXT:
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    if unicodedata.normalize("NFC", value) != value:
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    _guard_default_ignorables(value, pointer)
    bindings._check_scalar_text(value, pointer)
    bindings._validate_visible_text(value, pointer)
    if any(character in value for character in "\r\n\t"):
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    if value[0].isspace() or value[-1].isspace():
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    _guard_payload(value, pointer)
    if not source and value[-1] in ".!?。！？;；":
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    return value


def validate_composed_text(
    value: object,
    pointer: str,
    *,
    locale: str,
    category: str,
    language_view: str | None = None,
) -> str:
    """Recheck a localized clause after entity-token substitution."""

    checked = validate_composed_payload(value, pointer)
    _validate_entry_language(
        checked if language_view is None else language_view,
        locale=locale,
        category=category,
        pointer=pointer,
    )
    return checked


def validate_composed_payload(
    value: object,
    pointer: str,
    *,
    allow_reference_tokens: bool = False,
    allow_structured_frame_terms: bool = False,
) -> str:
    """Check a complete localized payload after cross-unit composition."""

    if not isinstance(value, str) or not value or len(value) > 20_000:
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    if unicodedata.normalize("NFC", value) != value:
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    _guard_default_ignorables(value, pointer)
    bindings._check_scalar_text(value, pointer)
    bindings._validate_visible_text(value, pointer)
    if any(character in value for character in "\r\t"):
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    _guard_payload(
        value,
        pointer,
        allow_reference_tokens=allow_reference_tokens,
        allow_structured_frame_terms=allow_structured_frame_terms,
    )
    return value


def validate_rendered_composition(value: object, pointer: str) -> str:
    """Scan authored text plus opaque handles without rewriting handle bytes.

    Authored text has already passed NFC, timing, provider-token, and language
    checks. Opaque provider handles have already passed their own byte-preserving
    safety check. This final pass only detects dangerous text assembled across a
    text/binding boundary; it must not reinterpret a legitimate handle as
    authored timing or require that externally captured bytes are NFC.
    """

    if not isinstance(value, str) or not value:
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    _guard_default_ignorables(value, pointer)
    bindings._check_scalar_text(value, pointer)
    bindings._validate_visible_text(value, pointer)
    if any(character in value for character in "\r\t"):
        _fail("PRM013_UNICODE_UNSAFE", pointer)
    skeleton = re.sub(r"\s+", " ", _comparison_skeleton(value))
    if META_INSTRUCTION.search(skeleton):
        _fail("PRM011_META_INSTRUCTION", pointer)
    if SECRET_TEXT.search(skeleton) or _contains_locator(value, skeleton):
        _fail("PRM012_SECRET_OR_LOCATOR", pointer)
    return value


def validate_opaque_handle_payload(value: object, pointer: str) -> str:
    """Fail closed on dangerous prose while preserving opaque handle bytes."""

    if not isinstance(value, str) or not value or len(value) > 512:
        _fail("PRM009_BINDING_CORE_MISMATCH", pointer)
    _guard_default_ignorables(value, pointer)
    skeleton = _comparison_skeleton(value)
    if META_INSTRUCTION.search(skeleton):
        _fail("PRM011_META_INSTRUCTION", pointer)
    if SECRET_TEXT.search(skeleton) or _contains_locator(value, skeleton):
        _fail("PRM012_SECRET_OR_LOCATOR", pointer)
    return value


@dataclass(frozen=True)
class ExpectedEntry:
    source_text: str
    required_entities: frozenset[str] | None
    category: str


def _expected_catalog(scene: dict[str, Any]) -> tuple[list[str], dict[str, ExpectedEntry]]:
    order: list[str] = []
    expected: dict[str, ExpectedEntry] = {}

    def add(
        key: str,
        text: str,
        *,
        required_entities: set[str] | None = None,
        category: str,
    ) -> None:
        if key in expected:
            _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/entries")
        order.append(key)
        expected[key] = ExpectedEntry(
            text,
            None if required_entities is None else frozenset(required_entities),
            category,
        )

    for entity in scene["entities"]:
        entity_id = entity["entity_id"]
        add(f"entity.{entity_id}.label", entity["label"], category="entity_label")
    for shot in scene["shots"]:
        for event in shot["events"]:
            add(
                f"event.{event['event_id']}.visible_state_change",
                event["visible_state_change"],
                required_entities=set(event["actor_ids"]) | set(event["target_ids"]),
                category="event",
            )
        move = shot["camera"]["primary_move"]
        for field in (
            "start_framing", "path", "speed", "subject_relationship", "endpoint_framing"
        ):
            add(
                f"shot.{shot['shot_id']}.camera.{field}",
                move[field],
                category="camera",
            )
    for audio in scene["audio_events"]:
        add(
            f"audio.{audio['audio_event_id']}.description",
            audio["description"],
            required_entities=set(audio["source_entity_ids"]),
            category="audio",
        )
    for invariant in scene["requested_invariants"]:
        add(
            f"invariant.{invariant['invariant_id']}.description",
            invariant["description"],
            required_entities=set(invariant["entity_ids"]),
            category="invariant",
        )
    return order, expected


def _entity_tokens(value: str, pointer: str, known_entities: set[str]) -> list[str]:
    matches = list(ENTITY_TOKEN.finditer(value))
    tokens = [match.group(1) for match in matches]
    remainder = ENTITY_TOKEN.sub("", value)
    if "{" in remainder or "}" in remainder:
        _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
    if len(tokens) != len(set(tokens)) or any(token not in known_entities for token in tokens):
        _fail("PRM004_ENTITY_AMBIGUOUS", pointer)
    for match in matches:
        before = value[match.start() - 1] if match.start() else ""
        after = value[match.end()] if match.end() < len(value) else ""
        if re.match(r"[A-Za-z0-9_]", before) or re.match(r"[A-Za-z0-9_]", after):
            _fail("PRM004_ENTITY_AMBIGUOUS", pointer)
    return tokens


def _validate_entry_language(
    value: str,
    *,
    locale: str,
    category: str,
    pointer: str,
) -> None:
    comparison = _comparison_skeleton(value)
    if locale == "en" and EN_PRONOUN.search(comparison):
        _fail("LANG001_UNSTABLE_SUBJECT_ALIAS", pointer)
    if locale == "zh-Hans":
        if ZH_PRONOUN.search(comparison) or (
            category == "entity_label" and comparison in {"他", "她", "它"}
        ) or (
            category != "entity_label"
            and ZH_STANDALONE_PRONOUN.search(comparison)
        ):
            _fail("LANG001_UNSTABLE_SUBJECT_ALIAS", pointer)
    if category == "camera":
        if (locale == "en" and EN_AUDIO_IN_CAMERA.search(comparison)) or (
            locale == "zh-Hans" and ZH_AUDIO_IN_CAMERA.search(comparison)
        ):
            _fail("PRM007_CAMERA_AUDIO_CONFLATED", pointer)
    if category == "audio":
        if (locale == "en" and EN_CAMERA_IN_AUDIO.search(comparison)) or (
            locale == "zh-Hans" and ZH_CAMERA_IN_AUDIO.search(comparison)
        ):
            _fail("PRM007_CAMERA_AUDIO_CONFLATED", pointer)
    if category == "event":
        if locale == "en":
            unframed = re.sub(
                r"\b(?:screen|subject|world)[ -]?(?:left|right)(?:ward|wards)?\b",
                "",
                comparison,
            )
            if re.search(r"\b(?:left|right)(?:ward|wards)?\b", unframed):
                _fail("PRM004_ENTITY_AMBIGUOUS", pointer)
        if locale == "zh-Hans":
            unframed = re.sub(
                r"(?:画面|屏幕|主体|世界).{0,4}[左右]",
                "",
                comparison,
            )
            if re.search(r"[左右]", unframed):
                _fail("PRM004_ENTITY_AMBIGUOUS", pointer)


def validate_catalog(
    scene: dict[str, Any],
    value: object,
    *,
    allow_unattested_fixture: bool = False,
) -> tuple[dict[str, dict[str, str]], str]:
    """Validate exact bilingual coverage and return entries keyed by semantic ID."""

    catalog = _object(value, CATALOG_KEYS, "/realization_catalog")
    if (
        catalog["$schema"] != CATALOG_SCHEMA_URI
        or catalog["schema_version"] != 1
        or not bindings._is_int(catalog["schema_version"])
    ):
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog")
    scene_hash = bindings.sha256_bytes(bindings.canonical_json(scene))
    if catalog["scene_ir_sha256"] != scene_hash:
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/scene_ir_sha256")
    attestation = _object(
        catalog["attestation"], ATTESTATION_KEYS, "/realization_catalog/attestation"
    )
    method = attestation["method"]
    equivalence = attestation["linguistic_equivalence"]
    if (
        not isinstance(method, str)
        or not isinstance(equivalence, str)
        or not isinstance(attestation["locales"], list)
    ):
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/attestation")
    human_declaration = (
        method in {"user_attested", "reviewer_attested"}
        and equivalence == "human_asserted"
    )
    fixture_unattested = (
        method == "unattested_fixture"
        and equivalence == "not_attested"
        and allow_unattested_fixture
    )
    if (
        not (human_declaration or fixture_unattested)
        or attestation["locales"] != ["en", "zh-Hans"]
    ):
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/attestation")

    expected_order, expected = _expected_catalog(scene)
    entries = _array(
        catalog["entries"],
        "/realization_catalog/entries",
        minimum=1,
        maximum=MAX_CATALOG_ENTRIES,
    )
    checked: dict[str, dict[str, str]] = {}
    actual_order: list[str] = []
    entry_indexes: dict[str, int] = {}
    known_entities = {entity["entity_id"] for entity in scene["entities"]}
    entity_labels: dict[str, set[str]] = {"en": set(), "zh-Hans": set()}
    event_texts: dict[str, set[str]] = {"en": set(), "zh-Hans": set()}

    for index, raw in enumerate(entries):
        pointer = f"/realization_catalog/entries/{index}"
        entry = _object(raw, ENTRY_KEYS, pointer)
        key = entry["semantic_key"]
        if not isinstance(key, str) or not SAFE_SEMANTIC_KEY.fullmatch(key) or key in checked:
            _fail("PRM025_LOCALE_CATALOG_INVALID", f"{pointer}/semantic_key")
        expected_entry = expected.get(key)
        if expected_entry is None:
            _fail("LANG003_LOCALIZATION_SET_MISMATCH", f"{pointer}/semantic_key")
        if entry["source_sha256"] != _source_hash(expected_entry.source_text):
            _fail("PRM025_LOCALE_CATALOG_INVALID", f"{pointer}/source_sha256")
        _safe_text(expected_entry.source_text, f"/scene_ir/{key}", source=True)
        en = _safe_text(entry["en"], f"{pointer}/en")
        zh = _safe_text(entry["zh_hans"], f"{pointer}/zh_hans")
        en_tokens = _entity_tokens(en, f"{pointer}/en", known_entities)
        zh_tokens = _entity_tokens(zh, f"{pointer}/zh_hans", known_entities)
        if set(en_tokens) != set(zh_tokens):
            _fail("PARITY001_SEMANTIC_TRACE_MISMATCH", pointer)
        if (
            expected_entry.required_entities is not None
            and set(en_tokens) != set(expected_entry.required_entities)
        ):
            _fail("PRM004_ENTITY_AMBIGUOUS", pointer)
        _validate_entry_language(
            en, locale="en", category=expected_entry.category, pointer=f"{pointer}/en"
        )
        _validate_entry_language(
            zh, locale="zh-Hans", category=expected_entry.category, pointer=f"{pointer}/zh_hans"
        )
        if expected_entry.category == "entity_label":
            if en_tokens or zh_tokens:
                _fail("PRM025_LOCALE_CATALOG_INVALID", pointer)
            for locale, text in (("en", en), ("zh-Hans", zh)):
                identity = _comparison_skeleton(text)
                if identity in entity_labels[locale]:
                    _fail("PRM003_ALIAS_COLLISION", pointer)
                entity_labels[locale].add(identity)
        if expected_entry.category == "event":
            for locale, text in (("en", en), ("zh-Hans", zh)):
                identity = _comparison_skeleton(text)
                if identity in event_texts[locale]:
                    _fail("PRM023_EVENT_TEXT_DUPLICATE", pointer)
                event_texts[locale].add(identity)
        actual_order.append(key)
        checked[key] = {"en": en, "zh-Hans": zh}
        entry_indexes[key] = index

    if actual_order != expected_order:
        _fail("LANG003_LOCALIZATION_SET_MISMATCH", "/realization_catalog/entries")

    endpoint_ids = {
        event["event_id"]
        for shot in scene["shots"]
        for event in shot["events"]
        if event["phase"] == "settled_endpoint"
    }
    for event_id in endpoint_ids:
        row = checked[f"event.{event_id}.visible_state_change"]
        raw_en_endpoint = re.sub(
            r"\s+",
            " ",
            _comparison_skeleton(ENTITY_TOKEN.sub("entity", row["en"])),
        )
        raw_en_endpoint = re.sub(
            "[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]",
            "-",
            raw_en_endpoint,
        )
        raw_en_endpoint = re.sub(r"\s*-\s*", "-", raw_en_endpoint)
        raw_zh_endpoint = re.sub(
            r"\s+",
            " ",
            unicodedata.normalize(
                "NFKC",
                ENTITY_TOKEN.sub("实体", row["zh-Hans"]),
            ),
        )
        raw_zh_endpoint = re.sub(
            "[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]",
            "-",
            raw_zh_endpoint,
        )
        raw_zh_endpoint = re.sub(r"\s*-\s*", "-", raw_zh_endpoint)
        raw_endpoint_contradiction = bool(
            EN_ENDPOINT_UNRESOLVED_DYNAMICS.search(raw_en_endpoint)
            or ZH_ENDPOINT_UNRESOLVED_DYNAMICS.search(raw_zh_endpoint)
        )
        en_endpoint = EN_ENDPOINT_FORCE_RESOLVED.sub(
            "terminalized",
            raw_en_endpoint,
        )
        en_endpoint = EN_ENDPOINT_DISSIPATED.sub(
            "terminalized",
            en_endpoint,
        )
        en_endpoint = EN_ENDPOINT_ZERO_OR_ABSENT.sub("stopped", en_endpoint)
        zh_endpoint = ZH_ENDPOINT_FORCE_RESOLVED.sub(
            "已消散",
            raw_zh_endpoint,
        )
        zh_endpoint = ZH_ENDPOINT_DISSIPATED.sub(
            "已消散",
            zh_endpoint,
        )
        zh_endpoint = ZH_ENDPOINT_ZERO_OR_ABSENT.sub("静止", zh_endpoint)
        if (
            raw_endpoint_contradiction
            or EN_ENDPOINT_INCOMPLETE.search(en_endpoint)
            or ZH_ENDPOINT_INCOMPLETE.search(zh_endpoint)
            or EN_ENDPOINT_NEGATED.search(en_endpoint)
            or ZH_ENDPOINT_NEGATED.search(zh_endpoint)
            or EN_ENDPOINT_ONGOING.search(en_endpoint)
            or ZH_ENDPOINT_ONGOING.search(zh_endpoint)
            or EN_ENDPOINT_RESUMES.search(en_endpoint)
            or EN_ENDPOINT_PERSISTING_DYNAMICS.search(en_endpoint)
            or ZH_ENDPOINT_PERSISTING_DYNAMICS.search(zh_endpoint)
            or EN_ENDPOINT_NONZERO_KINEMATICS.search(en_endpoint)
            or ZH_ENDPOINT_NONZERO_KINEMATICS.search(zh_endpoint)
            or EN_ENDPOINT_MEASURED_KINEMATICS.search(en_endpoint)
            or EN_ENDPOINT_UNBALANCED_DYNAMICS.search(en_endpoint)
            or ZH_ENDPOINT_UNBALANCED_DYNAMICS.search(zh_endpoint)
            or EN_ENDPOINT_TEMPORARY.search(en_endpoint)
            or ZH_ENDPOINT_TEMPORARY.search(zh_endpoint)
            or ZH_ENDPOINT_RESUMES.search(zh_endpoint)
            or not EN_ENDPOINT_COMPLETE.search(en_endpoint)
            or not ZH_ENDPOINT_COMPLETE.search(zh_endpoint)
        ):
            endpoint_key = f"event.{event_id}.visible_state_change"
            _fail(
                "PRM017_ENDPOINT_NOT_FINAL",
                f"/realization_catalog/entries/{entry_indexes[endpoint_key]}",
            )

    return checked, bindings.sha256_bytes(bindings.canonical_json(catalog))


def _unit(
    unit_id: str,
    kind: str,
    *,
    source_ids: list[str],
    entity_ids: list[str] | None = None,
    event_ids: list[str] | None = None,
    binding_ids: list[str] | None = None,
    semantic_tags: list[str] | None = None,
    emission: str = "prompt",
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "kind": kind,
        "source_ids": list(dict.fromkeys(source_ids)),
        "entity_ids": entity_ids or [],
        "event_ids": event_ids or [],
        "binding_ids": binding_ids or [],
        "semantic_tags": semantic_tags or [],
        "emission": emission,
    }


def reference_semantics(manifest: dict[str, Any]) -> dict[str, Any]:
    """Drop profile/transport/prose while preserving reference intent."""

    target_by_id = {item["target_id"]: item for item in manifest["targets"]}
    asset_by_id = {item["asset_id"]: item for item in manifest["assets"]}
    dimension_order = {item: index for index, item in enumerate(reference_planner.DIMENSIONS)}
    return {
        "operation": manifest["operation"],
        "targets": [
            {
                "target_id": item["target_id"],
                "target_kind": item["target_kind"],
                "required_dimensions": sorted(item["required_dimensions"], key=dimension_order.get),
                "not_applicable_dimensions": sorted(
                    item["not_applicable_dimensions"], key=dimension_order.get
                ),
            }
            for item in (target_by_id[target_id] for target_id in sorted(target_by_id))
        ],
        "assets": [
            {
                "asset_id": item["asset_id"],
                "media_type": item["media_type"],
                "use": item["use"],
                "subject_selector": item["subject_selector"],
                "selection_status": item["selection_status"],
                "observed_leakage_dimensions": sorted(
                    item["observed_leakage_dimensions"], key=dimension_order.get
                ),
            }
            for item in (asset_by_id[asset_id] for asset_id in manifest["selection_order"])
        ],
        "authority_assignments": [
            {
                "target_id": item["target_id"],
                "dimension": item["dimension"],
                "winner_asset_id": item["winner_asset_id"],
                "excluded_asset_ids": sorted(item["excluded_asset_ids"]),
                "excluded_transfer_dimensions": sorted(
                    item["excluded_transfer_dimensions"], key=dimension_order.get
                ),
                "leakage_risks": sorted(item["leakage_risks"], key=dimension_order.get),
                "resolved_leakage": sorted(item["resolved_leakage"], key=dimension_order.get),
            }
            for item in sorted(
                manifest["authority_assignments"],
                key=lambda row: (
                    row["target_id"],
                    dimension_order[row["dimension"]],
                    row["winner_asset_id"],
                ),
            )
        ],
        "selection_order": manifest["selection_order"],
        "ablation_order": manifest["ablation_order"],
    }


def build_prompt_program(
    manifest: dict[str, Any],
    scene: dict[str, Any],
    catalog: dict[str, dict[str, str]],
    catalog_sha256: str,
) -> dict[str, Any]:
    """Build the exact ordered provenance program consumed by both locales."""

    validate_supported_scope(scene)

    units: list[dict[str, Any]] = [
        _unit(
            "operation.1",
            "operation",
            source_ids=[manifest["operation"]],
            semantic_tags=[f"operation:{manifest['operation']}"],
        )
    ]
    assignments_by_asset: dict[str, list[dict[str, Any]]] = {
        asset_id: [] for asset_id in manifest["selection_order"]
    }
    for assignment in manifest["authority_assignments"]:
        assignments_by_asset[assignment["winner_asset_id"]].append(assignment)
    carried_bindings: dict[str, str] = {}
    if manifest["operation"] == "first_last_frame":
        for assignment in manifest["authority_assignments"]:
            if assignment["dimension"] == "opening_state":
                carried_bindings["initial_state"] = assignment["winner_asset_id"]
            elif assignment["dimension"] == "endpoint":
                carried_bindings["settled_endpoint"] = assignment["winner_asset_id"]
    for asset_id in manifest["selection_order"]:
        rows = sorted(
            assignments_by_asset[asset_id],
            key=lambda row: reference_planner.DIMENSIONS.index(row["dimension"]),
        )
        target_ids = sorted({row["target_id"] for row in rows})
        units.append(
            _unit(
                f"authority.{asset_id}",
                "authority",
                source_ids=list(dict.fromkeys([asset_id, *target_ids])),
                binding_ids=[asset_id],
                semantic_tags=[
                    *[f"dimension:{row['dimension']}" for row in rows],
                    *sorted(
                        {
                            f"exclude:{dimension}"
                            for row in rows
                            for dimension in row["excluded_transfer_dimensions"]
                        }
                    ),
                ],
            )
        )
    for entity in scene["entities"]:
        units.append(
            _unit(
                f"review.entity.{entity['entity_id']}",
                "review",
                source_ids=[entity["entity_id"]],
                entity_ids=[entity["entity_id"]],
                semantic_tags=[
                    f"entity_kind:{entity['kind']}",
                    "review:entity_source",
                ],
                emission="review_only",
            )
        )
    for material in scene["materials"]:
        units.append(
            _unit(
                f"review.material.{material['material_id']}",
                "review",
                source_ids=[material["material_id"]],
                entity_ids=[material["entity_id"]],
                semantic_tags=[
                    f"material_kind:{material['kind']}",
                    "review:material_source",
                ],
                emission="review_only",
            )
        )
    for shot in scene["shots"]:
        for event in shot["events"]:
            request_carried = (
                manifest["operation"] == "first_last_frame"
                and event["phase"] in {"initial_state", "settled_endpoint"}
            )
            units.append(
                _unit(
                    f"event.{event['event_id']}",
                    "event",
                    source_ids=[shot["shot_id"], event["event_id"]],
                    entity_ids=list(dict.fromkeys([*event["actor_ids"], *event["target_ids"]])),
                    event_ids=[event["event_id"]],
                    binding_ids=(
                        [carried_bindings[event["phase"]]]
                        if request_carried
                        else []
                    ),
                    semantic_tags=[
                        f"phase:{event['phase']}",
                        f"interaction:{event['interaction_kind']}",
                        *[f"depends:{item}" for item in event["depends_on"]],
                        *(
                            ["request_carried:structured_frame"]
                            if request_carried
                            else []
                        ),
                    ],
                    emission="request_carried" if request_carried else "prompt",
                )
            )
        move = shot["camera"]["primary_move"]
        observed = shot["camera"]["observability"]
        units.append(
            _unit(
                f"camera.{shot['shot_id']}",
                "camera",
                source_ids=[shot["shot_id"]],
                event_ids=[
                    observed["before_state_event_id"],
                    observed["decisive_event_id"],
                    *observed["consequence_event_ids"],
                    observed["endpoint_event_id"],
                ],
                semantic_tags=[
                    f"camera:{move['kind']}",
                    *(
                        [
                            "request_carried:start_framing",
                            "request_carried:endpoint_framing",
                        ]
                        if manifest["operation"] == "first_last_frame"
                        else []
                    ),
                ],
                binding_ids=(
                    [
                        carried_bindings["initial_state"],
                        carried_bindings["settled_endpoint"],
                    ]
                    if manifest["operation"] == "first_last_frame"
                    else []
                ),
            )
        )
    for audio in scene["audio_events"]:
        units.append(
            _unit(
                f"audio.{audio['audio_event_id']}",
                "audio",
                source_ids=[audio["audio_event_id"], audio["shot_id"]],
                entity_ids=audio["source_entity_ids"],
                event_ids=[audio["linked_event_id"]],
                semantic_tags=[
                    f"timing:{audio['temporal_relationship']}",
                    f"function:{audio['semantic_function']}",
                ],
            )
        )
    for invariant in scene["requested_invariants"]:
        units.append(
            _unit(
                f"invariant.{invariant['invariant_id']}",
                "invariant",
                source_ids=[invariant["invariant_id"]],
                entity_ids=invariant["entity_ids"],
                semantic_tags=["constraint:requested_invariant"],
            )
        )
    for fragility in scene["known_fragilities"]:
        units.append(
            _unit(
                f"review.fragility.{fragility['fragility_id']}",
                "review",
                source_ids=[fragility["fragility_id"]],
                event_ids=fragility["event_ids"],
                semantic_tags=["review:known_fragility"],
                emission="review_only",
            )
        )
    for acceptance in scene["acceptance_tests"]:
        units.append(
            _unit(
                f"review.acceptance.{acceptance['acceptance_id']}",
                "review",
                source_ids=[acceptance["acceptance_id"]],
                event_ids=acceptance["event_ids"],
                semantic_tags=["review:acceptance_test"],
                emission="review_only",
            )
        )
    for fallback in scene["post_fallbacks"]:
        units.append(
            _unit(
                f"review.fallback.{fallback['fallback_id']}",
                "review",
                source_ids=[fallback["fallback_id"]],
                semantic_tags=["review:post_fallback"],
                emission="review_only",
            )
        )

    expected_events = [
        event_id
        for row in scene_ir_check.causal_order(scene)
        for event_id in row["event_ids"]
    ]
    program_events = [
        unit["event_ids"][0]
        for unit in units
        if unit["kind"] == "event"
    ]
    if program_events != expected_events or len(program_events) != len(set(program_events)):
        _fail("PRM002_CAUSAL_ORDER_INVALID", "/units")
    if set(catalog) != set(_expected_catalog(scene)[0]):
        _fail("PRM025_LOCALE_CATALOG_INVALID", "/realization_catalog/entries")

    return {
        "$schema": PROGRAM_SCHEMA_URI,
        "schema_version": 1,
        "operation": manifest["operation"],
        "reference_semantics_sha256": bindings.sha256_bytes(
            bindings.canonical_json(reference_semantics(manifest))
        ),
        "scene_ir_sha256": bindings.sha256_bytes(bindings.canonical_json(scene)),
        "realization_catalog_sha256": catalog_sha256,
        "asset_order": list(manifest["selection_order"]),
        "units": units,
    }


def validate_supported_scope(scene: dict[str, Any]) -> None:
    """Fail before localization when V7-08/V7-09 contracts are required."""

    if len(scene["shots"]) != 1:
        _fail("PRM022_MULTI_SHOT_DEFERRED", "/scene_ir/shots")
    if any(
        item["semantic_function"] in {"dialogue", "voiceover"}
        for item in scene["audio_events"]
    ):
        _fail("PRM021_DIALOGUE_TEXT_REQUIRED", "/scene_ir/audio_events")


def validate_prompt_program(
    value: object,
    *,
    manifest: dict[str, Any],
    scene: dict[str, Any],
    catalog: dict[str, dict[str, str]],
    catalog_sha256: str,
) -> dict[str, Any]:
    """Recompute the program and reject any supplied provenance mutation."""

    if not isinstance(value, dict):
        _fail("PRM014_PROGRAM_HASH_MISMATCH", "/prompt_program")
    expected = build_prompt_program(manifest, scene, catalog, catalog_sha256)
    supplied_units = value.get("units")
    if not isinstance(supplied_units, list):
        _fail("PRM001_EVENT_COVERAGE_INVALID", "/prompt_program/units")
    expected_events = [
        unit["event_ids"][0]
        for unit in expected["units"]
        if unit["kind"] == "event"
    ]
    supplied_events = [
        unit.get("event_ids", [None])[0]
        for unit in supplied_units
        if isinstance(unit, dict) and unit.get("kind") == "event" and unit.get("event_ids")
    ]
    if set(supplied_events) != set(expected_events) or len(supplied_events) != len(expected_events):
        _fail("PRM001_EVENT_COVERAGE_INVALID", "/prompt_program/units")
    if supplied_events != expected_events:
        _fail("PRM002_CAUSAL_ORDER_INVALID", "/prompt_program/units")
    if value != expected:
        _fail("PRM014_PROGRAM_HASH_MISMATCH", "/prompt_program")
    return value


def lint_request(value: object) -> dict[str, Any]:
    request = _object(value, LINT_REQUEST_KEYS, "/")
    if request["schema_version"] != 1 or not bindings._is_int(request["schema_version"]):
        _fail("COMPILE001_REQUEST_CONTRACT_INVALID", "/schema_version")
    manifest = reference_planner.validate_reference_manifest(request["reference_manifest"])
    scene = scene_ir_check.validate_scene_ir(request["scene_ir"])
    reference_planner._align_manifest_targets_to_scene(manifest, scene)
    validate_supported_scope(scene)
    catalog, catalog_hash = validate_catalog(scene, request["realization_catalog"])
    return build_prompt_program(manifest, scene, catalog, catalog_hash)


def _self_test() -> None:
    if not REFERENCE_SKELETON.search(_comparison_skeleton("＠Ｉｍａｇｅ１")):
        _fail("SELF_TEST_FAILED")
    if REFERENCE_SKELETON.search(_comparison_skeleton("ordinary product image")):
        _fail("SELF_TEST_FAILED")
    try:
        bindings.parse_json_bytes(b'{"schema_version":1,"schema_version":1}')
    except bindings.BindingError as exc:
        if exc.code != "JSON_DUPLICATE_KEY":
            _fail("SELF_TEST_FAILED")
    else:
        _fail("SELF_TEST_FAILED")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lint a bilingual realization catalog and emit its semantic program."
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            _self_test()
            print("semantic lint self-test passed")
            return 0
        raw = sys.stdin.buffer.read(MAX_COMPILER_INPUT_BYTES + 1)
        if len(raw) > MAX_COMPILER_INPUT_BYTES:
            _fail("JSON_TOO_LARGE")
        program = lint_request(
            bindings.parse_json_bytes(
                raw,
                max_bytes=MAX_COMPILER_INPUT_BYTES,
            )
        )
        payload = bindings.canonical_json(program)
    except bindings.BindingError as exc:
        print(f"semantic-lint error: {exc.code} at {exc.pointer}", file=sys.stderr)
        return 1
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
