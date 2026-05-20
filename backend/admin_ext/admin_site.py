"""Extend default admin site with custom URLs."""
from django.contrib import admin

from admin_ext import views as ext_views


class KBAdminSite(admin.AdminSite):
    site_header = "KnowledgeBase Admin"
    site_title = "KnowledgeBase"

    def get_urls(self):
        return ext_views.get_urls() + super().get_urls()


# Swap the default site; config/urls.py uses admin.site, so we patch it.
def patch_admin_site():
    """Call from AppConfig.ready() to replace the default admin site."""
    from django.contrib import admin as _admin

    if not isinstance(_admin.site, KBAdminSite):
        new_site = KBAdminSite()
        # Copy over all registered models from the default site
        new_site._registry = _admin.site._registry
        _admin.site = new_site
        _admin.sites.site = new_site
