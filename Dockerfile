FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY app.py ./
RUN pip install ".[ui]"

EXPOSE 8501

# Pass your keys at runtime, e.g.  docker run --env-file .env -p 8501:8501 placement-prep
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
