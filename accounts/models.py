from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # None -> unusable password (invite flow sets it)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["role"] = User.Role.ADMIN
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Login is by email. Access is controlled by `role`, never by ad-hoc flags."""

    class Role(models.TextChoices):
        INTERN = "intern", "Intern"
        SUPERVISOR = "supervisor", "Supervisor"
        ADMIN = "admin", "Admin / Coordinator"

    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.INTERN)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name", "email"]

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        # Coordinators manage interns, lists and users through Django admin.
        is_admin = self.role == self.Role.ADMIN
        self.is_staff = is_admin
        self.is_superuser = is_admin
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_supervisor_role(self) -> bool:
        return self.role == self.Role.SUPERVISOR

    @property
    def can_view_all(self) -> bool:
        """Supervisors and admins can see every intern's records."""
        return self.role in (self.Role.SUPERVISOR, self.Role.ADMIN)
