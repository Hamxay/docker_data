FROM python:3.12-slim
WORKDIR /app

# Install necessary dependencies
RUN apt-get update && apt-get install -y build-essential gcc

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Open port
EXPOSE 5000

# Use existing SSL certificates
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "180", "manage:app"]