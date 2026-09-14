from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import NotificationRecipient


@login_required
def notification_list(request):
    recipients = NotificationRecipient.objects.filter(
        user=request.user,
        channel=NotificationRecipient.Channel.IN_APP,
    ).select_related("notification")
    if request.method == "POST":
        recipients.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notifications:list")
    return render(
        request,
        "notifications/notification_list.html",
        {"page": Paginator(recipients, 30).get_page(request.GET.get("page"))},
    )


@login_required
def mark_read(request, pk):
    if request.method == "POST":
        NotificationRecipient.objects.filter(pk=pk, user=request.user).update(read_at=timezone.now())
    return redirect("notifications:list")

# Create your views here.
