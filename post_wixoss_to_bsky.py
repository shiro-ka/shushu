import os
import requests
from bs4 import BeautifulSoup
from atproto import Client

# 環境変数
bsky_handle = os.environ["BSKY_HANDLE"]
bsky_app_password = os.environ["BSKY_APP_PASSWORD"]

# Nitter設定
nitter_base = "https://nitter.net"
target_user = "wixoss_TCG"
nitter_url = f"{nitter_base}/{target_user}"

# 投稿記録ファイル
posted_url_path = "last_posted.txt"
last_posted_url = None

# 初回判定（ファイルがない or 空）
is_first_run = not os.path.exists(posted_url_path) or os.path.getsize(posted_url_path) == 0
if not is_first_run:
    with open(posted_url_path, "r") as f:
        last_posted_url = f.read().strip()

# ツイート取得
res = requests.get(nitter_url, timeout=10)
soup = BeautifulSoup(res.text, "html.parser")
tweet = soup.select_one(".timeline-item")

if not tweet:
    print("ツイートが見つかりませんでした。HTMLをdumpします。")
    with open("nitter_debug.html", "w", encoding="utf-8") as f:
        f.write(res.text)
    exit()

tweet_text_tag = tweet.select_one(".tweet-content")
tweet_link_tag = tweet.select_one("a.tweet-link")
if tweet_text_tag is None or tweet_link_tag is None or not tweet_link_tag.has_attr('href'):
    print("ツイート内容またはリンクが取得できませんでした。")
    exit()

tweet_text = tweet_text_tag.text.strip()
tweet_link = tweet_link_tag['href']
full_url = f"https://twitter.com{tweet_link}"

# BlueSkyログイン
client = Client()
client.login(bsky_handle, bsky_app_password)

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

# 新しいツイートがなかった場合も最新ツイートをbskyにポストする
if is_first_run or full_url == last_posted_url:
    print("新しいツイートはありませんが、最新ツイートをbskyにポストします。")
    if images:
        client.send_images(text=post_text, images=images, image_alts=image_alts)
        print("画像付きで投稿しました！")
    else:
        client.send_post(text=post_text)
        print("テキストのみ投稿しました！")
    with open(posted_url_path, "w") as f:
        f.write(full_url)
    exit()

# 新しいツイートがあれば通常通りポスト
if images:
    client.send_images(text=post_text, images=images, image_alts=image_alts)
    print("画像付きで投稿しました！")
else:
    client.send_post(text=post_text)
    print("テキストのみ投稿しました！")

# 投稿記録
with open(posted_url_path, "w") as f:
    f.write(full_url) 