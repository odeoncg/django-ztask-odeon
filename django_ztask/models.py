from django.db.models import *

import uuid
import datetime

class Task(Model):
    uuid = CharField(max_length=36, primary_key=True)
    function_name = CharField(max_length=255)
    args = TextField()
    kwargs = TextField()
    retry_count = IntegerField(default=0)
    last_exception = TextField(blank=True, null=True)
    next_attempt = FloatField(blank=True, null=True)
    created = DateTimeField(blank=True, null=True)
    failed = DateTimeField(blank=True, null=True)
    
    def save(self, *args, **kwargs):
        if not self.uuid:
            self.created = datetime.datetime.utcnow()
            self.uuid = uuid.uuid4()
        super(Task, self).save(*args, **kwargs)
    
    class Meta:
        db_table = 'django_ztask_task'
    
