FROM python:3.11

WORKDIR /app

# Copy requirements first
COPY backend/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy full backend code
COPY backend .

# Start app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]