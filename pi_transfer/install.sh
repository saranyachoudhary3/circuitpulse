#!/bin/bash
set -e

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-opencv python3-venv

if [ ! -d "$HOME/circuitpulse_env" ]; then
    python3 -m venv "$HOME/circuitpulse_env"
fi

source "$HOME/circuitpulse_env/bin/activate"
pip install --upgrade pip
pip install ultralytics opencv-python-headless flask flask-cors
