from django.urls import path

from . import views

app_name = "workorders"

urlpatterns = [
    path("options/", views.work_order_options, name="options"),
    path("new/", views.work_order_create, name="create"),
    path("", views.work_order_list, name="list"),
    path("<uuid:pk>/", views.work_order_detail, name="detail"),
]
