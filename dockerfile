# Use Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements if you have them, else skip this
ADD requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files into the container
COPY . .

# Expose the application port if needed (e.g., 8000)
EXPOSE 8501

# Run the main Python script
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
