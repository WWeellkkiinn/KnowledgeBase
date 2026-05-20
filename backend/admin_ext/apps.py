from django.apps import AppConfig


class AdminExtConfig(AppConfig):
    name = "admin_ext"
    verbose_name = "Admin Extensions"

    def ready(self):
        from admin_ext.admin_site import patch_admin_site
        patch_admin_site()
