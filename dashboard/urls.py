from django.urls import path

from . import mission_widget_views, views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path(
        "mission/build/toggle/",
        mission_widget_views.dashboard_build_toggle,
        name="dashboard_build_toggle",
    ),
    path(
        "mission/pipeline/<int:pipeline_id>/next/",
        mission_widget_views.dashboard_pipeline_next,
        name="dashboard_pipeline_next",
    ),
    path(
        "mission/iot/<int:entry_id>/touch/",
        mission_widget_views.dashboard_iot_touch,
        name="dashboard_iot_touch",
    ),
    path("agents/<int:agent_id>/toggle/", views.toggle_agent_active, name="toggle_agent"),
    path("agents/<int:agent_id>/mode/", views.set_agent_mode, name="set_agent_mode"),
    path("api/nova/voice/", views.nova_voice_api, name="nova_voice_api"),
    path("api/nova/audio/<str:filename>", views.nova_audio_file, name="nova_audio_file"),
    path("api/nova/audio/device/<str:filename>", views.nova_audio_device, name="nova_audio_device"),
    path("api/nova/voice/internal/", views.nova_voice_gateway_api, name="nova_voice_gateway_api"),
    path("api/nova/device/bundle", views.nova_device_bundle, name="nova_device_bundle"),
    path("api/nova/ws-info/", views.nova_ws_info, name="nova_ws_info"),
    path("missions/", views.missions_list, name="missions_list"),
    path("missions/<slug:slug>/", views.mission_detail, name="mission_detail"),
    path("missions/<slug:slug>/download/", views.mission_download, name="mission_download"),
]
