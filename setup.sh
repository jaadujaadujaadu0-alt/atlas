#!/usr/bin/env bash
set -e

echo "Updating package list..."
sudo apt update

echo "Installing system packages..."
sudo apt install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    unzip \
    ca-certificates \
    fonts-liberation \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    xvfb

echo "Upgrading pip..."
python3 -m pip install --upgrade pip

echo "Installing Python dependencies..."
pip3 install \
    playwright \
    requests \
    faker

echo "Installing Chromium..."
python3 -m playwright install chromium

echo "Installing Playwright dependencies..."
python3 -m playwright install-deps chromium

echo "Creating folders..."
mkdir -p screenshots
mkdir -p responses
mkdir -p html_dump

echo "Setup complete."
