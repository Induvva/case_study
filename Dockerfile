FROM python:3.9-slim-buster
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV DATABASE_PATH=/data/railway.db
VOLUME ["/data"]
EXPOSE 5000
CMD ["python3", "app.py"]