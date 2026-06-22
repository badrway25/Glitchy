from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from greatkart.pii import mask_email
from .models import Account


class AccountAdmin(UserAdmin):
    # Masked email in the list (data minimisation); full email still searchable + on detail.
    list_display = ('masked_email', 'first_name', 'last_name', 'username',
                    'last_login', 'date_joined', 'is_active')
    list_display_links = ('first_name', 'last_name')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    readonly_fields = ('last_login', 'date_joined')
    ordering = ('-date_joined',)

    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()

    @admin.display(description=_("Email"))
    def masked_email(self, obj):
        return mask_email(obj.email)


admin.site.register(Account, AccountAdmin)