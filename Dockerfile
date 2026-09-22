FROM python:3.12-slim

WORKDIR /app

COPY app.py app.js app.css index.html requirements.txt ./
COPY dub84_programme.json ./dub84_programme.json
COPY render_seed.db ./render_seed.db

RUN mkdir -p static /data/uploads /data/backups \
    && cp app.js app.css index.html static/

ENV CONSTRUCTION_CONTROL_DB=/data/construction_control.db
ENV CONSTRUCTION_CONTROL_UPLOADS=/data/uploads
ENV CONSTRUCTION_CONTROL_BACKUPS=/data/backups
ENV PORT=10000

VOLUME ["/data"]

EXPOSE 10000

CMD ["python", "app.py"]
