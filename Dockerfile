FROM python:3.11.9

WORKDIR /app

RUN apt update && apt install -y --no-install-recommends gcc libc-dev

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
ENV TOKEN=""
CMD ["python", "moderation.py"]
