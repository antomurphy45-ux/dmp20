FROM python:3.12-slim
WORKDIR /app
COPY app.py app.js app.css index.html requirements.txt ./
COPY dub84_programme.json ./dub84_programme.json
# Root-level seed is deliberately tracked so a GitHub/Render upload cannot
# accidentally omit the SQLite baseline from the Docker build context.
COPY render_seed.db ./render_seed.db
RUN mkdir -p static /var/data/uploads \
    && cp app.js app.css index.html static/
ENV CONSTRUCTION_CONTROL_DB=/var/data/construction_control.db
ENV CONSTRUCTION_CONTROL_UPLOADS=/var/data/uploads
ENV PORT=10000
EXPOSE 10000
CMD ["python", "app.py"]
