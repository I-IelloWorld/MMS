from django.urls import path

from . import views

app_name = "assets"

urlpatterns = [
    path("", views.equipment_list, name="equipment-list"),
    path("new/", views.equipment_create, name="equipment-create"),
    path("options/components/", views.component_options, name="component-options"),
    path("<uuid:pk>/", views.equipment_detail, name="equipment-detail"),
]
