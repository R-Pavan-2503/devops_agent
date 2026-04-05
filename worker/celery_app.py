from celery import Celery

#  * Initialize our worker and connect  to the Redis 
celery_app = Celery(
    "devops_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# *  Define the job the worker needs to do
@celery_app.task  
def process_pull_request_task(payload_dict: dict):
    print(f"👷 Celery worker is now processing PR #{payload_dict.get('number')} in the background...")
    return "AI Processing Complete"