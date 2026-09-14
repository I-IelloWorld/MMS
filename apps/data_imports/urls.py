from django.urls import path

from . import views

app_name = "data-imports"

urlpatterns = [
    path("", views.import_list, name="list"),
    path("equipment/", views.equipment_import, name="equipment"),
    path("equipment/template.xlsx", views.equipment_import_template, name="equipment-template"),
    path("<uuid:pk>/", views.import_detail, name="detail"),
]
