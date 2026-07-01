from django.contrib import admin

try:
    from unfold.admin import ModelAdmin as BaseModelAdmin
except Exception:                       # graceful fallback if Unfold is absent
    from django.contrib.admin import ModelAdmin as BaseModelAdmin

from .models import Category


@admin.register(Category)
class CategoryAdmin(BaseModelAdmin):
    prepopulated_fields = {'slug': ('category_name',)}
    list_display = ('category_name', 'slug', 'is_public')
    list_editable = ('is_public',)
    list_filter = ('is_public',)
    search_fields = ('category_name', 'slug')
    # `cat_image` is not referenced anywhere on the storefront or in code, so it's hidden from
    # the form to keep it clean (the column stays in the DB — no migration, no data loss).
    fieldsets = (
        (None, {'fields': ('category_name', 'slug', 'description', 'is_public')}),
    )
