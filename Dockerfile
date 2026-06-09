# Use a lightweight, stable official Python footprint image base
FROM python:3.11-slim

# Set strict background environment execution variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Establish our secure app operations directory root within the container
WORKDIR /app

# Install operating dependencies (useful if any wheels need build compilation)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*

# Copy strictly your package requirements map first to optimize layer build caches
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire src folder into the active image root framework
COPY src/ ./src/

# Set Python's execution environment array to see your 'src' folder as a top-level module
ENV PYTHONPATH=/app/src

# Set working directory to src so main.py runs smoothly
WORKDIR /app/src

# Spin up our project engine
CMD ["python", "main.py"]
