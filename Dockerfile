FROM python:3.11-slim

WORKDIR /app
COPY campusclaw ./campusclaw
COPY main.py ./main.py

RUN mkdir -p /app/data

EXPOSE 8000
CMD ["python", "main.py"]
