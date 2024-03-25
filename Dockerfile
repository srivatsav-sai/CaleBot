FROM python:3.12.1-slim

ENV TOKEN=""
WORKDIR /app

RUN apt update && apt install -y --no-install-recommends gcc libc-dev

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

CMD ["python", "moderation.py"]
