from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex" / "skills" / "wechat-image-downloader" / "scripts" / "download_wechat_images.py"
spec = importlib.util.spec_from_file_location("download_wechat_images", SCRIPT)
wechat = importlib.util.module_from_spec(spec)
sys.modules["download_wechat_images"] = wechat
assert spec.loader is not None
spec.loader.exec_module(wechat)


class WechatImageDownloaderTest(unittest.TestCase):
    def test_collects_article_images_before_page_chrome(self) -> None:
        page = """
        <html>
          <head>
            <title> 测试文章 </title>
            <meta property="og:image" content="https://mmbiz.qpic.cn/cover/0?wx_fmt=jpeg&amp;tp=webp">
          </head>
          <body>
            <img src="https://res.wx.qq.com/icon.png">
            <div id="js_content">
              <img data-src="//mmbiz.qpic.cn/mmbiz_png/abc/640?wx_fmt=png&amp;from=appmsg" src="/placeholder.gif">
              <section style="background-image:url('https://mmbiz.qpic.cn/bg/0?wx_fmt=jpg')"></section>
            </div>
          </body>
        </html>
        """
        title, candidates = wechat.collect_image_candidates(page, "https://mp.weixin.qq.com/s/test")

        self.assertEqual(title, "测试文章")
        self.assertEqual(
            [candidate.url for candidate in candidates],
            [
                "https://mmbiz.qpic.cn/cover/0?wx_fmt=jpeg&tp=webp",
                "https://mmbiz.qpic.cn/mmbiz_png/abc/640?wx_fmt=png&from=appmsg",
                "https://mmbiz.qpic.cn/bg/0?wx_fmt=jpg",
            ],
        )

    def test_all_scope_includes_page_images(self) -> None:
        page = """
        <html><body>
          <img src="https://res.wx.qq.com/icon.png">
          <div id="js_content"><img data-src="https://mmbiz.qpic.cn/a/0?wx_fmt=jpeg"></div>
        </body></html>
        """
        _, candidates = wechat.collect_image_candidates(page, "https://mp.weixin.qq.com/s/test", scope="all")

        self.assertEqual(
            [candidate.url for candidate in candidates],
            [
                "https://res.wx.qq.com/icon.png",
                "https://mmbiz.qpic.cn/a/0?wx_fmt=jpeg",
            ],
        )

    def test_extension_prefers_content_type_then_wx_fmt(self) -> None:
        self.assertEqual(wechat.extension_for("https://mmbiz.qpic.cn/a/0?wx_fmt=jpeg", "image/webp"), ".webp")
        self.assertEqual(wechat.extension_for("https://mmbiz.qpic.cn/a/0?wx_fmt=jpeg", ""), ".jpg")
        self.assertEqual(wechat.extension_for("https://example.com/image.png", ""), ".png")

    def test_select_print_images_can_drop_edges(self) -> None:
        self.assertEqual(
            wechat.select_print_images(["001.jpg", "002.png", "003.png", "004.jpg"], drop_first=1, drop_last=1),
            ["002.png", "003.png"],
        )

    def test_saved_image_files_ignores_failed_records(self) -> None:
        manifest = {
            "images": [
                {"status": "saved", "file": "001.jpg"},
                {"status": "failed", "file": "002.png"},
                {"status": "saved", "file": "003.png"},
            ]
        }

        self.assertEqual(wechat.saved_image_files(manifest), ["001.jpg", "003.png"])

    def test_parse_pdf_image_spec_supports_ranges_and_filenames(self) -> None:
        image_files = ["001.jpg", "002.png", "003.png", "004.png"]

        self.assertEqual(wechat.parse_pdf_image_spec("2-3,004.png", image_files), ["002.png", "003.png", "004.png"])

    def test_document_title_can_retitle_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "download"
            out_dir.mkdir()
            manifest = {"output_dir": str(out_dir.resolve()), "images": []}

            updated = wechat.retitle_output_dir(manifest, "虹口区 2025 学年度 数学练习卷")

            self.assertTrue(Path(updated["output_dir"]).name.startswith("虹口区-2025-学年度-数学练习卷"))
            self.assertTrue((Path(updated["output_dir"]) / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
