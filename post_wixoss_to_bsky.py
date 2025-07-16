import os
import requests
from bs4 import BeautifulSoup
from atproto import Client
from datetime import datetime, timedelta, timezone
import time

# 環境変数
bsky_handle = os.environ["BSKY_HANDLE"]
bsky_app_password = os.environ["BSKY_APP_PASSWORD"]

# Nitter設定
nitter_base = "https://nitter.poast.org"
target_user = "wixoss_TCG"
nitter_url = f"{nitter_base}/{target_user}"

# 現在時刻（JST）
now = datetime.now(timezone.utc) + timedelta(hours=9)
window_start = now - timedelta(hours=24)

# ツイート取得
res = requests.get(nitter_url, timeout=10)
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
    # 日時取得（例: <span class="tweet-date"> <a href="...">2024年7月15日 12:34</a> ）
    date_tag = tweet.select_one(".tweet-date a")
    if date_tag is None:
        continue
    date_str = date_tag.text.strip()
    # 日付パース（例: '2024年7月15日 12:34'）
    try:
        tweet_time = datetime.strptime(date_str, "%Y年%m月%d日 %H:%M")
        tweet_time = tweet_time.replace(tzinfo=timezone(timedelta(hours=9)))
    except Exception:
        continue
    # 24時間以内か判定
    if not (window_start <= tweet_time <= now):
        continue

    tweet_text_tag = tweet.select_one(".tweet-content")
    tweet_link_tag = tweet.select_one("a.tweet-link")
    if tweet_text_tag is None or tweet_link_tag is None or not tweet_link_tag.has_attr('href'):
        continue

    tweet_text = tweet_text_tag.text.strip()
    tweet_link = tweet_link_tag['href']
    full_url = f"https://twitter.com{tweet_link}"

    # 画像取得（最大4枚まで）
    images = []
    image_alts = []
    for img_tag in tweet.select(".attachment.image img")[:4]:
        img_src = img_tag.get("src")
        if img_src and isinstance(img_src, str):
            if img_src.startswith("http://") or img_src.startswith("https://"):
                img_url = img_src
            else:
                img_url = nitter_base + img_src
            print(f"画像取得中: {img_url}")
            img_data = requests.get(img_url).content
            images.append(img_data)
            image_alts.append("")  # altテキストは空でOK

    # 投稿作成
    post_text = f"[wixoss公式] {tweet_text}\n{full_url}"

    # 投稿
    if images:
        client.send_images(text=post_text, images=images, image_alts=image_alts)
        print("画像付きで投稿しました！")
    else:
        client.send_post(text=post_text)
        print("テキストのみ投稿しました！")
    posted_any = True
    time.sleep(1)  # 連投防止

if not posted_any:
    print("24時間以内の新しいツイートはありませんでした。") 