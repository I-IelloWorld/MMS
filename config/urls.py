from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.utils.translation import gettext_lazy as _

from apps.workorders import views as work_order_views

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("apps.dashboard.urls")),
    path("equipment/", include("apps.assets.urls")),
    path("work-orders/", include("apps.workorders.urls")),
    path("imports/", include("apps.data_imports.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path(
        "internal/cron/work-orders/",
        work_order_views.generate_recurring_work_orders_cron,
        name="workorder-cron",
    ),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path('admin/', admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = _("MMS 系统管理")
admin.site.site_title = _("MMS 管理后台")
admin.site.index_title = _("主数据与业务配置")
