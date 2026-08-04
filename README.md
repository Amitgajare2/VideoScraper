# 🎬 VideoScraper

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/github/license/luisdiaz327/VideoScraper)
![Issues](https://img.shields.io/github/issues/luisdiaz327/VideoScraper)
![Last Commit](https://img.shields.io/github/last-commit/luisdiaz327/VideoScraper)
![Stars](https://img.shields.io/github/stars/luisdiaz327/VideoScraper)
![Forks](https://img.shields.io/github/forks/luisdiaz327/VideoScraper?style=social)

A best-effort universal video downloader that combines **yt-dlp** with a **Selenium/Chrome** fallback to discover and download video streams from web pages.

- ✅ Tries `yt-dlp` first (handles thousands of sites natively)
- ✅ Falls back to headless Chrome + network/DOM inspection when `yt-dlp` fails
- ✅ Detects direct video files (`.mp4`, `.webm`, `.mkv`…) and streams (HLS `.m3u8`, DASH `.mpd`)
- ✅ Scores and auto-selects the best-quality candidate
- ✅ Download progress shown with `tqdm`
- ✅ CLI flags for quality, output folder, headful mode, and more

---

## 🚀 Features

- **Two-stage strategy:** `yt-dlp` → Selenium/Chrome discovery
- **Headless Chrome automation** via Selenium with performance-log inspection
- **Smart media URL detection** by extension, MIME type, and scoring
- **Quality selection** through `yt-dlp` format selectors
- **Resumable direct downloads** with retry support
- **Graceful handling** of lazy-loaded players and iframes

---

## ⚙️ Requirements

- Python 3.10+
- `pip`
- Google Chrome installed (the Selenium fallback uses Chrome)

---

## 📦 Installation

1. Clone the repo:

   ```bash
   git clone https://github.com/luisdiaz327/VideoScraper.git
   cd VideoScraper
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   Or manually:

   ```bash
   pip install selenium requests tqdm webdriver-manager yt-dlp
   ```

---

## 🧠 How It Works

1. You provide a video page URL.
2. The script first tries `yt-dlp`, which natively supports thousands of sites.
3. If `yt-dlp` fails, it opens the page in headless Chrome, inspects the DOM and network requests for media URLs, and scores them by quality.
4. The best candidate is downloaded — streams go through `yt-dlp`, direct files via `requests` + `tqdm`.

---

## 🖥️ Usage

```bash
python VideoScraper.py "https://example.com/video-page"
```

If you omit the URL, you'll be prompted for one:

```
🔗 Enter video page URL: https://example.com/video-page
```

The video is saved to the `downloads/` folder by default.

### Useful options

```bash
# Only list discovered media URLs, do not download
python VideoScraper.py "https://example.com/video-page" --list-only

# Limit quality to 720p
python VideoScraper.py "https://example.com/video-page" -q "best[height<=720]"

# Skip yt-dlp and use Selenium discovery only
python VideoScraper.py "https://example.com/video-page" --no-ytdlp

# Show the browser window instead of headless mode
python VideoScraper.py "https://example.com/video-page" --headful

# Wait longer for lazy-loaded media
python VideoScraper.py "https://example.com/video-page" --wait 15

# Custom output folder
python VideoScraper.py "https://example.com/video-page" -o ./my_videos
```

### CLI flags

| Flag            | Description                                              | Default     |
| --------------- | -------------------------------------------------------- | ----------- |
| `url`           | Video page URL (positional; prompted if omitted)         | —           |
| `-o/--out-dir`  | Download folder                                          | `downloads` |
| `-q/--quality`  | `yt-dlp` format selector                                 | `best`      |
| `--no-ytdlp`    | Skip `yt-dlp` and use Selenium discovery only            | off         |
| `--list-only`   | Only list discovered media URLs                          | off         |
| `--headful`     | Show the browser window                                  | off         |
| `--wait`        | Extra seconds to wait for lazy-loaded media              | `8`         |
| `--timeout`     | Page-load timeout in seconds                             | `25`        |
| `--retries`     | Retry attempts for direct HTTP downloads                 | `3`         |
| `--verbose`     | Show `yt-dlp` warnings and extra debug output            | off         |
| `--version`     | Print version and exit                                   | —           |

---

## 🧼 Known Issues

- Some videos use DRM/encrypted media and cannot be downloaded.
- Sites requiring login or paid access are not supported.
- Lazy-loaded players may need a longer `--wait` value.
- Some sites block automated browsers.

---

## 📁 Folder Structure

```
VideoScraper/
├── VideoScraper.py     # Main script
├── requirements.txt    # Python dependencies
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── downloads/          # Output folder (created automatically)
```

---

## 🙋 FAQ

**Q: `yt-dlp` fails, what next?**
The script automatically falls back to Selenium/Chrome discovery. You can also force it with `--no-ytdlp`.

**Q: Download fails or is partial?**
Use `--retries` to increase retry attempts, and ensure a stable connection for large files.

**Q: Can I run this on a server?**
Yes — Chrome runs headless by default. Install Chrome and the dependencies, then run normally.

**Q: How do I pick a specific quality?**
Use the `-q` flag with a `yt-dlp` format selector, e.g. `-q "best[height<=1080]"`.

---

## 🚧 Limits

This script does **not** bypass DRM, paywalls, logins, or any access controls. Use it only where you have permission.

---

## ✅ TODO

- [ ] Improve scoring heuristics for more CDNs
- [ ] Add batch/multiple URL support
- [ ] Add proxy support
- [ ] Add config file for default options

---

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Please use responsibly and only on content you are legally permitted to download.
