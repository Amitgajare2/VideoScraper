#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse, unquote

import requests
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

DIRECT_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi")
STREAM_EXTS = (".m3u8", ".mpd")
MEDIA_MIME_HINTS = (
    "video/",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "application/dash+xml",
)


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("URL is empty.")

    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    return url


def sanitize_filename(name: str, fallback: str = "video") -> str:
    name = unquote(name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return name[:160] if name else fallback


def get_url_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in DIRECT_VIDEO_EXTS + STREAM_EXTS:
        if path.endswith(ext):
            return ext
    return ""


def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def looks_like_media_url(url: Optional[str], mime: str = "") -> bool:
    if not url:
        return False

    url = url.strip()
    if not url or url.startswith(("blob:", "data:", "javascript:")):
        return False

    lower_path = urlparse(url).path.lower()
    lower_url = url.lower()
    lower_mime = (mime or "").lower()

    # Avoid thumbnails and tiny previews when possible.
    bad_hints = ("thumbnail", "thumb", "sprite", "poster", ".jpg", ".jpeg", ".png", ".gif")
    if any(hint in lower_url for hint in bad_hints):
        return False

    if lower_path.endswith(DIRECT_VIDEO_EXTS + STREAM_EXTS):
        return True

    if any(hint in lower_mime for hint in MEDIA_MIME_HINTS):
        return True

    # Some CDNs hide extension but include video/stream hints in query/path.
    stream_hints = ("m3u8", "mp4", "webm", "manifest", "master.m3u8")
    return any(hint in lower_url for hint in stream_hints)


def score_media_url(url: str) -> int:
    lower = url.lower()
    path = urlparse(url).path.lower()
    score = 0

    if path.endswith(".mp4"):
        score += 120
    elif path.endswith(".webm"):
        score += 110
    elif path.endswith(".m3u8"):
        score += 100
    elif path.endswith(".mpd"):
        score += 90
    elif path.endswith(DIRECT_VIDEO_EXTS):
        score += 80

    # Prefer likely full-quality streams.
    if any(x in lower for x in ("1080", "1920x1080", "fhd")):
        score += 30
    if any(x in lower for x in ("720", "1280x720", "hd")):
        score += 20
    if any(x in lower for x in ("480", "360", "240")):
        score -= 10

    # Penalize obvious previews/ads.
    if any(x in lower for x in ("preview", "trailer", "ads", "doubleclick", "tracking")):
        score -= 40

    return score


def unique_sorted(urls: Iterable[str]) -> List[str]:
    cleaned: Set[str] = set()
    for url in urls:
        if not url:
            continue
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        if looks_like_media_url(url):
            cleaned.add(url)

    return sorted(cleaned, key=score_media_url, reverse=True)


def try_ytdlp_download(
    url: str,
    out_dir: Path,
    quality: str = "best",
    referer: Optional[str] = None,
    quiet: bool = False,
) -> bool:
    try:
        import yt_dlp
    except ImportError:
        print("⚠️ yt-dlp is not installed. Skipping yt-dlp step.")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)

    if quality == "best":
        format_selector = "bv*+ba/best"
    else:
        # Examples:
        # "best[height<=720]"
        # "best[height<=1080]"
        # "bv*[height<=720]+ba/best[height<=720]"
        format_selector = quality

    ydl_opts = {
        "outtmpl": str(out_dir / "%(title).160B [%(id)s].%(ext)s"),
        "format": format_selector,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "continuedl": True,
        "merge_output_format": "mp4",
        "quiet": quiet,
        "no_warnings": False,
        "http_headers": {
            "User-Agent": USER_AGENT,
            **({"Referer": referer} if referer else {}),
        },
    }

    try:
        print("🔎 Trying yt-dlp...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result_code = ydl.download([url])
        return result_code == 0
    except Exception as exc:
        print(f"⚠️ yt-dlp failed: {exc}")
        return False


def create_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    options = ChromeOptions()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1366,768")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={USER_AGENT}")

    # Enable Chrome performance logs so we can read Network events.
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=ChromeService(ChromeDriverManager().install()),
        options=options,
    )

    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass

    return driver


def wait_for_page(driver: webdriver.Chrome, timeout: int = 25) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
    )
    time.sleep(2)


def collect_dom_media_urls_in_current_frame(driver: webdriver.Chrome) -> Set[str]:
    urls: Set[str] = set()

    # <video src="..."> and video.currentSrc
    for video in driver.find_elements(By.TAG_NAME, "video"):
        for attr in ("currentSrc", "src"):
            try:
                value = driver.execute_script(
                    "return arguments[0][arguments[1]] || arguments[0].getAttribute(arguments[1]);",
                    video,
                    attr,
                )
                if looks_like_media_url(value):
                    urls.add(value)
            except Exception:
                pass

        try:
            for source in video.find_elements(By.TAG_NAME, "source"):
                value = source.get_attribute("src")
                if looks_like_media_url(value):
                    urls.add(value)
        except Exception:
            pass

    # Standalone <source src="...">
    for source in driver.find_elements(By.TAG_NAME, "source"):
        try:
            value = source.get_attribute("src")
            if looks_like_media_url(value):
                urls.add(value)
        except Exception:
            pass

    # Some players store URLs in attributes.
    attrs_to_check = ("src", "data-src", "data-video", "data-url", "data-file")
    css = ",".join(f"[{attr}]" for attr in attrs_to_check)

    try:
        elements = driver.find_elements(By.CSS_SELECTOR, css)
        for element in elements:
            for attr in attrs_to_check:
                try:
                    value = element.get_attribute(attr)
                    if looks_like_media_url(value):
                        urls.add(value)
                except Exception:
                    pass
    except Exception:
        pass

    return urls


def collect_dom_media_urls(driver: webdriver.Chrome, max_depth: int = 3) -> Set[str]:
    urls: Set[str] = set()

    def scan_frame(depth: int) -> None:
        urls.update(collect_dom_media_urls_in_current_frame(driver))

        if depth >= max_depth:
            return

        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for index in range(len(frames)):
            try:
                # Re-fetch because the DOM may change after switching.
                frames_now = driver.find_elements(By.TAG_NAME, "iframe")
                driver.switch_to.frame(frames_now[index])
                scan_frame(depth + 1)
            except Exception:
                pass
            finally:
                try:
                    driver.switch_to.parent_frame()
                except Exception:
                    pass

    driver.switch_to.default_content()
    scan_frame(0)
    driver.switch_to.default_content()

    return urls


def collect_network_media_urls(driver: webdriver.Chrome) -> Set[str]:
    urls: Set[str] = set()

    try:
        logs = driver.get_log("performance")
    except Exception as exc:
        print(f"⚠️ Could not read performance logs: {exc}")
        return urls

    for entry in logs:
        try:
            message = json.loads(entry["message"]).get("message", {})
            method = message.get("method", "")
            params = message.get("params", {})

            url = None
            mime = ""

            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                url = request.get("url")
            elif method == "Network.responseReceived":
                response = params.get("response", {})
                url = response.get("url")
                mime = response.get("mimeType", "")
            else:
                continue

            if looks_like_media_url(url, mime):
                urls.add(url)

        except Exception:
            continue

    return urls


def gently_trigger_video_loading(driver: webdriver.Chrome) -> None:
    """
    This does not bypass anything. It just asks already-present video elements to load/play muted,
    and scrolls the page so lazy-loaded players can appear.
    """
    try:
        driver.execute_script(
            """
            document.querySelectorAll('video').forEach(v => {
                try {
                    v.muted = true;
                    v.preload = 'auto';
                    v.load();
                    v.play().catch(() => {});
                } catch (e) {}
            });
            """
        )
    except Exception:
        pass

    try:
        height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
        for y in (0, height // 3, (height * 2) // 3, height):
            driver.execute_script("window.scrollTo(0, arguments[0]);", y)
            time.sleep(0.8)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass


def discover_media_urls_with_selenium(
    page_url: str,
    wait_seconds: int = 8,
    headless: bool = True,
) -> List[str]:
    driver = create_chrome_driver(headless=headless)

    try:
        print("🌐 Opening page with Selenium...")
        driver.get(page_url)
        wait_for_page(driver)

        gently_trigger_video_loading(driver)
        time.sleep(wait_seconds)

        dom_urls = collect_dom_media_urls(driver)
        network_urls = collect_network_media_urls(driver)

        all_urls = unique_sorted(dom_urls | network_urls)

        print(f"✅ Found {len(all_urls)} possible media URL(s).")
        return all_urls

    finally:
        driver.quit()


def build_output_path(page_url: str, media_url: str, out_dir: Path) -> Path:
    parsed_page = urlparse(page_url)
    parsed_media = urlparse(media_url)

    page_slug = sanitize_filename(Path(parsed_page.path.strip("/")).name, "video")
    media_slug = sanitize_filename(Path(parsed_media.path).stem, page_slug)

    ext = get_url_extension(media_url)
    if ext in STREAM_EXTS:
        ext = ".mp4"
    elif not ext:
        ext = ".mp4"

    return next_available_path(out_dir / f"{media_slug}{ext}")


def download_direct_file(media_url: str, out_path: Path, referer: Optional[str] = None) -> bool:
    headers = {
        "User-Agent": USER_AGENT,
        **({"Referer": referer} if referer else {}),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"⬇️ Downloading direct video:")
    print(media_url)
    print(f"💾 Saving as: {out_path}")

    try:
        with requests.get(media_url, headers=headers, stream=True, timeout=40) as response:
            response.raise_for_status()

            total = int(response.headers.get("content-length", 0))
            with open(out_path, "wb") as file, tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc="📥 Progress",
            ) as bar:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)
                        bar.update(len(chunk))

        print("✅ Download complete.")
        return True

    except Exception as exc:
        print(f"❌ Direct download failed: {exc}")
        return False


def download_best_candidate(
    page_url: str,
    candidates: List[str],
    out_dir: Path,
    quality: str = "best",
    list_only: bool = False,
) -> bool:
    if not candidates:
        print("❌ No downloadable media URL found.")
        return False

    print("\n🎥 Possible media URLs:")
    for i, candidate in enumerate(candidates[:20], 1):
        print(f"{i}. {candidate}")

    if list_only:
        return True

    chosen = candidates[0]
    ext = get_url_extension(chosen)

    print(f"\n🎯 Auto-selected best candidate:")
    print(chosen)

    if ext in STREAM_EXTS:
        print("📡 Stream detected. Using yt-dlp for HLS/DASH download...")
        return try_ytdlp_download(chosen, out_dir, quality=quality, referer=page_url)

    out_path = build_output_path(page_url, chosen, out_dir)
    return download_direct_file(chosen, out_path, referer=page_url)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Best-effort universal video downloader for authorized downloads."
    )

    parser.add_argument("url", nargs="?", help="Video page URL")
    parser.add_argument("-o", "--out-dir", default="downloads", help="Download folder")
    parser.add_argument(
        "-q",
        "--quality",
        default="best",
        help=(
            "yt-dlp format selector. Examples: best, best[height<=720], "
            "bv*[height<=1080]+ba/best[height<=1080]"
        ),
    )
    parser.add_argument("--no-ytdlp", action="store_true", help="Skip yt-dlp and use Selenium discovery only")
    parser.add_argument("--list-only", action="store_true", help="Only list discovered media URLs, do not download")
    parser.add_argument("--headful", action="store_true", help="Show browser window instead of headless mode")
    parser.add_argument("--wait", type=int, default=8, help="Extra seconds to wait for lazy-loaded media")

    args = parser.parse_args()

    url = args.url or input("🔗 Enter video page URL: ").strip()
    out_dir = Path(args.out_dir)

    try:
        page_url = normalize_url(url)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1

    print("🎬 Universal Video Downloader")
    print(f"🔗 URL: {page_url}")
    print("⚠️ Use only where you have permission. DRM/paywall/login bypass is not supported.\n")

    # Step 1: yt-dlp handles thousands of sites and many generic video pages.
    if not args.no_ytdlp and not args.list_only:
        if try_ytdlp_download(page_url, out_dir, quality=args.quality):
            print("✅ Finished with yt-dlp.")
            return 0

    # Step 2: Selenium fallback.
    candidates = discover_media_urls_with_selenium(
        page_url,
        wait_seconds=args.wait,
        headless=not args.headful,
    )

    if download_best_candidate(
        page_url,
        candidates,
        out_dir,
        quality=args.quality,
        list_only=args.list_only,
    ):
        return 0

    print("\n❌ Could not download this video.")
    print("Possible reasons:")
    print("- The site uses DRM/encrypted media.")
    print("- The video requires login or paid access.")
    print("- The stream URL is generated after manual interaction.")
    print("- The website blocks automated browsers.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
