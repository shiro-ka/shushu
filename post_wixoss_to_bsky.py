import os
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
from atproto import Client
import cloudscraper  # Cloudflare回避用

# 環境変数
bsky_handle = os.environ["BSKY_HANDLE"]
bsky_app_password = os.environ["BSKY_APP_PASSWORD"]

# Nitter設定
nitter_base = "https://nitter.net"
target_user = "wixoss_TCG"
nitter_url = f"{nitter_base}/{target_user}"

# cloudscraper のインスタンスを作成
scraper = cloudscraper.CloudScraper()

# UA偽装用ヘッダー
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml",
}

# 現在時刻（JST）
now = datetime.now(timezone.utc) + timedelta(hours=9)
window_start = now - timedelta(hours=24)

# ツイート取得（cloudscraper でリクエスト｜ヘッダー偽装付き）
res = scraper.get(nitter_url, headers=headers, timeout=10)
soup = BeautifulSoup(res.text, "html.parser")
tweets = soup.select(".timeline-item")

if not tweets:
    print("ツイートが見つかりませんでした。HTMLをdumpします。")
    with open("nitter_debug.html", "w", encoding="utf-8") as f:
        f.write(res.text)
    exit()

# BlueSkyログイン
client = Client()
client.login(bsky_handle, bsky_app_password)

posted_any = False
for tweet in tweets:
    # 日時取得
    date_tag = tweet.select_one(".tweet-date a")
    if date_tag is None:
        continue
    date_str = date_tag.text.strip()
    try:
        tweet_time = datetime.strptime(date_str, "%Y年%m月%d日 %H:%M")
        tweet_time = tweet_time.replace(tzinfo=timezone(timedelta(hours=9)))
    except Exception:
        continue
    if not (window_start <= tweet_time <= now):
        continue

    # 本文とURL
    tweet_text = tweet.select_one(".tweet-content").text.strip()
    link = tweet.select_one("a.tweet-link")["href"]
    full_url = f"https://twitter.com{link}"

    # 画像取得
    images, alts = [], []
    for img_tag in tweet.select(".attachment.image img")[:4]:
        src = img_tag.get("src")
        if not src:
            continue
        img_url = src if src.startswith("http") else nitter_base + src
        print(f"画像取得中: {img_url}")
        img_data = scraper.get(img_url, headers=headers, timeout=10).content
        images.append(img_data)
        alts.append("")

    # 投稿テキスト
    post_text = f"[wixoss公式] {tweet_text}\n{full_url}"

    # BlueSkyに送信
    if images:
        client.send_images(text=post_text, images=images, image_alts=alts)
        print("画像付きで投稿しました！")
    else:
        client.send_post(text=post_text)
        print("テキストのみ投稿しました！")

    posted_any = True
    time.sleep(1)

if not posted_any:
    print("24時間以内の新しいツイートはありませんでした。")
