#!/bin/bash
# Launcher script for the News Digest Assistant.
# Starts the FastAPI server if not running, then opens the dashboard in the default browser.

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$DIR"

# Check if port 8000 is already in use
PORT_IN_USE=$(lsof -i :8000 | grep LISTEN)

if [ -n "$PORT_IN_USE" ]; then
    echo "Dashboard server is already running."
else
    echo "Starting backend server..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        # Start server in the background and detach
        nohup python3 server.py > server.log 2>&1 &
        SERVER_PID=$!
        disown $SERVER_PID
        
        # Give the server a moment to spin up
        echo "Waiting for server to initialize..."
        sleep 1.5
    else
        echo "[Error] Virtual environment not found. Please run the setup first."
        exit 1
    fi
fi

# Open browser
echo "Opening http://127.0.0.1:8000/ in your default browser..."
if command -v xdg-open > /dev/null; then
    xdg-open "http://127.0.0.1:8000/" > /dev/null 2>&1
elif command -v open > /dev/null; then
    open "http://127.0.0.1:8000/" > /dev/null 2>&1
else
    echo "Could not launch browser automatically. Please open http://127.0.0.1:8000/ manually in your browser."
fi
