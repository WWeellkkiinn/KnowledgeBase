from django.db import models
from django.utils.text import slugify


class Tenant(models.Model):
    """A workspace. Every business row carries `tenant_id` → this row."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name)[:64] or "tenant"
        super().save(*args, **kwargs)
