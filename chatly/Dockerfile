FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data FORWARDED_ALLOW_IPS=*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
COPY run.py .
RUN useradd -m chatly && mkdir -p /data && chown chatly /data
USER chatly
VOLUME /data
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz')"
CMD ["python", "run.py"]
