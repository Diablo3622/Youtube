import json
import sqlite3
import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

# API keys
YOUTUBE_API_KEY = 'AIzaSyBas_wVJb7z1Erud-iQ3WiA_747s9NclSU'
GEMINI_API_KEY = 'AIzaSyDT8wOUCw6-OYJe-n7BbyJJVGxrEUfijac'  # Thay bằng API key của bạn
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# Thiết lập Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Kiểm tra danh sách mô hình có sẵn
def list_available_models():
    try:
        models = genai.list_models()
        available_models = []
        print("Danh sách mô hình có sẵn:")
        for model in models:
            print(f"- {model.name} (Supported methods: {model.supported_generation_methods})")
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name)
        return available_models
    except Exception as e:
        print(f"Lỗi khi liệt kê mô hình: {e}")
        return []

# Chọn mô hình hợp lệ
available_models = list_available_models()
preferred_models = [
    'models/gemini-2.0-flash-lite',  # Mô hình ưu tiên theo yêu cầu
    'models/gemini-1.5-pro-latest',
    'models/gemini-1.5-pro-001',
    'models/gemini-1.5-pro-002',
    'models/gemini-1.5-flash-latest'
]

MODEL_NAME = None
for model_name in preferred_models:
    if model_name in available_models:
        MODEL_NAME = model_name
        break

if not MODEL_NAME and available_models:
    MODEL_NAME = available_models[0]

if MODEL_NAME:
    print(f"Sử dụng mô hình: {MODEL_NAME}")
    model = genai.GenerativeModel(MODEL_NAME)
else:
    print("Không tìm thấy mô hình hỗ trợ generateContent. Thoát.")
    exit(1)

def get_channel_id(channel_url):
    """Lấy channelId từ URL kênh"""
    try:
        if '/channel/' in channel_url:
            channel_id = channel_url.split('/channel/')[1].split('?')[0]
        elif '/@' in channel_url:
            handle = channel_url.split('/@')[1].split('?')[0]
            request = youtube.search().list(
                part='snippet',
                q=handle,
                type='channel',
                maxResults=1
            )
            response = request.execute()
            channel_id = response['items'][0]['id']['channelId']
        return channel_id
    except HttpError as e:
        print(f"Lỗi khi lấy channel ID: {e}")
        return None

def get_uploads_playlist_id(channel_id):
    """Lấy playlistId của playlist uploads"""
    try:
        request = youtube.channels().list(
            part='contentDetails',
            id=channel_id
        )
        response = request.execute()
        return response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except HttpError as e:
        print(f"Lỗi khi lấy playlist uploads: {e}")
        return None

def get_videos(channel_id, published_after=None, published_before=None):
    """Crawl danh sách video từ playlist uploads"""
    videos = []
    next_page_token = None
    page_count = 0
    playlist_id = get_uploads_playlist_id(channel_id)
    if not playlist_id:
        print("Không thể lấy playlist ID. Thoát.")
        return videos

    try:
        while True:
            print(f"Đang xử lý trang {page_count + 1} với token: {next_page_token}")
            request = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            page_count += 1

            print(f"Thông tin trang: {response['pageInfo']}")
            if not response.get('items'):
                print("Không có video trong phản hồi. Dừng.")
                break

            for item in response['items']:
                video_id = item['snippet']['resourceId']['videoId']
                videos.append({
                    'videoId': video_id,
                    'title': item['snippet']['title'],
                    'publishedAt': item['snippet']['publishedAt'],
                    'description': item['snippet']['description']
                })

            print(f"Đã tìm thấy {len(videos)} video")
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                print("Không còn trang nào.")
                break

            with open(f'videos_page_{page_count}.json', 'w', encoding='utf-8') as f:
                json.dump(videos, f, ensure_ascii=False, indent=4)
    except HttpError as e:
        print(f"Lỗi khi crawl video: {e}")
        if e.resp.status == 403:
            print("Vượt quá quota. Lưu dữ liệu tạm thời.")
    return videos

def get_video_details(video_ids):
    """Lấy thông tin chi tiết của video"""
    video_details = []
    try:
        request = youtube.videos().list(
            part='contentDetails,statistics',
            id=','.join(video_ids)
        )
        response = request.execute()

        for item in response['items']:
            video_details.append({
                'videoId': item['id'],
                'duration': item['contentDetails']['duration'],
                'viewCount': item['statistics'].get('viewCount', 0),
                'likeCount': item['statistics'].get('likeCount', 0),
                'commentCount': item['statistics'].get('commentCount', 0)
            })
    except HttpError as e:
        delicatessen
        print(f"Lỗi khi lấy chi tiết video: {e}")
    return video_details

def get_captions(video_id):
    """Lấy phụ đề bằng youtube-transcript-api"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        available_languages = [transcript.language_code for transcript in transcript_list]
        print(f"Ngôn ngữ phụ đề có sẵn cho video {video_id}: {available_languages}")

        preferred_languages = ['vi', 'en', 'en-US']
        selected_transcript = None

        for transcript in transcript_list:
            if transcript.language_code in preferred_languages:
                selected_transcript = transcript
                break
        if not selected_transcript:
            for transcript in transcript_list:
                if transcript.is_generated and transcript.language_code in preferred_languages:
                    selected_transcript = transcript
                    break

        if selected_transcript:
            transcript_data = selected_transcript.fetch()
            return "\n".join([entry.text for entry in transcript_data])
        else:
            print(f"Không tìm thấy phụ đề phù hợp cho video {video_id}")
            return None

    except Exception as e:
        print(f"Lỗi khi lấy phụ đề cho video {video_id}: {str(e)}")
        return None

def summarize_captions(captions):
    """Tạo tóm tắt nội dung phụ đề bằng Gemini API"""
    if not captions:
        return "Không có phụ đề để tóm tắt."
    
    try:
        captions = captions[:10000]  # Giới hạn 10,000 ký tự để tránh lỗi token
        prompt = f"Tóm tắt nội dung của đoạn văn sau thành 3-5 câu bằng tiếng Việt:\n\n{captions}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Lỗi khi tóm tắt phụ đề: {e}")
        return "Không thể tóm tắt nội dung."

def main():
    channel_url = input("Nhập URL kênh YouTube: ")

    channel_id = get_channel_id(channel_url)
    if not channel_id:
        print("Không thể lấy channel ID. Thoát.")
        return

    try:
        request = youtube.channels().list(
            part='statistics',
            id=channel_id
        )
        response = request.execute()
        total_videos = response['items'][0]['statistics']['videoCount']
        print(f"Tổng số video trong kênh: {total_videos}")
    except HttpError as e:
        print(f"Lỗi khi lấy thông tin kênh: {e}")
        return

    print("Đang crawl video...")
    videos = get_videos(channel_id)
    if not videos:
        print("Không tìm thấy video. Thoát.")
        return
    print(f"Tổng số video đã crawl: {len(videos)}")

    video_ids = [video['videoId'] for video in videos]
    details = []
    for i in range(0, len(video_ids), 50):
        print(f"Đang lấy chi tiết cho video {i+1} đến {min(i+50, len(video_ids))}")
        details.extend(get_video_details(video_ids[i:i+50]))

    processed_videos = []
    for video, detail in zip(videos, details):
        duration = isodate.parse_duration(detail['duration']).total_seconds() if detail.get('duration') else 0
        captions = get_captions(video['videoId'])
        summary = summarize_captions(captions)

        processed_videos.append({
            'videoId': video['videoId'],
            'title': video['title'],
            'views': int(detail['viewCount']),
            'duration': duration,
            'publishedAt': video['publishedAt'],
            'captions': captions,
            'summary': summary
        })

    # Lưu dữ liệu vào file JSON
    with open('all_videos.json', 'w', encoding='utf-8') as f:
        json.dump(processed_videos, f, ensure_ascii=False, indent=4)

    # Lưu vào cơ sở dữ liệu SQLite
    conn = sqlite3.connect('youtube_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            videoId TEXT PRIMARY KEY,
            title TEXT,
            views INTEGER,
            duration REAL,
            publishedAt TEXT,
            captions TEXT,
            summary TEXT
        )
    ''')
    for video in processed_videos:
        cursor.execute('''
            INSERT OR REPLACE INTO videos (videoId, title, views, duration, publishedAt, captions, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            video['videoId'],
            video['title'],
            video['views'],
            video['duration'],
            video['publishedAt'],
            video['captions'],
            video['summary']
        ))
    conn.commit()
    conn.close()

    print(f"Đã xử lý {len(processed_videos)} video. Dữ liệu được lưu vào all_videos.json và youtube_data.db")

if __name__ == '__main__':
    main()