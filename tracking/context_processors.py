from .models import TimeEntry


def navigation(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_admin_role:
        return {"nav_review_count": TimeEntry.objects.needing_review().count()}
    return {}
