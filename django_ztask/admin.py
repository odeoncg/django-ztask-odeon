from django.contrib import admin
from django_ztask.models import *

class TaskAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'function_name', 'retry_count', 'created')
    search_fields = ('function_name',)
    list_filter = ('created',)

admin.site.register(Task, TaskAdmin)
