from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("agents/<int:agent_id>/toggle/", views.toggle_agent_active, name="toggle_agent"),
    path("agents/<int:agent_id>/mode/", views.set_agent_mode, name="set_agent_mode"),
    path("api/nova/voice/", views.nova_voice_api, name="nova_voice_api"),
    path("api/nova/ws-info/", views.nova_ws_info, name="nova_ws_info"),
    path("missions/", views.missions_list, name="missions_list"),
    path("missions/<slug:slug>/", views.mission_detail, name="mission_detail"),
    path("missions/<slug:slug>/download/", views.mission_download, name="mission_download"),
]
