FROM python:3.11.9

WORKDIR /app

RUN apt update && apt install -y --no-install-recommends gcc libc-dev

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
ENV TOKEN=""
CMD [Subprocess.run("python3 cogLeveling.py","python3 cogLogging.py","python3 cogModeration.py","python3 cogMusic.py")]
