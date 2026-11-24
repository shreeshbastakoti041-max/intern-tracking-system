from django.shortcuts import render


def csrf_failure(request, reason=""):
    """Shown when a form is submitted with an outdated security token.

    The usual cause is harmless: the page was opened before signing in, switching
    role or signing out (each issues a new token), then submitted from the Back
    button or another tab. The request is still rejected; we just explain it.
    """
    return render(request, "csrf_failure.html", status=403)
