import os

bind = f"0.0.0.0:{os.getenv('PORT', '8001')}"
workers = int(os.getenv("WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("WORKER_TIMEOUT", "130"))
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
preload_app = False
