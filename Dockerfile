FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && playwright install chromium --with-deps
COPY . .
CMD ["python", "monitor.py"]
