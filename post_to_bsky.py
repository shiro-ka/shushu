import os
import requests
from bs4 import BeautifulSoup
from atproto import Client

# 環境変数
bsky_handle = os.environ["BSKY_HANDLE"]
bsky_app_password = os.environ["BSKY_APP_PASSWORD"]

# Nitter設定
nitter_base = "https://nitter.poast.org"
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
    print("ツイートが見つかりませんでした。")
    exit()

tweet_text = tweet.select_one(".tweet-content").text.strip()
tweet_link = tweet.select_one("a.tweet-link")["href"]
full_url = f"https://twitter.com{tweet_link}"

# 初回なら記録して終了（投稿しない）
if is_first_run:
    print("初回起動：投稿は行わず記録だけ行います。")
    with open(posted_url_path, "w") as f:
        f.write(full_url)
    exit()

# 投稿済みならスキップ
if full_url == last_posted_url:
    print("新しいツイートはありません。")
    exit()

# BlueSkyログイン
client = Client()
client.login(bsky_handle, bsky_app_password)

# 画像取得（最大4枚まで）
images = []
for img_tag in tweet.select(".attachment.image img")[:4]:
    img_src = img_tag.get("src")
    if img_src:
        img_url = nitter_base + img_src
        print(f"画像取得中: {img_url}")
        img_data = requests.get(img_url).content
        uploaded = client.upload_blob(img_data, mime_type="image/jpeg")
        images.append(uploaded)

# 投稿作成
post_text = f"[wixoss公式] {tweet_text}\n{full_url}"

if images:
    embed = client.com.atproto.repo.upload_images(images)
    client.send_post(text=post_text, embed=embed)
    print("画像付きで投稿しました！")
else:
    client.send_post(text=post_text)
    print("テキストのみ投稿しました！")

# 投稿記録
with open(posted_url_path, "w") as f:
    f.write(full_url)

