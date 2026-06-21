"""Models for the contextual AI shopping assistant.

The knowledge base is curated in admin and is the ONLY non-catalog source the
assistant is allowed to use. Conversations/messages are logged (without raw IPs)
so admins can review and improve answers.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class KnowledgeEntry(models.Model):
    """A curated, multilingual Q/A snippet the assistant may ground answers on."""

    CATEGORY_CHOICES = [
        ("shipping", _("Shipping")),
        ("returns", _("Returns")),
        ("refunds", _("Refunds")),
        ("payments", _("Payments")),
        ("sizing", _("Sizing")),
        ("account", _("Account")),
        ("tracking", _("Tracking")),
        ("product", _("Product")),
        ("ondemand", _("Print on demand")),
        ("support", _("Support")),
        ("privacy", _("Privacy")),
        ("general", _("General")),
    ]

    key = models.SlugField(max_length=80, unique=True,
                           help_text=_("Stable identifier, e.g. 'returns-window'."))
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="general")

    question = models.CharField(max_length=255)
    question_it = models.CharField(max_length=255, blank=True, default="")
    question_fr = models.CharField(max_length=255, blank=True, default="")

    answer = models.TextField()
    answer_it = models.TextField(blank=True, default="")
    answer_fr = models.TextField(blank=True, default="")

    keywords = models.TextField(blank=True, default="",
                                help_text=_("Comma-separated retrieval keywords (all languages)."))
    priority = models.IntegerField(default=0, help_text=_("Higher shows first."))
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "category", "key"]
        verbose_name = _("Knowledge entry")
        verbose_name_plural = _("Knowledge base")

    def __str__(self):
        return f"[{self.category}] {self.key}"

    def question_for(self, lang):
        return {"it": self.question_it, "fr": self.question_fr}.get(lang) or self.question

    def answer_for(self, lang):
        return {"it": self.answer_it, "fr": self.answer_fr}.get(lang) or self.answer

    def search_blob(self):
        parts = [self.question, self.question_it, self.question_fr,
                 self.answer, self.answer_it, self.answer_fr, self.keywords, self.category]
        return " ".join(p for p in parts if p).lower()


class AssistantConversation(models.Model):
    session_key = models.CharField(max_length=64, db_index=True, blank=True, default="")
    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="assistant_conversations")
    language = models.CharField(max_length=5, blank=True, default="en")
    ip_hash = models.CharField(max_length=64, blank=True, default="",
                               help_text=_("Salted hash — never the raw IP."))
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Assistant conversation")
        verbose_name_plural = _("Assistant conversations")

    def __str__(self):
        who = self.account.email if self.account else f"guest:{self.session_key[:8]}"
        return f"{who} · {self.created_at:%Y-%m-%d %H:%M}"


class AssistantMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "user"), (ROLE_ASSISTANT, "assistant")]

    conversation = models.ForeignKey(AssistantConversation, on_delete=models.CASCADE,
                                     related_name="messages")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    content = models.TextField()
    provider = models.CharField(max_length=20, blank=True, default="",
                                help_text=_("openai | fallback | mock | guardrail"))
    grounded = models.BooleanField(default=True,
                                   help_text=_("False when the assistant declined for lack of context."))
    used_sources = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class AssistantFeedback(models.Model):
    message = models.ForeignKey(AssistantMessage, on_delete=models.CASCADE, related_name="feedback")
    helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Assistant feedback")
        verbose_name_plural = _("Assistant feedback")
