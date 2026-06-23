from django.contrib import admin
from .models import Category

# Register your models here.

class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('category_name',)}
    list_display = ('category_name', 'slug', 'is_public')
    list_editable = ('is_public',)
    list_filter = ('is_public',)

admin.site.register(Category, CategoryAdmin)