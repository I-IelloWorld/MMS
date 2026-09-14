from django.utils.translation import gettext_lazy as _


US_TIMEZONE_CHOICES = (
    ("America/Los_Angeles", _("美西时间")),
    ("America/Chicago", _("美中时间")),
    ("America/New_York", _("美东时间")),
)

DEFAULT_TIMEZONE = "America/Chicago"
