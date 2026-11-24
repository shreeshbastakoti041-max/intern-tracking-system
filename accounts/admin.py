from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .invites import send_invite
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "is_active", "last_login"]
    list_filter = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "role", "is_active")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "description": "Leave the password blank and use the “Send invite email” "
                "action so the person sets their own password.",
                "fields": ("email", "first_name", "last_name", "role"),
            },
        ),
    )
    readonly_fields = ["last_login", "date_joined"]
    actions = ["send_invites"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.password:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            # Plain ModelForm for creation: no password fields.
            kwargs["form"] = admin.ModelAdmin.form
        return super().get_form(request, obj, **kwargs)

    @admin.action(description="Send invite / set-password email")
    def send_invites(self, request, queryset):
        count = 0
        for user in queryset.filter(is_active=True):
            send_invite(request, user)
            count += 1
        self.message_user(request, f"Sent {count} invite email(s).", messages.SUCCESS)
