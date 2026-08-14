"""
HTML 简报转 PDF - 使用 Selenium + Edge 生成 PDF
"""
import sys
import time
import threading
import base64
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

from selenium import webdriver
from selenium.webdriver.edge.options import Options


class DirHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent.parent / "reports"), **kwargs)


def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()

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
        print(f"Loading: {url}")
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
        print(f"PDF saved: {pdf_path} ({size_kb:.0f} KB)")
        return True

    except Exception as e:
        print(f"Error: {e}")
        try:
            server.shutdown()
        except:
            pass
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        reports_dir = Path(__file__).parent.parent / "reports"
        briefs = sorted(reports_dir.glob("daily_brief_*.html"), reverse=True)
        if briefs:
            html_file = briefs[0]
        else:
            print("No brief HTML found")
            sys.exit(1)
    else:
        html_file = sys.argv[1]

    pdf_file = Path(html_file).with_suffix(".pdf")
    success = html_to_pdf(str(html_file), str(pdf_file))
    sys.exit(0 if success else 1)
