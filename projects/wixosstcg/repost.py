import os
import json
import requests
from datetime import datetime, timezone
from atproto import Client

# プロジェクト名
PROJECT_NAME = 'wixosstcg'

# 環境変数から認証情報を取得
TWITTER_API_KEY = os.environ.get('TWITTER_API_KEY')
TWITTER_API_SECRET = os.environ.get('TWITTER_API_SECRET')
BLUESKY_HANDLE = os.environ.get('SHUSHU_BLUESKY_HANDLE')
BLUESKY_PASSWORD = os.environ.get('SHUSHU_BLUESKY_PASSWORD')

# プロジェクトごとのディレクトリとファイル
PROJECT_DIR = f'projects/{PROJECT_NAME}'
STATE_FILE = f'{PROJECT_DIR}/last_tweet_id.json'
CONFIG_FILE = f'{PROJECT_DIR}/config.json'

def load_config():
    """プロジェクト設定を読み込む"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_last_tweet_id():
    """前回処理した最後のツイートIDを読み込む"""
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_tweet_id'), data.get('initialized', False)
    except FileNotFoundError:
        return None, False

def save_last_tweet_id(tweet_id):
    """最後に処理したツイートIDを保存"""
    os.makedirs(PROJECT_DIR, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump({
            'last_tweet_id': tweet_id,
            'initialized': True,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }, f, indent=2)

def get_bearer_token():
    """API KeyとSecretからBearer Tokenを取得"""
    import base64
    
    # Basic認証用のクレデンシャルを作成
    credentials = f"{TWITTER_API_KEY}:{TWITTER_API_SECRET}"
    b64_credentials = base64.b64encode(credentials.encode()).decode()
    
    # Bearer Tokenを取得
    url = 'https://api.twitter.com/oauth2/token'
    headers = {
        'Authorization': f'Basic {b64_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
    }
    data = {'grant_type': 'client_credentials'}
    
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()['access_token']

def get_twitter_timeline(username, since_id=None, max_results=10):
    """XのタイムラインをAPI v2で取得"""
    # Bearer Tokenを取得
    bearer_token = get_bearer_token()
    
    # まずユーザーIDを取得
    user_url = f'https://api.twitter.com/2/users/by/username/{username}'
    headers = {'Authorization': f'Bearer {bearer_token}'}
    
    user_response = requests.get(user_url, headers=headers)
    user_response.raise_for_status()
    user_data = user_response.json()
    user_id = user_data['data']['id']
    
    # タイムラインを取得
    url = f'https://api.twitter.com/2/users/{user_id}/tweets'
    params = {
        'max_results': max_results,
        'tweet.fields': 'created_at,attachments,referenced_tweets',
        'expansions': 'attachments.media_keys',
        'media.fields': 'url,preview_image_url,type',
        'exclude': 'retweets'  # リツイートを除外
    }
    
    if since_id:
        params['since_id'] = since_id
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def extract_links(text):
    """テキストからURLを抽出してファセット情報を作成"""
    import re
    
    # URLパターン（http/https）
    url_pattern = r'https?://[^\s]+'
    links = []
    
    for match in re.finditer(url_pattern, text):
        url = match.group()
        start = match.start()
        end = match.end()
        
        # バイト位置を計算
        byte_start = len(text[:start].encode('utf-8'))
        byte_end = len(text[:end].encode('utf-8'))
        
        links.append({
            'index': {
                'byteStart': byte_start,
                'byteEnd': byte_end
            },
            'features': [{
                '$type': 'app.bsky.richtext.facet#link',
                'uri': url
            }]
        })
    
    return links

def clean_tweet_text(text):
    """ツイートテキストから不要なt.coリンクを削除"""
    import re
    
    # 末尾のt.coリンクを削除（画像URLなど）
    # 例: "本文 https://t.co/xxxxx" → "本文"
    text = re.sub(r'\s+https://t\.co/\w+\s*$', '', text)
    
    # 複数のt.coリンクが末尾にある場合も対応
    while re.search(r'\s+https://t\.co/\w+\s*$', text):
        text = re.sub(r'\s+https://t\.co/\w+\s*$', '', text)
    
    return text.strip()

def create_bluesky_post(client, tweet, config):
    """Blueskyに投稿を作成"""
    # 元ツイートのリンク
    tweet_link = f"https://twitter.com/{config['twitter_username']}/status/{tweet['id']}"
    
    # ヘッダー部分（元ツイートのリンク埋め込み）
    header_text = config['header_text']
    
    # 本文（t.coリンクをクリーンアップ）
    cleaned_text = clean_tweet_text(tweet['text'])
    full_text = f"{header_text}\n\n{cleaned_text}"
    
    # ヘッダーに元ツイートのリンクを埋め込み
    facets = [{
        'index': {
            'byteStart': 0,
            'byteEnd': len(header_text.encode('utf-8'))
        },
        'features': [{
            '$type': 'app.bsky.richtext.facet#link',
            'uri': tweet_link
        }]
    }]
    
    # 本文中のリンクを抽出して追加（t.co以外）
    body_links = extract_links(cleaned_text)
    for link in body_links:
        # t.coリンクは除外
        if 't.co/' not in link['features'][0]['uri']:
            # ヘッダー分のオフセットを加算
            header_offset = len(f"{header_text}\n\n".encode('utf-8'))
            link['index']['byteStart'] += header_offset
            link['index']['byteEnd'] += header_offset
            facets.append(link)
    
    # 画像の処理（Blueskyは最大4枚まで）- このツイート専用の画像のみ
    images = []
    if 'attachments' in tweet and 'media_keys' in tweet['attachments']:
        tweet_media_keys = tweet['attachments']['media_keys']
        
        if 'includes' in tweet and 'media' in tweet['includes']:
            photo_count = 0
            for media in tweet['includes']['media']:
                # このツイートの画像のみを処理
                if media.get('media_key') in tweet_media_keys and media['type'] == 'photo' and photo_count < 4:
                    try:
                        # 画像をダウンロード
                        img_response = requests.get(media['url'])
                        img_response.raise_for_status()
                        
                        # Blueskyにアップロード
                        upload = client.upload_blob(img_response.content)
                        images.append({
                            'alt': '',
                            'image': upload.blob
                        })
                        photo_count += 1
                    except Exception as e:
                        print(f"[{PROJECT_NAME}] 画像アップロードエラー: {e}")
                        continue
            
            # 5枚以上ある場合は警告
            total_photos = sum(1 for m in tweet['includes']['media'] 
                             if m.get('media_key') in tweet_media_keys and m['type'] == 'photo')
            if total_photos > 4:
                print(f"[{PROJECT_NAME}] 警告: {total_photos}枚の画像のうち、最初の4枚のみ投稿しました")
    
    # メイン投稿を作成
    embed = None
    if images:
        embed = {
            '$type': 'app.bsky.embed.images',
            'images': images
        }
    
    main_post = client.send_post(
        text=full_text,
        facets=facets,
        embed=embed
    )
    
    print(f"Posted: {cleaned_text[:50]}...")

def main():
    # 設定を読み込む
    config = load_config()
    
    # 最後に処理したツイートIDを読み込む
    last_tweet_id, initialized = load_last_tweet_id()
    
    # 初回実行の判定と投稿数制限
    if not initialized:
        print(f"[{PROJECT_NAME}] 初回実行です。最新の{config['initial_post_limit']}件のみを投稿します。")
        max_results = config['initial_post_limit']
    else:
        max_results = 100
    
    # Xからツイートを取得
    try:
        tweets_data = get_twitter_timeline(
            config['twitter_username'], 
            since_id=last_tweet_id, 
            max_results=max_results
        )
    except requests.exceptions.HTTPError as e:
        print(f"[{PROJECT_NAME}] Twitter API Error: {e}")
        return
    
    if 'data' not in tweets_data or not tweets_data['data']:
        print(f"[{PROJECT_NAME}] 新しいツイートはありません")
        return
    
    tweets = tweets_data['data']
    # 古い順に処理するため逆順にする
    tweets.reverse()
    
    # 画像情報を各ツイートに関連付ける
    includes = tweets_data.get('includes', {})
    for tweet in tweets:
        tweet['includes'] = includes
    
    print(f"[{PROJECT_NAME}] {len(tweets)}件の新しいツイートを処理します")
    
    # Blueskyにログイン
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_PASSWORD)
    
    # 各ツイートを投稿
    posted_count = 0
    for tweet in tweets:
        try:
            create_bluesky_post(client, tweet, config)
            posted_count += 1
        except Exception as e:
            print(f"[{PROJECT_NAME}] 投稿エラー: {e}")
            continue
    
    print(f"[{PROJECT_NAME}] {posted_count}件の投稿が完了しました")
    
    # 最新のツイートIDを保存
    if tweets:
        save_last_tweet_id(tweets[-1]['id'])
        print(f"[{PROJECT_NAME}] 最新のツイートID {tweets[-1]['id']} を保存しました")

if __name__ == '__main__':
    main()