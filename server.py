import os
import sys
import sqlite3
import datetime
import asyncio
import signal
import threading
import subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest.db")
BRIEFINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "briefings")

# Ensure briefings directory exists
os.makedirs(BRIEFINGS_DIR, exist_ok=True)

IS_FETCHING = False
IS_FETCHING_LOCK = threading.Lock()

def run_fetcher_subprocess():
    global IS_FETCHING
    with IS_FETCHING_LOCK:
        if IS_FETCHING:
            return
        IS_FETCHING = True
        
    try:
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python3")
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetcher.py")
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetcher.log")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{datetime.datetime.now()}] === Auto Background Fetch Start ===\n")
            subprocess.run([venv_python, script_path], stdout=log_file, stderr=log_file, check=True)
            log_file.write(f"[{datetime.datetime.now()}] === Auto Background Fetch End ===\n")
    except Exception as e:
        print(f"Error running auto background fetch: {e}")
    finally:
        with IS_FETCHING_LOCK:
            IS_FETCHING = False

app = FastAPI(title="News Digest Assistant API")

# Setup serving static files
# We will create templates/index.html and serve it.
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)

class SaveNewsRequest(BaseModel):
    ids: List[int]

class MarkReadRequest(BaseModel):
    ids: List[int]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def compile_markdown_briefing(date_str: str):
    """Compile all saved briefings for a specific date into a markdown file."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query all items saved today
    # saved_time is stored in format 'YYYY-MM-DD HH:MM:SS'
    cursor.execute("""
    SELECT * FROM saved_briefings 
    WHERE saved_time LIKE ?
    ORDER BY topic, saved_time DESC
    """, (f"{date_str}%",))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return
        
    md_content = f"# 每日新闻简报 - {date_str}\n\n"
    md_content += f"> 采集汇总时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Group by topic
    topics_map = {
        "nexperia": "🌐 安世半导体与半导体行业动态",
        "cloning": "🧬 宠物/动物克隆与基因编辑行业前沿"
    }
    
    grouped = {}
    for row in rows:
        topic = row["topic"]
        if topic not in grouped:
            grouped[topic] = []
        grouped[topic].append(row)
        
    for topic_id, topic_title in topics_map.items():
        if topic_id in grouped:
            md_content += f"## {topic_title}\n\n"
            for i, item in enumerate(grouped[topic_id]):
                lang_tag = f" [{item['lang'].upper()}]" if item['lang'] and item['lang'] != 'zh' else ""
                md_content += f"### {i+1}. {item['title_zh']}{lang_tag}\n"
                md_content += f"* **出处**：{item['source']}\n"
                md_content += f"* **发布时间**：{item['publish_date']}\n"
                md_content += f"* **原文链接**：[{item['original_url']}]({item['original_url']})\n"
                md_content += f"* **中文摘要**：{item['summary_zh']}\n"
                
                # If there's an original summary in another language, show it too
                if item['lang'] and item['lang'] != 'zh' and item['summary_orig'] and item['summary_orig'] != "No summary description available.":
                    md_content += f"* **原文摘要** (*{item['lang']}*): {item['summary_orig']}\n"
                
                md_content += "\n---\n\n"
                
    md_path = os.path.join(BRIEFINGS_DIR, f"{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Compiled markdown briefing to {md_path}")

# Endpoints
@app.get("/")
def get_dashboard():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        return JSONResponse(status_code=404, content={"message": "Dashboard HTML template not found. Please create templates/index.html."})

@app.get("/api/news")
def get_news(background_tasks: BackgroundTasks, topic: str = None, fetch_date: str = None):
    """Retrieve raw news items where is_read = 0 (unread). Triggers fetch if no news today."""
    global IS_FETCHING
    
    # Check if a fetch has run today
    if not fetch_date:
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM raw_news WHERE fetch_date = ?", (today_str,))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0 and not IS_FETCHING:
            background_tasks.add_task(run_fetcher_subprocess)
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM raw_news WHERE is_read = 0"
    params = []
    
    if topic:
        query += " AND topic = ?"
        params.append(topic)
        
    if fetch_date:
        query += " AND fetch_date = ?"
        params.append(fetch_date)
        
    query += " ORDER BY fetch_date DESC, id DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Check if there are no unread items, maybe fetch some read items from today to show something
    if not rows and not fetch_date:
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        query_today = "SELECT * FROM raw_news WHERE fetch_date = ? ORDER BY id DESC"
        cursor.execute(query_today, [today_str])
        rows = cursor.fetchall()
        
    conn.close()
    
    result = [dict(row) for row in rows]
    return {
        "is_fetching": IS_FETCHING,
        "items": result
    }

@app.post("/api/save")
def save_news(req: SaveNewsRequest):
    """Save selected raw news items to saved_briefings and mark them read."""
    if not req.ids:
        raise HTTPException(status_code=400, detail="No news IDs provided")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    saved_count = 0
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    for news_id in req.ids:
        # Fetch the original item
        cursor.execute("SELECT * FROM raw_news WHERE id = ?", (news_id,))
        row = cursor.fetchone()
        if row:
            try:
                # Insert into saved_briefings
                cursor.execute("""
                INSERT INTO saved_briefings (title_orig, title_zh, original_url, source, publish_date, summary_orig, summary_zh, topic, lang, saved_time, fetch_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["title_orig"], row["title_zh"], row["original_url"],
                    row["source"], row["publish_date"], row["summary_orig"],
                    row["summary_zh"], row["topic"], row["lang"],
                    now_str, row["fetch_date"]
                ))
                saved_count += 1
            except sqlite3.IntegrityError:
                # Already saved, just update save time or ignore
                cursor.execute("UPDATE saved_briefings SET saved_time = ? WHERE original_url = ?", (now_str, row["original_url"]))
                saved_count += 1
                
            # Mark as read in raw_news
            cursor.execute("UPDATE raw_news SET is_read = 1 WHERE id = ?", (news_id,))
            
    conn.commit()
    conn.close()
    
    # Re-compile the markdown file for today
    compile_markdown_briefing(today_date)
    
    return {"message": f"Successfully saved {saved_count} articles to briefing database and compiled markdown document."}

@app.post("/api/mark_read")
def mark_read(req: MarkReadRequest):
    """Mark specified articles as read."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for news_id in req.ids:
        cursor.execute("UPDATE raw_news SET is_read = 1 WHERE id = ?", (news_id,))
        
    conn.commit()
    conn.close()
    return {"message": f"Successfully marked {len(req.ids)} articles as read."}

@app.post("/api/mark_all_read")
def mark_all_read():
    """Mark all currently unread articles as read."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE raw_news SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    conn.close()
    return {"message": "All unread articles marked as read."}

def shutdown_server():
    print("Received shutdown request. Stopping FastAPI server process...")
    # Send SIGINT to self
    os.kill(os.getpid(), signal.SIGINT)

@app.post("/api/shutdown")
def shutdown(background_tasks: BackgroundTasks):
    """Gracefully shut down the server."""
    background_tasks.add_task(shutdown_server)
    return {"message": "Server is shutting down... You can safely close this browser window."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
