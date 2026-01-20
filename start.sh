#!/bin/bash

# Temperature Control Bot - Startup Script
cd "$(dirname "$0")"

echo "🌡️  Starting Temperature Control Bot..."

# Kill any existing processes
pkill -f "ngrok http 8080" 2>/dev/null
pkill -f "python app.py" 2>/dev/null
sleep 1

# Start ngrok in background
echo "📡 Starting ngrok..."
ngrok http 8080 > /tmp/ngrok.log 2>&1 &
sleep 3

# Get the ngrok URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"https://[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$NGROK_URL" ]; then
    echo "❌ Failed to get ngrok URL. Check if ngrok is authenticated."
    exit 1
fi

echo "✅ ngrok URL: $NGROK_URL"

# Update .env file with new ngrok URL
sed -i '' "s|^NGROK_URL=.*|NGROK_URL=$NGROK_URL|" .env
echo "✅ Updated .env with ngrok URL"

# Activate virtual environment and start bot
echo "🤖 Starting Slack bot..."
source venv/bin/activate
python app.py
