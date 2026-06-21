"""Wishlist / save-for-later. Guests use the session key; authenticated users
get a persistent DB row. On login the guest items are merged into the account."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             null=True, blank=True, related_name="wishlist_items")
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    product = models.ForeignKey("store.Product", on_delete=models.CASCADE,
                                related_name="wishlisted_by")
    # save-for-later items were moved out of the cart (still in the wishlist list)
    saved_for_later = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Wishlist item")
        verbose_name_plural = _("Wishlist items")
        constraints = [
            models.UniqueConstraint(fields=["user", "product"],
                                    condition=models.Q(user__isnull=False),
                                    name="uniq_wishlist_user_product"),
            models.UniqueConstraint(fields=["session_key", "product"],
                                    condition=models.Q(user__isnull=True),
                                    name="uniq_wishlist_session_product"),
        ]

    def __str__(self):
        who = self.user.email if self.user_id else f"guest:{self.session_key[:8]}"
        return f"{who} ♥ {self.product.product_name}"
