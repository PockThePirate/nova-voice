from django.contrib import admin

from .models import Agent, NodeStatus, Mission, Event

admin.site.register(Agent)
admin.site.register(NodeStatus)
admin.site.register(Mission)
admin.site.register(Event)
