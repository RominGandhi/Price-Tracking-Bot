# Use Python as base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libgstreamer-gl1.0-0 \
    libgstreamer-plugins-bad1.0-0 \
    libavif15 \
    libenchant-2-2 \
    libsecret-1-0 \
    libmanette-0.2-0 \
    libgles2 \
    curl \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt 

# Install Playwright and its dependencies
RUN pip install playwright 
RUN playwright install --with-deps chromium

# Copy application files
COPY . .

# Command to run the bot
CMD ["python", "bot.py"]
