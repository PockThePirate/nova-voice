from django.contrib import admin

from .models import (
    Agent,
    NodeStatus,
    Mission,
    Event,
    IncomeProfile,
    PipelineItem,
    DailyBuildBlock,
    IoTLabEntry,
)

admin.site.register(Agent)
admin.site.register(NodeStatus)
admin.site.register(Mission)
admin.site.register(Event)
admin.site.register(IncomeProfile)
admin.site.register(PipelineItem)
admin.site.register(DailyBuildBlock)
admin.site.register(IoTLabEntry)
