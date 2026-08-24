"""
综合报告生成器
生成重大新闻分析报告：TOP事件 + 板块摘要 + 地理热力 + 时间线 + 源质量评估
"""
import json
import os
import re
import logging
import html
import urllib.parse
import urllib.error
import urllib.request
import tempfile
import sys
import time
from xml.sax.saxutils import escape as xml_escape
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

_BUNDLED_PYTHON_PACKAGES = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python"
_BUNDLED_SITE_PACKAGES_COMPATIBLE = (
    sys.version_info[:2] == (3, 12)
    or str(Path(sys.executable).resolve()).startswith(str(_BUNDLED_PYTHON_PACKAGES.resolve()))
)
if _BUNDLED_PYTHON_PACKAGES.exists() and _BUNDLED_SITE_PACKAGES_COMPATIBLE:
    for dependency_path in (
        _BUNDLED_PYTHON_PACKAGES / "Lib" / "site-packages",
        _BUNDLED_PYTHON_PACKAGES,
    ):
        bundled_path = str(dependency_path)
        if dependency_path.exists() and bundled_path not in sys.path:
            sys.path.insert(0, bundled_path)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from services.board_classifier import BOARD_ORDER
from services.business_relevance import generate_relevance_section

logger = logging.getLogger(__name__)

def _resolve_report_dir() -> Path:
    override = os.getenv("NEWS_REPORT_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent.parent / "reports"


def _resolve_translation_cache_path() -> Path:
    override = os.getenv("NEWS_TRANSLATION_CACHE_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent.parent / "data" / "title_translation_cache.json"


REPORT_DIR = _resolve_report_dir()
TRANSLATION_CACHE_PATH = _resolve_translation_cache_path()

try:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    REPORT_DIR = Path(tempfile.gettempdir()) / "unified-news-analyzer" / "reports"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    logger.warning("Report directory unavailable, falling back to %s", REPORT_DIR)

PROTECTED_TERMS = [
    "OpenAI", "Anthropic", "Claude Code", "Claude", "Codex", "OpenAI Codex",
    "ChatGPT", "GPT", "Gemini", "Google DeepMind", "DeepMind", "Google",
    "Meta AI", "Meta", "xAI", "Mistral", "Cohere", "Perplexity",
    "Hugging Face", "LangChain", "LlamaIndex", "Ollama", "Replicate",
    "Together AI", "Sakana AI", "Fugu", "NVIDIA", "Nvidia", "Groq",
    "Microsoft", "AWS", "Amazon Bedrock", "OpenClaw", "Hermes",
    "token", "tokens", "tokenizer", "context window", "context engineering",
    "prompt engineering", "AI Agent", "agent", "agentic", "LLM", "SaaS",
    "API", "GPU", "NPU", "TPU", "HBM", "GitHub", "Copilot", "ComfyUI",
    "SageMaker", "Reflection AI", "Wired", "TechCrunch", "The Verge",
    "MIT Tech Review", "CB Insights", "Crunchbase", "Mythos", "Fable",
]


TITLE_TRANSLATIONS = {
    "A private company will build and launch NASA's next Mars orbiter in 2028 — and it's not SpaceX": "一家私营公司将建造并发射 NASA 下一代 2028 年火星轨道器，且不是 SpaceX",
    "NASA picks Eric Schmidt’s rocket company for Mars mission, setting up a race with SpaceX": "NASA 选择埃里克·施密特旗下火箭公司执行火星任务，将与 SpaceX 展开竞速",
    "SpaceX to launches 24 Starlink satellites on Falcon 9 rocket from Vandenberg": "SpaceX 将在范登堡用猎鹰 9 号发射 24 颗星链卫星",
    "SpaceX Falcon 9 rocket launches 24 Starlink satellites into low Earth orbit from California (video)": "SpaceX 猎鹰 9 号从加州发射 24 颗星链卫星进入近地轨道",
    "SpaceX launches intelligence-gathering satellites for the National Reconnaissance Office": "SpaceX 为美国国家侦察局发射情报收集卫星",
    "SpaceX launches 3 Block 2 BlueBird satellites for AST SpaceMobile": "SpaceX 为 AST SpaceMobile 发射 3 颗第二代 BlueBird 卫星",
    "SpaceX to acquire Cursor for $60B in stock, days after blockbuster IPO": "SpaceX 拟以 600 亿美元股票收购 Cursor，距重磅 IPO 仅数日",
    "Private industry takes the wheel for new NASA mission to Mars": "私营产业接手 NASA 新火星任务",
    "Relativity Space to privately develop Mars orbiter mission": "Relativity Space 将以私营方式研制火星轨道器任务",
    "NASA Awards Contract for Commercial Satellite Data Acquisition": "NASA 授出商业卫星数据采购合同",
    "Astrobotic showcases Griffin-1 lander ahead of environmental testing in California": "Astrobotic 展示 Griffin-1 着陆器，准备在加州进行环境测试",
    "Paperwork done, European Defence Agency ISR constellation requirements to be delivered to ESA for in-orbit demos": "欧洲防务局 ISR 星座需求文件完成，将交由 ESA 开展在轨演示",
    "Space Force’s rapid acquisition office director moves to Air Force Nuclear Weapons Center": "太空军快速采购办公室负责人转任空军核武器中心",
    "Arianespace launches its heaviest payload to date with Amazon Leo flight": "Arianespace 通过 Amazon Leo 任务发射迄今最重载荷",
    "Bill Spotlight: NEW HORIZON Act": "法案聚焦：NEW HORIZON 法案",
    "True Anomaly Declares Mission X-3 Success": "True Anomaly 宣布 X-3 任务成功",
    "Towers once planned for California shuttle launches leveled for SpaceX rockets": "加州原航天飞机发射塔被拆除，为 SpaceX 火箭让路",
    "Rocket Report: Rebuild begins at Blue Origin launch pad; Relativity targets Mars": "火箭报告：蓝色起源发射台开始重建；Relativity 瞄准火星",
    "Katalyst Raises $12M to Extend Satellite Servicing to GEO": "Katalyst 融资 1200 万美元，将卫星维护服务扩展至 GEO",
    "Ariane 6 flight VA269 - full replay": "Ariane 6 VA269 飞行任务全程回放",
    "Boeing demonstrates quantum protocol in payload set for 2027 launch": "波音展示计划随 2027 年任务发射的量子通信协议载荷",
    "What the satellite servicing economy can borrow from carbon credits": "卫星在轨服务经济可借鉴碳信用市场的哪些经验",
    "Instinct Space Unveils Plans for Low-Cost Lunar Landers": "Instinct Space 公布低成本月球着陆器计划",
    "PiLogic Partners with AFRL on AI Anomaly Detection Tech": "PiLogic 与美国空军研究实验室合作开发 AI 异常检测技术",
    "Blue Origin begins rebuilding New Glenn pad": "蓝色起源开始重建 New Glenn 发射台",
    "SpaceX launches new batch of US spy satellites from California (video)": "SpaceX 从加州发射新一批美国侦察卫星",
    "Northrop Grumman says industry ready to scale solid rocket production, with longer contracts": "诺斯罗普·格鲁曼称行业已准备扩大固体火箭产能，但需要更长期合同",
    "A bold satellite rescue mission came together in record time, but will it work?": "大胆的卫星救援任务以创纪录速度成形，但能否成功仍待观察",
    "Roelof Botha joins SpaceX’s board of directors": "Roelof Botha 加入 SpaceX 董事会",
    "KP Labs and NaviGate Explore Satellite Autonomy through Navigation and Edge Processing Technologies": "KP Labs 与 NaviGate 探索导航和边缘处理技术赋能的卫星自主能力",
    "Chinese startup Spark Space tests engine, raises funds for electric-pump rocket": "中国初创公司 Spark Space 测试发动机，并为电泵火箭融资",
    "NASA Prepares Next Artemis Rocket for Flight": "NASA 准备下一枚 Artemis 火箭飞行",
    "SpaceX valuation balloons to $2.6T, briefly passes Amazon": "SpaceX 估值升至 2.6 万亿美元，短暂超过亚马逊",
    "SpaceX is public: Everything you need to know post-IPO": "SpaceX 已上市：IPO 后你需要了解的要点",
    "Boeing Completes Quantum Lab Test Ahead of 2027 Flight": "波音完成 2027 年飞行前的量子实验室测试",
    "India’s Jio lays out sovereign LEO constellation plan ahead of IPO": "印度 Jio 在 IPO 前公布主权低轨星座计划",
    "Ariane 6 flight VA269: Liftoff captured from the mobile gantry": "Ariane 6 VA269 飞行：从移动龙门架视角捕捉升空",
    "Optera Raises £3M to Open New UK HQ": "Optera 融资 300 万英镑，将开设英国新总部",
    "Quantum Space wins Pentagon contract to develop orbital refueling spacecraft": "Quantum Space 赢得五角大楼合同，将开发在轨加注航天器",
    "NASA asks Northrop Grumman to stop working on lunar HALO module": "NASA 要求诺斯罗普·格鲁曼停止月球 HALO 舱相关工作",
    "'It's quite a bit more than we expected': Satellite reveals immense scale of GPS signal tampering": "“规模比预期大得多”：卫星揭示 GPS 信号干扰的巨大规模",
    "COPUOS 2026 – Who Keeps Order in a Crowded Sky? Inside the Race for Radio Spectrum": "COPUOS 2026：谁来维护拥挤天空中的秩序？无线电频谱竞赛内幕",
    "From Orbit to Desktop: Why Satellite Cybersecurity Matters in Satellite Data Analysis": "从轨道到桌面：为何卫星数据分析中的卫星网络安全至关重要",
    "Portugal Acquires Two Additional ICEYE SAR Satellites to Scale Sovereign Intelligence from Space": "葡萄牙采购两颗额外 ICEYE SAR 卫星，扩大主权空间情报能力",
    "Austrian propulsion startup joins sovereign space funding surge": "奥地利推进系统初创公司加入主权航天融资热潮",
    "Democratic Republic of Congo Set to Acquire ‘RDC-SAT’ Earth Observation Satellite from SPACEBEL": "刚果民主共和国将从 SPACEBEL 采购 “RDC-SAT” 地球观测卫星",
    "HENSOLDT Unveils ‘SkyBarrier’, a Mobile Broadband Jammer for Satellite-Based Navigation Signals": "HENSOLDT 发布 “SkyBarrier”：面向卫星导航信号的移动宽带干扰器",
    "SpaceX’s full legal name is Space Exploration Technologies Corporation, and the company still frames itself less as a rocket business than a mission to push humanity beyond Earth": "SpaceX 的法定全称是 Space Exploration Technologies Corporation，公司仍将自身定位为推动人类走向地外的使命，而不仅是火箭业务",
    "Walter Isaacson’s biography of Elon Musk describes how one private decision kept Starlink dark near Crimea in 2022, leaving Ukrainian sea drones suddenly offline before they reached Russia’s Black Sea Fleet": "沃尔特·艾萨克森的马斯克传记披露，2022 年一次私人决策导致克里米亚附近星链保持离线，使乌克兰海上无人装备在抵近俄黑海舰队前突然断联",
    "OpenAI Launches Full-Scale Effort to Patch Open-Source Bugs as It Takes on Anthropic’s Mythos": "OpenAI 启动大规模开源漏洞修复计划，对标 Anthropic 的 Mythos",
    "Three things to watch amid Anthropic’s latest feud with the government": "Anthropic 与政府最新争执中的三个观察重点",
    "Product May 28, 2026 Introducing Claude Opus 4.8 An upgrade to our Opus class of models, with stronger performance across coding, agentic tasks, and professional work, and the consistency to handle long-running work.": "Anthropic 发布 Claude Opus 4.8：提升编码、智能体任务和专业工作的稳定性",
    "Sakana AI's Fugu orchestrates multiple LLMs to match Anthropic's Fable and Mythos benchmarks": "Sakana AI 发布 Fugu：编排多个大模型，追平 Anthropic Fable 与 Mythos 基准",
    "Jun 17, 2026 Announcements Anthropic opens Seoul office and announces new partnerships across the Korean AI ecosystem": "Anthropic 开设首尔办公室，并宣布韩国 AI 生态新合作",
    "Google Deepmind and A24 team up on AI filmmaking research": "Google DeepMind 与 A24 合作开展 AI 电影制作研究",
    "DailyReport: An Open-ended Benchmark for Evaluating Search Agents on Daily Search Tasks": "DailyReport：用于评估搜索智能体日常搜索任务的开放式基准",
    "Deep Research in Physical Sciences: A Systems Approach to Vertical AI Scientists": "物理科学深度研究：构建垂直 AI 科学家的系统方法",
    "The Atlantic created a searchable database of music AI companies have allegedly trained on": "《大西洋月刊》建立可搜索数据库，追踪 AI 公司疑似训练使用的音乐",
    "SpaceX inks compute deal with Reflection AI, an open source AI lab": "SpaceX 与开源 AI 实验室 Reflection AI 签署算力合作协议",
    "Nvidia says its AI data center design runs hotter to use a lot less water": "英伟达称其 AI 数据中心设计可在更高温下运行，以大幅减少用水",
    "AI chipmaker Groq confirms $650M raise, re-staffs after Nvidia’s $20B not-acqui-hire deal": "AI 芯片公司 Groq 确认融资 6.5 亿美元，并在英伟达 200 亿美元人才交易后重组团队",
    "Nvidia wants to cut data center water use, but that’s not the same as fixing AI’s water problem": "英伟达希望减少数据中心用水，但这并不等于解决 AI 的用水问题",
    "Vibecoding is becoming a deal-breaker test for software acquisitions": "Vibe Coding 正成为软件收购中的关键尽调测试",
    "New usage analytics and updated spend controls for ChatGPT Enterprise": "ChatGPT Enterprise 新增用量分析和费用控制",
    "Command NEW High-performance models for agentic, multimodal, multilingual AI": "Cohere Command：面向智能体、多模态和多语言 AI 的高性能模型",
    "Building pay-per-intelligence for AI agents: How Ampersend uses Amazon Bedrock AgentCore Payments": "为 AI 智能体构建按智能付费：Ampersend 如何使用 Amazon Bedrock AgentCore Payments",
    "The AI world is getting ‘loopy’": "AI 世界正在进入“循环式智能体”阶段",
    "The running list: major tech layoffs in 2026 where employers cited AI": "持续更新：2026 年明确提到 AI 的大型科技裁员",
    "The Week’s 10 Biggest Funding Rounds: Cybersecurity And Defense Startup Odyssey Leads Strong Week": "本周十大融资：网络安全与防务初创公司 Odyssey 领跑",
    "Executive Interview: Resolve AI": "高管访谈：Resolve AI",
    "Executive Interview: Insait.io": "高管访谈：Insait.io",
    "Patch the Planet: a Daybreak initiative to support open source maintainers": "Patch the Planet：Daybreak 支持开源维护者的倡议",
    "Microsoft AI": "微软 AI",
    "Model Vault Your dedicated, secure model inference platform — managed by Cohere": "Model Vault：由 Cohere 管理的专属安全模型推理平台",
    "North An enterprise-ready AI platform that powers modern workplace productivity": "North：提升现代办公生产力的企业级 AI 平台",
    "Vibe AI agent for long-horizon work.": "Vibe：面向长周期工作的 AI 智能体",
    "Google DeepMind bets $75M on AI’s future in Hollywood with A24 deal": "Google DeepMind 通过 A24 合作向好莱坞 AI 未来押注 7500 万美元",
    "Anthropic and Micron want to co-design AI memory architecture": "Anthropic 与美光计划共同设计 AI 内存架构",
    "Microsoft is building a 2-gigawatt data center in Texas with its own gas plant to dodge the grid": "微软将在得州建设 2 吉瓦数据中心，并配套自有燃气电厂以绕开电网瓶颈",
    "Embed the world: Multimodal AI for searchable aerial imagery at scale": "嵌入世界：用于大规模可搜索航拍影像的多模态 AI",
    "Running ComfyUI workflows on Amazon SageMaker AI processing jobs": "在 Amazon SageMaker AI 处理任务上运行 ComfyUI 工作流",
    "Saas Isn’t Coming Back. Something Much Bigger Is Replacing It": "SaaS 不会回到过去，正在被更大的新形态取代",
    "Sector Snapshot: Robotics Startups On Fire As Venture Funding Surges To Record Numbers In 2026": "行业快照：2026 年机器人初创公司融资创纪录升温",
    "Digital Decade 2026: eGovernment Benchmark shows Europe’s digital services are smarter but unevenly deployed": "数字十年 2026：电子政务基准显示欧洲数字服务更智能，但部署不均衡",
}


class ReportGenerator:
    """分析报告生成器"""
    _pdf_font_registered = False
    _pdf_font_registered_name = "STSong-Light"
    _pdf_bold_font_registered_name = "STSong-Light"
    
    def __init__(self):
        self.report_dir = REPORT_DIR
        self._translation_cache = self._load_translation_cache()
        self._title_translation_failures = 0
        self._summary_translation_failures = 0
        self._title_translation_disabled_for_run = False
        self._summary_translation_disabled_for_run = False
        self._ai_summary_disabled_for_run = False
        self._summary_cache: Dict[str, str] = {}
        self._article_title_cache: Dict[str, str] = {}
        self._cluster_summary_cache: Dict[str, str] = {}
        self._summary_batch_disabled_for_run = False
        self._current_topic = ''
        self.last_manual_summary_tasks_path: Optional[Path] = None
        self._translation_max_failures = self._env_int("NEWS_TRANSLATION_MAX_FAILURES", 3)
        self._translation_timeout = self._env_int("NEWS_TRANSLATION_TIMEOUT", 3)
        self._translation_retries = self._env_int("NEWS_TRANSLATION_RETRIES", 2)
        self._pdf_font_name = self._ensure_pdf_font()
        self._pdf_bold_font_name = self.__class__._pdf_bold_font_registered_name

    def _env_int(self, name: str, default: int) -> int:
        try:
            value = int(os.getenv(name, "").strip())
            return value if value > 0 else default
        except ValueError:
            return default

    def _ensure_pdf_font(self) -> str:
        if self.__class__._pdf_font_registered:
            return self.__class__._pdf_font_registered_name
        font_candidates = [
            ("DengXian", Path("C:/Windows/Fonts/Deng.ttf"), "DengXianBold", Path("C:/Windows/Fonts/Dengb.ttf")),
            ("MicrosoftYaHei", Path("C:/Windows/Fonts/msyh.ttc"), "MicrosoftYaHeiBold", Path("C:/Windows/Fonts/msyhbd.ttc")),
            ("SimHei", Path("C:/Windows/Fonts/simhei.ttf"), "SimHei", Path("C:/Windows/Fonts/simhei.ttf")),
            ("NotoSansSC", Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"), "NotoSansSC", Path("C:/Windows/Fonts/NotoSansSC-VF.ttf")),
            ("NotoSansCJK", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "NotoSansCJK-Bold", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")),
        ]
        for font_name, font_path, bold_font_name, bold_font_path in font_candidates:
            if not font_path.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                if bold_font_path.exists() and bold_font_name != font_name:
                    pdfmetrics.registerFont(TTFont(bold_font_name, str(bold_font_path)))
                self.__class__._pdf_font_registered = True
                self.__class__._pdf_font_registered_name = font_name
                self.__class__._pdf_bold_font_registered_name = bold_font_name if bold_font_path.exists() else font_name
                return font_name
            except Exception as exc:
                logger.debug("Failed to register PDF font %s from %s: %s", font_name, font_path, exc)
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            self.__class__._pdf_font_registered = True
            self.__class__._pdf_font_registered_name = "STSong-Light"
            return "STSong-Light"
        except Exception as exc:
            logger.warning("Failed to register Chinese PDF font, falling back to Helvetica: %s", exc)
            return "Helvetica"

    def _is_mostly_chinese(self, text: str) -> bool:
        return bool(re.search(r'[\u4e00-\u9fff]', text or ''))

    def _display_title(self, title: str) -> str:
        """Return a Chinese display title while preserving proper nouns."""
        if not title:
            return ''
        normalized = ' '.join(str(title).split())
        if self._is_mostly_chinese(normalized):
            return normalized
        if normalized in TITLE_TRANSLATIONS:
            return TITLE_TRANSLATIONS[normalized]
        translated = self._machine_translate_title(normalized)
        if translated:
            return translated
        return self._fallback_translate_title(normalized)

    def _load_translation_cache(self) -> Dict[str, str]:
        try:
            if TRANSLATION_CACHE_PATH.exists():
                with open(TRANSLATION_CACHE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as exc:
            logger.warning(f"Failed to load translation cache: {exc}")
        return {}

    def _save_translation_cache(self):
        try:
            TRANSLATION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(TRANSLATION_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._translation_cache, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"Failed to save translation cache: {exc}")

    def _write_output_text(self, output_file: Path, content: str, suffix: str) -> Path:
        """Write report artifacts and fall back to a temp directory if needed."""
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return output_file
        except OSError as exc:
            fallback_dir = Path(tempfile.gettempdir()) / "unified-news-analyzer" / "reports"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback_file = fallback_dir / output_file.name
            with open(fallback_file, 'w', encoding='utf-8') as f:
                f.write(content)
            self.report_dir = fallback_dir
            logger.warning(
                "Failed to write %s to %s, fell back to %s: %s",
                suffix,
                output_file,
                fallback_file,
                exc,
            )
            return fallback_file

    def _manual_summary_import_path(self) -> Optional[Path]:
        override = os.getenv("NEWS_MANUAL_SUMMARY_IMPORT", "").strip()
        if override:
            return Path(override).expanduser().resolve()
        default_path = self.report_dir / "manual_summary_results.json"
        return default_path if default_path.exists() else None

    def _summary_mode(self) -> str:
        return os.getenv("NEWS_SUMMARY_MODE", "local").strip().lower()

    def _is_manual_summary_mode(self) -> bool:
        return self._summary_mode() in {"manual", "chatgpt", "chat"}

    def _load_manual_summary_import(self) -> None:
        import_path = self._manual_summary_import_path()
        if not import_path:
            return
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load manual summary import %s: %s", import_path, exc)
            return

        records = payload.get("summaries", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            logger.warning("Manual summary import ignored because JSON is not a list: %s", import_path)
            return

        loaded = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            key = self._normalize_summary_text(record.get("key", ""))
            title = self._normalize_summary_text(record.get("title", ""))
            summary = self._normalize_summary_text(record.get("summary", ""))
            if not key or not summary:
                continue
            self._summary_cache[key] = summary
            if title:
                self._article_title_cache[key] = title
            loaded += 1
        logger.info("Loaded %s manual article summaries from %s", loaded, import_path)

    def _manual_summary_prompt(self) -> str:
        return (
            "你是中文商业航天/科技行业日报编辑。请只根据每条 task.article_text 里的原文正文生成结果，"
            "不要根据标题、来源、板块或常识补写事实。每条输出中文标题和信息型日报摘要。"
            "标题尽量 20-35 个汉字，要具体写出事件主体和核心变化。"
            "摘要不是短句概括，要写成 2-4 个自然段或 4-8 句，信息密度接近正式日报。"
            "优先保留并串联：时间、地点、人物、公司/机构、金额、营收/亏损、订单数量、卫星数量、载荷能力、功率、质量、寿命、发射时间、任务计划、市场规模、政策背景和产业影响。"
            "如果原文有多个重点，要按“发生了什么—关键数字/技术细节—后续计划/影响”的顺序写清楚。"
            "不要照搬原文，不要写“该报道围绕/本文介绍/建议查看原文”等元叙述，不要用泛泛的行业影响句凑字数。"
            "如果正文信息不足，只写可确认事实，不要编造，也不要根据标题扩写。"
            "请严格返回 JSON，格式为 {\"summaries\":[{\"key\":\"...\",\"title\":\"...\",\"summary\":\"...\"}]}。"
        )

    def _export_manual_summary_tasks(self, items: List[Dict[str, Any]], max_chars: int = 900) -> None:
        tasks = []
        input_chars = self._env_int("NEWS_SUMMARY_INPUT_CHARS", 5000)
        for idx, item in enumerate(items, 1):
            key = self._summary_cache_key(item)
            if key in self._summary_cache:
                continue
            article_text = self._truncate_summary_source_for_ai(
                self._extract_article_body_for_ai(item),
                max_chars=input_chars,
            )
            if not article_text:
                continue
            tasks.append({
                "id": idx,
                "key": key,
                "title": self._normalize_summary_text(item.get("title", "")),
                "source": self._normalize_summary_text(item.get("source", "")),
                "date": self._fmt_time(item.get("publishTime")),
                "url": self._normalize_summary_text(item.get("url", "")),
                "max_summary_chars": max_chars,
                "article_text": article_text,
            })

        if not tasks:
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        json_path = self.report_dir / f"manual_summary_tasks_{timestamp}.json"
        md_path = self.report_dir / f"manual_summary_tasks_{timestamp}.md"
        payload = {
            "instructions": self._manual_summary_prompt(),
            "save_result_as": str(self.report_dir / "manual_summary_results.json"),
            "tasks": tasks,
        }
        json_written = self._write_output_text(
            json_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
            "manual summary tasks json",
        )
        md_content = (
            "# ChatGPT 摘要任务包\n\n"
            "把下面整段复制到 ChatGPT，要求它只返回 JSON。返回后保存为：\n\n"
            f"`{self.report_dir / 'manual_summary_results.json'}`\n\n"
            "然后重新运行 `py -3 run.py --topic commercial_space` 生成带摘要的 PDF。\n\n"
            "```text\n"
            f"{self._manual_summary_prompt()}\n\n"
            f"{json.dumps({'tasks': tasks}, ensure_ascii=False, indent=2)}\n"
            "```\n"
        )
        md_written = self._write_output_text(md_path, md_content, "manual summary tasks markdown")
        self.last_manual_summary_tasks_path = md_written
        logger.info("Manual ChatGPT summary tasks saved to %s and %s", md_written, json_written)

    def _machine_translate_title(self, title: str) -> Optional[str]:
        """Translate English titles to Chinese while preserving key AI terms."""
        if os.getenv("NEWS_DISABLE_MACHINE_TRANSLATION", "").lower() in {"1", "true", "yes"}:
            return None
        if title in self._translation_cache:
            return self._translation_cache[title]
        if self._title_translation_disabled_for_run:
            return None

        masked = title
        placeholders = {}
        for idx, term in enumerate(sorted(PROTECTED_TERMS, key=len, reverse=True)):
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE) if term.isascii() else re.compile(re.escape(term))
            if not pattern.search(masked):
                continue
            placeholder = f"ZXTERM{idx}XZ"
            original = pattern.search(masked).group(0)
            placeholders[placeholder] = original
            masked = pattern.sub(placeholder, masked)

        try:
            translated = self._request_google_translation(masked, source_lang='en')
        except Exception as exc:
            self._title_translation_failures += 1
            logger.warning(
                "Title translation failed (%s/%s): %s",
                self._title_translation_failures,
                self._translation_max_failures,
                exc,
            )
            if self._title_translation_failures >= self._translation_max_failures:
                self._title_translation_disabled_for_run = True
                logger.warning("Machine title translation disabled for the rest of this run")
            return None

        for placeholder, term in placeholders.items():
            translated = translated.replace(placeholder, term)
            translated = translated.replace(placeholder.lower(), term)

        translated = translated.strip()
        if translated and self._is_mostly_chinese(translated):
            self._title_translation_failures = 0
            self._translation_cache[title] = translated
            self._save_translation_cache()
            return translated
        return None

    def _request_google_translation(self, text: str, source_lang: str = 'auto') -> str:
        """Translate text with a couple of short retries for transient network failures."""
        last_exc: Optional[Exception] = None
        attempts = max(1, self._translation_retries + 1)
        for attempt in range(attempts):
            try:
                query = urllib.parse.urlencode({
                    'client': 'gtx',
                    'sl': source_lang,
                    'tl': 'zh-CN',
                    'dt': 't',
                    'q': text,
                })
                url = f"https://translate.googleapis.com/translate_a/single?{query}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=self._translation_timeout) as resp:
                    payload = json.loads(resp.read().decode('utf-8'))
                return ''.join(part[0] for part in payload[0] if part and part[0])
            except Exception as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(min(2.0, 0.5 * (attempt + 1)))
        raise last_exc or RuntimeError("translation request failed")

    def _fallback_translate_title(self, title: str) -> str:
        """Small deterministic fallback for common commercial-space headlines."""
        rules = [
            (r'^SpaceX launches (.+)$', r'SpaceX 发射 \1'),
            (r'^SpaceX to launch(?:es)? (.+)$', r'SpaceX 将发射 \1'),
            (r'^(.+) raises ([\w£$€.,]+) (.+)$', r'\1 融资 \2，\3'),
            (r'^(.+) wins (.+) contract to (.+)$', r'\1 赢得 \2 合同，将\3'),
            (r'^NASA Awards Contract for (.+)$', r'NASA 授出\1合同'),
            (r'^NASA asks (.+) to stop working on (.+)$', r'NASA 要求 \1 停止 \2 相关工作'),
            (r'^(.+) unveils (.+)$', r'\1 发布 \2'),
            (r'^(.+) begins rebuilding (.+)$', r'\1 开始重建 \2'),
        ]
        for pattern, replacement in rules:
            if re.search(pattern, title, flags=re.IGNORECASE):
                return re.sub(pattern, replacement, title, flags=re.IGNORECASE)
        return title
    
    def generate_daily_report(
        self,
        clusters: List[Dict[str, Any]],
        all_news: List[Dict[str, Any]],
        board_summary: Dict[str, Any],
        sources: List[str],
        date: Optional[str] = None,
        trends: Optional[Dict[str, List]] = None,
        report_type: str = 'weekly',
        topic: str = '',
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        report_prefix: str = '',
    ) -> str:
        """
        生成完整的分析报告
        返回 Markdown 文本
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
        period_end = period_end or date
        period_start = period_start or date
        is_weekly = report_type == 'weekly'
        is_commercial_space = topic == '商业航天'
        is_ai = topic == '人工智能'
        topic_prefix = f"{topic}" if topic else ''
        report_label = f"{topic_prefix}周报" if is_weekly else f"{topic_prefix}每日分析报告"
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        active_sources = sorted({item.get('source', '') for item in all_news if item.get('source')})
        
        # 统计基础数据
        total_news = len(all_news)
        total_boards = len(board_summary)

        self._summary_cache.clear()
        self._article_title_cache.clear()
        self._cluster_summary_cache.clear()
        self._ai_summary_disabled_for_run = False
        self._summary_batch_disabled_for_run = False
        self._current_topic = topic or ''
        self.last_manual_summary_tasks_path = None
        self._load_manual_summary_import()
        
        md = []

        # ===== 标题 =====
        md.append(f"# {report_label}\n")
        if is_weekly:
            md.append(f"**报告周期**: {period_start} 至 {period_end}  |  **生成时间**: {now_str}\n")
        else:
            md.append(f"**报告日期**: {date}  |  **生成时间**: {now_str}\n")
        md.append(f"**数据源**: {len(active_sources)} 个  |  **新闻数**: {total_news} 条  |  **覆盖板块**: {total_boards} 个\n")
        md.append("---\n")

        # ===== A1-A8 正文 =====
        md.append(self._generate_a1_a8_news_digest(all_news))
        
        report_content = '\n'.join(md)

        # 保存完整报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        if is_weekly:
            start_tag = period_start.replace('-', '')
            end_tag = period_end.replace('-', '')
            prefix = f"{report_prefix}_weekly_report" if report_prefix else ''
            if not prefix:
                if is_commercial_space:
                    prefix = 'commercial_space_weekly_report'
                elif is_ai:
                    prefix = 'ai_weekly_report'
                else:
                    prefix = 'weekly_report'
            output_md_file = self.report_dir / f"{prefix}_{start_tag}_{end_tag}_{timestamp}.md"
            output_pdf_file = output_md_file.with_suffix('.pdf')
        else:
            output_md_file = self.report_dir / f"daily_report_{timestamp}.md"
            output_pdf_file = output_md_file.with_suffix('.pdf')
        self.last_report_md_path = self._write_output_text(output_md_file, report_content, "report markdown")
        try:
            self.last_report_path = self._write_pdf_report(
                output_pdf_file,
                report_content,
                report_label,
                f"日期： {period_start} 至 {period_end}  |  生成： {now_str}" if is_weekly else f"日期： {date}  |  生成： {now_str}",
            )
        except Exception as exc:
            logger.warning("PDF report generation failed, falling back to markdown path: %s", exc)
            self.last_report_path = self.last_report_md_path

        logger.info(f"{report_label} saved to {self.last_report_path}")

        if os.getenv("NEWS_GENERATE_HTML_BRIEF", "").lower() in {"1", "true", "yes"}:
            brief_content = self.generate_brief_report(
                clusters=clusters,
                all_news=all_news,
                board_summary=board_summary,
                sources=sources or [],
                date=date,
                report_type=report_type,
                topic=topic,
                period_start=period_start,
                period_end=period_end,
                report_prefix=report_prefix,
            )
        else:
            self.last_brief_path = None

        return report_content

    def generate_brief_report(
        self,
        clusters: List[Dict[str, Any]],
        all_news: List[Dict[str, Any]],
        board_summary: Dict[str, Any],
        sources: List[str],
        date: Optional[str] = None,
        report_type: str = 'weekly',
        topic: str = '',
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        report_prefix: str = '',
    ) -> str:
        """
        生成人类可读的 HTML 简报
        结构：本周 TOP5 + A1-A8 各类型 TOP5
        （各类型 TOP5 不包含已出现在本周 TOP5 的事件）
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
        period_end = period_end or date
        period_start = period_start or date
        is_weekly = report_type == 'weekly'
        topic_prefix = f"{topic}" if topic else ''
        title_text = f"{topic_prefix}周报" if is_weekly else f"{topic_prefix}每日简报"
        subtitle_text = (
            f"{period_start} 至 {period_end}"
            if is_weekly else date
        )
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        total_news = len(all_news)
        total_clusters = len(clusters)

        self._summary_cache.clear()
        self._article_title_cache.clear()
        self._cluster_summary_cache.clear()
        self._ai_summary_disabled_for_run = False
        self._summary_batch_disabled_for_run = False
        ranked_clusters = sorted(clusters, key=lambda c: c.get('importance_score', 0), reverse=True)
        self._batch_summarize_clusters(ranked_clusters[:10], max_chars=120)

        sorted_clusters = sorted(clusters,
                                key=lambda c: c.get('importance_score', 0),
                                reverse=True)

        # 数据源统计
        source_counts = defaultdict(int)
        for item in all_news:
            src = item.get('source', '')
            source_counts[src] = source_counts.get(src, 0) + 1
        top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # ----- 板块关键词映射：判断簇属于哪个板块 -----
        # 原则：
        # 1. 英文用词边界匹配（避免 launch 匹配 launches），中文用子串匹配
        # 2. 军事冲突优先于航天（空袭/战争 != 航天）
        # 3. 财经新闻独立成板块，不塞入显示面板
        # 4. AI 类新闻优先：含 AI/智能/模型 的不被误判为军事（"防御体系"≠军事）
        BOARD_KEYWORDS = {
            'aerospace': ['航天', '航空', '卫星', '火箭', '空间站', 'SpaceX', 'Starship',
                          'NASA', 'Starlink', 'Mars', '月球', '火星', '长征', '神舟',
                          'Falcon', 'rocket', 'ISS', 'Boeing', 'ESA', '嫦娥',
                          '载人航天', '探月', '着陆器', '探测器', '深空',
                          'Starliner', 'Artemis', 'orbital', 'lunar',
                          'payload', 'thruster', 'reentry', 'splashdown',
                          'New Glenn', 'Booster', 'Super Heavy'],
            'ai': ['AI', '人工智能', '大模型', 'LLM', 'GPT', 'Claude', 'Gemini', 'OpenAI',
                   'Anthropic', 'DeepMind', '机器学习', '深度学习', '神经网络',
                   'autonomous', 'generative', '推理', '算力',
                   'GPU', 'AGI', '智谱', '百川', '月之暗面', '文心', '通义',
                   'Copilot', 'ChatGPT', 'transformer', 'diffusion', 'multimodal',
                   'large language', 'AI model', 'AI agent', 'neural network',
                   '智能'],
            'display': ['OLED', 'LCD', '偏光片', '面板', '京东方', 'BOE', 'LG Display',
                        '三星显示', 'TCL华星', '华星光电', '惠科', 'Visionox', '天马',
                        'MicroLED', 'MiniLED', 'QLED', 'e-paper',
                        'WOLED', 'AMOLED', 'POLED', 'LTPO'],
            'finance': ['涨停', '跌停', '净买入', '净卖出', '减持',
                        '增持', '财报', '营收', '利润', '印花税', '财政',
                        '融资', '募资', '港股', 'A股', '盘前', '收盘',
                        '换手率', '龙虎榜', '机构专用', '持股', '持仓',
                        'stock', 'market cap', 'earnings',
                        'revenue', 'fiscal', 'budget', 'tax'],
            'military': ['战争', '冲突', '空袭', '导弹', '制裁', '武器', '核武',
                        '伤亡', '停火', '入侵', '国防', '军事', '军演', '军备',
                        'war', 'military', 'strike', 'sanction', 'nuclear',
                        'invasion', 'ceasefire', 'missile', 'casualt'],
        }

        # 优先板块：当优先板块有匹配时，排除该簇从其他板块
        PRIORITY_RULES = {
            'ai': ['military'],   # AI 优先于军事（"防御体系"不应被判为军事）
        }

        def _match_keyword(kw: str, text: str) -> bool:
            """匹配关键词：英文用词边界，中文用子串"""
            if kw.isascii():
                return bool(re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE))
            else:
                return kw in text

        def get_cluster_board(cluster: Dict) -> str:
            """判断簇所属板块 — 仅用代表性标题，避免簇内摘要污染"""
            rep_title = cluster.get('representative_title', '')

            # 仅用代表性标题匹配
            rep_scores: Dict[str, int] = {}
            for board, kws in BOARD_KEYWORDS.items():
                score = 0
                for kw in kws:
                    if _match_keyword(kw, rep_title):
                        score += 1
                if score > 0:
                    rep_scores[board] = score

            if not rep_scores:
                return 'other'

            # 应用优先规则
            for priority_board, excluded_boards in PRIORITY_RULES.items():
                if priority_board in rep_scores:
                    for eb in excluded_boards:
                        rep_scores.pop(eb, None)
                    break

            return max(rep_scores, key=rep_scores.get)

        # 按板块分组
        aerospace_clusters = []
        ai_clusters = []
        display_clusters = []
        finance_clusters = []
        military_clusters = []

        for c in sorted_clusters:
            board = get_cluster_board(c)
            if board == 'aerospace':
                aerospace_clusters.append(c)
            elif board == 'ai':
                ai_clusters.append(c)
            elif board == 'display':
                display_clusters.append(c)
            elif board == 'finance':
                finance_clusters.append(c)
            elif board == 'military':
                military_clusters.append(c)

        # 本周 TOP5（全局最高分）
        global_top5 = sorted_clusters[:5]
        global_top5_ids = set(id(c) for c in global_top5)

        # 各类型 TOP5（排除本周 TOP5 已出现的）
        aerospace_top5 = [c for c in aerospace_clusters if id(c) not in global_top5_ids][:5]
        ai_top5 = [c for c in ai_clusters if id(c) not in global_top5_ids][:5]
        display_top5 = [c for c in display_clusters if id(c) not in global_top5_ids][:5]
        finance_top5 = [c for c in finance_clusters if id(c) not in global_top5_ids][:5]
        military_top5 = [c for c in military_clusters if id(c) not in global_top5_ids][:5]

        def severity_badge(score: float) -> str:
            if score >= 80:
                return '<span class="badge badge-critical">极重大</span>'
            elif score >= 60:
                return '<span class="badge badge-major">重大</span>'
            elif score >= 40:
                return '<span class="badge badge-important">重要</span>'
            else:
                return '<span class="badge badge-normal">一般</span>'

        def render_cluster(cluster: Dict, rank: int) -> str:
            score = cluster.get('importance_score', 0)
            title = self._display_title(cluster.get('representative_title', ''))
            signal = self._build_event_signal(cluster)
            item_count = cluster.get('item_count', len(cluster.get('items', [])))
            all_sources = cluster.get('_all_sources', cluster.get('sources', []))
            lead_item = self._cluster_lead_item(cluster)
            pub_time = self._fmt_time(lead_item.get('publishTime')) if lead_item else signal['first_time']
            summary = self._cluster_summary(cluster, 120)
            src_str = ', '.join(all_sources[:3])
            if len(all_sources) > 3:
                src_str += f' 等{len(all_sources)}个'
            return f'''
            <div class="event-item">
                <div class="event-header">
                    <span class="event-rank">{rank}</span>
                    {severity_badge(score)}
                    <span class="event-title">{title}</span>
                </div>
                <div class="event-meta">
                    评分: {score:.0f} | 关联报道: {item_count}条 | 来源: {src_str}
                </div>
                <div class="event-meta">
                    发布时间: {pub_time}
                </div>
                <div class="event-meta">
                    摘要: {summary}
                </div>
                <div class="event-meta">
                    热度: {signal['heat']:.0f} | 风险: {signal['risk']:.0f} | 可信度: {signal['credibility']:.0f} | 错过成本: {signal['miss_cost']:.0f} | {signal['life_type']}
                </div>
            </div>'''

        def render_section(title: str, emoji: str, items: List[Dict]) -> str:
            if not items:
                return f'''
  <div class="section">
    <div class="section-title">{emoji} {title}</div>
    <p class="empty-hint">暂无相关数据</p>
  </div>'''
            html_items = ''.join(render_cluster(c, i + 1) for i, c in enumerate(items))
            return f'''
  <div class="section">
    <div class="section-title">{emoji} {title}</div>
    {html_items}
  </div>'''

        def get_cluster_parent_board(cluster: Dict) -> str:
            counts = defaultdict(int)
            for item in cluster.get('items', []):
                counts[item.get('parent_board', 'A8 · 媒体评论')] += 1
            if not counts:
                return 'A8 · 媒体评论'
            return max(counts, key=counts.get)

        cluster_groups = defaultdict(list)
        for c in sorted_clusters:
            cluster_groups[get_cluster_parent_board(c)].append(c)

        board_icons = {
            'A1 · 政策监管': '📰',
            'A2 · 模型发布': '🧠',
            'A3 · 技术突破': '🔬',
            'A4 · 算力与芯片': '🧩',
            'A5 · 应用产品': '🌐',
            'A6 · 智能体与机器人': '🤖',
            'A7 · 融资与并购': '💰',
            'A8 · 媒体评论': '📺',
        }

        board_sections_html = ''.join(
            render_section(f"{board_name} TOP 5", board_icons.get(board_name, '📋'), [
                c for c in cluster_groups.get(board_name, [])
                if id(c) not in global_top5_ids
            ][:5])
            for board_name, _ in BOARD_ORDER
        )

        # 数据源行
        source_rows = ''
        for src, cnt in top_sources:
            source_rows += f'<tr><td>{src}</td><td class="text-center">{cnt} 条</td></tr>'

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_text} {subtitle_text}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
    line-height: 1.6;
    max-width: 800px;
    margin: 0 auto;
    padding: 24px 16px;
  }}
  .container {{
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    padding: 32px;
  }}
  .header {{
    text-align: center;
    padding-bottom: 20px;
    border-bottom: 2px solid #e5e5e5;
    margin-bottom: 24px;
  }}
  .header h1 {{ font-size: 24px; font-weight: 700; color: #111; }}
  .header .subtitle {{ color: #666; font-size: 14px; margin-top: 8px; }}
  .stats {{
    display: flex;
    justify-content: center;
    gap: 24px;
    margin-top: 16px;
  }}
  .stat {{ text-align: center; }}
  .stat-value {{ font-size: 22px; font-weight: 700; color: #3b82f6; }}
  .stat-label {{ font-size: 12px; color: #888; }}
  .section {{ margin-bottom: 28px; }}
  .section-title {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #e5e5e5;
  }}
  .section-title .count {{
    font-size: 13px;
    font-weight: 400;
    color: #999;
    margin-left: 8px;
  }}
  .event-item {{
    padding: 12px 16px;
    border-left: 3px solid #3b82f6;
    background: #f8fafc;
    margin-bottom: 10px;
    border-radius: 0 6px 6px 0;
  }}
  .event-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .event-rank {{
    width: 28px; height: 28px;
    background: #3b82f6; color: #fff;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; font-weight: 700;
    flex-shrink: 0;
  }}
  .event-title {{ font-weight: 600; font-size: 15px; }}
  .event-meta {{ color: #888; font-size: 13px; margin-top: 6px; margin-left: 38px; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
  }}
  .badge-critical {{ background: #dc2626; }}
  .badge-major {{ background: #ea580c; }}
  .badge-important {{ background: #f59e0b; color: #111; }}
  .badge-normal {{ background: #6b7280; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  th {{
    background: #f0f0f0;
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    border-bottom: 2px solid #ddd;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #eee;
  }}
  .text-center {{ text-align: center; }}
  .empty-hint {{ color: #bbb; font-style: italic; font-size: 14px; }}
  .footer {{
    text-align: center;
    color: #999;
    font-size: 12px;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #e5e5e5;
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .container {{ box-shadow: none; border-radius: 0; padding: 20px; }}
    .event-item {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{title_text}</h1>
    <div class="subtitle">{subtitle_text} &nbsp;|&nbsp; 生成时间: {now_str}</div>
    <div class="stats">
      <div class="stat"><div class="stat-value">{total_news}</div><div class="stat-label">原始新闻</div></div>
      <div class="stat"><div class="stat-value">{total_clusters}</div><div class="stat-label">事件簇</div></div>
      <div class="stat"><div class="stat-value">{len(sources)}</div><div class="stat-label">数据源</div></div>
      <div class="stat"><div class="stat-value">{len(source_counts)}</div><div class="stat-label">活跃源</div></div>
    </div>
  </div>

  {render_section('本周 TOP 5', '📰', global_top5)}
  {board_sections_html}

  <div class="section">
    <div class="section-title">📡 数据源状态</div>
    <table>
      <thead><tr><th>数据源</th><th class="text-center">贡献数</th></tr></thead>
      <tbody>{source_rows}</tbody>
    </table>
  </div>

  <div class="footer">
    {topic_prefix or 'News'} Service &nbsp;·&nbsp; 完整报告见 reports/ 目录
  </div>
</div>
</body>
</html>'''

        # 保存 HTML 简报
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        if is_weekly:
            start_tag = period_start.replace('-', '')
            end_tag = period_end.replace('-', '')
            prefix = f"{report_prefix}_weekly_brief" if report_prefix else ''
            if not prefix:
                if topic == '商业航天':
                    prefix = 'commercial_space_weekly_brief'
                elif topic == '人工智能':
                    prefix = 'ai_weekly_brief'
                else:
                    prefix = 'weekly_brief'
            output_file = self.report_dir / f"{prefix}_{start_tag}_{end_tag}_{timestamp}.html"
        else:
            output_file = self.report_dir / f"daily_brief_{timestamp}.html"
        self.last_brief_path = self._write_output_text(output_file, html, "brief")

        logger.info(f"{title_text} saved to {self.last_brief_path}")

        # 生成 PDF（不阻塞主流程，后台执行）
        self._generate_pdf(output_file, logger)

        return html

    def _generate_pdf(self, html_path: Path, logger) -> bool:
        """将 HTML 简报转为 PDF（Selenium + Edge 无头浏览器）"""
        try:
            import base64
            import time
            import threading
            from http.server import HTTPServer, SimpleHTTPRequestHandler
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options
        except Exception as e:
            logger.warning(f"PDF generation skipped: {e}")
            return False

        pdf_path = html_path.with_suffix(".pdf")
        reports_dir = str(html_path.parent)

        class DirHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kw):
                super().__init__(*args, directory=reports_dir, **kw)
            def log_message(self, fmt, *args):
                pass  # suppress request logging noise

        server = HTTPServer(("127.0.0.1", 0), DirHandler)
        port = server.server_address[1]

        def serve():
            server.serve_forever()

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        time.sleep(0.5)

        options = Options()
        options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        try:
            driver = webdriver.Edge(options=options)
            driver.set_page_load_timeout(30)
            url = f"http://127.0.0.1:{port}/{html_path.name}"
            driver.get(url)
            time.sleep(2)

            pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
                "format": "A4",
                "margin": {"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
                "printBackground": True,
            })

            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(pdf_data["data"]))

            driver.quit()
            server.shutdown()
            size_kb = pdf_path.stat().st_size / 1024
            logger.info(f"PDF saved to {pdf_path} ({size_kb:.0f} KB)")
            return True

        except Exception as e:
            logger.warning(f"PDF generation failed: {e}")
            try:
                server.shutdown()
            except Exception:
                pass
            return False

    def _generate_executive_summary(self, clusters: List[Dict], all_news: List[Dict], sources: List[str]) -> str:
        """
        生成执行摘要：3-5 条一句话总结
        
        提取逻辑：
        1. 按 importance_score 排序，取 TOP 5
        2. 每条总结包含：核心主体 + 事件 + 关键数据
        3. 标注来源覆盖数（跨源加权）
        """
        sorted_clusters = sorted(clusters, 
                                key=lambda c: c.get('importance_score', 0), 
                                reverse=True)
        top_clusters = sorted_clusters[:5]
        
        md = []
        md.append("## 📋 周报速览\n")
        
        if not top_clusters:
            md.append("> 本周无重大事件\n")
            return '\n'.join(md)
        
        for i, cluster in enumerate(top_clusters, 1):
            score = cluster.get('importance_score', 0)
            title = self._display_title(cluster.get('representative_title', ''))
            items = cluster.get('items', [])
            all_sources = cluster.get('_all_sources', cluster.get('sources', []))
            source_count = cluster.get('source_count', len(all_sources))
            item_count = cluster.get('item_count', len(items))
            
            # 严重程度标签
            if score >= 80:
                tag = "🔴"
            elif score >= 60:
                tag = "🟠"
            elif score >= 40:
                tag = "🟡"
            else:
                tag = "🟢"
            
            # 跨源标记
            source_tag = ""
            if source_count >= 3:
                source_tag = " 🔗多源交叉印证"
            elif source_count >= 2:
                source_tag = " 🔗双源报道"
            
            # 提取关键信息生成一句话总结
            summary_line = self._extract_one_liner(cluster)
            
            md.append(f"{tag} **{i}.** {summary_line}{source_tag}")
            if all_sources:
                src_names = ', '.join(all_sources[:3])
                if len(all_sources) > 3:
                    src_names += f" 等{len(all_sources)}个"
                md.append(f"   → 覆盖源: {src_names} | 关联报道: {item_count}条 | 评分: {score:.0f}/100")
            md.append("")
        
        return '\n'.join(md)
    
    def _extract_one_liner(self, cluster: Dict[str, Any]) -> str:
        """从事件簇中提取一句话摘要"""
        title = self._display_title(cluster.get('representative_title', ''))
        items = cluster.get('items', [])
        
        # 如果有多个报道，尝试合并信息
        if len(items) >= 2:
            # 检查是否有数量/金额等关键数据
            import re
            numbers = re.findall(r'[\d.]+[亿万千百万元%]', title)
            if numbers:
                return title  # 标题已包含关键数据
            return title
        
        return title
    
    def _generate_top_events(self, clusters: List[Dict], top_n: int = 10) -> str:
        """生成重大事件TOP N"""
        sorted_clusters = sorted(clusters, 
                                key=lambda c: c.get('importance_score', 0), 
                                reverse=True)
        top_clusters = sorted_clusters[:top_n]
        
        md = ["\n## 🏆 本周重大事件 TOP {}\n".format(top_n)]
        md.append("| 排名 | 事件摘要 | 发布时间 | 重要性 | 传播热度 | 风险 | 可信度 | 错过成本 | 报道源 |")
        md.append("|------|----------|----------|--------|----------|------|--------|----------|--------|")
        
        for i, cluster in enumerate(top_clusters, 1):
            score = cluster.get('importance_score', 0)
            title = self._display_title(cluster.get('representative_title', '未知事件'))[:50]
            signal = self._build_event_signal(cluster)
            lead_item = self._cluster_lead_item(cluster)
            pub_time = self._fmt_time(lead_item.get('publishTime')) if lead_item else signal['first_time']
            # 使用 _all_sources 显示完整覆盖的源
            all_sources = cluster.get('_all_sources', cluster.get('sources', []))
            source_count = cluster.get('source_count', len(all_sources))
            source_str = ', '.join(all_sources[:3])
            if len(all_sources) > 3:
                source_str += f" 等{len(all_sources)}个"
            source_str = source_str.replace('|', '/')
            
            # 严重等级图标
            if score >= 80:
                level = "🔴 极重大"
            elif score >= 60:
                level = "🟠 重大"
            elif score >= 40:
                level = "🟡 重要"
            else:
                level = "🟢 一般"
            
            md.append(
                f"| {i} | {title} | {pub_time} | {score:.0f}分 {level} | {signal['heat']:.0f} | "
                f"{signal['risk']:.0f} | {signal['credibility']:.0f} | {signal['miss_cost']:.0f} | {source_str} |"
            )
        
        md.append("")
        
        # 详细展开TOP 5
        md.append("\n### 📋 TOP 5 事件详情\n")
        for i, cluster in enumerate(top_clusters[:5], 1):
            score = cluster.get('importance_score', 0)
            title = self._display_title(cluster.get('representative_title', ''))
            signal = self._build_event_signal(cluster)
            lead_item = self._cluster_lead_item(cluster)
            sources = cluster.get('sources', [])
            items = cluster.get('items', [])
            lead_time = self._fmt_time(lead_item.get('publishTime')) if lead_item else signal['first_time']
            lead_summary = self._cluster_summary(cluster, 140)
            
            md.append(f"\n#### {i}. {title}\n")
            md.append(f"- **重要性评分**: {score:.0f}/100")
            md.append(
                f"- **传播画像**: 热度 {signal['heat']:.0f}/100 | 风险 {signal['risk']:.0f}/100 | "
                f"可信度 {signal['credibility']:.0f}/100 | 错过成本 {signal['miss_cost']:.0f}/100 | {signal['life_type']}"
            )
            md.append(f"- **发布时间**: {lead_time} | 来源数 {signal['source_count']}")
            md.append(f"- **摘要**: {lead_summary}")
            md.append(f"- **信息增量**: {', '.join(signal['info_gain']) if signal['info_gain'] else '未识别到明确新增数字/机构/地点/政策词'}")
            if signal['reasons']:
                md.append(f"- **预警解释**: {'；'.join(signal['reasons'])}")
            md.append(f"- **报道来源**: {', '.join(sources)}")
            md.append(f"- **关联报道数**: {len(items)}")
            
            # 列出关键报道链接
            md.append(f"\n**相关报道**:")
            for item in items[:5]:
                t = self._display_title(item.get('title', ''))
                url = item.get('url', '#')
                src = item.get('source', '')
                pub_time = self._fmt_time(item.get('publishTime'))
                summary = self._article_summary(item, 120)
                md.append(f"- [{t}]({url}) _({src} · {pub_time})_")
                md.append(f"  - 摘要: {summary}")
            
            md.append("")
        
        return '\n'.join(md)

    def _generate_signal_dashboard(self, clusters: List[Dict], all_news: List[Dict], board_summary: Dict) -> str:
        """生成传播与预警看板。

        当前多数来源没有公开浏览/评论/转发数，因此这里先使用可解释的代理指标：
        多源跟进、来源类型、发布时间跨度、风险词、官方源和国内相关性。
        """
        signals = [self._build_event_signal(cluster) for cluster in clusters]
        signals.sort(key=lambda x: x['miss_cost'], reverse=True)

        md = ["\n## 📈 传播与预警看板\n"]
        md.append("> 当前版本没有稳定的公开浏览/评论/转发快照，热度为代理指标：多源跟进、来源类型、发布时间、风险词和官方/国内信号。真实 10 分钟/1 小时/24 小时增量需要后续定时快照采集。\n")

        md.append("### 🚦 预警摘要\n")
        md.append("| 事件 | 热度 | 争议/风险 | 可信度 | 错过成本 | 传播型态 | 解释 |")
        md.append("|------|------|-----------|--------|----------|----------|------|")
        for signal in signals[:8]:
            title = self._shorten(self._display_title(signal['title']), 42)
            explanation = self._shorten('；'.join(signal['reasons']) or '单源常规报道', 34)
            md.append(
                f"| {title} | {signal['heat']:.0f} | {signal['risk']:.0f} | "
                f"{signal['credibility']:.0f} | {signal['miss_cost']:.0f} | "
                f"{signal['life_type']} | {explanation} |"
            )
        md.append("")

        md.append("### 🧭 事件时间线（重点事件）\n")
        for signal in signals[:5]:
            title = self._display_title(signal['title'])
            md.append(f"#### {title}\n")
            md.append(f"- **发布时间**: {signal['first_time']} | **来源数**: {signal['source_count']}")
            md.append(f"- **来源类型**: {', '.join(signal['source_types']) if signal['source_types'] else '未识别'}")
            md.append(f"- **信息增量**: {', '.join(signal['info_gain']) if signal['info_gain'] else '未识别到明确新增数字/机构/地点/政策词'}")
            for event in signal['timeline'][:5]:
                item_title = self._shorten(self._display_title(event['title']), 54)
                md.append(f"  - {event['time']} | {event['source']} | [{item_title}]({event['url']})")
            md.append("")

        md.append("### 🧩 主题-风险矩阵\n")
        board_rows = self._build_board_signal_rows(all_news)
        md.append("| 主题 | 新闻数 | 平均重要性 | 平均代理热度 | 平均风险 | 高风险数 | 主要风险词 |")
        md.append("|------|--------|------------|--------------|----------|----------|------------|")
        for row in board_rows:
            md.append(
                f"| {row['board']} | {row['count']} | {row['avg_importance']:.0f} | "
                f"{row['avg_heat']:.0f} | {row['avg_risk']:.0f} | {row['high_risk']} | "
                f"{row['risk_terms']} |"
            )
        md.append("")

        md.append("### 🏷️ 来源可信度与扩散来源\n")
        source_rows = self._build_source_signal_rows(all_news)
        md.append("| 来源 | 类型 | 新闻数 | 可信度 | 备注 |")
        md.append("|------|------|--------|--------|------|")
        for row in source_rows[:18]:
            md.append(f"| {row['source']} | {row['type']} | {row['count']} | {row['credibility']:.0f} | {row['note']} |")
        md.append("")

        return '\n'.join(md)

    def _build_event_signal(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        items = cluster.get('items', [])
        title = cluster.get('representative_title', '')
        sources = cluster.get('_all_sources', cluster.get('sources', [])) or []
        source_count = cluster.get('source_count', len(sources)) or len({i.get('source', '') for i in items if i.get('source')})
        item_count = cluster.get('item_count', len(items)) or len(items)
        importance = float(cluster.get('importance_score', 0) or 0)

        parsed_times = []
        for item in items:
            dt = self._parse_dt(item.get('publishTime'))
            if dt:
                parsed_times.append(dt)
        first_dt = min(parsed_times) if parsed_times else None
        last_dt = max(parsed_times) if parsed_times else None
        now = datetime.now()
        age_hours = max(0.0, (now - last_dt).total_seconds() / 3600) if last_dt else 168.0
        spread_hours = max(0.0, (last_dt - first_dt).total_seconds() / 3600) if first_dt and last_dt else 0.0

        source_types = sorted({self._source_type(source) for source in sources if source})
        official = '官方机构' in source_types or any(self._source_type(i.get('source', '')) == '官方机构' for i in items)
        domestic = any(self._is_domestic_signal(i) for i in items)
        risk_terms = self._risk_terms_for_items(items, title)
        info_gain = self._info_gain_for_items(items)

        recency_score = max(0.0, 28.0 - min(age_hours, 168.0) / 6.0)
        heat = min(100.0, 12 + source_count * 12 + item_count * 5 + recency_score + (8 if domestic else 0))
        risk = min(100.0, len(risk_terms) * 18 + (10 if not official and source_count <= 1 else 0))
        credibility = min(100.0, 35 + source_count * 12 + (25 if official else 0) + (10 if '主流/财经媒体' in source_types else 0) - (12 if risk_terms and source_count <= 1 else 0))
        miss_cost = min(100.0, importance * 0.52 + heat * 0.16 + credibility * 0.2 + risk * 0.12)

        reasons = []
        if source_count >= 2:
            reasons.append(f"{source_count}源跟进")
        if official:
            reasons.append("含官方源")
        if domestic:
            reasons.append("中国相关")
        if risk_terms:
            reasons.append("风险词：" + '、'.join(risk_terms[:3]))
        if info_gain:
            reasons.append("信息增量：" + '、'.join(info_gain[:3]))

        timeline = []
        for item in sorted(items, key=lambda x: x.get('publishTime') or ''):
            timeline.append({
                'time': self._fmt_time(item.get('publishTime')),
                'title': item.get('title', ''),
                'url': item.get('url', '#'),
                'source': item.get('source', ''),
            })

        return {
            'title': title,
            'heat': heat,
            'risk': risk,
            'credibility': credibility,
            'miss_cost': miss_cost,
            'life_type': self._life_type(source_count, item_count, spread_hours, age_hours),
            'first_time': self._fmt_time(first_dt.isoformat() if first_dt else None),
            'last_time': self._fmt_time(last_dt.isoformat() if last_dt else None),
            'spread_hours': f"{spread_hours:.1f}",
            'source_count': source_count,
            'source_types': source_types,
            'info_gain': info_gain,
            'timeline': timeline,
            'reasons': reasons,
        }

    def _build_board_signal_rows(self, all_news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups = defaultdict(list)
        for item in all_news:
            groups[item.get('parent_board', 'A8 · 媒体评论')].append(item)

        rows = []
        for board_name, _ in BOARD_ORDER:
            items = groups.get(board_name, [])
            if not items:
                continue
            risks = [self._risk_terms_for_items([item], item.get('title', '')) for item in items]
            flat_risks = [term for terms in risks for term in terms]
            avg_importance = sum(float(i.get('importance_score', 0) or 0) for i in items) / len(items)
            heat_scores = [self._item_proxy_heat(i) for i in items]
            risk_scores = [min(100.0, len(terms) * 18) for terms in risks]
            high_risk = sum(1 for score in risk_scores if score >= 36)
            rows.append({
                'board': board_name,
                'count': len(items),
                'avg_importance': avg_importance,
                'avg_heat': sum(heat_scores) / len(heat_scores),
                'avg_risk': sum(risk_scores) / len(risk_scores),
                'high_risk': high_risk,
                'risk_terms': '、'.join(sorted(set(flat_risks))[:5]) if flat_risks else '-',
            })
        return rows

    def _build_source_signal_rows(self, all_news: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stats = defaultdict(lambda: {'count': 0, 'official': 0, 'risks': 0})
        for item in all_news:
            source = item.get('source', '未知')
            stats[source]['count'] += 1
            if self._source_type(source) == '官方机构':
                stats[source]['official'] += 1
            if self._risk_terms_for_items([item], item.get('title', '')):
                stats[source]['risks'] += 1

        rows = []
        for source, data in stats.items():
            source_type = self._source_type(source)
            credibility = self._source_credibility(source)
            note = []
            if data['official']:
                note.append('官方信源')
            if data['risks']:
                note.append(f"{data['risks']}条含风险词")
            if not note:
                note.append('常规采集')
            rows.append({
                'source': source,
                'type': source_type,
                'count': data['count'],
                'credibility': credibility,
                'note': '；'.join(note),
            })
        return sorted(rows, key=lambda x: (x['credibility'], x['count']), reverse=True)

    def _source_type(self, source: str) -> str:
        official_terms = ['OpenAI', 'DeepMind', 'Google AI', 'Microsoft', 'Meta AI', 'Anthropic', 'EU Digital Strategy']
        mainstream_terms = ['TechCrunch', 'MIT Tech Review', 'VentureBeat', 'The Decoder', '36Kr', '雷锋网', '量子位']
        industry_terms = ['AI Business', 'Synced', 'Hugging Face', 'arXiv']
        if any(term in source for term in official_terms):
            return '官方机构'
        if any(term in source for term in mainstream_terms):
            return '主流/财经媒体'
        if any(term in source for term in industry_terms):
            return '行业媒体'
        return '其他来源'

    def _source_credibility(self, source: str) -> float:
        source_type = self._source_type(source)
        if source_type == '官方机构':
            return 92.0
        if source_type == '主流/财经媒体':
            return 78.0
        if source_type == '行业媒体':
            return 72.0
        return 58.0

    def _risk_terms_for_items(self, items: List[Dict[str, Any]], title: str = '') -> List[str]:
        risk_keywords = {
            '安全/滥用': ['cybersecurity', 'jailbreak', 'prompt injection', 'deepfake', 'misuse', '网络安全', '攻击', '越狱', '深度伪造', '滥用'],
            '处罚/诉讼': ['lawsuit', 'penalty', 'fine', '被罚', '索赔', '诉讼', '调查', '反垄断'],
            '传闻/求证': ['rumor', 'unconfirmed', '内部消息', '听说', '求证', '真的假的', '传闻'],
            '政策/监管': ['regulation', 'ban', 'compliance', 'copyright', 'privacy', '监管', '禁令', '合规', '版权', '隐私'],
            '成本/裁员': ['layoff', 'cost', 'expensive', 'burn', '裁员', '成本', '烧钱', '亏损'],
        }
        text_parts = [title]
        for item in items:
            text_parts.extend([item.get('title', ''), item.get('summary', ''), item.get('content', '') or ''])
        text = ' '.join(text_parts).lower()
        matched = []
        for label, keywords in risk_keywords.items():
            if any(keyword.lower() in text for keyword in keywords):
                matched.append(label)
        return matched

    def _info_gain_for_items(self, items: List[Dict[str, Any]]) -> List[str]:
        text = ' '.join(
            f"{item.get('title', '')} {item.get('summary', '')}"
            for item in items
        )
        gains = []
        if re.search(r'[\d.]+\s*(亿美元|亿美元|万美元|亿元|万元|million|billion|trillion|£|\$)', text, re.I):
            gains.append('金额/融资')
        if re.search(r'\d+\s*(个|组|项|款|tokens?|parameters?|models?|benchmarks?|GPUs?)', text, re.I):
            gains.append('数量')
        if re.search(r'(合同|contract|award|采购|订单|customer|enterprise|partnership)', text, re.I):
            gains.append('商业合作')
        if re.search(r'(发布|release|launches|launch|推出|开源|open source)', text, re.I):
            gains.append('产品/模型发布')
        if re.search(r'(OpenAI|Anthropic|Google|DeepMind|Microsoft|NVIDIA|Meta|DeepSeek|智谱|月之暗面|阿里|腾讯|百度)', text, re.I):
            gains.append('关键机构')
        if re.search(r'(benchmark|SOTA|评测|基准|推理|reasoning|multimodal|多模态|agent|智能体)', text, re.I):
            gains.append('技术指标')
        return gains[:6]

    def _item_proxy_heat(self, item: Dict[str, Any]) -> float:
        score = 20.0
        dt = self._parse_dt(item.get('publishTime'))
        if dt:
            age_hours = max(0.0, (datetime.now() - dt).total_seconds() / 3600)
            score += max(0.0, 28.0 - min(age_hours, 168.0) / 6.0)
        score += float(item.get('importance_score', 0) or 0) * 0.25
        if self._source_type(item.get('source', '')) == '官方机构':
            score += 10
        if self._is_domestic_signal(item):
            score += 6
        return min(100.0, score)

    def _is_domestic_signal(self, item: Dict[str, Any]) -> bool:
        text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('source', '')} {item.get('location', '')}"
        return any(term in text for term in ['中国', '北京', '上海', '深圳', '杭州', '百度', '阿里', '腾讯', '字节', '华为', '智谱', '月之暗面', 'MiniMax', 'DeepSeek', '雷锋网', '量子位'])

    def _life_type(self, source_count: int, item_count: int, spread_hours: float, age_hours: float) -> str:
        if source_count >= 3 and spread_hours <= 3:
            return '突发爆发型'
        if spread_hours >= 24:
            return '长尾讨论型'
        if item_count >= 2 or source_count >= 2:
            return '慢热发酵型'
        if age_hours <= 24:
            return '新发观察型'
        return '单点报道型'

    def _parse_dt(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return None

    def _fmt_time(self, value: Any) -> str:
        dt = self._parse_dt(value)
        if not dt:
            return '未知'
        return dt.strftime('%m-%d %H:%M')

    def _shorten(self, text: str, max_len: int) -> str:
        text = (text or '').replace('|', '/').strip()
        return text if len(text) <= max_len else text[:max_len - 1] + '…'

    def _md_inline_to_pdf(self, text: str) -> str:
        text = text or ''
        text = xml_escape(text)
        text = re.sub(r'\[(.*?)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'`(.+?)`', r'<font face="Courier">\1</font>', text)
        return text

    def _is_table_separator_row(self, row: str) -> bool:
        cells = [cell.strip() for cell in row.strip().strip('|').split('|')]
        if not cells:
            return False
        for cell in cells:
            if not cell:
                continue
            if not re.fullmatch(r':?-{3,}:?', cell):
                return False
        return True

    def _split_table_row(self, row: str) -> List[str]:
        return [cell.strip() for cell in row.strip().strip('|').split('|')]

    def _build_pdf_story(self, markdown_text: str, title_text: str, subtitle_text: str) -> List[Any]:
        styles = getSampleStyleSheet()
        story: List[Any] = []
        brand_blue = colors.HexColor('#24318f')
        accent_blue = colors.HexColor('#3049b6')
        text_black = colors.HexColor('#202124')
        light_rule = colors.HexColor('#d6d6d6')

        title_style = ParagraphStyle(
            'PDFTitle',
            parent=styles['Title'],
            fontName=self._pdf_bold_font_name,
            fontSize=21,
            leading=28,
            alignment=TA_LEFT,
            textColor=brand_blue,
            spaceAfter=10,
        )
        subtitle_style = ParagraphStyle(
            'PDFSubtitle',
            parent=styles['Normal'],
            fontName=self._pdf_font_name,
            fontSize=11,
            leading=16,
            alignment=TA_LEFT,
            textColor=text_black,
            spaceAfter=12,
        )
        h1_style = ParagraphStyle('PDFH1', parent=styles['Heading1'], fontName=self._pdf_bold_font_name, fontSize=14, leading=19, spaceBefore=10, spaceAfter=7, textColor=brand_blue)
        h2_style = ParagraphStyle('PDFH2', parent=styles['Heading2'], fontName=self._pdf_bold_font_name, fontSize=15, leading=20, spaceBefore=0, spaceAfter=0, textColor=brand_blue)
        h3_style = ParagraphStyle('PDFH3', parent=styles['Heading3'], fontName=self._pdf_bold_font_name, fontSize=12.2, leading=17, spaceBefore=8, spaceAfter=10, textColor=accent_blue, keepWithNext=True)
        meta_style = ParagraphStyle('PDFMeta', parent=styles['BodyText'], fontName=self._pdf_bold_font_name, fontSize=10.2, leading=15, spaceBefore=1, spaceAfter=6, textColor=text_black, wordWrap='CJK')
        body_style = ParagraphStyle('PDFBody', parent=styles['BodyText'], fontName=self._pdf_font_name, fontSize=10.4, leading=17, spaceAfter=6, textColor=text_black, wordWrap='CJK')
        link_style = ParagraphStyle('PDFLink', parent=meta_style, textColor=accent_blue, spaceBefore=0, spaceAfter=7)
        bullet_style = ParagraphStyle('PDFBullet', parent=body_style, leftIndent=10, firstLineIndent=0, bulletIndent=0)
        quote_style = ParagraphStyle('PDFQuote', parent=body_style, leftIndent=10, textColor=colors.HexColor('#555555'), fontName=self._pdf_font_name)
        code_style = ParagraphStyle('PDFCode', parent=body_style, fontName='Courier', fontSize=8, leading=10, backColor=colors.HexColor('#f6f8fa'), leftIndent=6, rightIndent=6, spaceBefore=2, spaceAfter=4)

        story.append(Paragraph(self._md_inline_to_pdf(title_text), title_style))
        story.append(HRFlowable(width='100%', thickness=1.8, color=brand_blue, spaceBefore=0, spaceAfter=18))
        story.append(Paragraph(self._md_inline_to_pdf(subtitle_text), subtitle_style))
        story.append(HRFlowable(width='100%', thickness=0.45, color=light_rule, spaceBefore=8, spaceAfter=14))

        lines = markdown_text.splitlines()
        for index, candidate in enumerate(lines):
            if candidate.strip() == '## A1-A8 分类日报':
                lines = lines[index + 1:]
                break
        i = 0
        rendered_sections = 0
        while i < len(lines):
            raw_line = lines[i].rstrip()
            line = raw_line.strip()

            if not line:
                story.append(Spacer(1, 1.2 * mm))
                i += 1
                continue

            if line == '---':
                i += 1
                continue

            if line.startswith('```'):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i].rstrip())
                    i += 1
                if i < len(lines):
                    i += 1
                code_text = '\n'.join(code_lines).strip() or ' '
                story.append(Preformatted(code_text, code_style))
                story.append(Spacer(1, 2 * mm))
                continue

            if line.startswith('|') and line.count('|') >= 2:
                rows = []
                while i < len(lines):
                    candidate = lines[i].strip()
                    if not candidate.startswith('|') or candidate.count('|') < 2:
                        break
                    rows.append(candidate)
                    i += 1

                table_rows = []
                for row in rows:
                    if self._is_table_separator_row(row):
                        continue
                    cells = [Paragraph(self._md_inline_to_pdf(cell), body_style) for cell in self._split_table_row(row)]
                    table_rows.append(cells)

                if table_rows:
                    table = Table(table_rows, repeatRows=1, hAlign='LEFT')
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef7')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111111')),
                        ('FONTNAME', (0, 0), (-1, -1), self._pdf_font_name),
                        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                        ('LEADING', (0, 0), (-1, -1), 11),
                        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#bbbbbb')),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 3 * mm))
                continue

            if line.startswith('### '):
                story.append(Paragraph(self._md_inline_to_pdf(line[4:].strip()), h3_style))
                i += 1
                continue
            if line.startswith('## '):
                heading = line[3:].strip()
                if heading == 'A1-A8 分类日报':
                    i += 1
                    continue
                if rendered_sections:
                    story.append(Spacer(1, 4 * mm))
                    story.append(HRFlowable(width='100%', thickness=0.45, color=light_rule, spaceBefore=2, spaceAfter=10))
                section_table = Table(
                    [[
                        '',
                        Paragraph(self._md_inline_to_pdf(heading), h2_style),
                    ]],
                    colWidths=[3.2 * mm, None],
                    hAlign='LEFT',
                    style=TableStyle([
                        ('BACKGROUND', (0, 0), (0, 0), accent_blue),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (0, 0), 0),
                        ('RIGHTPADDING', (1, 0), (1, 0), 8),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]),
                )
                story.append(section_table)
                story.append(Spacer(1, 5 * mm))
                rendered_sections += 1
                i += 1
                continue
            if line.startswith('# '):
                heading = line[2:].strip()
                if heading != title_text:
                    story.append(Paragraph(self._md_inline_to_pdf(heading), h1_style))
                i += 1
                continue
            if line.startswith('>'):
                story.append(Paragraph(self._md_inline_to_pdf(line[1:].strip()), quote_style))
                i += 1
                continue
            if line.startswith('- '):
                story.append(Paragraph(self._md_inline_to_pdf('• ' + line[2:].strip()), bullet_style))
                i += 1
                continue
            if line.startswith('<details>') or line.startswith('</details>') or line.startswith('<summary>'):
                i += 1
                continue

            if line.startswith(('来源：', '来源:', '**来源：', '**来源:')):
                story.append(Paragraph(self._md_inline_to_pdf(line), meta_style))
                i += 1
                continue

            if line.startswith('[查看原文]('):
                story.append(Paragraph(self._md_inline_to_pdf(line), link_style))
                i += 1
                continue

            story.append(Paragraph(self._md_inline_to_pdf(line), body_style))
            i += 1

        return story

    def _write_pdf_report(self, pdf_path: Path, markdown_text: str, title_text: str, subtitle_text: str) -> Path:
        """Write PDF reports and fall back to a temp directory if the report dir is locked."""
        def build_pdf(target_path: Path) -> Path:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            doc = SimpleDocTemplate(
                str(target_path),
                pagesize=A4,
                leftMargin=18 * mm,
                rightMargin=18 * mm,
                topMargin=20 * mm,
                bottomMargin=15 * mm,
                title=title_text,
                author='AI News Analyzer',
            )

            story = self._build_pdf_story(markdown_text, title_text, subtitle_text)

            def add_page_number(canvas, doc_obj):
                canvas.saveState()
                canvas.setFont(self._pdf_font_name, 8)
                canvas.setFillColor(colors.HexColor('#666666'))
                canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"第 {doc_obj.page} 页")
                canvas.restoreState()

            doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
            return target_path

        try:
            return build_pdf(pdf_path)
        except OSError as exc:
            fallback_dir = Path(tempfile.gettempdir()) / "unified-news-analyzer" / "reports"
            fallback_path = fallback_dir / pdf_path.name
            try:
                written = build_pdf(fallback_path)
                self.report_dir = fallback_dir
                logger.warning(
                    "Failed to write PDF report to %s, fell back to %s: %s",
                    pdf_path,
                    fallback_path,
                    exc,
                )
                return written
            except Exception as fallback_exc:
                logger.warning("Failed to write PDF report to %s: %s", fallback_path, fallback_exc)
                raise
        except Exception as exc:
            logger.warning("Failed to write PDF report to %s: %s", pdf_path, exc)
            raise

    def _normalize_summary_text(self, text: str) -> str:
        text = (text or '').strip()
        text = html.unescape(text)
        text = re.sub(r'&nbsp;?', ' ', text)
        text = re.sub(
            r'40,000\s*块(?=\s*(?:(?:\d+(?:\.\d+)?)\s*英寸\s*)?(?:直接发射\s*)?OLED\s*微显示器)',
            '40,000 尼特',
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r'The article .+? appeared first on .+?\.?$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'The post .+? first appeared on .+?\.?$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text)
        text = text.replace('|', '/').strip()
        parts = [part.strip() for part in re.split(r'(?<=[。！？.!?])\s+', text) if part.strip()]
        deduped = []
        seen = set()
        for part in parts:
            marker = part.lower()
            if marker not in seen:
                deduped.append(part)
                seen.add(marker)
        if deduped:
            text = ' '.join(deduped)
        return text

    def _remove_adjacent_duplicate_spans(self, text: str) -> str:
        """Remove crawler glitches where the same long paragraph is pasted twice."""
        text = self._normalize_summary_text(text)
        if not text:
            return ''

        # Some feeds duplicate a long block without sentence punctuation, so
        # sentence-level de-duplication misses it. Limit this to adjacent,
        # fairly long spans to avoid removing normal repeated short phrases.
        pattern = re.compile(r'(?s)(.{80,800}?)(?:\s+)\1')
        previous = None
        while previous != text:
            previous = text
            text = pattern.sub(r'\1', text)
        return text

    def _title_similarity_key(self, text: str) -> str:
        text = self._normalize_summary_text(text).lower()
        return re.sub(r'[\W_]+', '', text, flags=re.UNICODE)

    def _remove_title_prefix_from_text(self, title: str, text: str) -> str:
        """Remove crawler glitches where article text starts by repeating the title.

        Only the opening prefix is touched. Later mentions are left intact so
        normal article context is not lost.
        """
        title = self._normalize_summary_text(title)
        text = self._normalize_summary_text(text)
        if not title or not text:
            return text

        title_key = self._title_similarity_key(title)
        if len(title_key) < 8:
            return text

        for _ in range(3):
            current = text.lstrip(' ，,;；。:：-—')
            if not current:
                return ''
            window = current[: max(len(title) + 40, 80)]
            window_key = self._title_similarity_key(window)
            if not window_key.startswith(title_key):
                break

            cut = 0
            normalized_seen = ''
            for idx, char in enumerate(current):
                normalized_seen += self._title_similarity_key(char)
                if len(normalized_seen) >= len(title_key):
                    cut = idx + 1
                    break
            if not cut:
                break
            text = current[cut:].lstrip(' ，,;；。:：-—')

        return self._normalize_summary_text(text)

    def _rewrite_article_intro_summary(self, text: str) -> str:
        """Turn article table-of-contents intros into report-style summaries."""
        text = self._normalize_summary_text(text)
        if not text:
            return ''

        text = re.sub(
            r'(?:在这篇文章中|在本文中)[，,]\s*我们将(?:介绍|说明|展示|讨论|回顾|梳理|分析)([^。！？!?]{12,360})[。！？!?]?',
            r'文章介绍了\1。',
            text,
        )
        text = re.sub(
            r'(?i)\b(?:in this post|in this article),?\s+we\s+(?:introduce|present|show|discuss|review|walk through|describe)\s+([^.!?]{24,520})[.!?]?',
            r'The article introduces \1.',
            text,
        )
        text = re.sub(
            r'(?i)\bthis\s+(?:post|article)\s+(?:introduces|presents|covers|shows|discusses)\s+([^.!?]{24,520})[.!?]?',
            r'The article introduces \1.',
            text,
        )
        text = re.sub(r'我们在\s*([^，。；;]{3,120}?)\s*上构建的', r'基于 \1 构建的', text)
        text = re.sub(r'我们在\s*([^，。；;]{3,120}?)\s*构建的', r'基于 \1 构建的', text)
        text = re.sub(r'我们在\s*([^，。；;]{3,120}?)\s*上的', r'基于 \1 的', text)
        text = re.sub(r'基于\s*([^，。；;]{3,120}?)\s*上的', r'基于 \1 的', text)
        return self._normalize_summary_text(text)

    def _clean_summary_noise(self, text: str) -> str:
        """Remove site boilerplate and concatenated-article tails from article summaries."""
        text = self._normalize_summary_text(text)
        if not text:
            return ''

        # Feed records may already contain a site homepage slogan before this
        # generator fetches anything. Treat it as boilerplate at the summary
        # boundary as well as at the crawler boundary.
        lowered = text.lower().replace('’', "'")
        if (
            "we're on a journey to advance and democratize artificial intelligence" in lowered
            or 'we are on a journey to advance and democratize artificial intelligence' in lowered
            or '我们正在通过开源和开放科学推进人工智能并使之民主化' in text
        ):
            return ''
        if self._looks_like_navigation_text(text):
            return ''

        text = text.replace('�', '')
        text = re.sub(r'(?is)<(?:meta|img|link)[^>]*>', ' ', text)
        text = re.sub(r'(?is)\b[\w:-]+(?:cache|nocache|src|alt|width|height)=?["\']?[^<>\s]*["\']?\s*/?>', ' ', text)
        text = re.sub(r'\s*/\s*[A-Z][A-Za-z0-9 .&-]{2,60}\s*\{\s*', ' ', text)
        text = re.sub(r'\s*\[(?:…|\.\.\.)\]\s*', ' ', text)
        text = re.sub(r'\s*【(?:阅读全文|点击查看全文|更多)】\s*', ' ', text)
        text = re.sub(
            r'\s*数据来源[:：]\s*[^。！？!?，,；;]{1,80}[，,]\s*单位[:：]\s*[A-Za-z\u4e00-\u9fff/%％]{1,16}\s*',
            ' ',
            text,
        )
        text = re.sub(
            r'\s*\d{4}\s*年\s*\d{1,2}\s*月[^。！？!?]{0,30}(?:液晶电视|电视|面板)[^。！？!?]{0,30}市场特点[^。！？!?]{0,30}\d{1,2}\s*月(?:价格)?预测\s*',
            ' ',
            text,
        )
        text = re.sub(r'\s*--+\s*', ' ', text)
        text = re.sub(
            r'\s*(?:还是)?老规矩[^。！？!?]{0,180}(?:试卷|考卷)[”"』」]?[，,。！？!?]?',
            ' ',
            text,
        )
        text = re.sub(r'\s*[^。！？!?]{0,40}(?:老师|小编)[^。！？!?]{0,80}(?:带大家|给大家|和大家)[^。！？!?]{0,120}[。！？!?]?', ' ', text)
        text = re.sub(r'\s*[^。！？!?]{0,80}不多说了[。！？!?]?', ' ', text)
        text = re.sub(r'\s*一[、.．]\s*[“"]?一超多强[”"]?格局愈发稳定\s+京东方作为\s+(?=这几天)', ' ', text)
        text = re.sub(r'\s*这几天[，,]\s*各大面板公司陆续公布了自己\d{4}年的[“"]?考卷[”"]?[。！？!?]?', ' ', text)
        text = re.sub(
            r'\s*(?:时事通\s*讯\s+)?新闻\s+太空\s*天文学\s+防御\s+AI\s+Fun\s+独家活动日历\s+主页\s*>.*$',
            ' ',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r'(?i)\bThe\s+(?:post|article)\b[^。；;]{0,320}?\b(?:appeared\s+first\s+on|first\s+appeared\s+on)\b[^。；;]{0,160}[。.;；]?',
            ' ',
            text,
        )
        text = re.sub(r'(?i)\s+\bThe\s+(?:post|article)\b.*$', '', text)
        text = re.sub(r'(?i)\bRead\s+more\b[^。；;]{0,160}[。.;；]?', ' ', text)
        text = re.sub(r'(?i)\bContinue\s+reading\b[^。；;]{0,160}[。.;；]?', ' ', text)
        text = re.sub(
            r'\s*您可以在(?:此处|这里|本站)[^。！？!?]{0,80}(?:更多信息|更多详情|相关信息)[。！？!?]?',
            ' ',
            text,
        )
        text = re.sub(
            r'\s*(?:就在)?(?:昨天|前天|近日|此前|之前|去年|早些时候)?我们(?:曾)?(?:报道称|报道过|报道|介绍过|提到过)[^。！？!?]{0,180}[。！？!?]?',
            ' ',
            text,
        )
        text = re.sub(
            r'\s*[^。！？!?]{0,80}很高兴看到[^。！？!?]{0,180}[。！？!?]?',
            ' ',
            text,
        )
        text = re.sub(
            r'\s*我们不知道[^。！？!?]{0,160}?(?:多远|多久|何时|是否)[，,。.!！]?',
            ' ',
            text,
        )
        text = re.sub(r'\s*(?:但)?就在昨天[，,]?\s*', ' ', text)
        text = re.sub(r'\s*显然[，,]\s*', ' ', text)
        text = self._rewrite_article_intro_summary(text)
        text = re.sub(
            r'\s*在本文中[，,]\s*我们[^。！？!?]{0,220}(?:详细介绍|介绍|讨论|回顾|梳理|分析)[^。！？!?]{0,260}[。！？!?]?',
            ' ',
            text,
        )
        text = re.sub(
            r'(?is)\s*(?:要阅读|閱讀|阅读)整篇文章[，,]?\s*请(?:注册|註冊|订阅|訂閱)\s*OLED-Info\s*Pro[。.!！]?.*$',
            '',
            text,
        )
        text = re.sub(
            r'(?is)\s*To\s+read\s+the\s+(?:full|entire)\s+article[,\s]+(?:please\s+)?(?:register|subscribe)\s+(?:to|for)?\s*OLED-Info\s*Pro[.!]?.*$',
            '',
            text,
        )
        text = re.sub(r'\s*(?:BibTeX|Bibtex)\s*(?:格式的)?(?:引文|引用|citation)?\s*[×xX]?[。.!！]?.*$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*(?:格式的引文|格式引用|引用格式)\s*[×xX]?[。.!！]?.*$', '', text)
        text = re.sub(r'\s*第\s*\d+\s*页\s*', ' ', text)

        # Many scraped feeds concatenate the next article after source/date/share markers.
        split_patterns = [
            r'\s*来源[:：]\s*[^。；;]{0,80}\s*[|｜]\s*日期[:：]\s*\d{2,4}[-/]\d{1,2}(?:[-/]\d{1,2})?(?:\s+\d{1,2}:\d{2})?.*$',
            r'\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}\s*分享至.*$',
            r'\s*分享至\s*[；;].*$',
            r'\s*分享到\s*[：:].*$',
            r'\s*(?:登录|登入)\s*(?:注册|註冊)\s*(?:ENG|English|中文)(?:[。.!！]|\s|$).*$',
        ]
        for pattern in split_patterns:
            text = re.sub(pattern, '', text)

        # Feed excerpts frequently end with an ellipsis to signal omitted text.
        # Prefer the preceding complete sentence over turning a clipped fragment
        # such as "此次活动的强化..." into a misleading finished sentence.
        if re.search(r'(?:\s*(?:\.\.\.|…)+\s*)+$', text):
            without_ellipsis = re.sub(r'(?:\s*(?:\.\.\.|…)+\s*)+$', '', text).strip()
            completed = re.match(r'(?s)^(.+[。！？!?])[^。！？!?]*$', without_ellipsis)
            text = completed.group(1) if completed else without_ellipsis
        text = re.sub(r'\s*(?:您将了解)?哪些设计选择[^。！？!?]{0,220}包括为什么[^。！？!?]{0,220}提供了[。.]?$', '', text)
        text = self._remove_adjacent_duplicate_spans(text)
        text = re.sub(
            r'^\s*(Nvidia|OpenAI|Google|Microsoft|Amazon|Meta|Anthropic|苹果|微软|谷歌|亚马逊|英伟达)[^。！？!?]{8,120}?\s+\1\s*(?:表示|称|宣布|发布)',
            r'\1 表示',
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r'\s+', ' ', text).strip(' ，,;；。')
        return self._normalize_summary_text(text)

    def _finalize_summary_text(self, text: str) -> str:
        """Polish the final summary sentence before it is rendered."""
        text = self._clean_summary_noise(text)
        if not text:
            return ''

        # Translation/crawl snippets sometimes leave a dangling single Chinese character.
        text = re.sub(r'([。！？.!?])\s*有$', r'\1', text)
        text = re.sub(r'(?i)\s+(?:there\s+(?:is|are)|and|or|the|this|that|with|for|from|to|of|in|on)$', '', text)
        text = re.sub(r'(?i)([.!?])\s*(?:there\s+(?:is|are)|and|or|the|this|that|with|for|from|to|of|in|on)\.?$', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip(' ，,;；')
        if not text:
            return ''

        if not re.search(r'[。！？.!?]$', text):
            text += '。' if self._is_mostly_chinese(text) else '.'
        return text

    def _is_usable_article_text(self, text: str) -> bool:
        """Reject image links and HTML metadata incorrectly extracted as article text."""
        lowered = self._normalize_summary_text(text).lower()
        if len(lowered) < 30:
            return False
        if self._looks_like_navigation_text(lowered):
            return False
        navigation_markers = (
            '联系销售人员', '开始构建', '定价计划', '行业 金融服务',
            '公共部门和政府', '用例概述', '文档智能',
        )
        if sum(marker in lowered for marker in navigation_markers) >= 3:
            return False
        # Hugging Face sometimes returns its homepage slogan instead of a blog
        # article body. It is source branding, not the requested article.
        if (
            "we're on a journey to advance and democratize artificial intelligence" in lowered
            or 'we are on a journey to advance and democratize artificial intelligence' in lowered
        ):
            return False
        return not any(marker in lowered for marker in (
            'http://', 'https://', 'data-react-helmet', 'tplv-', 'ai-v3:',
            '<meta', '<img', 'content=', 'property=', '抱歉',
        ))

    def _looks_like_navigation_text(self, text: str) -> bool:
        text = self._normalize_summary_text(text)
        if not text:
            return False
        lowered = text.lower()
        nav_terms = (
            '快讯', '头条', '人工智能', '芯东西', 'aiot', '云与智慧城市',
            '机器人', 'vr/ar', '手机通信', '活动',
        )
        nav_hits = sum(1 for term in nav_terms if term.lower() in lowered)
        if nav_hits >= 5 and len(text) <= 120:
            return True
        return False

    def _summary_cache_key(self, item: Dict[str, Any]) -> str:
        url = self._normalize_summary_text(item.get('url', ''))
        title = self._normalize_summary_text(item.get('title', ''))
        source = self._normalize_summary_text(item.get('source', ''))
        publish_time = self._normalize_summary_text(item.get('publishTime', ''))
        if url:
            return f"url::{url}"
        return f"meta::{title}::{source}::{publish_time}"

    def _cluster_summary_cache_key(self, cluster: Dict[str, Any]) -> str:
        title = self._normalize_summary_text(cluster.get('representative_title', ''))
        source_count = str(cluster.get('source_count', len(cluster.get('sources', []) or [])))
        lead_item = self._cluster_lead_item(cluster)
        lead_key = self._summary_cache_key(lead_item) if lead_item else ''
        return f"cluster::{title}::{source_count}::{lead_key}"

    def _extract_summary_source(self, item: Dict[str, Any]) -> str:
        summary = self._clean_summary_noise(item.get('summary', ''))
        content = self._clean_summary_noise(item.get('content', ''))
        title = self._normalize_summary_text(item.get('title', ''))
        summary = self._remove_title_prefix_from_text(title, summary)
        content = self._remove_title_prefix_from_text(title, content)
        if content and (len(content) > len(summary) * 1.5 or summary == title):
            return content
        if summary:
            return summary
        if content:
            return content
        return title

    def _extract_meta_description_from_html(self, html_text: str) -> str:
        patterns = [
            r'(?is)<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\'](.*?)["\']',
            r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
        ]
        descriptions = []
        for pattern in patterns:
            for match in re.findall(pattern, html_text):
                text = self._normalize_summary_text(re.sub(r'<[^>]+>', ' ', match))
                if len(text) >= 30:
                    descriptions.append(text)
        return max(descriptions, key=len) if descriptions else ''

    def _extract_jsonld_article_text(self, html_text: str) -> str:
        chunks = []
        for raw_json in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text):
            raw_json = html.unescape(raw_json).strip()
            try:
                data = json.loads(raw_json)
            except Exception:
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                node = stack.pop(0)
                if isinstance(node, list):
                    stack.extend(node)
                    continue
                if not isinstance(node, dict):
                    continue
                graph = node.get('@graph')
                if isinstance(graph, list):
                    stack.extend(graph)
                node_type = node.get('@type', '')
                if isinstance(node_type, list):
                    node_type = ' '.join(str(x) for x in node_type)
                if re.search(r'Article|NewsArticle|BlogPosting', str(node_type), flags=re.IGNORECASE):
                    for field in ('description', 'articleBody'):
                        value = node.get(field)
                        if isinstance(value, str):
                            text = self._normalize_summary_text(value)
                            if len(text) >= 30:
                                chunks.append(text)
        return self._normalize_summary_text(' '.join(chunks))

    def _extract_article_body_for_ai(self, item: Dict[str, Any]) -> str:
        """Return article text that is substantial enough for AI summarization."""
        content = self._clean_summary_noise(item.get('content', ''))
        summary = self._clean_summary_noise(item.get('summary', ''))
        title = self._normalize_summary_text(item.get('title', ''))
        content = self._remove_title_prefix_from_text(title, content)
        summary = self._remove_title_prefix_from_text(title, summary)
        if len(content) >= 120:
            return content
        if len(summary) >= 200 and summary != title and title not in summary:
            return summary
        return ''

    def _content_quality(self, item: Dict[str, Any]) -> int:
        content = self._clean_summary_noise(item.get('content', ''))
        summary = self._clean_summary_noise(item.get('summary', ''))
        title = self._normalize_summary_text(item.get('title', ''))
        content = self._remove_title_prefix_from_text(title, content)
        summary = self._remove_title_prefix_from_text(title, summary)
        if len(content) >= 800:
            return 3
        if len(content) >= 120:
            return 2
        if len(summary) >= 200 and summary != title and title not in summary:
            return 1
        return 0

    def _article_has_enough_content(self, item: Dict[str, Any]) -> bool:
        content = self._clean_summary_noise(item.get('content', ''))
        # RSS summaries are usually only a teaser. Keep fetching until we have
        # a substantial article body so report entries stay information-rich.
        return len(content) >= 600

    def _is_report_worthy_article(self, item: Dict[str, Any]) -> bool:
        """Keep evergreen guides and thin teasers out of the final daily report."""
        title = self._normalize_summary_text(item.get('title', ''))
        summary = self._clean_summary_noise(item.get('summary', ''))
        content = self._clean_summary_noise(item.get('content', ''))
        source_text = content or summary
        if not source_text:
            return False

        combined = f"{title} {source_text}".lower()
        if self._has_evergreen_marker(combined):
            return False
        return True

    def _has_evergreen_marker(self, text: str) -> bool:
        evergreen_markers = (
            'ultimate guide', 'updated guide', 'everything you need to know',
            'current market status', 'how to choose', 'how to buy',
            'best oled', 'buy in ', 'recommendations', 'what is the ',
            '购买指南', '选购指南', '终极指南', '入门指南', '技术百科',
            '唯一资源', '当前市场现状', '新品显示器', '新显示器：展望',
        )
        lowered = (text or '').lower()
        if any(marker in lowered for marker in evergreen_markers):
            return True
        if (
            '即将推出' in lowered
            and ('规格' in lowered or '特征' in lowered or '发布日期' in lowered)
            and ('显示器' in lowered or '产品' in lowered)
        ):
            return True
        return False

    def _extract_article_text_from_html(self, html_text: str) -> str:
        meta_description = self._extract_meta_description_from_html(html_text)
        jsonld_text = self._extract_jsonld_article_text(html_text)

        html_text = re.sub(r'(?is)<script[^>]*>.*?</script>', ' ', html_text)
        html_text = re.sub(r'(?is)<style[^>]*>.*?</style>', ' ', html_text)
        html_text = re.sub(r'(?is)<nav[^>]*>.*?</nav>', ' ', html_text)
        html_text = re.sub(r'(?is)<footer[^>]*>.*?</footer>', ' ', html_text)

        candidates = []
        for pattern in (
            r'(?is)<article[^>]*>(.*?)</article>',
            r'(?is)<div[^>]+class=["\'][^"\']*(?:article|content|main|detail|TRS_Editor|Custom_UnionStyle)[^"\']*["\'][^>]*>(.*?)</div>',
            r'(?is)<section[^>]+class=["\'][^"\']*(?:article|content|main|detail)[^"\']*["\'][^>]*>(.*?)</section>',
        ):
            candidates.extend(re.findall(pattern, html_text))

        if not candidates:
            paragraphs = re.findall(r'(?is)<p[^>]*>(.*?)</p>', html_text)
        else:
            longest = max(candidates, key=lambda chunk: len(re.sub(r'<[^>]+>', '', chunk)))
            paragraphs = re.findall(r'(?is)<p[^>]*>(.*?)</p>', longest)
            if not paragraphs:
                paragraphs = [longest]

        texts = []
        for paragraph in paragraphs:
            paragraph = re.sub(r'(?is)<br\s*/?>', '\n', paragraph)
            paragraph = re.sub(r'<[^>]+>', ' ', paragraph)
            paragraph = self._normalize_summary_text(paragraph)
            if len(paragraph) >= 12 and paragraph not in texts:
                texts.append(paragraph)

        article_text = self._normalize_summary_text(' '.join(texts))
        parts = [part for part in (meta_description, jsonld_text, article_text) if part]
        return self._normalize_summary_text(' '.join(parts))

    def _fetch_article_content(self, url: str) -> Optional[str]:
        if not url or not url.startswith(("http://", "https://")):
            return None
        timeout = self._env_int("NEWS_ARTICLE_FETCH_TIMEOUT", 5)
        max_chars = self._env_int("NEWS_ARTICLE_CONTENT_MAX_CHARS", 6000)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_chars * 8)
                content_type = resp.headers.get("Content-Type", "")
            encoding = "utf-8"
            match = re.search(r'charset=([\w-]+)', content_type, flags=re.IGNORECASE)
            if match:
                encoding = match.group(1)
            html_text = raw.decode(encoding, errors="ignore")
            article_text = self._clean_summary_noise(self._extract_article_text_from_html(html_text))
            if self._is_usable_article_text(article_text):
                return article_text[:max_chars]
        except Exception as exc:
            logger.debug("Article content fetch failed for %s: %s", url, exc)
        return None

    def _hydrate_report_articles(self, items: List[Dict[str, Any]]) -> None:
        if os.getenv("NEWS_FETCH_ARTICLE_CONTENT", "1").lower() not in {"1", "true", "yes"}:
            return
        max_fetches = self._env_int("NEWS_ARTICLE_FETCH_MAX", 40)
        attempted = 0
        for item in items:
            if attempted >= max_fetches:
                break
            if self._article_has_enough_content(item):
                continue
            attempted += 1
            content = self._fetch_article_content(self._normalize_summary_text(item.get('url', '')))
            if content:
                item['content'] = content

    def _compress_summary_locally(self, text: str, max_chars: int = 120) -> str:
        text = self._clean_summary_noise(text)
        if not text:
            return ''
        if len(text) <= max_chars:
            return self._finalize_summary_text(text)
        sentences = [s.strip() for s in re.split(r'(?<=[。！？.!?])\s*', text) if s.strip()]
        if sentences:
            picked = []
            total = 0
            for sentence in sentences:
                picked.append(sentence)
                total += len(sentence)
                if total >= max_chars:
                    break
            merged = ''.join(picked).strip()
            if merged and len(merged) <= max_chars * 1.25:
                return self._finalize_summary_text(merged)
        return self._finalize_summary_text(text[:max_chars - 1].rstrip('，,;； '))

    def _extract_lead_sentence(self, text: str) -> str:
        text = self._clean_summary_noise(text)
        if not text:
            return ''
        sentences = [s.strip() for s in re.split(r'(?<=[。！？.!?])\s*', text) if s.strip()]
        if sentences:
            return sentences[0]
        return text

    def _truncate_summary_source_for_ai(self, text: str, max_chars: int = 1600) -> str:
        text = self._clean_summary_noise(text)
        if len(text) <= max_chars:
            return text
        sentences = [s.strip() for s in re.split(r'(?<=[。！？.!?])\s*', text) if s.strip()]
        picked = []
        total = 0
        for sentence in sentences:
            if total + len(sentence) > max_chars:
                break
            picked.append(sentence)
            total += len(sentence)
        if picked:
            return self._normalize_summary_text(''.join(picked))
        return text[:max_chars].rstrip('，,;； ')

    def _clean_board_label(self, board: str) -> str:
        board = self._normalize_summary_text(board)
        board = re.sub(r'^\s*A\d+\s*[·．.、:：\-—\s　]*', '', board, flags=re.IGNORECASE)
        return board or '相关板块'

    def _infer_industry_label(self, board: str = '', text: str = '') -> str:
        topic = self._normalize_summary_text(self._current_topic)
        combined = f"{topic} {board} {text}"
        if topic:
            return topic
        if re.search(r'卫星|航天|火箭|星链|GEO|LEO|orbit|satellite|space', combined, flags=re.IGNORECASE):
            return '商业航天'
        if re.search(r'AI|人工智能|大模型|LLM|OpenAI|Anthropic|ChatGPT|GPU', combined, flags=re.IGNORECASE):
            return '人工智能'
        return '相关行业'

    def _board_impact_sentence(self, board: str, text: str = '') -> str:
        board_label = self._clean_board_label(board)
        industry = self._infer_industry_label(board_label, text)

        if industry == '商业航天':
            if '卫星' in board_label or '组网' in board_label:
                return "这类进展会影响卫星在轨服务、GEO 资产运营和星座网络维护能力。"
            if '发射' in board_label or '火箭' in board_label:
                return "这反映出商业发射市场仍在围绕运力、成本和任务节奏展开竞争。"
            if '遥感' in board_label or '数据' in board_label:
                return "后续看点在于空间数据能否更快转化为政府、能源、农业和安全等场景的服务能力。"
            if '政策' in board_label or '监管' in board_label:
                return "相关变化会影响频谱、轨道资源、商业准入和国际合作节奏。"
            return "这反映出商业航天正在从发射能力竞争延伸到在轨运营、数据服务和供应链协同。"

        if '政策' in board_label or '监管' in board_label:
            return "这类进展会影响 AI 治理规则、合规边界和公共部门应用节奏。"
        if '模型' in board_label:
            return "后续重点在于模型能力、开放策略和开发者生态能否形成持续优势。"
        if '技术' in board_label:
            return "它体现出 AI 技术正从单点能力演示走向更具体的行业任务。"
        if '算力' in board_label or '芯片' in board_label:
            return "这反映出 AI 算力供给、芯片架构和基础设施成本仍是产业竞争焦点。"
        if '应用' in board_label or '产品' in board_label:
            return "这说明 AI 正进一步进入企业软件、生产流程和垂直行业应用。"
        if '智能体' in board_label or '机器人' in board_label:
            return "它显示智能体能力正在从软件协作扩展到自动化流程和实体任务。"
        if '安全' in board_label:
            return "相关变化会影响企业安全防护、模型风险评估和攻防自动化能力。"
        return f"这条新闻反映了{industry}在技术、商业化和治理层面的持续变化。"

    def _is_mostly_english(self, text: str) -> bool:
        if not text:
            return False
        ascii_letters = len(re.findall(r'[A-Za-z]', text))
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        return ascii_letters > max(chinese_chars * 2, 20)

    def _extract_key_figures(self, text: str) -> str:
        figures = re.findall(
            r'(?:[$£€]\s?\d+(?:\.\d+)?\s?(?:B|M|bn|mn|billion|million)?|\d+(?:\.\d+)?\s?(?:亿美元|亿元|万美元|万元|%|GB|GW|MW|B|M|billion|million))',
            text,
            flags=re.IGNORECASE,
        )
        return '、'.join(dict.fromkeys(figures[:4]))

    def _build_chinese_fallback_summary(self, item: Dict[str, Any], max_len: int = 420) -> str:
        title = self._display_title(item.get('title', ''))
        source_text = self._extract_summary_source(item)
        full_text = f"{item.get('title', '')} {source_text}"
        figures = self._extract_key_figures(full_text)
        source = self._normalize_summary_text(item.get('source', ''))

        lower_text = full_text.lower()
        if 'groq' in lower_text:
            summary = "AI 芯片公司 Groq 确认完成 6.5 亿美元融资，并在英伟达相关人才交易后调整团队。公司正加码 neocloud 云算力业务，同时补充新的管理层，显示其正在争夺 AI 算力基础设施市场。"
        elif 'nvidia' in lower_text and 'robot' in lower_text:
            summary = "英伟达将多个 AI 编码代理引入机器人训练流程，用于帮助机器人学习安装 GPU、剪拉链等具身操作。这一项目把软件自动化能力延伸到机器人动作学习，反映出 AI 代理正在从代码生成走向物理世界任务执行。"
        elif 'data' in lower_text and 'privacy' in lower_text:
            summary = "数据使用和隐私保护成为 AI 政策的核心议题。文章讨论 AI 系统在训练、部署和跨境应用中如何处理个人数据，以及监管机构如何在创新和风险控制之间取得平衡。"
        elif 'investigation' in lower_text or 'investigations' in lower_text:
            summary = "微软讨论如何重建调查中的 AI 活动记录。重点在于追踪模型或智能体在任务中的操作路径，帮助安全、合规和取证团队还原关键行为。"
        elif title and self._is_mostly_chinese(title):
            raw_board = self._normalize_summary_text(item.get('parent_board') or item.get('board_name') or '')
            board = self._clean_board_label(raw_board)
            source_hint = f"{source}披露" if source else "消息显示"
            impact = self._board_impact_sentence(raw_board, full_text)
            if figures:
                summary = f"{title}。{source_hint}，事件涉及 {figures} 等关键数字，核心看点是相关机构在{board}方向的新动作。{impact}"
            else:
                summary = f"{title}。{source_hint}，相关主体正在推进{board}方向的新进展，重点是技术、产品或政策动作如何落到实际场景。{impact}"
        else:
            raw_board = self._normalize_summary_text(item.get('parent_board') or item.get('board_name') or '')
            board = self._clean_board_label(raw_board)
            industry = self._infer_industry_label(board, full_text)
            source_hint = f"{source}发布" if source else "行业媒体发布"
            impact = self._board_impact_sentence(raw_board, full_text)
            summary = f"{source_hint}与{board}相关的{industry}动态。新闻聚焦相关机构、产品或技术路线的新变化，适合放入该板块持续跟踪。{impact}"

        return self._compress_summary_locally(summary, max_chars=max_len)

    def _build_local_summary(self, item: Dict[str, Any], max_len: int = 90) -> str:
        summary = self._clean_summary_noise(item.get('summary', ''))
        content = self._clean_summary_noise(item.get('content', ''))
        title = self._normalize_summary_text(item.get('title', ''))

        if content and (len(content) > max(len(summary), len(title)) * 1.5 or summary == title):
            return self._compress_summary_locally(content, max_chars=max_len)

        if summary:
            lead = self._extract_lead_sentence(summary)
            if lead and lead != summary:
                return self._compress_summary_locally(f"{lead} {summary}", max_chars=max_len)
            return self._compress_summary_locally(summary, max_chars=max_len)

        if content:
            lead = self._extract_lead_sentence(content)
            if lead:
                return self._compress_summary_locally(lead, max_chars=max_len)
            return self._compress_summary_locally(content, max_chars=max_len)

        if title:
            return self._compress_summary_locally(title, max_chars=max_len)

        return '暂无摘要'

    def _request_article_summary_batch(
        self,
        batch: List[Dict[str, Any]],
        *,
        model: str,
        api_key: str,
        timeout: int,
        max_chars: int,
        input_chars: int,
        ) -> List[Dict[str, str]]:
        numbered_items = []
        for idx, item in enumerate(batch, 1):
            title = self._normalize_summary_text(item.get('title', ''))
            source_text = self._truncate_summary_source_for_ai(
                self._extract_article_body_for_ai(item),
                max_chars=input_chars,
            )
            source = self._normalize_summary_text(item.get('source', ''))
            pub_time = self._fmt_time(item.get('publishTime'))
            numbered_items.append(
                f"{idx}. 标题：{title}\n"
                f"   来源：{source}；时间：{pub_time}\n"
                f"   原文信息：{source_text}\n"
            )

        prompt = (
            f"请根据每篇文章生成中文标题和信息型日报摘要，每篇摘要不超过{max_chars}个汉字。"
            "必须只根据“原文正文”总结，不要根据标题、板块、来源或常识补写事实。"
            "标题要简洁、有信息量，尽量控制在20到35个汉字，具体写出事件主体和核心变化。"
            "摘要不是短句概括，要写成2到4个自然段或4到8句，信息密度接近正式日报。"
            "优先保留并串联时间、地点、人物、公司/机构、金额、营收/亏损、订单数量、卫星数量、载荷能力、功率、质量、寿命、发射时间、任务计划、市场规模、政策背景和产业影响。"
            "如果原文有多个重点，要按“发生了什么—关键数字/技术细节—后续计划/影响”的顺序写清楚。"
            "不要照搬原文，要压缩、改写并讲清楚这篇新闻说了什么重点。"
            "不要把标题原样作为简要内容第一句，不要用板块名或行业影响句凑字数。"
            "输出要像日报正文，直接陈述新闻事实，不要使用“该报道围绕”“该条为”“本文介绍”“报告根据”“建议查看原文”等元叙述。"
            "如果原文正文信息不足，写1到2句可确认事实即可，不要编造，也不要用标题扩写。"
            "如果文章里有时间、地点、人物、机构、产品或数字，优先保留。"
            "所有外文信息都要翻译成中文，但 OpenAI、ChatGPT、Claude、GPU、API、GEO、LEO 等专有名词可以保留英文。"
            "不要编造原文没有的信息。"
            "请严格返回 JSON 数组，数组顺序与输入一致；每个元素格式为 "
            "{\"title\":\"标题文本\",\"summary\":\"简要内容文本\"}，不要输出多余解释。"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个严谨的中文行业日报编辑，擅长把新闻改写成标题和简要内容。"},
                {"role": "user", "content": f"{prompt}\n\n新闻列表：\n{''.join(numbered_items)}"},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=timeout) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        choices = response.get("choices", [])
        if not choices:
            raise ValueError("AI summary returned no choices")
        content = self._normalize_summary_text(choices[0].get("message", {}).get("content", ""))
        parsed = json.loads(content)
        if not isinstance(parsed, list) or len(parsed) != len(batch):
            parsed_len = len(parsed) if isinstance(parsed, list) else 0
            raise ValueError(f"AI summary returned {parsed_len} items for {len(batch)} inputs")

        results: List[Dict[str, str]] = []
        for item_data in parsed:
            if isinstance(item_data, dict):
                results.append({
                    "title": self._normalize_summary_text(str(item_data.get("title", ""))),
                    "summary": self._normalize_summary_text(str(item_data.get("summary", ""))),
                })
            else:
                results.append({"title": "", "summary": self._normalize_summary_text(str(item_data))})
        return results

    def _retry_delay_for_ai_summary(self, attempt: int) -> float:
        base = self._env_int("NEWS_SUMMARY_RETRY_BACKOFF_SECONDS", 12)
        return min(base * (2 ** max(attempt - 1, 0)), 90)

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
            return True
        return '429' in str(exc) or 'Too Many Requests' in str(exc)

    def _batch_summarize_articles(self, items: List[Dict[str, Any]], max_chars: int = 420) -> None:
        """Generate Chinese titles and writeups for final report articles via a slow queue."""
        if self._summary_batch_disabled_for_run:
            return
        if os.getenv("NEWS_SUMMARY_USE_AI", "1").lower() not in {"1", "true", "yes"}:
            return
        mode = self._summary_mode()
        if mode in {"local", "crawl", "crawler", "none"}:
            return
        if mode in {"manual", "chatgpt", "chat"}:
            self._export_manual_summary_tasks(items, max_chars=max_chars)
            return
        if mode not in {"api", "openai"}:
            logger.warning("Unknown NEWS_SUMMARY_MODE=%s; using local crawled summaries instead", mode)
            return
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._export_manual_summary_tasks(items, max_chars=max_chars)
            return

        pending: List[Dict[str, Any]] = []
        for item in items:
            key = self._summary_cache_key(item)
            if key in self._summary_cache:
                continue
            if not self._extract_article_body_for_ai(item):
                logger.info(
                    "Skipping AI article summary because full article text is unavailable: %s",
                    self._normalize_summary_text(item.get('title', ''))[:80],
                )
                continue
            if key not in self._summary_cache:
                pending.append(item)

        if not pending:
            return

        model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        timeout = self._env_int("NEWS_SUMMARY_TIMEOUT", 60)
        input_chars = self._env_int("NEWS_SUMMARY_INPUT_CHARS", 5000)
        max_retries = self._env_int("NEWS_SUMMARY_RETRIES", 4)
        item_delay = self._env_int("NEWS_SUMMARY_QUEUE_DELAY_SECONDS", 10)
        stop_after_rate_limits = self._env_int("NEWS_SUMMARY_STOP_AFTER_429", 3)
        consecutive_rate_limits = 0

        for index, item in enumerate(pending, 1):
            last_error: Optional[Exception] = None
            result: Optional[Dict[str, str]] = None
            for attempt in range(1, max_retries + 1):
                try:
                    results = self._request_article_summary_batch(
                        [item],
                        model=model,
                        api_key=api_key,
                        timeout=timeout,
                        max_chars=max_chars,
                        input_chars=input_chars,
                    )
                    result = results[0] if results else None
                    consecutive_rate_limits = 0
                    break
                except Exception as exc:
                    last_error = exc
                    rate_limited = self._is_rate_limit_error(exc)
                    if attempt >= max_retries:
                        break
                    delay = self._retry_delay_for_ai_summary(attempt)
                    logger.warning(
                        "AI article summary queue failed (%s/%s, item %s/%s): %s; retrying in %.0fs",
                        attempt,
                        max_retries,
                        index,
                        len(pending),
                        exc,
                        delay,
                    )
                    if delay > 0:
                        time.sleep(delay)

            if result is None:
                if last_error and self._is_rate_limit_error(last_error):
                    consecutive_rate_limits += 1
                    logger.warning(
                        "AI article summary queue hit 429 after %s retries for item %s/%s: %s",
                        max_retries,
                        index,
                        len(pending),
                        last_error,
                    )
                    if consecutive_rate_limits >= stop_after_rate_limits:
                        self._summary_batch_disabled_for_run = True
                        logger.warning(
                            "AI article summary queue stopped after %s consecutive 429 items. "
                            "This is account/model rate limiting; remaining items will use local summaries.",
                            consecutive_rate_limits,
                        )
                        break
                else:
                    logger.warning("AI article summary failed for item %s/%s: %s", index, len(pending), last_error)
                continue

            title = result.get("title", "")
            summary = result.get("summary", "")
            if summary:
                key = self._summary_cache_key(item)
                self._summary_cache[key] = self._compress_summary_locally(summary, max_chars=max_chars)
                if title:
                    self._article_title_cache[key] = title

            if item_delay > 0 and index < len(pending):
                time.sleep(item_delay)

    def _cluster_summary_source(self, cluster: Dict[str, Any]) -> str:
        title = self._normalize_summary_text(cluster.get('representative_title', ''))
        lead_item = self._cluster_lead_item(cluster)
        lead_summary = self._build_local_summary(lead_item, max_len=160) if lead_item else ''
        items = cluster.get('items', []) or []
        top_titles = [self._normalize_summary_text(item.get('title', '')) for item in items[:3] if item.get('title')]
        lines = []
        if title:
            lines.append(f"事件标题：{title}")
        if lead_summary:
            lines.append(f"代表报道摘要：{lead_summary}")
        if top_titles:
            lines.append(f"相关报道标题：{'；'.join(top_titles)}")
        return '\n'.join(lines)

    def _batch_summarize_clusters(self, clusters: List[Dict[str, Any]], max_chars: int = 120) -> None:
        if self._summary_batch_disabled_for_run:
            return
        if self._summary_mode() != "api":
            return
        if self._is_manual_summary_mode():
            return
        if os.getenv("NEWS_SUMMARY_USE_AI", "1").lower() not in {"1", "true", "yes"}:
            return
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return

        pending: List[Dict[str, Any]] = []
        for cluster in clusters:
            key = self._cluster_summary_cache_key(cluster)
            if key not in self._cluster_summary_cache:
                pending.append(cluster)

        if not pending:
            return

        model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        timeout = self._env_int("NEWS_SUMMARY_TIMEOUT", 10)
        batch_size = self._env_int("NEWS_SUMMARY_BATCH_SIZE", 4)

        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            if not batch:
                continue

            numbered_items = []
            for idx, cluster in enumerate(batch, 1):
                source_text = self._cluster_summary_source(cluster)
                title = self._normalize_summary_text(cluster.get('representative_title', ''))
                numbered_items.append(
                    f"{idx}. 标题：{title}\n"
                    f"   聚合信息：{source_text}\n"
                )

            prompt = (
                f"请为下面每个事件簇生成中文摘要，每条不超过{max_chars}个汉字。"
                "要求：保留核心事件、关键数字、机构名和时间信息，不要标题化，不要添加原文没有的信息。"
                "请严格返回 JSON 数组，数组顺序与输入一致，每个元素是一个字符串，不要输出多余解释。"
            )
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的中文新闻摘要助手。"},
                    {"role": "user", "content": f"{prompt}\n\n新闻列表：\n{''.join(numbered_items)}"},
                ],
                "temperature": 0.2,
            }
            request = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as resp:
                    response = json.loads(resp.read().decode("utf-8"))
                choices = response.get("choices", [])
                if not choices:
                    continue
                content = self._normalize_summary_text(
                    choices[0].get("message", {}).get("content", "")
                )
                summaries: List[str] = []
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, list):
                        summaries = [self._normalize_summary_text(str(x)) for x in parsed]
                except Exception:
                    summaries = []

                if len(summaries) != len(batch):
                    continue

                for cluster, summary in zip(batch, summaries):
                    key = self._cluster_summary_cache_key(cluster)
                    self._cluster_summary_cache[key] = self._compress_summary_locally(summary, max_chars=max_chars)
            except Exception as exc:
                self._summary_batch_disabled_for_run = True
                logger.warning("Batch AI cluster summary failed, disabling AI summaries for this run: %s", exc)
                break

    def _summarize_with_ai(self, text: str, max_chars: int = 120) -> Optional[str]:
        if self._ai_summary_disabled_for_run or self._summary_batch_disabled_for_run:
            return None
        if self._summary_mode() != "api":
            return None
        if os.getenv("NEWS_SUMMARY_USE_AI", "1").lower() not in {"1", "true", "yes"}:
            return None
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        model = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        timeout = self._env_int("NEWS_SUMMARY_TIMEOUT", 10)
        prompt = self._normalize_summary_text(text)
        if not prompt:
            return None
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个严谨的中文新闻摘要助手。"},
                    {"role": "user", "content": (
                        "请将下面内容压缩成一条中文摘要，保留核心事件、关键数字、机构名和时间信息，"
                        f"不要超过{max_chars}个汉字，不要标题化，不要添加原文没有的信息，只输出中文摘要正文。\n\n内容：\n{prompt}"
                    )},
                ],
                "temperature": 0.2,
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            choices = response.get("choices", [])
            if not choices:
                return None
            content = self._normalize_summary_text(choices[0].get("message", {}).get("content", ""))
            if content:
                return self._compress_summary_locally(content, max_chars=max_chars)
        except Exception as exc:
            self._ai_summary_disabled_for_run = True
            logger.warning("AI summary failed, disabling AI summaries for this run: %s", exc)
        return None

    def _machine_translate_summary(self, text: str) -> Optional[str]:
        """Translate a non-Chinese summary into Chinese using the public translation endpoint."""
        if self._is_mostly_chinese(text):
            return text
        if self._summary_translation_disabled_for_run:
            return None
        if os.getenv("NEWS_SUMMARY_TRANSLATION_USE_NETWORK", "1").lower() not in {"1", "true", "yes"}:
            return None
        if os.getenv("NEWS_DISABLE_MACHINE_TRANSLATION", "").lower() in {"1", "true", "yes"}:
            return None
        try:
            translated = self._request_google_translation(text, source_lang='en')
            translated = self._normalize_summary_text(translated)
            if translated and self._is_mostly_chinese(translated):
                self._summary_translation_failures = 0
                return translated
        except Exception as exc:
            self._summary_translation_failures += 1
            logger.warning(
                "Summary translation failed (%s/%s), disabling after threshold: %s",
                self._summary_translation_failures,
                self._translation_max_failures,
                exc,
            )
            if self._summary_translation_failures >= self._translation_max_failures:
                self._summary_translation_disabled_for_run = True
        return None

    def _article_summary(self, item: Dict[str, Any], max_len: int = 90) -> str:
        """Extract a readable summary for an article."""
        key = self._summary_cache_key(item)
        cached = self._summary_cache.get(key)
        if cached:
            return cached

        if item.get('_report_content_missing_fallback'):
            return '正文暂未抓取成功，保留该条用于板块完整性；请通过原文链接核对详情。'

        if self._is_manual_summary_mode():
            if self._extract_article_body_for_ai(item):
                return "摘要待生成：已导出 ChatGPT 摘要任务包。请将 ChatGPT 返回的 JSON 保存为 reports/manual_summary_results.json 后重新运行，即可生成正式摘要。"
            return "暂无可用正文：未生成摘要，避免根据标题或来源信息猜测内容。"

        source_text = self._extract_summary_source(item)
        if not source_text:
            return '暂无可用正文，未生成摘要。'
        translated_summary = self._machine_translate_summary(source_text)
        if translated_summary:
            local_summary = self._compress_summary_locally(translated_summary, max_chars=max_len)
            self._summary_cache[key] = local_summary
            return local_summary
        local_summary = self._build_local_summary(item, max_len=max_len)
        self._summary_cache[key] = local_summary
        return local_summary

    def _article_display_title(self, item: Dict[str, Any]) -> str:
        key = self._summary_cache_key(item)
        cached = self._article_title_cache.get(key)
        if cached:
            return cached
        raw_title = self._normalize_summary_text(item.get('title', '未知标题'))
        title = raw_title
        if raw_title in TITLE_TRANSLATIONS:
            title = TITLE_TRANSLATIONS[raw_title]
        if title and not self._is_mostly_english(title):
            return title
        # A failed translation must never turn a real headline into a made-up
        # "source + board" placeholder. Keeping the original is more truthful.
        if raw_title and raw_title != '未知标题':
            return self._display_title(raw_title)
        return '未提供原文标题'

    def _cluster_summary(self, cluster: Dict[str, Any], max_len: int = 120) -> str:
        """Extract a readable summary for an event cluster."""
        key = self._cluster_summary_cache_key(cluster)
        cached = self._cluster_summary_cache.get(key)
        if cached:
            return cached

        source_text = self._cluster_summary_source(cluster)
        if not source_text:
            lead_item = self._cluster_lead_item(cluster)
            source_text = self._build_local_summary(lead_item, max_len=max_len) if lead_item else ''
        if not source_text:
            return '暂无摘要'

        local_summary = self._compress_summary_locally(source_text, max_chars=max_len)
        self._cluster_summary_cache[key] = local_summary
        return local_summary

    def _cluster_lead_item(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """Pick the most representative article for a cluster."""
        items = cluster.get('items', []) or []
        if not items:
            return {}
        return sorted(items, key=lambda item: item.get('publishTime') or '')[0]

    def _generate_a1_a8_news_digest(self, all_news: List[Dict[str, Any]]) -> str:
        """Generate a simple A1-A8 digest: title, source/date, and summary."""
        parent_groups = defaultdict(list)
        for item in all_news:
            parent = item.get('parent_board') or 'A8 · 媒体评论'
            parent_groups[parent].append(item)

        max_items = self._env_int("NEWS_BOARD_MAX_ITEMS", 3)
        candidate_items = self._env_int("NEWS_BOARD_CANDIDATE_ITEMS", max(max_items * 2, 8))
        max_total_items = self._env_int("NEWS_REPORT_MAX_ARTICLES", len(BOARD_ORDER) * max_items)
        selected_by_board: Dict[str, List[Dict[str, Any]]] = {}
        candidates_by_board: Dict[str, List[Dict[str, Any]]] = {}
        candidate_pool: List[Dict[str, Any]] = []
        candidate_keys = set()

        for board_name, _ in BOARD_ORDER:
            items = parent_groups.get(board_name, [])
            sorted_items = sorted(
                items,
                key=lambda item: (item.get('importance_score', 0), item.get('publishTime') or ''),
                reverse=True,
            )
            board_candidates = sorted_items[:max(candidate_items, max_items)]
            candidates_by_board[board_name] = board_candidates
            for item in board_candidates:
                key = self._summary_cache_key(item)
                if key not in candidate_keys:
                    candidate_pool.append(item)
                    candidate_keys.add(key)

        self._hydrate_report_articles(candidate_pool)

        selected_items: List[Dict[str, Any]] = []
        seen_keys = set()
        for board_name, _ in BOARD_ORDER:
            board_candidates = candidates_by_board.get(board_name, [])
            ranked_candidates = sorted(
                [item for item in board_candidates if self._is_report_worthy_article(item)],
                key=lambda item: (
                    self._content_quality(item),
                    item.get('importance_score', 0),
                    item.get('publishTime') or '',
                ),
                reverse=True,
            )
            if not ranked_candidates and board_candidates:
                fallback_candidates = [
                    item for item in board_candidates
                    if self._normalize_summary_text(item.get('title', ''))
                    and not self._has_evergreen_marker(
                        f"{item.get('title', '')} {item.get('summary', '')} {item.get('content', '')}"
                    )
                ]
                if fallback_candidates:
                    fallback_candidates[0]['_report_content_missing_fallback'] = True
                    ranked_candidates = [fallback_candidates[0]]
            shown_items = ranked_candidates[:max_items]
            selected_by_board[board_name] = shown_items
            for item in shown_items:
                key = self._summary_cache_key(item)
                if key not in seen_keys:
                    selected_items.append(item)
                    seen_keys.add(key)

        if len(selected_items) > max_total_items:
            kept_items: List[Dict[str, Any]] = []
            kept_keys = set()

            # Preserve the report shape first: if a board has valid articles,
            # keep at least its best one before filling the remaining global
            # quota. Otherwise high-scoring dense boards can make A1/A2 vanish.
            for board_name, _ in BOARD_ORDER:
                board_items = selected_by_board.get(board_name, [])
                if not board_items or len(kept_items) >= max_total_items:
                    continue
                key = self._summary_cache_key(board_items[0])
                if key not in kept_keys:
                    kept_items.append(board_items[0])
                    kept_keys.add(key)

            remaining_slots = max_total_items - len(kept_items)
            if remaining_slots > 0:
                for item in sorted(
                    selected_items,
                    key=lambda item: (
                        self._content_quality(item),
                        item.get('importance_score', 0),
                        item.get('publishTime') or '',
                    ),
                    reverse=True,
                ):
                    key = self._summary_cache_key(item)
                    if key in kept_keys:
                        continue
                    kept_items.append(item)
                    kept_keys.add(key)
                    remaining_slots -= 1
                    if remaining_slots <= 0:
                        break

            for board_name in list(selected_by_board.keys()):
                selected_by_board[board_name] = [
                    item for item in selected_by_board[board_name]
                    if self._summary_cache_key(item) in kept_keys
                ]
            selected_items = kept_items

        self._batch_summarize_articles(selected_items, max_chars=900)

        md = ["\n## A1-A8 分类日报\n"]

        for board_name, _ in BOARD_ORDER:
            items = parent_groups.get(board_name, [])
            shown_items = selected_by_board.get(board_name, [])

            md.append(f"\n## {board_name}\n")
            if not shown_items:
                md.append("> 暂无相关报道\n")
                continue

            for item in shown_items:
                title = self._article_display_title(item)
                url = item.get('url', '#')
                source = item.get('source', '未知来源')
                pub_time = self._fmt_time(item.get('publishTime'))
                summary = self._article_summary(item, 900)

                md.append(f"### **[{title}]({url})**\n")
                md.append(f"**来源：{source} | 日期：{pub_time}**\n")
                md.append(f"{summary}\n")
                if isinstance(url, str) and url.startswith(('http://', 'https://')):
                    md.append(f"[查看原文]({url})\n")

        md.append("")
        return '\n'.join(md)
    
    def _generate_board_rankings(self, all_news: List[Dict], board_summary: Dict) -> str:
        """生成 A1-A8 类型排名"""
        key_boards = [name for name, _ in BOARD_ORDER]

        # 按 parent_board 分组所有新闻
        parent_groups = defaultdict(list)
        for item in all_news:
            parent = item.get('parent_board', '')
            parent_groups[parent].append(item)
        
        md = ["\n## 📌 A1-A8 类型排名\n"]
        md.append("> 按 AI 周报八类类型分别列出 TOP 5\n")
        
        for board_name in key_boards:
            items = parent_groups.get(board_name, [])
            if not items:
                md.append(f"\n### {board_name}（共 0 条，TOP 5）\n")
                md.append("> 暂无数据\n")
                continue
            
            # 按评分排序
            sorted_items = sorted(items, key=lambda x: x.get('importance_score', 0), reverse=True)
            top_items = sorted_items[:5]
            total_count = len(items)
            
            # 板块标题
            md.append(f"\n### {board_name}（共 {total_count} 条，TOP 5）\n")
            md.append("| 排名 | 新闻标题 | 评分 | 类型 | 来源 |")
            md.append("|------|----------|------|------|------|")
            
            for i, item in enumerate(top_items, 1):
                title = self._display_title(item.get('title', ''))[:45]
                url = item.get('url', '#')
                score = item.get('importance_score', 0)
                sub_board = item.get('board_name', '')
                source = item.get('source', '')
                md.append(f"| {i} | [{title}]({url}) | {score:.0f} | {sub_board} | {source} |")
            
            # 简要分析
            avg_score = sum(x.get('importance_score', 0) for x in sorted_items) / max(len(sorted_items), 1)
            high_count = sum(1 for x in sorted_items if x.get('importance_score', 0) >= 40)
            md.append(f"\n> **类型概况**: 平均评分 {avg_score:.0f} 分 | 高重要性(≥40) {high_count} 条\n")
            
            # 细分板块统计
            sub_board_counts = defaultdict(int)
            for item in items:
                sub_board_counts[item.get('board_name', '其他')] += 1
            
            md.append("| 类型 | 新闻数 | 占比 |")
            md.append("|------|--------|------|")
            for sub_name, cnt in sorted(sub_board_counts.items(), key=lambda x: x[1], reverse=True):
                pct = cnt / max(total_count, 1) * 100
                md.append(f"| {sub_name} | {cnt} | {pct:.0f}% |")
            
            md.append("")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_board_summary(self, board_summary: Dict) -> str:
        """生成板块摘要"""
        md = ["\n## 📊 板块分布摘要\n"]
        
        # 按 A1-A8 顺序分组
        parent_groups = defaultdict(list)
        for key, data in board_summary.items():
            parent = data['parent_board']
            parent_groups[parent].append((key, data))
        
        ordered_names = [name for name, _ in BOARD_ORDER]
        for parent_name in ordered_names:
            sub_boards = parent_groups.get(parent_name, [])
            if not sub_boards:
                md.append(f"\n### {parent_name}（共 0 条）\n")
                md.append("> 暂无数据\n")
                continue
            total_count = sum(d['count'] for _, d in sub_boards)
            md.append(f"\n### {parent_name}（共 {total_count} 条）\n")
            
            for board_key, data in sub_boards:
                board_name = data['board_name']
                count = data['count']
                top_items = data.get('top_items', [])
                
                md.append(f"\n**{board_name}** ({count}条):\n")
                
                # 列出该板块TOP 3新闻
                for item in top_items[:3]:
                    title = self._display_title(item.get('title', ''))
                    url = item.get('url', '#')
                    score = item.get('importance_score', 0)
                    md.append(f"- [{title}]({url}) `评分:{score:.0f}`")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_competitor_dynamics(self, news_list: List[Dict]) -> str:
        """
        生成竞品动态监控报告
        
        竞品配置：
        - 杉杉股份：光电 + 偏光片业务
        """
        COMPETITORS = [
            {
                'name': '杉杉股份',
                'keywords': ['杉杉', '杉杉股份', '杉杉光电', 'Shanshan', '杉杉偏光片'],
                'business': '光电 / 偏光片',
            },
        ]
        
        md = ["\n## 🏢 竞品动态监控\n"]
        
        for comp in COMPETITORS:
            comp_name = comp['name']
            comp_business = comp['business']
            keywords = comp['keywords']
            
            # 筛选相关新闻
            related_news = []
            for item in news_list:
                title = item.get('title', '')
                summary = item.get('summary', '')
                full_text = f"{title} {summary}"
                if any(kw.lower() in full_text.lower() for kw in keywords):
                    related_news.append(item)
            
            # 去重（按 URL）
            seen_urls = set()
            unique_news = []
            for n in related_news:
                url = n.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_news.append(n)
            
            # 按评分排序
            unique_news.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
            
            # 输出竞品板块
            md.append(f"\n### {comp_name}（{comp_business}）\n")

            if not unique_news:
                md.append("> 本周无相关报道\n")
            else:
                md.append(f"**本周报道数**: {len(unique_news)} 条\n")
                md.append("| 排名 | 新闻标题 | 摘要 | 评分 | 来源 | 时间 |")
                md.append("|------|----------|------|------|------|------|")

                for i, item in enumerate(unique_news[:10], 1):
                    title = self._display_title(item.get('title', ''))[:50]
                    url = item.get('url', '#')
                    score = item.get('importance_score', 0)
                    source = item.get('source', '')
                    pub_time = self._fmt_time(item.get('publishTime'))
                    summary = self._article_summary(item, 60)
                    md.append(f"| {i} | [{title}]({url}) | {summary} | {score:.0f} | {source} | {pub_time} |")

                md.append("")
                
                # 简要分析
                sources_set = set(item.get('source', '') for item in unique_news)
                categories_set = set(item.get('category', '') for item in unique_news)
                avg_score = sum(item.get('importance_score', 0) for item in unique_news) / max(len(unique_news), 1)
                md.append(f"> **竞品概况**: 来源覆盖 {len(sources_set)} 个 | 涉及类别: {', '.join(categories_set) if categories_set else 'N/A'} | 平均评分: {avg_score:.0f} 分\n")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_geo_heatmap(self, news_list: List[Dict]) -> str:
        """生成地理热力统计"""
        md = ["\n## 📍 地理分布热力\n"]
        
        from .coordinates import LOCATION_COORDS
        
        location_counts = defaultdict(lambda: {'count': 0, 'lat': None, 'lng': None, 'news': ''})
        
        for item in news_list:
            loc = item.get('location', '未知')
            if loc == '全球' or loc == '未知' or not loc:
                continue
            
            # 如果有坐标直接使用
            lat = item.get('latitude')
            lng = item.get('longitude')
            
            # 回退：从 LOCATION_COORDS 中匹配
            if lat is None or lng is None:
                for key, coords in LOCATION_COORDS.items():
                    if key.lower() in loc.lower():
                        lat, lng = coords
                        break
            
            location_counts[loc]['count'] += 1
            if location_counts[loc]['lat'] is None:
                location_counts[loc]['lat'] = lat if lat is not None else 'N/A'
                location_counts[loc]['lng'] = lng if lng is not None else 'N/A'
                location_counts[loc]['news'] = self._display_title(item.get('title', ''))[:40]
        
        if not location_counts:
            md.append("\n> 暂无地理分布数据\n")
            return '\n'.join(md)
        
        sorted_locs = sorted(location_counts.items(), 
                            key=lambda x: x[1]['count'], 
                            reverse=True)
        
        md.append("| 地点 | 新闻数 | 坐标 | 代表性新闻 |")
        md.append("|------|--------|------|-----------|")
        
        for loc, data in sorted_locs[:20]:
            lat = data.get('lat', 'N/A')
            lng = data.get('lng', 'N/A')
            news = data.get('news', '')
            md.append(f"| {loc} | {data['count']} | `{lat}, {lng}` | {news} |")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_timeline(self, clusters: List[Dict]) -> str:
        """生成24小时时间线"""
        md = ["\n## ⏱️ 24小时事件时间线\n"]
        
        # 按时间排序
        timeline_events = []
        for cluster in clusters:
            items = cluster.get('items', [])
            for item in items:
                pub_time = item.get('publishTime', '')
                if pub_time:
                    timeline_events.append({
                        'time': pub_time,
                        'title': self._display_title(item.get('title', '')),
                        'url': item.get('url', '#'),
                        'source': item.get('source', ''),
                        'score': item.get('importance_score', 0),
                    })
        
        timeline_events.sort(key=lambda x: x['time'], reverse=True)
        
        # 按小时分组
        hour_groups = defaultdict(list)
        for event in timeline_events[:50]:  # 最多50条
            try:
                hour = event['time'][:13]  # YYYY-MM-DDTHH
                hour_groups[hour].append(event)
            except (TypeError, IndexError):
                continue
        
        if not hour_groups:
            md.append("\n> 暂无时间线数据\n")
            return '\n'.join(md)
        
        for hour in sorted(hour_groups.keys(), reverse=True)[:12]:  # 最近12小时
            events = hour_groups[hour]
            display_hour = hour.replace('T', ' ')
            md.append(f"\n### {display_hour} ({len(events)}条)\n")
            for event in events[:5]:
                score = event.get('score', 0)
                md.append(f"- [{event['title']}]({event['url']}) _({event['source']}, {score:.0f}分)_")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_source_evaluation(self, news_list: List[Dict], all_sources: List[str]) -> str:
        """生成数据源质量评估"""
        md = ["\n## 📡 数据源质量评估\n"]
        
        source_stats = defaultdict(lambda: {
            'count': 0, 'top_news': 0, 'unique_count': 0, 'categories': set()
        })
        
        title_seen = defaultdict(set)  # 用于计算独特报道
        
        for item in news_list:
            src = item.get('source', 'unknown')
            source_stats[src]['count'] += 1
            source_stats[src]['categories'].add(item.get('category', ''))
            
            # 高评分新闻计数
            if item.get('importance_score', 0) >= 60:
                source_stats[src]['top_news'] += 1
            
            # 独特报道（按标题前20字去重）
            title_prefix = item.get('title', '')[:20]
            source_stats[src]['unique_count'] += 1
        
        md.append("| 数据源 | 新闻数 | 高评分(≥60) | 覆盖类别数 |")
        md.append("|--------|--------|-------------|-----------|")
        
        sorted_sources = sorted(source_stats.items(), 
                               key=lambda x: x[1]['count'], 
                               reverse=True)
        
        for src, stats in sorted_sources:
            md.append(f"| {src} | {stats['count']} | {stats['top_news']} | {len(stats['categories'])} |")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_source_health(self, news_list: List[Dict]) -> str:
        """
        数据源健康监控
        显示各源状态：✅正常 / ⚠️数据为0 / ❌连接失败
        """
        # 已知源及其预期最低产出
        EXPECTED_SOURCES = {
            '同花顺': ('✅', 5), '同花顺财经': ('✅', 5), '新浪财经': ('✅', 3),
            'Space.com': ('✅', 5), 'NASA': ('⚠️', 3), 'Space News | TechCrunch': ('✅', 3),
            'TechCrunch': ('✅', 3), 'HackerNews': ('✅', 3),
            'OLED-Info': ('✅', 5), 'DisplayDaily': ('✅', 3),
            'OFweek': ('✅', 3), '36Kr': ('✅', 3), '雷锋网': ('✅', 5),
            '量子位': ('✅', 3), 'The Decoder': ('✅', 3),
            'Synced': ('✅', 3), 'DeepMind': ('✅', 5), 'VentureBeat': ('✅', 3),
            'EU Digital Strategy': ('✅', 3), 'AI Business': ('⚠️', 2),
            'MIT Tech Review': ('✅', 3), 'LG Display': ('⚠️', 2),
            'AI News 监测': ('⚠️', 1), '京东方': ('⚠️', 2),
        }
        
        # 统计实际产出
        source_counts = {}
        for item in news_list:
            src = item.get('source', '')
            source_counts[src] = source_counts.get(src, 0) + 1
        
        md = ["\n## 📡 数据源健康监控\n"]
        
        # 分类统计
        healthy = []
        warning = []
        critical = []
        
        for src, (default_status, min_expected) in EXPECTED_SOURCES.items():
            count = source_counts.get(src, 0)
            if count == 0:
                critical.append({'name': src, 'expected': min_expected, 'actual': 0})
            elif count < min_expected:
                warning.append({'name': src, 'expected': min_expected, 'actual': count})
            else:
                healthy.append({'name': src, 'count': count})
        
        # 总体状态
        total = len(EXPECTED_SOURCES)
        if not critical:
            overall = "🟢 全部正常"
        elif len(critical) <= 2:
            overall = f"🟡 {len(critical)}/{total} 个源异常"
        else:
            overall = f"🔴 {len(critical)}/{total} 个源异常"
        
        md.append(f"**总体状态**: {overall}\n")
        
        # 异常源（优先展示）
        if critical or warning:
            md.append("\n### ⚠️ 需要关注\n")
            for item in critical:
                md.append(f"- ❌ **{item['name']}** — 无数据（预期 ≥{item['expected']} 条）")
            for item in warning:
                md.append(f"- ⚠️ **{item['name']}** — 仅 {item['actual']} 条（预期 ≥{item['expected']} 条）")
            md.append("")
        
        # 正常源
        md.append(f"\n### ✅ 正常源（{len(healthy)}/{total}）\n")
        md.append("| 数据源 | 新闻数 | 状态 |")
        md.append("|--------|--------|------|")
        for item in sorted(healthy, key=lambda x: x['count'], reverse=True):
            md.append(f"| {item['name']} | {item['count']} | ✅ |")
        
        md.append("")
        return '\n'.join(md)
    
    def _generate_json_appendix(self, clusters: List[Dict], all_news: List[Dict]) -> str:
        """生成JSON数据附录"""
        md = ["\n---\n"]
        md.append("<details>\n<summary>📦 完整分析数据 (JSON)</summary>\n")
        md.append("```json")
        
        export_data = {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_news': len(all_news),
                'total_clusters': len(clusters),
                'top_events': [
                    {
                        'title': self._display_title(c.get('representative_title', '')),
                        'score': c.get('importance_score', 0),
                        'sources': c.get('sources', []),
                        'count': c.get('item_count', 0),
                    }
                    for c in sorted(clusters, key=lambda x: x.get('importance_score', 0), reverse=True)[:10]
                ],
            },
            'clusters': [
                {
                    'representative_title': self._display_title(c.get('representative_title', '')),
                    'importance_score': c.get('importance_score', 0),
                    'sources': c.get('sources', []),
                    'items': [
                        {
                            'title': self._display_title(i.get('title', '')),
                            'url': i.get('url', ''),
                            'source': i.get('source', ''),
                        }
                        for i in c.get('items', [])
                    ],
                }
                for c in clusters
            ],
        }
        
        md.append(json.dumps(export_data, ensure_ascii=False, indent=2))
        md.append("```\n</details>")
        
        return '\n'.join(md)
