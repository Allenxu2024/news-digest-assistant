import os
import sys
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
import datetime
import time
import requests
from googlenewsdecoder import gnewsdecoder
from deep_translator import GoogleTranslator

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest.db")

# RSS Search Configuration (Dynamic URL compilation to support UTF-8 queries)
FEEDS_CONFIG = {
    "nexperia": [
        {
            "query": 'Nexperia OR "安世半导体"',
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
            "default_lang": "zh"
        },
        {
            "query": 'Nexperia',
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
            "default_lang": "en"
        },
        {
            "query": 'Nexperia',
            "hl": "nl",
            "gl": "NL",
            "ceid": "NL:nl",
            "default_lang": "nl"
        }
    ],
    "cloning": [
        {
            "query": '宠物克隆 OR 犬猫克隆 OR 动物克隆 OR 动物基因编辑',
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
            "default_lang": "zh"
        },
        {
            "query": '"pet cloning" OR "dog cloning" OR "cat cloning" OR "animal cloning" OR "animal gene editing"',
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
            "default_lang": "en"
        }
    ]
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Create raw_news table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title_orig TEXT,
        title_zh TEXT,
        original_url TEXT UNIQUE,
        source TEXT,
        publish_date TEXT,
        summary_orig TEXT,
        summary_zh TEXT,
        topic TEXT,
        lang TEXT,
        fetch_date TEXT,
        is_read INTEGER DEFAULT 0
    )
    """)
    # Create saved_briefings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saved_briefings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title_orig TEXT,
        title_zh TEXT,
        original_url TEXT UNIQUE,
        source TEXT,
        publish_date TEXT,
        summary_orig TEXT,
        summary_zh TEXT,
        topic TEXT,
        lang TEXT,
        saved_time TEXT,
        fetch_time TEXT
    )
    """)
    conn.commit()
    conn.close()

def clean_html(raw_html):
    """Remove HTML tags from raw string."""
    clean_r = re.compile('<.*?>')
    text = re.sub(clean_r, '', raw_html)
    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return text.strip()

def fetch_meta_description(url):
    """Fetch the target webpage and extract the meta description or a fallback summary."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        # Attempt to auto-detect encoding
        if res.encoding is None or res.encoding == 'ISO-8859-1':
            res.encoding = res.apparent_encoding
            
        html = res.text
        
        # Look for meta description
        meta_desc = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE)
        if not meta_desc:
            meta_desc = re.search(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
            
        if meta_desc:
            desc = clean_html(meta_desc.group(1))
            if desc:
                return desc
                
        # Fallback: grab first 200 characters of paragraphs
        paragraphs = re.findall(r'<p>(.*?)</p>', html)
        if paragraphs:
            text = " ".join([clean_html(p) for p in paragraphs[:3]])
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 10:
                return text[:250] + "..."
    except Exception as e:
        print(f"  [Warning] Failed to fetch summary for {url}: {e}")
        
    return ""

def translate_text(text, target_lang='zh-CN'):
    """Translate text to target language, with robust error fallback."""
    if not text or text.strip() == "":
        return ""
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        return translator.translate(text)
    except Exception as e:
        print(f"  [Warning] Translation failed: {e}")
        return text # Fallback to original text

def is_already_saved(url):
    """Check if URL exists in briefings or raw_news (meaning it's already processed)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM raw_news WHERE original_url = ?", (url,))
    exists_raw = cursor.fetchone()
    
    cursor.execute("SELECT 1 FROM saved_briefings WHERE original_url = ?", (url,))
    exists_saved = cursor.fetchone()
    
    conn.close()
    return (exists_raw is not None) or (exists_saved is not None)

def process_feed(topic, feed_config):
    query_encoded = urllib.parse.quote(feed_config["query"])
    url = f"https://news.google.com/rss/search?q={query_encoded}&hl={feed_config['hl']}&gl={feed_config['gl']}&ceid={feed_config['ceid']}"
    default_lang = feed_config["default_lang"]
    print(f"Fetching RSS feed for query: '{feed_config['query']}' (Topic: {topic})")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
    except Exception as e:
        print(f"Error fetching RSS from {url}: {e}")
        return
        
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"Error parsing RSS XML: {e}")
        return
        
    items = root.findall('.//item')
    print(f"Found {len(items)} items in RSS.")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    new_count = 0
    # Process top 12 items for each feed to ensure fresh results
    for item in items[:12]:
        title_orig = item.find('title').text
        gnews_link = item.find('link').text
        pub_date_raw = item.find('pubDate').text
        source_name = item.find('source').text if item.find('source') is not None else "Unknown"
        
        # Standardize source_name
        # Google News titles are usually "Title - Source" - let's extract the main title part
        # if source_name is in title_orig
        title_clean = title_orig
        if source_name and title_orig.endswith(f" - {source_name}"):
            title_clean = title_orig[:-len(f" - {source_name}")]
            
        # Decode the Google News redirection link
        print(f"Decoding: {title_clean[:40]}...")
        try:
            decoded = gnewsdecoder(gnews_link, interval=0.5)
            if decoded.get('status'):
                real_url = decoded['decoded_url']
            else:
                real_url = gnews_link
        except Exception as e:
            print(f"  Failed decoding: {e}")
            real_url = gnews_link
            
        # Check if already processed
        if is_already_saved(real_url):
            print(f"  Already processed: {real_url}")
            continue
            
        # Fetch original summary
        print(f"  Fetching summary from: {real_url[:50]}...")
        summary_orig = fetch_meta_description(real_url)
        if not summary_orig:
            summary_orig = "No summary description available."
            
        # Determine language (if Chinese, don't translate)
        # Use simple character check for Chinese
        is_chinese = any(u'\u4e00' <= char <= u'\u9fff' for char in title_clean)
        
        if is_chinese:
            title_zh = title_clean
            summary_zh = summary_orig
            lang = "zh"
        else:
            print("  Translating to Chinese...")
            title_zh = translate_text(title_clean)
            summary_zh = translate_text(summary_orig)
            lang = default_lang
            
        # Format dates
        fetch_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        try:
            cursor.execute("""
            INSERT INTO raw_news (title_orig, title_zh, original_url, source, publish_date, summary_orig, summary_zh, topic, lang, fetch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (title_clean, title_zh, real_url, source_name, pub_date_raw, summary_orig, summary_zh, topic, lang, fetch_date))
            conn.commit()
            new_count += 1
            print(f"  [Success] Saved to DB: {title_zh[:40]}")
        except sqlite3.IntegrityError:
            # Duplicate URL hit
            pass
        except Exception as e:
            print(f"  [Error] Failed to insert: {e}")
            
    conn.close()
    print(f"Completed feed. Added {new_count} new articles.")

def main():
    print(f"[{datetime.datetime.now()}] Starting News Digest Fetcher...")
    init_db()
    for topic, feeds_list in FEEDS_CONFIG.items():
        for feed_config in feeds_list:
            process_feed(topic, feed_config)
            # Add a small delay between feeds
            time.sleep(2)
    print(f"[{datetime.datetime.now()}] News Digest Fetcher Finished.")

if __name__ == "__main__":
    main()
