# -------- Base Image --------
FROM python:3.12-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY music-librarian/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY music-librarian/*.py .
# Expose Flask port
EXPOSE 5000

# Start with gunicorn (recommended for production)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
