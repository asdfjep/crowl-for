import asyncio
import builtins
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def _install_fastapi_stubs():
    """Install tiny stubs so server.py can be imported without external deps."""
    if "fastapi" not in sys.modules:
        fastapi_mod = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class _App:
            def __init__(self, *args, **kwargs):
                pass

            def post(self, *args, **kwargs):
                def decorator(fn):
                    return fn

                return decorator

            def get(self, *args, **kwargs):
                def decorator(fn):
                    return fn

                return decorator

        fastapi_mod.FastAPI = _App
        fastapi_mod.HTTPException = HTTPException
        sys.modules["fastapi"] = fastapi_mod

    if "pydantic" not in sys.modules:
        pydantic_mod = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **data):
                for key, value in data.items():
                    setattr(self, key, value)

        pydantic_mod.BaseModel = BaseModel
        sys.modules["pydantic"] = pydantic_mod


class TrendDetectorTests(unittest.TestCase):
    def test_save_daily_digest_uses_override_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"NEWS_DIGEST_DIR": tmp}, clear=False):
                sys.modules.pop("services.trend_detector", None)
                import services.trend_detector as trend_detector
                importlib.reload(trend_detector)
                trend_detector.DIGEST_DIR = Path(tmp)

                out = trend_detector.save_daily_digest(
                    "2026-06-24",
                    {"OpenAI": 3, "Claude": 2},
                    total_news=5,
                    cluster_count=2,
                    top_event="OpenAI 发布新模型",
                )

                self.assertTrue(out)
                expected = Path(tmp) / "digest_2026-06-24.json"
                self.assertEqual(Path(out), expected)
                self.assertEqual(trend_detector.DIGEST_DIR, Path(tmp))


class AnalyzerDateTests(unittest.TestCase):
    def test_analyze_json_file_defaults_to_current_run_date_not_crawl_time(self):
        from services.analyzer import NewsAnalyzer

        analyzer = NewsAnalyzer(topic="ai")
        payload = {
            "crawlTime": "2026-06-23T10:59:42",
            "sources": ["Source A"],
            "news": [{"title": "新闻", "publishTime": "2026-06-29T10:00:00"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            path = f.name

        try:
            with mock.patch.object(analyzer, "analyze", return_value={"ok": True}) as analyze:
                analyzer.analyze_json_file(path)
            self.assertIsNone(analyze.call_args.kwargs["date"])
        finally:
            Path(path).unlink(missing_ok=True)

    def test_analyze_json_file_accepts_explicit_report_date(self):
        from services.analyzer import NewsAnalyzer

        analyzer = NewsAnalyzer(topic="ai")
        payload = {
            "crawlTime": "2026-06-23T10:59:42",
            "sources": ["Source A"],
            "news": [{"title": "新闻", "publishTime": "2026-06-23T10:00:00"}],
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            path = f.name

        try:
            with mock.patch.object(analyzer, "analyze", return_value={"ok": True}) as analyze:
                analyzer.analyze_json_file(path, date="2026-06-23")
            self.assertEqual(analyze.call_args.kwargs["date"], "2026-06-23")
        finally:
            Path(path).unlink(missing_ok=True)


class RunRefreshTests(unittest.TestCase):
    def test_extract_json_from_service_report(self):
        import run as runner

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(
                "# report\n\n"
                "```json\n"
                "[{\"title\": \"新闻\", \"source\": \"Source A\", \"publishTime\": \"2026-06-29T10:00:00\"}]\n"
                "```\n"
            )
            path = Path(f.name)

        try:
            items = runner._extract_json_from_service_report(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(items[0]["title"], "新闻")
        self.assertEqual(items[0]["source"], "Source A")

    def test_write_analyzer_json_uses_current_crawl_time(self):
        import run as runner
        from services.analyzer import NewsAnalyzer

        analyzer = NewsAnalyzer(topic="ai")
        with tempfile.TemporaryDirectory() as tmp:
            analyzer.data_dir = Path(tmp)
            output = runner._write_analyzer_json(
                analyzer,
                [{"title": "新闻", "source": "Source A", "publishTime": "2026-06-29T10:00:00"}],
                ["Source A"],
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(output.name.startswith("news_"))
        self.assertEqual(payload["sources"], ["Source A"])
        self.assertEqual(payload["news"][0]["title"], "新闻")
        self.assertIn("T", payload["crawlTime"])

    def test_extract_health_payload_from_mixed_logs(self):
        import run as runner

        output = (
            "2026-06-30 log line\n"
            "{\"checked_at\":\"2026-06-30T10:00:00\",\"summary\":{\"ok\":1},"
            "\"results\":[{\"source\":\"OFweek\",\"status\":\"ok\"}]}\n"
        )

        payload = runner._extract_health_payload(output)

        self.assertEqual(payload["summary"]["ok"], 1)
        self.assertEqual(payload["results"][0]["source"], "OFweek")

    def test_format_health_markdown_lists_problem_sources(self):
        import run as runner
        from services.analyzer import NewsAnalyzer

        analyzer = NewsAnalyzer(topic="display_polarizer")
        payload = {
            "checked_at": "2026-06-30T10:00:00",
            "service_dir": "service",
            "settings": {"timeout_sec": 30, "retries": 1, "stale_days": 7},
            "summary": {"ok": 1, "warn": 1, "error": 1},
            "results": [
                {
                    "source": "OFweek",
                    "status": "warn",
                    "items": 0,
                    "newest": "",
                    "issues": ["no_items", "body_extract_abnormal"],
                    "attempts": 2,
                    "duration_sec": 1.2,
                    "error": "",
                },
                {
                    "source": "OLED-Info",
                    "status": "ok",
                    "items": 5,
                    "newest": "2026-06-30T01:00:00+00:00",
                    "issues": [],
                    "attempts": 1,
                    "duration_sec": 0.8,
                    "error": "",
                },
            ],
        }

        report = runner._format_health_markdown(analyzer, payload)

        self.assertIn("偏光板与显示行业数据源巡检报告", report)
        self.assertIn("OFweek", report)
        self.assertIn("没有抓到文章", report)
        self.assertIn("正文/摘要提取异常", report)


class BoardClassifierTests(unittest.TestCase):
    def tearDown(self):
        from services.board_classifier import BoardClassifier
        from services.topic_config import load_topic_config

        BoardClassifier(load_topic_config("ai"))

    def test_display_polarizer_category_does_not_force_a2_without_signal(self):
        from services.board_classifier import BoardClassifier
        from services.topic_config import load_topic_config

        classifier = BoardClassifier(load_topic_config("display_polarizer"))
        item = {
            "title": "第26届上海国际LED展震撼来袭",
            "summary": "展会聚焦LED显示、AR应用与终端产品。",
            "category": "polarizer",
            "source": "OFweek",
            "tags": [],
        }

        result = classifier.classify(item)

        self.assertNotEqual(result["parent_board"], "A2 · 偏光片与光学膜")

    def test_display_polarizer_real_film_keywords_enter_a2(self):
        from services.board_classifier import BoardClassifier
        from services.topic_config import load_topic_config

        classifier = BoardClassifier(load_topic_config("display_polarizer"))
        item = {
            "title": "偏光片与光学膜材料供应链出现新订单",
            "summary": "新闻涉及TAC膜、PVA膜和偏光片产能。",
            "category": "polarizer",
            "source": "行业媒体",
            "tags": [],
        }

        result = classifier.classify(item)

        self.assertEqual(result["parent_board"], "A2 · 偏光片与光学膜")

    def test_display_panel_price_supply_articles_enter_a1(self):
        from services.board_classifier import BoardClassifier
        from services.topic_config import load_topic_config

        classifier = BoardClassifier(load_topic_config("display_polarizer"))
        item = {
            "title": "2026年6月液晶电视面板价格预测及波动追踪",
            "summary": (
                "洛图科技认为，当前市场进入弱势整理期，预测6月价格继续全面持平。"
                "需求端受618备货收尾影响，品牌采购转向保守，库存和结算节奏仍需观察。"
            ),
            "category": "polarizer",
            "source": "OFweek",
            "tags": [],
        }

        result = classifier.classify(item)

        self.assertEqual(result["parent_board"], "A1 · 政策与供需")


class ReportGeneratorTests(unittest.TestCase):
    def setUp(self):
        self._env_patcher = mock.patch.dict(os.environ, {"NEWS_DISABLE_MACHINE_TRANSLATION": "1"}, clear=False)
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_write_output_text_falls_back_to_temp(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "reports" / "report.md"
            real_open = builtins.open

            def fake_open(path, mode="r", *args, **kwargs):
                if Path(path) == target and "w" in mode:
                    raise PermissionError("blocked for test")
                return real_open(path, mode, *args, **kwargs)

            with mock.patch("builtins.open", side_effect=fake_open):
                written = generator._write_output_text(target, "hello", "report")

            self.assertNotEqual(written, target)
            self.assertTrue(written.exists())
            self.assertEqual(written.read_text(encoding="utf-8"), "hello")

    def test_write_pdf_report_creates_pdf(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "report.pdf"
            written = generator._write_pdf_report(
                pdf_path,
                "# 测试报告\n\n## 一览\n\n| 标题 | 时间 |\n|------|------|\n| 示例新闻 | 2026-06-24 10:20 |\n\n- 第一条摘要\n- 第二条摘要\n",
                "测试报告",
                "2026-06-24",
            )

            self.assertEqual(written, pdf_path)
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)

    def test_write_pdf_report_falls_back_to_temp(self):
        import services.report_generator as report_generator
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "locked" / "report.pdf"

            class FakeDoc:
                def __init__(self, path, *args, **kwargs):
                    self.path = Path(path)
                    if self.path == pdf_path:
                        raise PermissionError("blocked for test")

                def build(self, story, onFirstPage=None, onLaterPages=None):
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_bytes(b"%PDF fake")

            with mock.patch.object(report_generator, "SimpleDocTemplate", FakeDoc):
                with mock.patch.object(generator, "_build_pdf_story", return_value=[]):
                    written = generator._write_pdf_report(
                        pdf_path,
                        "# 测试报告\n\n正文",
                        "测试报告",
                        "2026-06-24",
                    )

            self.assertNotEqual(written, pdf_path)
            self.assertTrue(written.exists())
            self.assertEqual(written.suffix, ".pdf")
            self.assertEqual(written.read_bytes(), b"%PDF fake")

    def test_generate_daily_report_outputs_pdf_path(self):
        from services.report_generator import ReportGenerator

        with tempfile.TemporaryDirectory() as tmp:
            generator = ReportGenerator()
            generator.report_dir = Path(tmp)
            report = generator.generate_daily_report(
                clusters=[],
                all_news=[],
                board_summary={},
                sources=[],
                date="2026-06-24",
                report_type="weekly",
                topic="人工智能",
                period_start="2026-06-18",
                period_end="2026-06-24",
                report_prefix="ai",
            )

            self.assertIn("# 人工智能周报", report)
            self.assertTrue(str(generator.last_report_path).endswith(".pdf"))
            self.assertTrue(Path(generator.last_report_path).exists())

    def test_top_events_include_summary_and_time(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        clusters = [
            {
                "representative_title": "测试事件",
                "importance_score": 91,
                "sources": ["Source A"],
                "_all_sources": ["Source A"],
                "item_count": 1,
                "items": [
                    {
                        "title": "文章一",
                        "summary": "这是一个用于测试的简短摘要。",
                        "publishTime": "2026-06-24T10:20:00",
                        "url": "https://example.com/a",
                        "source": "Source A",
                    }
                ],
            }
        ]

        output = generator._generate_top_events(clusters, top_n=1)

        self.assertIn("发布时间", output)
        self.assertIn("摘要:", output)
        self.assertIn("10:20", output)

    def test_article_summary_uses_article_summary_field(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "这个标题不应该出现在摘要里",
            "summary": "这是文章的摘要内容，应该优先显示。",
            "content": "",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            summary = generator._article_summary(item, 120)

        self.assertIn("这是文章的摘要内容", summary)
        self.assertNotIn("标题", summary)

    def test_article_summary_translates_to_chinese(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "English headline",
            "summary": "The company said it will launch a new model next week.",
            "content": "",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            with mock.patch.object(generator, "_machine_translate_summary", return_value="公司表示将于下周发布新模型。"):
                summary = generator._article_summary(item, 120)

        self.assertIn("公司表示将于下周发布新模型", summary)

    def test_title_translation_failure_does_not_disable_summary_translation(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        generator._translation_cache = {}
        generator._translation_max_failures = 1
        with mock.patch.dict(os.environ, {"NEWS_DISABLE_MACHINE_TRANSLATION": "0"}, clear=False):
            with mock.patch.object(generator, "_request_google_translation", side_effect=TimeoutError("title timeout")):
                self.assertIsNone(generator._machine_translate_title("Uncached test title releases a new model"))

        self.assertTrue(generator._title_translation_disabled_for_run)
        self.assertFalse(generator._summary_translation_disabled_for_run)

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_TRANSLATION_USE_NETWORK": "1", "NEWS_DISABLE_MACHINE_TRANSLATION": "0"}, clear=False):
            with mock.patch.object(generator, "_request_google_translation", return_value="公司发布了新的人工智能模型。"):
                translated = generator._machine_translate_summary("The company released a new AI model.")

        self.assertIn("人工智能模型", translated)

    def test_summary_translation_failure_does_not_disable_title_translation(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        generator._translation_cache = {}
        generator._translation_max_failures = 1
        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_TRANSLATION_USE_NETWORK": "1", "NEWS_DISABLE_MACHINE_TRANSLATION": "0"}, clear=False):
            with mock.patch.object(generator, "_request_google_translation", side_effect=TimeoutError("summary timeout")):
                self.assertIsNone(generator._machine_translate_summary("The company released a new AI model."))

        self.assertTrue(generator._summary_translation_disabled_for_run)
        self.assertFalse(generator._title_translation_disabled_for_run)

        with mock.patch.dict(os.environ, {"NEWS_DISABLE_MACHINE_TRANSLATION": "0"}, clear=False):
            with mock.patch.object(generator, "_request_google_translation", return_value="OpenAI 发布新模型"):
                translated = generator._machine_translate_title("OpenAI announces uncached regression model")

        self.assertIn("发布新模型", translated)

    def test_article_summary_uses_content_sentence_before_title(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "标题",
            "summary": "",
            "content": "第一句是正文重点。第二句是补充说明。",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            summary = generator._article_summary(item, 80)

        self.assertIn("第一句是正文重点", summary)
        self.assertNotIn("标题", summary)

    def test_a1_a8_digest_summarizes_only_displayed_items(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = [
            {
                "title": f"新闻{i}",
                "summary": f"摘要{i}",
                "parent_board": "A1 · 政策监管",
                "importance_score": 100 - i,
                "publishTime": f"2026-06-24T10:0{i}:00",
                "source": "Source A",
                "url": f"https://example.com/{i}",
            }
            for i in range(7)
        ]

        with mock.patch.dict(os.environ, {"NEWS_BOARD_MAX_ITEMS": "3"}, clear=False):
            with mock.patch.object(generator, "_batch_summarize_articles") as batch:
                output = generator._generate_a1_a8_news_digest(items)

        summarized_items = batch.call_args.args[0]
        self.assertEqual(len(summarized_items), 3)
        self.assertIn("新闻0", output)
        self.assertIn("新闻2", output)
        self.assertNotIn("新闻3", output)
        self.assertNotIn("未展示", output)
        self.assertNotIn("NEWS_BOARD_MAX_ITEMS", output)

    def test_a1_a8_digest_limits_total_report_articles_when_configured(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = []
        boards = ["A1 · 政策监管", "A2 · 模型发布", "A3 · 技术突破"]
        for i in range(9):
            items.append({
                "title": f"新闻{i}",
                "summary": f"摘要{i}",
                "parent_board": boards[i % len(boards)],
                "importance_score": 100 - i,
                "publishTime": f"2026-06-24T10:0{i}:00",
                "source": "Source A",
                "url": f"https://example.com/limit-{i}",
            })

        with mock.patch.dict(os.environ, {"NEWS_BOARD_MAX_ITEMS": "5", "NEWS_REPORT_MAX_ARTICLES": "4"}, clear=False):
            with mock.patch.object(generator, "_batch_summarize_articles") as batch:
                output = generator._generate_a1_a8_news_digest(items)

        summarized_items = batch.call_args.args[0]
        self.assertEqual(len(summarized_items), 4)
        self.assertIn("新闻0", output)
        self.assertIn("新闻3", output)
        self.assertNotIn("新闻4", output)

    def test_a1_a8_digest_preserves_boards_when_total_limit_is_configured(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        boards = [
            "A1 · 政策监管",
            "A2 · 模型发布",
            "A3 · 技术突破",
            "A4 · 算力与芯片",
            "A5 · 应用产品",
        ]
        items = [
            {
                "title": f"{board} 保底新闻",
                "summary": f"{board} 摘要内容完整，包含事件、主体和影响。",
                "content": f"{board} 正文内容完整，包含事件、主体、数字和影响。" * 10,
                "parent_board": board,
                "importance_score": 10 if board.startswith("A1") else 100,
                "publishTime": "2026-06-24T10:00:00",
                "source": "Source A",
                "url": f"https://example.com/{i}",
            }
            for i, board in enumerate(boards)
        ]
        items.append({
            "title": "A5 · 应用产品 额外高分新闻",
            "summary": "额外摘要内容完整，包含事件、主体和影响。",
            "content": "额外正文内容完整，包含事件、主体、数字和影响。" * 10,
            "parent_board": "A5 · 应用产品",
            "importance_score": 99,
            "publishTime": "2026-06-24T11:00:00",
            "source": "Source A",
            "url": "https://example.com/extra",
        })

        with mock.patch.dict(os.environ, {"NEWS_BOARD_MAX_ITEMS": "3", "NEWS_REPORT_MAX_ARTICLES": "5"}, clear=False):
            with mock.patch.object(generator, "_batch_summarize_articles") as batch:
                output = generator._generate_a1_a8_news_digest(items)

        summarized_titles = [item["title"] for item in batch.call_args.args[0]]
        self.assertEqual(len(summarized_titles), 5)
        self.assertIn("A1 · 政策监管 保底新闻", summarized_titles)
        self.assertIn("A1 · 政策监管 保底新闻", output)
        self.assertNotIn("A5 · 应用产品 额外高分新闻", summarized_titles)

    def test_a1_a8_digest_defaults_to_three_items_per_board(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = [
            {
                "title": f"新闻{i}",
                "summary": f"摘要{i}",
                "parent_board": "A1 · 政策监管",
                "importance_score": 100 - i,
                "publishTime": f"2026-06-24T10:0{i}:00",
                "source": "Source A",
                "url": f"https://example.com/default-{i}",
            }
            for i in range(6)
        ]

        with mock.patch.object(generator, "_batch_summarize_articles") as batch:
            output = generator._generate_a1_a8_news_digest(items)

        summarized_items = batch.call_args.args[0]
        self.assertEqual(len(summarized_items), 3)
        self.assertIn("新闻0", output)
        self.assertIn("新闻2", output)
        self.assertNotIn("新闻3", output)

    def test_a1_a8_digest_prefers_content_rich_board_candidates(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = [
            {
                "title": "高分但只有标题",
                "summary": "高分但只有标题",
                "parent_board": "A1 · 政策监管",
                "importance_score": 100,
                "publishTime": "2026-06-24T10:00:00",
                "source": "Source A",
                "url": "https://example.com/title-only",
            },
            {
                "title": "分数略低但正文完整",
                "summary": "分数略低但正文完整",
                "content": "这是一篇有足够正文的新闻，介绍事件背景、关键主体、数字和影响。" * 20,
                "parent_board": "A1 · 政策监管",
                "importance_score": 90,
                "publishTime": "2026-06-24T09:00:00",
                "source": "Source A",
                "url": "https://example.com/content-rich",
            },
        ]

        with mock.patch.dict(os.environ, {"NEWS_BOARD_MAX_ITEMS": "1", "NEWS_BOARD_CANDIDATE_ITEMS": "2"}, clear=False):
            with mock.patch.object(generator, "_batch_summarize_articles") as batch:
                output = generator._generate_a1_a8_news_digest(items)

        summarized_items = batch.call_args.args[0]
        self.assertEqual([item["title"] for item in summarized_items], ["分数略低但正文完整"])
        self.assertIn("分数略低但正文完整", output)
        self.assertNotIn("高分但只有标题", output)

    def test_a1_a8_digest_keeps_title_only_board_fallback_when_board_would_be_empty(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = [
            {
                "title": "显示面板涨价潮汹涌而来：TV、MNT、NB全面跟进",
                "summary": "",
                "content": "",
                "parent_board": "A1 · 政策监管",
                "importance_score": 50,
                "publishTime": "2026-06-24T10:00:00",
                "source": "OFweek",
                "url": "https://example.com/price",
            },
            {
                "title": "OLED Monitors In 2026: The Current Market Status",
                "summary": "",
                "content": "",
                "parent_board": "A6 · 智能体与机器人",
                "importance_score": 80,
                "publishTime": "2026-06-24T10:00:00",
                "source": "DisplayNinja",
                "url": "https://example.com/guide",
            },
        ]

        with mock.patch.object(generator, "_batch_summarize_articles") as batch:
            output = generator._generate_a1_a8_news_digest(items)

        summarized_titles = [item["title"] for item in batch.call_args.args[0]]
        self.assertIn("显示面板涨价潮汹涌而来：TV、MNT、NB全面跟进", summarized_titles)
        self.assertIn("显示面板涨价潮汹涌而来", output)
        self.assertIn("正文暂未抓取成功", output)
        self.assertNotIn("OLED Monitors In 2026", output)

    def test_report_worthy_rejects_chinese_evergreen_monitor_tracker(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "2026 年新显示器：展望",
            "summary": (
                "这是您跟踪即将推出的监视器所需的唯一资源。"
                "我们记录了它们的规格、特征和发布日期，以便您了解即将推出的产品。"
            ),
            "content": "",
            "source": "DisplayNinja",
            "parent_board": "A6 · 终端应用",
        }

        self.assertFalse(generator._is_report_worthy_article(item))

    def test_english_article_fallback_summary_uses_real_source_text(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "AI chipmaker Groq confirms $650M raise, re-staffs after Nvidia’s $20B not-acqui-hire deal",
            "summary": "What does an AI company do after one of those not-acqui-hire deals? Groq raised money, is leaning into its neocloud business, and is hiring new execs.",
            "source": "TechCrunch AI",
            "parent_board": "A4 · 算力与芯片",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            summary = generator._article_summary(item, 420)

        self.assertIn("Groq raised money", summary)
        self.assertIn("neocloud business", summary)
        self.assertNotIn("该报道", summary)
        self.assertNotIn("6.5 亿美元", summary)

    def test_english_article_title_fallback_keeps_real_headline(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "Nvidia's self-improvement program for robots enlists teams of AI coding agents",
            "summary": "Nvidia's self-improvement program for robots enlists teams of AI coding agents.",
            "source": "Ars Technica AI",
            "parent_board": "A6 · 智能体与机器人",
        }

        title = generator._article_display_title(item)

        self.assertEqual(title, item["title"])
        self.assertNotIn("相关动态", title)

    def test_space_fallback_summary_uses_clean_board_and_industry(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        generator._current_topic = "商业航天"
        item = {
            "title": "Katalyst Raises $12M to Extend Satellite Servicing to GEO",
            "summary": "Katalyst Raises $12M to Extend Satellite Servicing to GEO",
            "source": "Payload Space",
            "parent_board": "A2 　 卫星组网",
        }

        summary = generator._build_chinese_fallback_summary(item, max_len=420)
        title = generator._article_display_title(item)

        self.assertIn("卫星组网方向", summary)
        self.assertIn("GEO", summary)
        self.assertNotIn("A2", summary)
        self.assertNotIn("人工智能产业", summary)
        self.assertNotIn("A2", title)

    def test_a1_a8_digest_fetches_content_for_displayed_articles(self):
        from services.report_generator import ReportGenerator

        class FakeResponse:
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, *_args):
                return (
                    "<html><body><article>"
                    "<p>论坛围绕智能体创新、技术应用和治理规则展开交流。</p>"
                    "<p>与会嘉宾讨论了智能体在政务、产业和安全治理中的落地路径。</p>"
                    "</article></body></html>"
                ).encode("utf-8")

        generator = ReportGenerator()
        item = {
            "title": "第九届数字中国建设峰会智能体创新与治理分论坛举行",
            "summary": "第九届数字中国建设峰会智能体创新与治理分论坛举行",
            "content": None,
            "parent_board": "A1 · 政策监管",
            "importance_score": 90,
            "publishTime": "2026-06-23T10:59:00",
            "source": "中国网信办",
            "url": "https://example.com/article",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            with mock.patch.object(generator, "_batch_summarize_articles"):
                with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
                    output = generator._generate_a1_a8_news_digest([item])

        self.assertIn("论坛围绕智能体创新", output)
        self.assertNotEqual(item.get("content"), None)

    def test_article_text_extraction_uses_meta_and_jsonld(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        html = """
        <html><head>
        <meta name="description" content="NASA selected a private company to build and launch a 2028 Mars orbiter mission.">
        <script type="application/ld+json">
        {"@type":"NewsArticle","description":"The mission will provide communications relay and imaging support around Mars.","articleBody":"NASA plans to launch the orbiter in 2028 and use it to support future Mars missions."}
        </script>
        </head><body><article><p>The spacecraft will carry instruments for science and communications.</p></article></body></html>
        """

        text = generator._extract_article_text_from_html(html)

        self.assertIn("NASA selected a private company", text)
        self.assertIn("communications relay", text)
        self.assertIn("The spacecraft will carry instruments", text)

    def test_summary_noise_cleaner_removes_scraped_site_tails(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "波音公司在 2027 年在轨实验之前展示了一种关键的量子网络协议。"
            "“高保真纠缠交换”已于今年早些时候进行了演示 […] "
            "The post Boeing demonstrates quantum protocol in payload set for 2027 launch appeared first on Payload. "
            "来源：36Kr | 日期：06-22 16:33 大型低轨卫星互联网星座“千帆星座”的建设与运营主体启动新一轮融资。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("波音公司在 2027 年在轨实验之前展示了一种关键的量子网络协议", cleaned)
        self.assertNotIn("The post", cleaned)
        self.assertNotIn("appeared first", cleaned)
        self.assertNotIn("来源：36Kr", cleaned)
        self.assertNotIn("千帆星座", cleaned)
        self.assertNotIn("[…]", cleaned)

    def test_summary_noise_cleaner_removes_truncated_the_post_tail(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "PORTLAND, Ore. - Boeing demonstrated a key quantum networking protocol in ground testing "
            "ahead of an on-orbit experiment in 2027. High-fidelity entanglement swapping was demonstrated earlier this The post Boeing demonstrates quantum protocol in payload set for 2027 launch"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("Boeing demonstrated a key quantum networking protocol", cleaned)
        self.assertNotIn("The post", cleaned)
        self.assertNotIn("payload set for 2027 launch", cleaned)

    def test_summary_noise_cleaner_removes_oled_info_pro_tail(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "Samsung Display 在 AWE USA 2026 上展示了 40,000 尼特 1.3 英寸直接发射 OLED 微显示器。"
            "该公司计划建设一条 RGB OLEDoS 生产线，预计将于 2028 年实现量产。"
            "要阅读整篇文章，请注册 OLED-Info Pro。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("40,000 尼特", cleaned)
        self.assertIn("2028 年实现量产", cleaned)
        self.assertNotIn("OLED-Info Pro", cleaned)
        self.assertNotIn("要阅读整篇文章", cleaned)

    def test_summary_noise_cleaner_removes_english_oled_info_pro_tail(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "INT Tech announced a native RGB OLED microdisplay with brightness up to 150,000 nits. "
            "The company says the display uses its uNEEDXR architecture. "
            "To read the full article, subscribe to OLED-Info Pro."
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("150,000 nits", cleaned)
        self.assertIn("uNEEDXR", cleaned)
        self.assertNotIn("OLED-Info Pro", cleaned)
        self.assertNotIn("To read the full article", cleaned)

    def test_summary_noise_cleaner_removes_oled_info_editorial_asides(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "INT Tech 宣布开发出亮度高达 150,000 尼特的原生 RGB 全彩 OLED 微显示器。"
            "您可以在此处找到有关这些显示器的更多信息。"
            "去年我们曾报道，第一批从京东方新工厂订购 14 英寸笔记本电脑 OLED 面板的客户是华硕和宏碁。"
            "京东方成都 B16 8.6 代 IT AMOLED 工厂正式开始量产商用显示器。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("150,000 尼特", cleaned)
        self.assertIn("京东方成都 B16", cleaned)
        self.assertNotIn("您可以在此处", cleaned)
        self.assertNotIn("去年我们曾报道", cleaned)

    def test_summary_noise_cleaner_removes_oled_info_translated_asides(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "Samsung Display 展示 40,000 块直接发射 OLED 微显示器。"
            "Samsung Display 在 AWE USA 2026 上展示了其最新的 OLED 微显示器，其中包括 40,000 块 1.3 英寸直接发射 OLED 微显示器。"
            "SDC 之前的最高亮度 OLED 微显示器原型早在 2025 年 5 月就达到了 20,000 尼特，因此很高兴看到该公司在一年内将亮度提高了一倍。"
            "我们不知道三星距离实际生产这种高亮度 OLED 微显示器还有多远，但就在昨天，"
            "在 AWE 2026 上，该公司还展示了采用较小尺寸的 AR 智能眼镜原型，配备 0.62 英寸直接发射 OLED。"
            "三星的直接发射 OLED 技术源自美国 eMagin 公司，三星于 2022 年以 2.18 亿美元收购了该公司。"
        )

        cleaned = generator._clean_summary_noise(dirty)
        title = generator._normalize_summary_text("Samsung Display 展示 40,000 块直接发射 OLED 微显示器")

        self.assertIn("40,000 尼特", title)
        self.assertIn("40,000 尼特", cleaned)
        self.assertIn("0.62 英寸直接发射 OLED", cleaned)
        self.assertIn("2022 年以 2.18 亿美元", cleaned)
        self.assertNotIn("40,000 块", cleaned)
        self.assertNotIn("很高兴看到", cleaned)
        self.assertNotIn("我们不知道", cleaned)
        self.assertNotIn("就在昨天", cleaned)
        self.assertNotIn("更多信息", cleaned)

    def test_summary_noise_cleaner_removes_article_toc_intro(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "维信诺发布了 AMOLED 与 MicroLED 技术路线更新，并披露 8.6 代产线规划。"
            "在本文中，我们详细介绍了维信诺的历史和公司结构、市场地位、AMOLED 能力和晶圆厂、ViP 和 pTSF 技术、8.6 代和 microLED 路线图以及股票表现、机遇和挑战。"
            "公司预计新产线将面向 IT OLED 和车载显示等应用。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("维信诺发布了 AMOLED", cleaned)
        self.assertIn("车载显示", cleaned)
        self.assertNotIn("在本文中", cleaned)
        self.assertNotIn("历史和公司结构", cleaned)

    def test_summary_noise_cleaner_rewrites_useful_article_intro(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "在这篇文章中，我们将介绍问题空间、我们在 Amazon Bedrock 和 Amazon OpenSearch Serverless 上的架构、"
            "我们在 OpenStreetMap ground Truth 上构建的评估方法、比较嵌入模型、融合策略、字幕和搜索方法的四个实验，"
            "以及构建类似系统时可以应用的实用指南。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("文章介绍了问题空间", cleaned)
        self.assertIn("基于 Amazon Bedrock 和 Amazon OpenSearch Serverless 的架构", cleaned)
        self.assertIn("基于 OpenStreetMap ground Truth 构建的评估方法", cleaned)
        self.assertNotIn("在这篇文章中", cleaned)
        self.assertNotIn("我们将介绍", cleaned)
        self.assertNotIn("我们在", cleaned)

    def test_summary_noise_cleaner_removes_html_cache_and_source_fragments(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            'nocache"/> Nvidia 表示，其 AI 数据中心设计运行温度更高，可使用更少的水 '
            '/ The Verge { Nvidia 表示，其全液冷 AI 数据中心设计可以减少能源和水的使用。'
            '公众对数据中心的反对强调了其水和能源消耗。'
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("Nvidia 表示，其全液冷 AI 数据中心设计可以减少能源和水的使用", cleaned)
        self.assertIn("公众对数据中心的反对", cleaned)
        self.assertNotIn("nocache", cleaned)
        self.assertNotIn("The Verge", cleaned)
        self.assertNotIn("/>", cleaned)
        self.assertEqual(cleaned.count("Nvidia 表示"), 1)

    def test_summary_noise_cleaner_rejects_channel_navigation_text(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = "快讯 头条 人工智能 芯东西 AIoT 云与智慧城市 机器人 VR/AR 手机通信 活动。"

        self.assertEqual(generator._clean_summary_noise(dirty), "")
        self.assertFalse(generator._is_usable_article_text(dirty))

    def test_summary_noise_cleaner_removes_arxiv_bibtex_tail(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "我们的结果表明，LLM 代理的有效内部世界建模需要能力优先的培训渠道，"
            "以实现扎根和校准的远见。 BibTeX 格式的引文 ×。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("有效内部世界建模", cleaned)
        self.assertNotIn("BibTeX", cleaned)
        self.assertNotIn("格式的引文", cleaned)
        self.assertNotIn("×", cleaned)

    def test_summary_noise_cleaner_removes_orbital_today_breadcrumbs(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "在 Dragonoon 成功证明了未来任务的低地球轨道通信技术后，SDA 取消了 11 颗计划中的演示卫星。"
            "时事通讯 新闻 太空 天文学 防御 AI Fun 独家活动日历 主页 > 太空 > "
            "SDA 在成功的 LEO 通信测试后取消了 11 颗卫星 SDA 在成功的 LEO 通信测试卫星后取消了 11 颗卫星，"
            "太空 2026 年 6 月 26 日。。。。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertIn("SDA 取消了 11 颗计划中的演示卫星", cleaned)
        self.assertNotIn("时事通讯", cleaned)
        self.assertNotIn("活动日历", cleaned)
        self.assertNotIn("主页", cleaned)
        self.assertNotIn(">", cleaned)

        dirty_with_wrapped_nav = (
            "美国宇航局与美国公司的新合作伙伴关系旨在开发长期月球操作和未来人类火星任务所需的技术。"
            "时事通 讯 新闻 太空天文学 防御 AI Fun 独家活动日历 主页 > 太空 > "
            "NASA 选择 41 个太空技术项目来支持未来的月球和火星任务 "
            "NASA 选择 41 个太空技术项目来支持未来的月球和火星任务 N"
        )
        cleaned = generator._clean_summary_noise(dirty_with_wrapped_nav)

        self.assertIn("未来人类火星任务所需的技术", cleaned)
        self.assertNotIn("时事通", cleaned)
        self.assertNotIn("太空天文学", cleaned)
        self.assertNotIn("主页", cleaned)
        self.assertNotIn("NASA 选择 41 个太空技术项目", cleaned)

    def test_summary_noise_cleaner_removes_adjacent_duplicate_blocks(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        repeated = (
            "数据来源：洛图科技（RUNTO），单位：美元 2026年5月液晶电视面板市场特点及6月预测 "
            "--全球液晶电视面板市场的产品价格在5月全线停涨。事实上，4月的涨价动能已经明显收尾，其最后一涨后成为阶段性"
        )
        dirty = repeated + " " + repeated + " 高点。洛图科技认为，当前市场进入了弱势整理期。"

        cleaned = generator._clean_summary_noise(dirty)

        self.assertNotIn("数据来源：洛图科技（RUNTO）", cleaned)
        self.assertNotIn("单位：美元", cleaned)
        self.assertNotIn("--", cleaned)
        self.assertNotIn("2026年5月液晶电视面板市场特点及6月预测", cleaned)
        self.assertIn("全球液晶电视面板市场的产品价格在5月全线停涨", cleaned)
        self.assertIn("当前市场进入了弱势整理期", cleaned)

    def test_summary_noise_cleaner_removes_blogger_intro_and_short_duplicate_sections(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        dirty = (
            "还是老规矩，通天晓老师，今天带大家过一下“试卷”，用独立的年报对比出趋势，从冷冰冰的数据里寻找规律。"
            "一、“一超多强”格局愈发稳定 京东方作为 "
            "这几天，各大面板公司陆续公布了自己2025年的“考卷”。"
            "一、“一超多强”格局愈发稳定 京东方作为行业“一超”，再次展现出强大的实力，营收再次突破 2000 亿大关。"
            "至于全应用第一；LCD、OLED、mini LED、OLED OS、车载、整机代工等各个领域的表现，支撑2000亿就不多说了。"
            "TCL华星稳定超过1000亿，2026年有望通过吃下的新T10工厂超越LGD。"
        )

        cleaned = generator._clean_summary_noise(dirty)

        self.assertNotIn("通天晓老师", cleaned)
        self.assertNotIn("带大家", cleaned)
        self.assertNotIn("试卷", cleaned)
        self.assertNotIn("考卷", cleaned)
        self.assertNotIn("不多说了", cleaned)
        self.assertEqual(cleaned.count("一、“一超多强”格局愈发稳定 京东方作为"), 1)
        self.assertIn("营收再次突破 2000 亿大关", cleaned)
        self.assertIn("TCL华星稳定超过1000亿", cleaned)

    def test_local_summary_truncates_after_share_marker(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "“千帆星座”建设与运营主体垣信卫星启动新一轮融资",
            "summary": (
                "大型低轨卫星互联网星座“千帆星座”的建设与运营主体上海垣信卫星科技有限公司启动新一轮融资。"
                "募集资金主要用于卫星星座工程建设、技术研发、市场开拓以及日常运营支出等。"
                "“千帆星座”建设与运营主体垣信卫星启动新一轮融资 2026-06-22 16:13 分享至；"
                "NASA 已选择八家新公司，并将从六家现有商业卫星数据采集合同持有者处获取新的数据产品。"
            ),
            "source": "36Kr",
            "parent_board": "A2 · 卫星组网",
        }

        summary = generator._article_summary(item, 500)

        self.assertIn("上海垣信卫星科技有限公司启动新一轮融资", summary)
        self.assertNotIn("分享至", summary)
        self.assertNotIn("NASA 已选择八家新公司", summary)

    def test_summary_finalizer_removes_dangling_you_and_adds_period(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()

        summary = generator._compress_summary_locally(
            "仅 2026 年 1 月，美国联邦通信委员会就授权了 15,000 颗 Starlink Gen2 卫星。Starcloud 已申请 88,000 颗轨道数据中心卫星。SpaceX 已申请 100 万美元。有",
            500,
        )

        self.assertTrue(summary.endswith("。"))
        self.assertNotIn("。有", summary)
        self.assertNotRegex(summary, r"有$")

    def test_summary_finalizer_removes_dangling_english_fragment(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()

        summary = generator._compress_summary_locally(
            "In January 2026 alone, the Federal Communications Commission authorized 15,000 Starlink Gen2 satellites. Starcloud has filed for 88,000 orbital data center satellites. SpaceX has filed for 1 million. There is",
            500,
        )

        self.assertTrue(summary.endswith("."))
        self.assertNotIn("There is", summary)
        self.assertIn("SpaceX has filed for 1 million.", summary)

    def test_summary_finalizer_adds_sentence_punctuation(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()

        chinese = generator._compress_summary_locally("垣信卫星启动新一轮融资，募集资金将用于星座工程建设", 500)
        english = generator._compress_summary_locally("Boeing demonstrated a quantum networking protocol", 500)

        self.assertTrue(chinese.endswith("。"))
        self.assertTrue(english.endswith("."))

    def test_local_summary_uses_real_english_content_not_template(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "A private company will build and launch NASA's next Mars orbiter in 2028",
            "summary": "A private company will build and launch NASA's next Mars orbiter in 2028",
            "content": "NASA selected a private company to build and launch its next Mars orbiter in 2028. The spacecraft will support communications relay, imaging, and future Mars exploration missions.",
            "source": "Space.com",
            "parent_board": "A1 · 政府政策",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "api"}, clear=False):
            summary = generator._article_summary(item, 420)

        self.assertIn("NASA selected a private company", summary)
        self.assertIn("communications relay", summary)
        self.assertNotIn("政府政策方向的新进展", summary)

    def test_batch_article_prompt_uses_title_and_brief_rules(self):
        from services.report_generator import ReportGenerator

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps([
                                    {"title": "测试标题", "summary": "测试简要内容。"}
                                ], ensure_ascii=False)
                            }
                        }
                    ]
                }).encode("utf-8")

        generator = ReportGenerator()
        item = {
            "title": "测试新闻",
            "summary": "测试新闻",
            "content": "这是用于摘要的完整正文，包含足够的信息来说明事件背景、关键主体和后续影响。" * 4,
            "source": "Source A",
            "publishTime": "2026-06-24T10:20:00",
            "url": "https://example.com/a",
        }

        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "NEWS_SUMMARY_MODE": "api"}, clear=False):
            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                generator._batch_summarize_articles([item], max_chars=900)

        prompt = captured["payload"]["messages"][1]["content"]
        self.assertIn("必须只根据“原文正文”总结", prompt)
        self.assertIn("信息型日报摘要", prompt)
        self.assertIn("20到35个汉字", prompt)
        self.assertIn("4到8句", prompt)
        self.assertIn("关键数字/技术细节", prompt)
        self.assertIn("订单数量", prompt)
        self.assertIn("不要照搬原文", prompt)
        self.assertIn("直接陈述新闻事实", prompt)
        self.assertIn("不要使用“该报道围绕”", prompt)
        self.assertIn("不要把标题原样作为简要内容第一句", prompt)
        self.assertIn("不要用板块名或行业影响句凑字数", prompt)
        self.assertIn("不要用标题扩写", prompt)
        self.assertIn("标题文本", prompt)
        self.assertIn("简要内容文本", prompt)

    def test_article_summary_queue_retries_after_rate_limit(self):
        from services.report_generator import ReportGenerator

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps([
                                    {"title": "重试后的标题", "summary": "重试后生成了完整新闻摘要。"}
                                ], ensure_ascii=False)
                            }
                        }
                    ]
                }).encode("utf-8")

        generator = ReportGenerator()
        item = {
            "title": "测试新闻",
            "summary": "测试新闻",
            "content": "这是用于摘要的完整正文，包含足够的信息来说明事件背景、关键主体和后续影响。" * 4,
            "source": "Source A",
            "publishTime": "2026-06-24T10:20:00",
            "url": "https://example.com/a",
        }
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    429,
                    "Too Many Requests",
                    hdrs=None,
                    fp=None,
                )
            return FakeResponse()

        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "NEWS_SUMMARY_MODE": "api",
            "NEWS_SUMMARY_RETRY_BACKOFF_SECONDS": "1",
            "NEWS_SUMMARY_QUEUE_DELAY_SECONDS": "1",
        }, clear=False):
            with mock.patch("time.sleep") as sleep:
                with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    generator._batch_summarize_articles([item], max_chars=420)

        key = generator._summary_cache_key(item)
        self.assertEqual(calls["count"], 2)
        self.assertIn("完整新闻摘要", generator._summary_cache[key])
        sleep.assert_called_once()

    def test_article_summary_queue_stops_after_repeated_rate_limit(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        items = [
            {
                "title": f"测试新闻{i}",
                "summary": f"测试新闻{i}",
                "content": f"这是第{i}篇用于摘要的完整正文，包含足够的信息来说明事件背景、关键主体和后续影响。" * 4,
                "source": "Source A",
                "publishTime": "2026-06-24T10:20:00",
                "url": f"https://example.com/{i}",
            }
            for i in range(3)
        ]
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=None,
            )

        with mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key",
            "NEWS_SUMMARY_MODE": "api",
            "NEWS_SUMMARY_RETRIES": "2",
            "NEWS_SUMMARY_RETRY_BACKOFF_SECONDS": "1",
            "NEWS_SUMMARY_STOP_AFTER_429": "2",
            "NEWS_SUMMARY_QUEUE_DELAY_SECONDS": "1",
        }, clear=False):
            with mock.patch("time.sleep"):
                with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    generator._batch_summarize_articles(items, max_chars=420)

        self.assertEqual(calls["count"], 4)
        self.assertTrue(generator._summary_batch_disabled_for_run)
        self.assertEqual(generator._summary_cache, {})

    def test_article_summary_queue_skips_title_only_items(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "Astrobotic 展示 Griffin-1 着陆器",
            "summary": "Astrobotic 展示 Griffin-1 着陆器",
            "source": "Spaceflight Now",
            "publishTime": "2026-06-16T01:08:00",
            "url": "https://example.com/title-only",
        }

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "NEWS_SUMMARY_MODE": "api"}, clear=False):
            with mock.patch("urllib.request.urlopen") as urlopen:
                generator._batch_summarize_articles([item], max_chars=420)

        urlopen.assert_not_called()
        self.assertEqual(generator._summary_cache, {})

    def test_manual_summary_mode_exports_chatgpt_tasks(self):
        from services.report_generator import ReportGenerator

        with tempfile.TemporaryDirectory() as tmp:
            generator = ReportGenerator()
            generator.report_dir = Path(tmp)
            item = {
                "title": "测试新闻",
                "summary": "测试新闻",
                "content": "这是用于 ChatGPT 手动摘要的完整正文，包含事件背景、关键主体、数字和后续影响。" * 4,
                "source": "Source A",
                "publishTime": "2026-06-24T10:20:00",
                "url": "https://example.com/manual",
            }

            with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "manual"}, clear=False):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    generator._batch_summarize_articles([item], max_chars=900)

            urlopen.assert_not_called()
            self.assertIsNotNone(generator.last_manual_summary_tasks_path)
            task_text = Path(generator.last_manual_summary_tasks_path).read_text(encoding="utf-8")
            self.assertIn("ChatGPT 摘要任务包", task_text)
            self.assertIn("task.article_text", task_text)
            self.assertIn("信息型日报摘要", task_text)
            self.assertIn('"max_summary_chars": 900', task_text)
            self.assertIn("manual_summary_results.json", task_text)

    def test_default_local_mode_does_not_export_or_call_api(self):
        from services.report_generator import ReportGenerator

        with tempfile.TemporaryDirectory() as tmp:
            generator = ReportGenerator()
            generator.report_dir = Path(tmp)
            item = {
                "title": "测试新闻",
                "summary": "测试新闻",
                "content": "这是本地摘要可用的完整正文，包含事件背景、关键主体、数字和后续影响。" * 4,
                "source": "Source A",
                "publishTime": "2026-06-24T10:20:00",
                "url": "https://example.com/local",
            }

            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    generator._batch_summarize_articles([item], max_chars=900)

            urlopen.assert_not_called()
            self.assertIsNone(generator.last_manual_summary_tasks_path)
            self.assertFalse(list(Path(tmp).glob("manual_summary_tasks_*")))

    def test_manual_summary_import_populates_article_cache(self):
        from services.report_generator import ReportGenerator

        with tempfile.TemporaryDirectory() as tmp:
            generator = ReportGenerator()
            generator.report_dir = Path(tmp)
            item = {
                "title": "测试新闻",
                "summary": "测试新闻",
                "content": "这是用于 ChatGPT 手动摘要的完整正文，包含事件背景、关键主体、数字和后续影响。" * 4,
                "source": "Source A",
                "publishTime": "2026-06-24T10:20:00",
                "url": "https://example.com/manual-import",
            }
            key = generator._summary_cache_key(item)
            import_path = Path(tmp) / "manual_summary_results.json"
            import_path.write_text(json.dumps({
                "summaries": [
                    {"key": key, "title": "导入后的中文标题", "summary": "导入后的中文摘要。"}
                ]
            }, ensure_ascii=False), encoding="utf-8")

            generator._load_manual_summary_import()

            self.assertEqual(generator._article_display_title(item), "导入后的中文标题")
            self.assertEqual(generator._article_summary(item, 420), "导入后的中文摘要。")

    def test_manual_summary_mode_does_not_use_local_fake_summary(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "一家私营公司将建造并发射 NASA 下一代 2028 年火星轨道器，且不是 SpaceX",
            "summary": "一家私营公司将建造并发射 NASA 下一代 2028 年火星轨道器，且不是 SpaceX",
            "content": "NASA 选择一家私营公司建造并发射下一代火星轨道器。正文包含任务背景、发射计划和项目安排。" * 4,
            "source": "Space.com",
            "parent_board": "A1 · 政府政策",
            "url": "https://example.com/mars-orbiter",
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "manual"}, clear=False):
            summary = generator._article_summary(item, 900)

        self.assertIn("摘要待生成", summary)
        self.assertNotIn("政府政策方向的新进展", summary)
        self.assertNotIn("频谱、轨道资源", summary)

    def test_default_local_summary_uses_crawled_content_automatically(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "一家私营公司将建造并发射 NASA 下一代 2028 年火星轨道器，且不是 SpaceX",
            "summary": "一家私营公司将建造并发射 NASA 下一代 2028 年火星轨道器，且不是 SpaceX",
            "content": "NASA 选择一家私营公司建造并发射下一代火星轨道器。正文包含任务背景、发射计划和项目安排。" * 4,
            "source": "Space.com",
            "parent_board": "A1 · 政府政策",
            "url": "https://example.com/mars-orbiter",
        }

        with mock.patch.dict(os.environ, {}, clear=True):
            summary = generator._article_summary(item, 900)

        self.assertIn("NASA 选择一家私营公司", summary)
        self.assertNotIn("摘要待生成", summary)
        self.assertNotIn("政府政策方向的新进展", summary)

    def test_article_summary_removes_repeated_title_prefix_only(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        item = {
            "title": "聚焦前沿：Micro LED 需求爆发，量产进程全面提速",
            "summary": (
                "聚焦前沿：Micro LED 需求爆发，量产进程全面提速 "
                "聚焦 前沿： Micro LED 需求爆发，量产进程全面提速 "
                "当显示技术迭代驶入快车道，Micro-LED正从实验室走向规模化商用。"
            ),
            "content": "",
            "source": "OFweek",
            "publishTime": "2026-06-30T10:00:00",
            "url": "https://example.com/micro-led",
        }

        source = generator._extract_summary_source(item)

        self.assertTrue(source.startswith("当显示技术迭代驶入快车道"))
        self.assertNotIn("聚焦前沿：Micro LED 需求爆发", source[:40])

    def test_title_prefix_cleanup_keeps_later_title_mentions(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        text = (
            "这是正文第一句，包含事件背景。"
            "文章随后引用标题“聚焦前沿：Micro LED 需求爆发，量产进程全面提速”作为栏目名称。"
            "后续继续说明产业链影响。"
        )

        cleaned = generator._remove_title_prefix_from_text(
            "聚焦前沿：Micro LED 需求爆发，量产进程全面提速",
            text,
        )

        self.assertIn("引用标题", cleaned)
        self.assertIn("聚焦前沿：Micro LED 需求爆发", cleaned)

    def test_manual_summary_mode_skips_cluster_api(self):
        from services.report_generator import ReportGenerator

        generator = ReportGenerator()
        cluster = {
            "representative_title": "测试事件",
            "items": [{"title": "测试新闻", "summary": "测试摘要"}],
        }

        with mock.patch.dict(os.environ, {"NEWS_SUMMARY_MODE": "manual", "OPENAI_API_KEY": "test-key"}, clear=False):
            with mock.patch("urllib.request.urlopen") as urlopen:
                generator._batch_summarize_clusters([cluster])

        urlopen.assert_not_called()

    def test_batch_article_prompt_truncates_long_article_content(self):
        from services.report_generator import ReportGenerator

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps([
                                    {"title": "测试标题", "summary": "测试简要内容。"}
                                ], ensure_ascii=False)
                            }
                        }
                    ]
                }).encode("utf-8")

        generator = ReportGenerator()
        long_content = "第一句介绍事件。" + ("很长的正文内容。" * 300)
        item = {
            "title": "测试新闻",
            "summary": "测试新闻",
            "content": long_content,
            "source": "Source A",
            "publishTime": "2026-06-24T10:20:00",
            "url": "https://example.com/a",
        }

        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "NEWS_SUMMARY_MODE": "api", "NEWS_SUMMARY_INPUT_CHARS": "120"}, clear=False):
            with mock.patch("time.sleep"):
                with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    generator._batch_summarize_articles([item], max_chars=420)

        prompt = captured["payload"]["messages"][1]["content"]
        self.assertIn("第一句介绍事件", prompt)
        self.assertLess(len(prompt), 1200)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_fastapi_stubs()
        sys.modules.pop("server", None)
        import server  # noqa: F401

    def test_analyze_news_counts_all_clusters_and_truncates_top_events(self):
        import server

        class FakeAnalyzer:
            def __init__(self):
                self.reporter = types.SimpleNamespace(report_dir=Path(tempfile.gettempdir()))

            def analyze(self, news_list, sources=None, date=None):
                clusters = [
                    {
                        "representative_title": f"Event {i}",
                        "importance_score": 100 - i,
                        "sources": ["src"],
                        "item_count": i + 1,
                    }
                    for i in range(12)
                ]
                return {
                    "dedup": {"input_count": 12, "unique_count": 12, "duplicate_count": 0},
                    "ranked_clusters": clusters,
                    "board_summary": {"ai": {"count": 3}},
                    "report_path": "r.md",
                    "brief_path": "b.html",
                }

        server.analyzer = FakeAnalyzer()
        req = server.AnalyzeRequest(news=[{"title": "x"}], sources=["a"], date="2026-06-24")
        response = asyncio.run(server.analyze_news(req))

        self.assertEqual(response.summary["cluster_count"], 12)
        self.assertEqual(len(response.top_events), 10)

    def test_list_reports_includes_weekly_and_briefs(self):
        import server

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            (report_dir / "daily_report_1.md").write_text("a", encoding="utf-8")
            (report_dir / "ai_weekly_report_1.md").write_text("b", encoding="utf-8")
            (report_dir / "daily_brief_1.html").write_text("c", encoding="utf-8")
            (report_dir / "ai_weekly_brief_1.html").write_text("d", encoding="utf-8")

            now = datetime.now().timestamp()
            for item in report_dir.iterdir():
                os.utime(item, (now, now))

            server.analyzer = types.SimpleNamespace(
                reporter=types.SimpleNamespace(report_dir=report_dir)
            )
            result = asyncio.run(server.list_reports())

            names = [item["name"] for item in result["reports"]]
            self.assertIn("daily_report_1.md", names)
            self.assertIn("ai_weekly_report_1.md", names)
            self.assertIn("daily_brief_1.html", names)
            self.assertIn("ai_weekly_brief_1.html", names)


if __name__ == "__main__":
    unittest.main()
