from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ChatMessage,
    ClaspType,
    ExtraGenerationPurchase,
    GalleryComment,
    GalleryCommentVote,
    GalleryLike,
    HatKnitStyle,
    HatModel,
    MasterInquiry,
    RecoveryRequest,
    StoneCatalogItem,
    TryOnGeneration,
    YarnBrand,
    YarnColor,
)


@admin.register(YarnBrand)
class YarnBrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(YarnColor)
class YarnColorAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "hex_value", "is_active", "sort_order")
    list_filter = ("brand", "is_active")
    search_fields = ("name", "slug", "brand__name", "hex_value")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HatModel)
class HatModelAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "preview_thumb", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description", "preview_asset_path")
    prepopulated_fields = {"slug": ("name",)}

    @staticmethod
    def preview_thumb(obj):
        if not obj.preview_asset_path:
            return "—"
        return obj.preview_asset_path


@admin.register(HatKnitStyle)
class HatKnitStyleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "texture_density", "texture_scale", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "description")


@admin.register(StoneCatalogItem)
class StoneCatalogItemAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "diameter_mm", "occupied_length_display", "material", "is_active", "sort_order")
    list_filter = ("is_active", "material", "shape")
    search_fields = ("name", "slug", "material", "description")
    prepopulated_fields = {"slug": ("name",)}

    @staticmethod
    def occupied_length_display(obj):
        return obj.occupied_length_mm


@admin.register(ClaspType)
class ClaspTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "visual_length_mm", "material", "is_active", "sort_order")
    list_filter = ("is_active", "material")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MasterInquiry)
class MasterInquiryAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "status", "created_at", "has_preview")
    list_filter = ("category", "status", "created_at")
    search_fields = ("user__email", "summary", "comment")
    autocomplete_fields = ("user",)
    readonly_fields = ("preview_image_tag",)

    @staticmethod
    def has_preview(obj):
        return "есть" if obj.preview_image else "—"

    @staticmethod
    def preview_image_tag(obj):
        if not obj.preview_image:
            return "Превью не прикреплено"
        return format_html(
            '<img src="{}" style="max-width: 280px; border-radius: 16px; border: 1px solid #e2e8f0;" />',
            obj.preview_image.url,
        )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "sender", "linked_generation", "created_at", "short_text")
    list_filter = ("sender", "created_at")
    search_fields = ("user__email", "text", "external_reference_url", "linked_generation__summary")
    autocomplete_fields = ("user", "linked_generation")

    @staticmethod
    def short_text(obj):
        return (obj.text or "")[:60]


@admin.register(RecoveryRequest)
class RecoveryRequestAdmin(admin.ModelAdmin):
    list_display = ("email", "user", "created_at", "short_details")
    list_filter = ("created_at",)
    search_fields = ("email", "details", "user__email")
    autocomplete_fields = ("user",)

    @staticmethod
    def short_details(obj):
        return obj.details[:60]


@admin.register(TryOnGeneration)
class TryOnGenerationAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "provider", "used_ai", "consumed_extra_credit", "created_at")
    list_filter = ("category", "provider", "used_ai", "consumed_extra_credit", "created_at")
    search_fields = ("user__email", "summary")
    autocomplete_fields = ("user",)

    def has_add_permission(self, request):
        return False


@admin.action(description="Одобрить выбранные покупки")
def mark_purchases_paid(modeladmin, request, queryset):
    for purchase in queryset.exclude(status=ExtraGenerationPurchase.STATUS_PAID):
        purchase.status = ExtraGenerationPurchase.STATUS_PAID
        purchase.approved_by = request.user if request.user.is_authenticated else None
        purchase.save()


@admin.action(description="Пометить выбранные покупки как ожидающие проверки")
def mark_purchases_review(modeladmin, request, queryset):
    for purchase in queryset.exclude(status=ExtraGenerationPurchase.STATUS_PAID):
        purchase.status = (
            ExtraGenerationPurchase.STATUS_REVIEW
            if purchase.receipt_image
            else ExtraGenerationPurchase.STATUS_PENDING
        )
        purchase.approved_by = None
        purchase.approved_at = None
        purchase.save()


@admin.register(ExtraGenerationPurchase)
class ExtraGenerationPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "quantity",
        "unit_price_rub",
        "total_price_rub",
        "status",
        "receipt_badge",
        "created_at",
        "approved_at",
    )
    list_filter = ("status", "created_at", "approved_at", "receipt_uploaded_at")
    search_fields = ("user__email", "payment_note", "admin_comment")
    actions = (mark_purchases_paid, mark_purchases_review)
    autocomplete_fields = ("user", "approved_by")
    readonly_fields = ("total_price_rub", "receipt_preview")

    @staticmethod
    def receipt_badge(obj):
        return "есть" if obj.receipt_image else "—"

    @staticmethod
    def receipt_preview(obj):
        if not obj.receipt_image:
            return "Чек не загружен"
        return format_html(
            '<img src="{}" style="max-width: 240px; border-radius: 12px; border: 1px solid #e2e8f0;" />',
            obj.receipt_image.url,
        )



@admin.register(GalleryLike)
class GalleryLikeAdmin(admin.ModelAdmin):
    list_display = ("user", "generation", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__email", "generation__summary")
    autocomplete_fields = ("user", "generation")


@admin.register(GalleryComment)
class GalleryCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "generation", "short_text", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__email", "text", "generation__summary")
    autocomplete_fields = ("user", "generation")

    @staticmethod
    def short_text(obj):
        return obj.text[:80]


@admin.register(GalleryCommentVote)
class GalleryCommentVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "comment", "value", "created_at")
    list_filter = ("value", "created_at")
    search_fields = ("user__email", "comment__text", "comment__generation__summary")
    autocomplete_fields = ("user", "comment")
