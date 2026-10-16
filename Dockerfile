FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY web ./web
RUN pip install --no-cache-dir -e ".[foundry]"
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn pitchside.api:app --host 0.0.0.0 --port ${PORT}"]
