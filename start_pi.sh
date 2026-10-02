#!/bin/bash
echo "🚀 Starting CircuitPulse on Raspberry Pi 5..."

if [ ! -d "venv" ]; then
    echo "Creating Python Virtual Environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Checking dependencies..."
pip install ultralytics flask opencv-python-headless --quiet

export CAMERA_SOURCE="0"

PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=========================================================="
echo "🌍 AI BACKEND IS RUNNING!"
echo "💻 ON YOUR WINDOWS LAPTOP, OPEN CHROME/EDGE AND GO TO:"
echo "👉  http://$PI_IP:5000  👈"
echo "=========================================================="
echo ""

echo "🧠 Starting AI Inference..."
python backend/app.py
