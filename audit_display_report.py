import re
from pathlib import Path

from services.board_classifier import BoardClassifier
from services.topic_config import load_topic_config


REPORT = Path(
    r"C:\Users\orang\.openclaw\workspace\.tmp_unified_news_analyzer\unified-news-analyzer\reports"
    r"\display_polarizer_llm_weekly_report_20260701_20260707_20260707_1133.md"
)


def parse_report(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    current = None
    items = []
    i = 0
    while i < len(lines):
        board_match = re.match(r"^## (A[1-8] · .+)$", lines[i])
        if board_match:
            current = board_match.group(1)
            i += 1
            continue

        article_match = re.match(r"^### \*\*\[(.*?)\]\((.*?)\)\*\*", lines[i])
        if article_match and current:
            title, url = article_match.group(1), article_match.group(2)
            source = ""
            date = ""
            summary_lines = []
            j = i + 1
            while j < len(lines):
                if lines[j].startswith("### ") or lines[j].startswith("## "):
                    break
                meta_match = re.match(r"^\*\*来源：(.+?) \| 日期：(.+?)\*\*$", lines[j])
                if meta_match:
                    source, date = meta_match.group(1), meta_match.group(2)
                elif lines[j].strip() and not lines[j].startswith("[查看原文]"):
                    if not lines[j].startswith("---") and not lines[j].startswith("#"):
                        summary_lines.append(lines[j].strip())
                j += 1
            items.append(
                {
                    "current": current,
                    "title": title,
                    "url": url,
                    "source": source,
                    "date": date,
                    "summary": " ".join(summary_lines),
                }
            )
            i = j
            continue
        i += 1
    return items


def main():
    cfg = load_topic_config("display_polarizer")
    classifier = BoardClassifier(cfg)
    items = parse_report(REPORT)
    print(f"report={REPORT}")
    print(f"items={len(items)}")
    print()
    for index, item in enumerate(items, 1):
        pred = classifier.classify(
            {
                "title": item["title"],
                "summary": item["summary"],
                "content": item["summary"],
                "source": item["source"],
                "category": "display",
                "url": item["url"],
            }
        )
        current = item["current"]
        predicted = pred["parent_board"]
        mark = "OK" if current == predicted else "CHECK"
        print(
            f"{index:02d} {mark} | current={current} | pred={predicted} | "
            f"{item['title']} | {item['source']}"
        )
        if mark == "CHECK":
            print(f"    summary={item['summary'][:240]}")


if __name__ == "__main__":
    main()
