import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cineflux.settings')

app = Celery('cineflux')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Built-in debug task for verifying Celery is working."""
    print(f'Request: {self.request!r}')
