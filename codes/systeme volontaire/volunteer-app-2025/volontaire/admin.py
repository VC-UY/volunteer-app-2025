from django.contrib import admin
from django.utils.html import format_html
from .models import TaskProgress, MachineInfo, EtatMachine, PreferenceModel

# Déjà enregistré automatiquement par Django
# @admin.register(Task)
# class TaskAdmin(admin.ModelAdmin):
#     pass

@admin.register(TaskProgress)
class TaskProgressAdmin(admin.ModelAdmin):
    list_display = ('task', 'progress_type', 'percentage', 'timestamp', 'message_preview')
    list_filter = ('progress_type', 'timestamp')
    search_fields = ('task__name', 'task__task_id', 'message')
    readonly_fields = ('timestamp',)
    
    def message_preview(self, obj):
        if obj.message and len(obj.message) > 50:
            return f"{obj.message[:50]}..."
        return obj.message
    message_preview.short_description = 'Message'

admin.site.register(MachineInfo)
admin.site.register(EtatMachine)
admin.site.register(PreferenceModel)


