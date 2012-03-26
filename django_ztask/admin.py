from django.contrib import admin
from django_ztask.models import *

class TaskAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'created', 'function_name', 'args', 'kwargs', 'retry_count', 'failed', 'last_exception', 'next_attempt')
    search_fields = ('function_name',)
    list_filter = ('created',)

admin.site.register(Task, TaskAdmin)
