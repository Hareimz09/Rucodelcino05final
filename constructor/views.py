from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.contrib.auth import authenticate, get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth import password_validation
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import URLValidator, validate_email
from django.db.models import Count, Prefetch, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps

from constructor.models import (
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
from constructor.services.ai_tryon import TryOnError, encode_png_data_url, parse_data_url, perform_tryon


HAT_YARN_SHOP_URLS = {
    'alize-lanagold': 'https://rkdl.ru/sitesearch/?search=ALIZE+Lanagold',
    'lanoso-alpacana': 'https://rkdl.ru/sitesearch/?search=Lanoso+Alpacana',
}


JEWELRY_KIND_OPTIONS = (
    {
        "code": "necklace",
        "name": "Колье",
        "description": "Классическая сборка на шею.",
        "photo_hint": "Для колье лучше фото с открытой шеей и плечами, без сильных перекрытий волосами.",
    },
    {
        "code": "bracelet",
        "name": "Браслет",
        "description": "Сборка для запястья и кисти.",
        "photo_hint": "Для браслета используйте фото с хорошо видимым запястьем или кистью.",
    },
    {
        "code": "earrings",
        "name": "Серьги",
        "description": "Парная сборка для ушей.",
        "photo_hint": "Для серёг лучше фото анфас или лёгкий полупрофиль с открытыми ушами.",
    },
)

JEWELRY_BASE_OPTIONS = (
    {
        "code": "jewelry_cable",
        "kind": "necklace",
        "name": "Ювелирный тросик",
        "stroke": "#8b8fa1",
        "line_width": 3.5,
        "description": "Держит форму, подходит для плотной сборки.",
        "render_style": "necklace",
    },
    {
        "code": "silk_thread",
        "kind": "necklace",
        "name": "Шёлковая нить",
        "stroke": "#b58c62",
        "line_width": 2.4,
        "description": "Более мягкая посадка и деликатная сборка.",
        "render_style": "necklace",
    },
    {
        "code": "fishing_line",
        "kind": "necklace",
        "name": "Прозрачная леска",
        "stroke": "#cbd5e1",
        "line_width": 2.0,
        "description": "Минимально заметная основа.",
        "render_style": "necklace",
    },
    {
        "code": "bracelet-elastic",
        "kind": "bracelet",
        "name": "Эластичная нить",
        "stroke": "#94a3b8",
        "line_width": 2.8,
        "description": "Удобная посадка без жёсткого замка.",
        "render_style": "bracelet",
    },
    {
        "code": "bracelet-cable",
        "kind": "bracelet",
        "name": "Тонкий тросик",
        "stroke": "#7c8595",
        "line_width": 3.0,
        "description": "Аккуратный браслет с чёткой формой.",
        "render_style": "bracelet",
    },
    {
        "code": "bracelet-cord",
        "kind": "bracelet",
        "name": "Шнур",
        "stroke": "#8b6b52",
        "line_width": 3.4,
        "description": "Более мягкая, ремешковая посадка.",
        "render_style": "bracelet",
    },
    {
        "code": "ear-hook",
        "kind": "earrings",
        "name": "Швенза-крючок",
        "stroke": "#8b949e",
        "line_width": 2.2,
        "description": "Лёгкая классическая посадка для серёг.",
        "render_style": "hook",
    },
    {
        "code": "ear-stud",
        "kind": "earrings",
        "name": "Пусета",
        "stroke": "#8b949e",
        "line_width": 2.0,
        "description": "Крепление-гвоздик с подвесом.",
        "render_style": "stud",
    },
    {
        "code": "ear-hoop",
        "kind": "earrings",
        "name": "Мини-кольцо",
        "stroke": "#8b949e",
        "line_width": 2.4,
        "description": "Небольшое кольцо с подвесной сборкой.",
        "render_style": "hoop",
    },
)

JEWELRY_LENGTH_OPTIONS = (
    {"kind": "necklace", "label": "38 см", "value_mm": 380},
    {"kind": "necklace", "label": "42 см", "value_mm": 420},
    {"kind": "necklace", "label": "45 см", "value_mm": 450},
    {"kind": "necklace", "label": "50 см", "value_mm": 500},
    {"kind": "bracelet", "label": "16 см", "value_mm": 160},
    {"kind": "bracelet", "label": "18 см", "value_mm": 180},
    {"kind": "bracelet", "label": "20 см", "value_mm": 200},
    {"kind": "bracelet", "label": "22 см", "value_mm": 220},
    {"kind": "earrings", "label": "4 см", "value_mm": 40},
    {"kind": "earrings", "label": "5.5 см", "value_mm": 55},
    {"kind": "earrings", "label": "7 см", "value_mm": 70},
)


def render_page(request: HttpRequest, template_name: str, context: dict[str, Any] | None = None) -> HttpResponse:
    """Render a template with an optional context dictionary."""

    return render(request, template_name, context)


def _static_asset_url(asset_path: str | None) -> str:
    asset_path = str(asset_path or "").strip()
    return static(asset_path) if asset_path else ""


def _prefer_raster_hat_preview(asset_path: str | None) -> str:
    asset_path = str(asset_path or "").strip()
    if not asset_path:
        return ""
    lower = asset_path.lower()
    if lower.endswith('.svg'):
        png_path = f"{asset_path[:-4]}.png"
        if finders.find(png_path):
            return png_path
    return asset_path


def _serialize_hat_catalog() -> dict[str, Any]:
    hat_models = [
        {
            "id": item.id,
            "name": item.name,
            "slug": item.slug,
            "description": item.description,
            "preview_asset_url": _static_asset_url(item.preview_asset_path),
            "render_preset": item.render_preset or {},
        }
        for item in HatModel.objects.filter(is_active=True, slug__in=["beanie", "pompom-beanie"]).order_by("sort_order", "name")
    ]
    knit_styles = [
        {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "description": item.description,
            "texture_density": item.texture_density,
            "texture_scale": float(item.texture_scale),
        }
        for item in HatKnitStyle.objects.filter(is_active=True).order_by("sort_order", "name")
    ]
    yarn_brands = [
        {
            "id": item.id,
            "name": item.name,
            "slug": item.slug,
            "description": item.description,
            "shop_url": HAT_YARN_SHOP_URLS.get(item.slug, ""),
        }
        for item in YarnBrand.objects.filter(is_active=True).order_by("sort_order", "name")
    ]
    yarn_colors = [
        {
            "id": item.id,
            "brand_id": item.brand_id,
            "brand_name": item.brand.name,
            "brand_slug": item.brand.slug,
            "name": item.name,
            "slug": item.slug,
            "hex_value": item.hex_value,
            "swatch_asset_url": _static_asset_url(item.swatch_asset_path),
            "full_label": item.full_label,
        }
        for item in YarnColor.objects.select_related("brand").filter(is_active=True, brand__is_active=True).order_by(
            "brand__sort_order",
            "sort_order",
            "name",
        )
    ]
    return {
        "models": hat_models,
        "knit_styles": knit_styles,
        "yarn_brands": yarn_brands,
        "yarn_colors": yarn_colors,
    }


def _serialize_jewelry_catalog() -> dict[str, Any]:
    stones = [
        {
            "id": item.id,
            "name": item.name,
            "slug": item.slug,
            "preview_asset_url": _static_asset_url(item.preview_asset_path),
            "diameter_mm": float(item.diameter_mm),
            "occupied_length_mm": float(item.occupied_length_mm),
            "color_hex": item.color_hex,
            "material": item.material,
            "shape": item.shape,
            "description": item.description,
            "metadata": item.metadata or {},
        }
        for item in StoneCatalogItem.objects.filter(is_active=True).order_by("sort_order", "name")
    ]
    clasps = [
        {
            "id": item.id,
            "name": item.name,
            "slug": item.slug,
            "preview_asset_url": _static_asset_url(item.preview_asset_path),
            "visual_length_mm": float(item.visual_length_mm),
            "material": item.material,
            "description": item.description,
        }
        for item in ClaspType.objects.filter(is_active=True).order_by("sort_order", "name")
    ]
    return {
        "kinds": list(JEWELRY_KIND_OPTIONS),
        "bases": list(JEWELRY_BASE_OPTIONS),
        "lengths": list(JEWELRY_LENGTH_OPTIONS),
        "stones": stones,
        "clasps": clasps,
    }


def _comment_prefetch_queryset():
    return GalleryComment.objects.select_related("user", "parent", "parent__user").order_by("created_at")


def _safe_redirect_url(request: HttpRequest, candidate: str | None, fallback: str) -> str:
    candidate = str(candidate or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


def _get_public_gallery_queryset():
    return (
        TryOnGeneration.objects.filter(is_public_gallery=True)
        .select_related("user")
        .prefetch_related(Prefetch("gallery_comments", queryset=_comment_prefetch_queryset()))
        .annotate(
            likes_count=Count("gallery_likes", distinct=True),
            comments_count=Count("gallery_comments", distinct=True),
        )
        .order_by("-created_at")
    )


def _build_generation_title(category: str, sequence_number: int | None = None) -> str:
    base_label = "Шапка" if category == TryOnGeneration.CATEGORY_HAT else "Украшение"
    safe_number = max(int(sequence_number or 1), 1)
    return f"{base_label} #{safe_number}"


def _build_generation_sequence_map(items: list[TryOnGeneration]) -> dict[int, int]:
    if not items:
        return {}

    relevant_pairs = {(item.user_id, item.category) for item in items}
    user_ids = {item.user_id for item in items}
    categories = {item.category for item in items}
    counters: dict[tuple[int, str], int] = defaultdict(int)
    sequence_map: dict[int, int] = {}

    queryset = (
        TryOnGeneration.objects.filter(user_id__in=user_ids, category__in=categories)
        .only("id", "user_id", "category", "created_at")
        .order_by("user_id", "category", "created_at", "id")
    )

    for generation in queryset:
        pair = (generation.user_id, generation.category)
        if pair not in relevant_pairs:
            continue
        counters[pair] += 1
        sequence_map[generation.id] = counters[pair]

    return sequence_map


def _get_generation_sequence_number(generation: TryOnGeneration) -> int:
    if not generation.pk:
        return 1

    return max(
        TryOnGeneration.objects.filter(user_id=generation.user_id, category=generation.category)
        .filter(
            Q(created_at__lt=generation.created_at)
            | Q(created_at=generation.created_at, id__lte=generation.id)
        )
        .count(),
        1,
    )


def _build_display_title_for_generation(generation: TryOnGeneration, sequence_map: dict[int, int] | None = None) -> str:
    sequence_number = None
    if sequence_map is not None:
        sequence_number = sequence_map.get(generation.id)
    if sequence_number is None and generation.pk:
        sequence_number = _get_generation_sequence_number(generation)
    return _build_generation_title(generation.category, sequence_number)


def _is_ajax_request(request: HttpRequest) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _parse_bool_post_value(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_comment_widget_context(request: HttpRequest) -> dict[str, Any]:
    next_base = str(request.POST.get("next_base") or request.path).strip() or request.path
    anchor_prefix = str(request.POST.get("anchor_prefix") or "gallery-work").strip() or "gallery-work"
    return {
        "next_base": next_base,
        "anchor_prefix": anchor_prefix,
        "show_likes_meta": _parse_bool_post_value(request.POST.get("show_likes_meta")),
    }


def _get_decorated_public_work(work_id: int, user) -> TryOnGeneration | None:
    decorated_items = _decorate_gallery_items(_get_public_gallery_queryset().filter(id=work_id), user)
    return decorated_items[0] if decorated_items else None


def _render_gallery_like_html(request: HttpRequest, work: TryOnGeneration) -> str:
    return render_to_string(
        "constructor/includes/gallery_like_button.html",
        {"work": work},
        request=request,
    )


def _render_work_comments_payload(request: HttpRequest, work_id: int) -> dict[str, Any] | None:
    work = _get_decorated_public_work(work_id, request.user)
    if work is None:
        return None

    context = _get_comment_widget_context(request)
    comments_html = render_to_string(
        "constructor/includes/work_comments.html",
        {
            "work": work,
            **context,
        },
        request=request,
    )
    return {
        "work": work,
        "comments_html": comments_html,
        "context": context,
    }


def _decorate_gallery_items(items, user):
    item_list = list(items)
    if not item_list:
        return item_list

    sequence_map = _build_generation_sequence_map(item_list)
    generation_ids = [item.id for item in item_list]
    liked_ids: set[int] = set()
    if getattr(user, "is_authenticated", False):
        liked_ids = set(
            GalleryLike.objects.filter(user=user, generation_id__in=generation_ids).values_list("generation_id", flat=True)
        )

    comment_ids: list[int] = []
    for item in item_list:
        comment_ids.extend(comment.id for comment in item.gallery_comments.all())

    user_comment_votes: dict[int, int] = {}
    vote_count_map: dict[int, dict[int, int]] = defaultdict(lambda: {1: 0, -1: 0})
    if comment_ids:
        for row in GalleryCommentVote.objects.filter(comment_id__in=comment_ids).values("comment_id", "value").annotate(total=Count("id")):
            vote_count_map[row["comment_id"]][row["value"]] = row["total"]
        if getattr(user, "is_authenticated", False):
            user_comment_votes = {
                vote.comment_id: vote.value
                for vote in GalleryCommentVote.objects.filter(user=user, comment_id__in=comment_ids)
            }

    for item in item_list:
        item.gallery_title_display = _build_display_title_for_generation(item, sequence_map)
        item.gallery_description_display = item.gallery_description or item.summary or ""
        item.is_liked_by_current_user = item.id in liked_ids

        comments = list(item.gallery_comments.all())
        comments_by_parent: dict[int | None, list[GalleryComment]] = defaultdict(list)
        for comment in comments:
            counts = vote_count_map.get(comment.id, {1: 0, -1: 0})
            comment.upvotes_count = counts.get(1, 0)
            comment.downvotes_count = counts.get(-1, 0)
            comment.current_user_vote = user_comment_votes.get(comment.id, 0)
            comments_by_parent[comment.parent_id].append(comment)

        top_level_comments: list[GalleryComment] = []
        for comment in comments:
            if comment.parent_id is None:
                comment.replies_list = comments_by_parent.get(comment.id, [])
                top_level_comments.append(comment)

        item.top_level_comments = top_level_comments
    return item_list
@ensure_csrf_cookie
def home(request: HttpRequest) -> HttpResponse:
    gallery_preview = _decorate_gallery_items(_get_public_gallery_queryset()[:3], request.user)
    return render_page(
        request,
        "constructor/mainpages/home.html",
        {
            "gallery_preview": gallery_preview,
            "gallery_preview_count": len(gallery_preview),
        },
    )


@ensure_csrf_cookie
def hats_constructor(request: HttpRequest) -> HttpResponse:
    hat_catalog = _serialize_hat_catalog()
    context = {
        "hat_catalog": hat_catalog,
        **_build_tryon_page_context(request),
    }
    return render_page(request, "constructor/mainpages/hats.html", context)


@ensure_csrf_cookie
def jewelry_constructor(request: HttpRequest) -> HttpResponse:
    jewelry_catalog = _serialize_jewelry_catalog()
    copied_work_data = request.session.pop("copied_jewelry_work", None)
    context = {
        "jewelry_catalog": jewelry_catalog,
        "copied_jewelry_work": copied_work_data,
        **_build_tryon_page_context(request),
    }
    return render_page(request, "constructor/mainpages/jewelry.html", context)


def contact(request: HttpRequest) -> HttpResponse:
    return render_page(request, "constructor/secondarypages/contact.html")


def registration(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account")

    next_url = _safe_redirect_url(request, request.GET.get("next") or request.POST.get("next"), reverse("account"))
    errors: list[str] = []
    form_data = {
        "name": request.POST.get("name", "").strip(),
        "email": request.POST.get("email", "").strip().lower(),
        "agree": request.POST.get("agree") == "on",
    }

    if request.method == "POST":
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")
        agree = form_data["agree"]

        if not form_data["name"]:
            errors.append("Введите имя.")

        try:
            validate_email(form_data["email"])
        except ValidationError:
            errors.append("Введите корректный email.")

        if get_user_model().objects.filter(email__iexact=form_data["email"]).exists():
            errors.append("Пользователь с таким email уже зарегистрирован.")

        if password1 != password2:
            errors.append("Пароли должны совпадать.")

        try:
            password_validation.validate_password(password1)
        except ValidationError as validation_error:
            errors.extend(validation_error.messages)

        if not agree:
            errors.append("Необходимо согласиться с условиями.")

        if not errors:
            user = get_user_model().objects.create_user(
                username=form_data["email"],
                email=form_data["email"],
                first_name=form_data["name"],
            )
            user.set_password(password1)
            user.save()
            auth_login(request, user)
            _configure_session_persistence(request, persist=True)
            return redirect(next_url)

    return render_page(
        request,
        "constructor/secondarypages/registration.html",
        {"errors": errors, "form_data": form_data, "next": next_url},
    )


def login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account")

    next_url = _safe_redirect_url(request, request.GET.get("next") or request.POST.get("next"), reverse("account"))
    errors: list[str] = []
    form_data = {
        "email": request.POST.get("email", "").strip().lower(),
        "remember": request.POST.get("remember") == "on",
    }

    if request.method == "POST":
        password = request.POST.get("password", "")

        if not form_data["email"] or not password:
            errors.append("Введите email и пароль.")
        else:
            user = authenticate(request, username=form_data["email"], password=password)
            if user is None:
                errors.append("Неверный email или пароль.")
            else:
                auth_login(request, user)
                _configure_session_persistence(request, persist=form_data["remember"])
                return redirect(next_url)

    return render_page(
        request,
        "constructor/secondarypages/login.html",
        {"errors": errors, "form_data": form_data, "next": next_url},
    )


def forgot_password(request: HttpRequest) -> HttpResponse:
    errors: list[str] = []
    success = False

    form_data = {
        "email": request.POST.get("email", "").strip().lower(),
        "name": request.POST.get("name", "").strip(),
        "details": request.POST.get("details", "").strip(),
    }

    if request.method == "POST":
        try:
            validate_email(form_data["email"])
        except ValidationError:
            errors.append("Введите корректный email, который вы указывали при регистрации.")

        user = (
            get_user_model()
            .objects.filter(email__iexact=form_data["email"])
            .first()
            if not errors
            else None
        )

        if user is None and not errors:
            errors.append("Пользователь с таким email не найден.")

        if not form_data["details"]:
            errors.append("Опишите ситуацию, чтобы администратор мог помочь.")

        if not errors and user:
            RecoveryRequest.objects.create(
                user=user,
                name=form_data["name"],
                email=form_data["email"],
                details=form_data["details"],
            )
            success = True
            form_data["details"] = ""

    return render_page(
        request,
        "constructor/secondarypages/forgot_password.html",
        {
            "errors": errors,
            "form_data": form_data,
            "success": success,
            "MASTER_EMAIL": settings.MASTER_EMAIL,
        },
    )


def about05(request: HttpRequest) -> HttpResponse:
    return render_page(request, "constructor/secondarypages/about05.html")


def aboutstore(request: HttpRequest) -> HttpResponse:
    return render_page(request, "constructor/secondarypages/aboutstore.html")


def _get_user_initials(full_name: str, email: str) -> str:
    if full_name:
        parts = full_name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        return full_name[:2].upper()

    prefix = email.split("@", maxsplit=1)[0]
    return prefix[:2].upper() if prefix else "?"


def _is_master_user(user: Any) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and user.email
        and user.email.lower() == settings.MASTER_EMAIL.lower()
    )


def _month_range(now=None):
    now = now or timezone.localtime()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _get_monthly_limit() -> int:
    return max(int(getattr(settings, "TRYON_MONTHLY_LIMIT", 7)), 0)


def _get_extra_generation_price_rub() -> int:
    return max(int(getattr(settings, "TRYON_EXTRA_GENERATION_PRICE_RUB", 25)), 1)


def _get_generation_count_for_user(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0
    start, end = _month_range()
    return TryOnGeneration.objects.filter(user=user, created_at__gte=start, created_at__lt=end).count()


def _get_paid_extra_generations(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0
    paid_total = ExtraGenerationPurchase.objects.filter(
        user=user,
        status=ExtraGenerationPurchase.STATUS_PAID,
    ).aggregate(total=Sum("quantity"))["total"]
    return int(paid_total or 0)


def _get_used_extra_generations(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0
    return TryOnGeneration.objects.filter(user=user, consumed_extra_credit=True).count()


def _get_available_extra_generations(user) -> int:
    return max(_get_paid_extra_generations(user) - _get_used_extra_generations(user), 0)


def _get_tryon_quota(user) -> dict[str, int]:
    monthly_limit = _get_monthly_limit()
    monthly_used = _get_generation_count_for_user(user) if getattr(user, "is_authenticated", False) else 0
    monthly_remaining = max(monthly_limit - monthly_used, 0)
    extra_available = _get_available_extra_generations(user) if getattr(user, "is_authenticated", False) else 0
    total_remaining = monthly_remaining + extra_available
    return {
        "monthly_limit": monthly_limit,
        "monthly_used": monthly_used,
        "monthly_remaining": monthly_remaining,
        "extra_available": extra_available,
        "total_remaining": total_remaining,
        "extra_price_rub": _get_extra_generation_price_rub(),
    }


def _generation_will_consume_extra_credit(user) -> bool:
    quota = _get_tryon_quota(user)
    return quota["monthly_used"] >= quota["monthly_limit"]


AI_IMAGE_COST_USD = Decimal("0.29")


def _openai_tryon_available() -> bool:
    return bool(getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY"))


def _build_tryon_error_payload(code: int | str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": message,
        "error_code": str(code),
        "support_message": f"Если проблема повторится, сообщите в поддержку код ошибки {code}.",
    }
    payload.update(extra)
    return payload


def _tryon_error_response(code: int | str, message: str, *, status: int, **extra: Any) -> JsonResponse:
    return JsonResponse(_build_tryon_error_payload(code, message, **extra), status=status)


def _status_for_tryon_error_code(code: int | str) -> int:
    code_text = str(code)
    if code_text.startswith("13"):
        return 502
    if code_text.startswith("10"):
        return 403 if code_text in {"1002", "1003"} else 401
    return 400


def _build_tryon_page_context(request: HttpRequest) -> dict[str, Any]:
    quota = _get_tryon_quota(request.user)
    is_master = _is_master_user(request.user)
    openai_enabled = _openai_tryon_available()
    can_generate = bool(getattr(request.user, "is_authenticated", False)) and not is_master and openai_enabled

    disabled_reason = ""
    if is_master:
        disabled_reason = "Для администратора AI-примерка отключена. В личном кабинете доступна статистика по пользователям."
    elif not getattr(request.user, "is_authenticated", False):
        disabled_reason = "AI-примерка доступна только зарегистрированным пользователям."
    elif not openai_enabled:
        disabled_reason = "AI-примерка временно недоступна: сервер OpenAI не настроен."

    return {
        "ai_tryon_enabled": openai_enabled,
        "tryon_requires_auth": True,
        "tryon_monthly_limit": quota["monthly_limit"],
        "tryon_monthly_remaining": quota["monthly_remaining"],
        "tryon_extra_remaining": quota["extra_available"],
        "tryon_remaining": quota["total_remaining"],
        "tryon_extra_price_rub": quota["extra_price_rub"],
        "tryon_login_url": f"{reverse('login')}?next={request.path}",
        "tryon_purchase_url": reverse("extra_generations"),
        "tryon_can_generate": can_generate,
        "tryon_disabled_reason": disabled_reason,
        "tryon_is_master_user": is_master,
    }


def _resolve_generation_reference(user, raw_generation_id: str | None) -> TryOnGeneration | None:
    generation_id = str(raw_generation_id or "").strip()
    if not generation_id:
        return None
    return TryOnGeneration.objects.filter(user=user, id=generation_id).first()


def _clean_reference_url(raw_url: str | None) -> str:
    url = str(raw_url or "").strip()
    if not url:
        return ""
    URLValidator()(url)
    return url


def _create_chat_message(
    *,
    target_user,
    sender: str,
    message_text: str,
    linked_generation: TryOnGeneration | None,
    external_reference_url: str,
) -> ChatMessage:
    final_text = message_text.strip()
    if not final_text and (linked_generation or external_reference_url):
        final_text = "Прикрепил(а) работу для обсуждения."

    return ChatMessage.objects.create(
        user=target_user,
        sender=sender,
        text=final_text,
        linked_generation=linked_generation,
        external_reference_url=external_reference_url,
    )


def _get_master_generation_queryset():
    return TryOnGeneration.objects.exclude(user__email__iexact=settings.MASTER_EMAIL).filter(used_ai=True)


def _build_master_stats() -> dict[str, Any]:
    now = timezone.localtime()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    year_start = day_start.replace(month=1, day=1)

    periods = (
        ("day", "За день", day_start),
        ("week", "За неделю", week_start),
        ("month", "За месяц", month_start),
        ("year", "За год", year_start),
    )

    queryset = _get_master_generation_queryset()
    stats_cards: list[dict[str, Any]] = []

    for key, label, period_start in periods:
        count = queryset.filter(created_at__gte=period_start).count()
        cost_usd = (AI_IMAGE_COST_USD * count).quantize(Decimal("0.01"))
        stats_cards.append(
            {
                "key": key,
                "label": label,
                "count": count,
                "cost_usd": f"{cost_usd:.2f}",
            }
        )

    User = get_user_model()
    return {
        "cards": stats_cards,
        "clients_total": User.objects.exclude(email__iexact=settings.MASTER_EMAIL).count(),
        "pending_receipts_count": ExtraGenerationPurchase.objects.exclude(user__email__iexact=settings.MASTER_EMAIL).filter(
            status=ExtraGenerationPurchase.STATUS_REVIEW
        ).count(),
        "recent_receipts": ExtraGenerationPurchase.objects.exclude(user__email__iexact=settings.MASTER_EMAIL).select_related(
            "user",
            "approved_by",
        )[:8],
        "master_inquiries_count": MasterInquiry.objects.exclude(user__email__iexact=settings.MASTER_EMAIL).filter(
            status=MasterInquiry.STATUS_NEW
        ).count(),
    }


def _create_extra_purchase(*, user, quantity: int, payment_note: str, receipt_image) -> ExtraGenerationPurchase:
    purchase = ExtraGenerationPurchase(
        user=user,
        quantity=quantity,
        unit_price_rub=_get_extra_generation_price_rub(),
        payment_note=payment_note,
    )
    if receipt_image:
        purchase.receipt_image = receipt_image
        purchase.status = ExtraGenerationPurchase.STATUS_REVIEW
    purchase.save()
    return purchase


def _submit_purchase_receipt(*, purchase: ExtraGenerationPurchase, payment_note: str, receipt_image) -> ExtraGenerationPurchase:
    if payment_note:
        purchase.payment_note = payment_note
    if receipt_image:
        purchase.receipt_image = receipt_image
        purchase.status = ExtraGenerationPurchase.STATUS_REVIEW
    purchase.save()
    return purchase


def _set_purchase_status(*, purchase: ExtraGenerationPurchase, status: str, approved_by=None, admin_comment: str = "") -> ExtraGenerationPurchase:
    purchase.status = status
    purchase.admin_comment = admin_comment.strip()
    purchase.approved_by = approved_by if status == ExtraGenerationPurchase.STATUS_PAID else None
    purchase.approved_at = timezone.now() if status == ExtraGenerationPurchase.STATUS_PAID else None
    purchase.save()
    return purchase


def _parse_purchase_quantity(raw_value: str | None) -> int:
    try:
        quantity = int(str(raw_value or "1").strip())
    except (TypeError, ValueError):
        raise ValidationError("Укажите корректное количество генераций.")

    if quantity < 1:
        raise ValidationError("Количество генераций должно быть больше нуля.")
    if quantity > 100:
        raise ValidationError("За один заказ можно оформить не более 100 генераций.")
    return quantity


def _build_purchase_page_context(user, *, form_data: dict[str, Any] | None = None) -> dict[str, Any]:
    quota = _get_tryon_quota(user)
    unit_price = quota["extra_price_rub"]
    if form_data:
        try:
            quantity_value = max(min(int(form_data.get("quantity") or 1), 100), 1)
        except (TypeError, ValueError):
            quantity_value = 1
        payment_note = str(form_data.get("payment_note") or "")
    else:
        quantity_value = 1
        payment_note = ""
    presets = [1, 3, 5, 10]
    purchases = ExtraGenerationPurchase.objects.filter(user=user).select_related("approved_by").order_by("-created_at")

    return {
        "extra_generation_price_rub": unit_price,
        "extra_generations_available": quota["extra_available"],
        "monthly_limit": quota["monthly_limit"],
        "monthly_remaining": quota["monthly_remaining"],
        "total_generations_remaining": quota["total_remaining"],
        "purchases": purchases,
        "purchase_presets": [
            {
                "quantity": preset,
                "total_price_rub": preset * unit_price,
            }
            for preset in presets
        ],
        "purchase_form": {
            "quantity": quantity_value,
            "payment_note": payment_note,
        },
        "purchase_total_price_rub": quantity_value * unit_price,
    }


@login_required(login_url="login")
def extra_generations(request: HttpRequest) -> HttpResponse:
    user = request.user
    if _is_master_user(user):
        return redirect("account")

    form_data = {
        "quantity": request.POST.get("quantity", request.GET.get("quantity", "1")).strip() or "1",
        "payment_note": request.POST.get("payment_note", "").strip(),
    }

    if request.method == "POST":
        form_type = request.POST.get("form")

        if form_type == "buy_extra_generation":
            try:
                quantity = _parse_purchase_quantity(form_data["quantity"])
            except ValidationError as validation_error:
                messages.error(request, validation_error.messages[0])
            else:
                receipt_image = request.FILES.get("receipt_image")
                purchase = _create_extra_purchase(
                    user=user,
                    quantity=quantity,
                    payment_note=form_data["payment_note"],
                    receipt_image=receipt_image,
                )
                if receipt_image:
                    messages.success(
                        request,
                        f"Заказ на {purchase.quantity} генерац{'ию' if purchase.quantity == 1 else 'ии' if 2 <= purchase.quantity <= 4 else 'ий'} создан. Чек отправлен на проверку. Сумма: {purchase.total_price_rub} ₽.",
                    )
                else:
                    messages.success(
                        request,
                        f"Заказ на {purchase.quantity} генерац{'ию' if purchase.quantity == 1 else 'ии' if 2 <= purchase.quantity <= 4 else 'ий'} создан. Сумма: {purchase.total_price_rub} ₽. После оплаты загрузите чек в карточку заказа.",
                    )
                return redirect("extra_generations")

        elif form_type == "upload_purchase_receipt":
            purchase_id = request.POST.get("purchase_id", "").strip()
            purchase = ExtraGenerationPurchase.objects.filter(
                user=user,
                id=purchase_id,
            ).exclude(status__in=[ExtraGenerationPurchase.STATUS_PAID, ExtraGenerationPurchase.STATUS_CANCELLED]).first()
            receipt_image = request.FILES.get("receipt_image")

            if purchase is None:
                messages.error(request, "Заказ для загрузки чека не найден.")
            elif not receipt_image:
                messages.error(request, "Прикрепите изображение чека.")
            else:
                _submit_purchase_receipt(
                    purchase=purchase,
                    payment_note=request.POST.get("payment_note", "").strip(),
                    receipt_image=receipt_image,
                )
                messages.success(request, "Чек отправлен администратору. После проверки кредиты появятся автоматически.")
                return redirect("extra_generations")

    return render_page(
        request,
        "constructor/secondarypages/extra_generations.html",
        _build_purchase_page_context(user, form_data=form_data),
    )


@login_required(login_url="login")
def account(request: HttpRequest) -> HttpResponse:
    user = request.user
    display_name = user.get_full_name() or user.first_name or user.email or "Ваш профиль"
    is_master = _is_master_user(user)

    works_queryset = (
        TryOnGeneration.objects.filter(user=user)
        .prefetch_related(Prefetch("gallery_comments", queryset=_comment_prefetch_queryset()))
        .annotate(
            likes_count=Count("gallery_likes", distinct=True),
            comments_count=Count("gallery_comments", distinct=True),
        )
        .order_by("-created_at")
    )
    public_works_count = works_queryset.filter(is_public_gallery=True).count()
    works = _decorate_gallery_items(works_queryset, request.user)
    chat_messages = ChatMessage.objects.filter(user=user).select_related("user", "linked_generation").order_by("created_at")
    purchases = ExtraGenerationPurchase.objects.filter(user=user).order_by("-created_at")[:3]
    inquiries = MasterInquiry.objects.filter(user=user).order_by("-created_at")[:5]

    message_error: str | None = None
    chat_form = {
        "message": "",
        "linked_generation_id": request.GET.get("work", "").strip(),
        "external_reference_url": "",
    }
    if request.method == "POST":
        form_type = request.POST.get("form")

        if form_type == "chat":
            chat_form = {
                "message": request.POST.get("message", "").strip(),
                "linked_generation_id": request.POST.get("linked_generation_id", "").strip(),
                "external_reference_url": request.POST.get("external_reference_url", "").strip(),
            }
            linked_generation = _resolve_generation_reference(user, chat_form["linked_generation_id"])
            if chat_form["linked_generation_id"] and linked_generation is None:
                message_error = "Прикреплённая работа не найдена в вашем профиле."
            else:
                try:
                    external_reference_url = _clean_reference_url(chat_form["external_reference_url"])
                except ValidationError:
                    message_error = "Ссылка на работу должна быть корректным URL."
                else:
                    if not chat_form["message"] and linked_generation is None and not external_reference_url:
                        message_error = "Введите сообщение или прикрепите работу/ссылку."
                    else:
                        _create_chat_message(
                            target_user=user,
                            sender=ChatMessage.SENDER_MASTER if is_master else ChatMessage.SENDER_USER,
                            message_text=chat_form["message"],
                            linked_generation=linked_generation,
                            external_reference_url=external_reference_url,
                        )
                        return redirect("account")

    quota = _get_tryon_quota(user)
    master_stats = _build_master_stats() if is_master else None

    return render_page(
        request,
        "constructor/secondarypages/account.html",
        {
            "user_display_name": display_name,
            "user_email": user.email,
            "user_initials": _get_user_initials(display_name, user.email or ""),
            "chat_messages": chat_messages,
            "chat_message_count": chat_messages.count(),
            "is_master_user": is_master,
            "message_error": message_error,
            "chat_form": chat_form,
            "works": works,
            "works_count": len(works),
            "public_works_count": public_works_count,
            "chat_reference_works": works[:20],
            "monthly_limit": quota["monthly_limit"],
            "monthly_used": quota["monthly_used"],
            "monthly_remaining": quota["monthly_remaining"],
            "extra_generations_available": quota["extra_available"],
            "total_generations_remaining": quota["total_remaining"],
            "extra_generation_price_rub": quota["extra_price_rub"],
            "purchases": purchases,
            "inquiries": inquiries,
            "master_stats": master_stats,
        },
    )


@require_POST
@login_required(login_url="login")
def update_work_title(request: HttpRequest, work_id: int) -> HttpResponse:
    _ = work_id
    messages.error(request, "Редактирование названия работы отключено.")
    next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("account"))
    return redirect(next_url)


@require_POST
@login_required(login_url="login")
def delete_work(request: HttpRequest, work_id: int) -> HttpResponse:
    work = TryOnGeneration.objects.filter(user=request.user, id=work_id).first()
    if work is None:
        messages.error(request, "Работа не найдена или уже удалена.")
        return redirect("account")

    for field_name in ("user_image", "accessory_image", "result_image"):
        file_field = getattr(work, field_name, None)
        if file_field:
            file_field.delete(save=False)

    work.delete()
    messages.success(request, "Работа удалена из профиля.")
    return redirect("account")


def gallery(request: HttpRequest) -> HttpResponse:
    gallery_items = _decorate_gallery_items(_get_public_gallery_queryset()[:24], request.user)
    return render_page(
        request,
        "constructor/secondarypages/gallery.html",
        {
            "gallery_items": gallery_items,
        },
    )


@require_POST
@login_required(login_url="login")
def toggle_gallery_visibility(request: HttpRequest, work_id: int) -> HttpResponse:
    work = TryOnGeneration.objects.filter(user=request.user, id=work_id).first()
    if work is None:
        messages.error(request, "Работа не найдена.")
        return redirect("account")

    if work.is_public_gallery:
        work.is_public_gallery = False
        work.save(update_fields=["is_public_gallery"])
        messages.success(request, "Работа убрана из общей галереи.")
    else:
        work.is_public_gallery = True
        gallery_description = request.POST.get("gallery_description", "").strip()[:1000]
        gallery_title = request.POST.get("gallery_title", "").strip()[:140]
        default_gallery_title = _build_display_title_for_generation(work)
        work.gallery_title = gallery_title or work.gallery_title or default_gallery_title
        work.gallery_description = gallery_description or (work.gallery_description or work.summary or "").strip()
        work.save(update_fields=["is_public_gallery", "gallery_title", "gallery_description"])
        messages.success(request, "Работа выложена в общую галерею.")

    next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("account"))
    return redirect(next_url)


@require_POST
@login_required(login_url="login")
def toggle_gallery_like(request: HttpRequest, work_id: int) -> HttpResponse:
    work = TryOnGeneration.objects.filter(id=work_id, is_public_gallery=True).first()
    if work is None:
        if _is_ajax_request(request):
            return JsonResponse({"ok": False, "error": "Работа для лайка не найдена."}, status=404)
        messages.error(request, "Работа для лайка не найдена.")
        return redirect("gallery")

    like = GalleryLike.objects.filter(user=request.user, generation=work).first()
    if like:
        like.delete()
    else:
        GalleryLike.objects.create(user=request.user, generation=work)

    if _is_ajax_request(request):
        decorated_work = _get_decorated_public_work(work.id, request.user)
        if decorated_work is None:
            return JsonResponse({"ok": False, "error": "Работа для лайка не найдена."}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "work_id": decorated_work.id,
                "liked": decorated_work.is_liked_by_current_user,
                "likes_count": decorated_work.likes_count,
                "like_html": _render_gallery_like_html(request, decorated_work),
            }
        )

    next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("gallery"))
    return redirect(next_url)
@require_POST
@login_required(login_url="login")
def add_gallery_comment(request: HttpRequest, work_id: int) -> HttpResponse:
    work = TryOnGeneration.objects.filter(id=work_id, is_public_gallery=True).first()
    if work is None:
        if _is_ajax_request(request):
            return JsonResponse({"ok": False, "error": "Работа для комментария не найдена."}, status=404)
        messages.error(request, "Работа для комментария не найдена.")
        return redirect("gallery")

    comment_text = request.POST.get("comment", "").strip()
    parent_comment = None
    parent_id = request.POST.get("parent_id", "").strip()
    if parent_id:
        parent_comment = GalleryComment.objects.filter(id=parent_id, generation=work).first()
        if parent_comment is None:
            if _is_ajax_request(request):
                return JsonResponse({"ok": False, "error": "Комментарий, на который вы отвечаете, не найден."}, status=404)
            messages.error(request, "Комментарий, на который вы отвечаете, не найден.")
            next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("gallery"))
            return redirect(next_url)

    if not comment_text:
        if _is_ajax_request(request):
            return JsonResponse({"ok": False, "error": "Комментарий не может быть пустым."}, status=400)
        messages.error(request, "Комментарий не может быть пустым.")
    else:
        created_comment = GalleryComment.objects.create(
            user=request.user,
            generation=work,
            parent=parent_comment,
            text=comment_text[:1000],
        )
        if _is_ajax_request(request):
            payload = _render_work_comments_payload(request, work.id)
            if payload is None:
                return JsonResponse({"ok": False, "error": "Работа для комментария не найдена."}, status=404)
            return JsonResponse(
                {
                    "ok": True,
                    "work_id": payload["work"].id,
                    "comment_id": created_comment.id,
                    "comments_count": payload["work"].comments_count,
                    "likes_count": payload["work"].likes_count,
                    "comments_html": payload["comments_html"],
                }
            )
        messages.success(request, "Комментарий добавлен.")

    next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("gallery"))
    return redirect(next_url)
@require_POST
@login_required(login_url="login")
def vote_gallery_comment(request: HttpRequest, comment_id: int) -> HttpResponse:
    comment = GalleryComment.objects.select_related("generation").filter(id=comment_id, generation__is_public_gallery=True).first()
    if comment is None:
        if _is_ajax_request(request):
            return JsonResponse({"ok": False, "error": "Комментарий не найден."}, status=404)
        messages.error(request, "Комментарий не найден.")
        return redirect("gallery")

    raw_value = request.POST.get("value", "").strip()
    if raw_value not in {"1", "-1"}:
        if _is_ajax_request(request):
            return JsonResponse({"ok": False, "error": "Некорректный голос."}, status=400)
        messages.error(request, "Некорректный голос.")
    else:
        value = int(raw_value)
        vote = GalleryCommentVote.objects.filter(user=request.user, comment=comment).first()
        if vote and vote.value == value:
            vote.delete()
        elif vote:
            vote.value = value
            vote.save(update_fields=["value"])
        else:
            GalleryCommentVote.objects.create(user=request.user, comment=comment, value=value)

    if _is_ajax_request(request):
        payload = _render_work_comments_payload(request, comment.generation_id)
        if payload is None:
            return JsonResponse({"ok": False, "error": "Комментарий не найден."}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "work_id": payload["work"].id,
                "comment_id": comment.id,
                "comments_count": payload["work"].comments_count,
                "likes_count": payload["work"].likes_count,
                "comments_html": payload["comments_html"],
            }
        )

    next_url = _safe_redirect_url(request, request.POST.get("next"), reverse("gallery"))
    return redirect(next_url)
def copy_gallery_work(request: HttpRequest, work_id: int) -> HttpResponse:
    work = TryOnGeneration.objects.filter(id=work_id, is_public_gallery=True, category=TryOnGeneration.CATEGORY_JEWELRY).first()
    if work is None:
        messages.error(request, "Эту работу нельзя скопировать в конструктор.")
        return redirect("gallery")

    request.session["copied_jewelry_work"] = {
        "id": work.id,
        "summary": work.summary,
        "gallery_title": work.gallery_title,
        "selections": work.selections or {},
    }
    messages.success(request, "Сборка перенесена в конструктор украшений.")
    return redirect(f"{reverse('jewelry_constructor')}?copied=1")


def privacy(request: HttpRequest) -> HttpResponse:
    return render_page(request, "constructor/secondarypages/privacy.html")


@ensure_csrf_cookie
@user_passes_test(_is_master_user, login_url="login")
def master_chat(request: HttpRequest) -> HttpResponse:
    User = get_user_model()
    clients = User.objects.exclude(email__iexact=settings.MASTER_EMAIL).order_by("first_name", "email")

    selected_user_id = request.POST.get("user_id") or request.GET.get("user_id")
    selected_user = clients.filter(id=selected_user_id).first() if selected_user_id else None
    if not selected_user:
        selected_user = clients.first()

    message_error: str | None = None
    purchase_notice_code = request.GET.get("purchase_notice", "").strip()
    purchase_notice_map = {
        "approved": "Чек подтверждён, дополнительный кредит начислен пользователю.",
        "cancelled": "Заказ отклонён.",
    }
    purchase_notice: str | None = purchase_notice_map.get(purchase_notice_code)
    chat_form = {
        "message": "",
        "linked_generation_id": "",
        "external_reference_url": "",
    }

    if request.method == "POST" and selected_user:
        form_type = request.POST.get("form", "chat")

        if form_type == "chat":
            chat_form = {
                "message": request.POST.get("message", "").strip(),
                "linked_generation_id": request.POST.get("linked_generation_id", "").strip(),
                "external_reference_url": request.POST.get("external_reference_url", "").strip(),
            }
            linked_generation = _resolve_generation_reference(selected_user, chat_form["linked_generation_id"])
            if chat_form["linked_generation_id"] and linked_generation is None:
                message_error = "Выбранная работа клиента не найдена."
            else:
                try:
                    external_reference_url = _clean_reference_url(chat_form["external_reference_url"])
                except ValidationError:
                    message_error = "Ссылка на работу должна быть корректным URL."
                else:
                    if not chat_form["message"] and linked_generation is None and not external_reference_url:
                        message_error = "Введите сообщение или прикрепите работу/ссылку."
                    else:
                        _create_chat_message(
                            target_user=selected_user,
                            sender=ChatMessage.SENDER_MASTER,
                            message_text=chat_form["message"],
                            linked_generation=linked_generation,
                            external_reference_url=external_reference_url,
                        )
                        redirect_url = f"{reverse('master_chat')}?user_id={selected_user.id}"
                        return redirect(redirect_url)

        elif form_type in {"approve_purchase", "cancel_purchase"}:
            purchase_id = request.POST.get("purchase_id", "").strip()
            admin_comment = request.POST.get("admin_comment", "").strip()
            purchase = ExtraGenerationPurchase.objects.filter(user=selected_user, id=purchase_id).first()
            if purchase is None:
                purchase_notice = "Заказ клиента не найден."
            else:
                new_status = (
                    ExtraGenerationPurchase.STATUS_PAID
                    if form_type == "approve_purchase"
                    else ExtraGenerationPurchase.STATUS_CANCELLED
                )
                _set_purchase_status(
                    purchase=purchase,
                    status=new_status,
                    approved_by=request.user if new_status == ExtraGenerationPurchase.STATUS_PAID else None,
                    admin_comment=admin_comment,
                )
                notice_code = "approved" if new_status == ExtraGenerationPurchase.STATUS_PAID else "cancelled"
                return redirect(f"{reverse('master_chat')}?user_id={selected_user.id}&purchase_notice={notice_code}#purchase-management")

    chat_messages = (
        ChatMessage.objects.filter(user=selected_user)
        .select_related("user", "linked_generation")
        .order_by("created_at")
        if selected_user
        else []
    )

    clients_data = [
        {
            "user": client,
            "last_message": ChatMessage.objects.filter(user=client).order_by("-created_at").first(),
            "pending_receipts": ExtraGenerationPurchase.objects.filter(
                user=client,
                status=ExtraGenerationPurchase.STATUS_REVIEW,
            ).count(),
        }
        for client in clients
    ]
    selected_user_works = (
        TryOnGeneration.objects.filter(user=selected_user).order_by("-created_at")[:20]
        if selected_user
        else []
    )
    selected_user_purchases = (
        ExtraGenerationPurchase.objects.filter(user=selected_user)
        .select_related("approved_by")
        .order_by("-created_at")
        if selected_user
        else []
    )
    selected_user_inquiries = (
        MasterInquiry.objects.filter(user=selected_user).order_by("-created_at")[:20]
        if selected_user
        else []
    )

    return render_page(
        request,
        "constructor/secondarypages/master_chat.html",
        {
            "clients": clients_data,
            "clients_count": clients.count(),
            "selected_user": selected_user,
            "selected_user_works": selected_user_works,
            "selected_user_purchases": selected_user_purchases,
            "selected_user_inquiries": selected_user_inquiries,
            "chat_messages": chat_messages,
            "message_error": message_error,
            "purchase_notice": purchase_notice,
            "chat_form": chat_form,
            "master_stats": _build_master_stats(),
        },
    )


@user_passes_test(_is_master_user, login_url="login")
def master_recovery_requests(request: HttpRequest) -> HttpResponse:
    recovery_requests = RecoveryRequest.objects.select_related("user").order_by("-created_at")

    return render_page(
        request,
        "constructor/secondarypages/master_recovery_requests.html",
        {
            "requests": recovery_requests,
            "requests_count": recovery_requests.count(),
        },
    )


def _build_master_request_text(category: str, summary: str, selections: dict[str, Any], comment: str) -> str:
    category_label = "шапке" if category == "hat" else "украшению"
    lines = [f"[Заявка из панели мастера по {category_label}]"]
    if summary:
        lines.append(summary)

    field_labels = {
        "hat_model": "Модель",
        "knit_style": "Вязка",
        "yarn_brand": "Фирма пряжи",
        "yarn_color": "Цвет",
        "target_length": "Длина",
        "base": "Основа",
        "clasp": "Застёжка",
        "used_length_mm": "Занято длины, мм",
    }
    for key, value in selections.items():
        if value in (None, "", [], {}):
            continue
        if key == "stones" and isinstance(value, list):
            stone_lines = []
            for stone in value:
                if not isinstance(stone, dict):
                    continue
                stone_name = stone.get("name") or stone.get("slug") or "Камень"
                diameter = stone.get("diameter_mm")
                stone_lines.append(f"{stone_name} ({diameter} мм)")
            if stone_lines:
                lines.append("Камни: " + ", ".join(stone_lines))
            continue
        label = field_labels.get(key, key.replace("_", " ").capitalize())
        lines.append(f"{label}: {value}")

    if comment:
        lines.append(f"Комментарий клиента: {comment}")

    return "\n".join(lines)


@require_POST
def master_request_api(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "ok": False,
                "error": "Панель мастера доступна только после входа в аккаунт.",
                "login_url": f"{reverse('login')}?next={request.META.get('HTTP_REFERER') or reverse('account')}",
            },
            status=401,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Тело запроса должно быть JSON."}, status=400)

    category = str(payload.get("category", "")).strip().lower()
    if category not in {MasterInquiry.CATEGORY_HAT, MasterInquiry.CATEGORY_JEWELRY}:
        return JsonResponse({"ok": False, "error": "Неизвестная категория заявки."}, status=400)

    summary = str(payload.get("summary", "")).strip()
    comment = str(payload.get("comment", "")).strip()
    selections = payload.get("selections") if isinstance(payload.get("selections"), dict) else {}
    preview_data_url = str(payload.get("preview_image", "")).strip()

    if not summary and not selections:
        return JsonResponse({"ok": False, "error": "Не переданы параметры заявки."}, status=400)

    inquiry = MasterInquiry(
        user=request.user,
        category=category,
        summary=summary,
        comment=comment,
        selections=selections,
    )

    if preview_data_url:
        try:
            preview_bytes = parse_data_url(preview_data_url)
        except TryOnError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        preview_content = _make_uploaded_image_content(preview_bytes, prefix=f"{category}-master-request")
        inquiry.preview_image.save(preview_content.name, preview_content, save=False)

    inquiry.save()
    _create_chat_message(
        target_user=request.user,
        sender=ChatMessage.SENDER_USER,
        message_text=_build_master_request_text(category, summary, selections, comment),
        linked_generation=None,
        external_reference_url="",
    )

    return JsonResponse(
        {
            "ok": True,
            "message": "Параметры отправлены мастеру. Ответ можно продолжить в личном кабинете.",
            "request": {
                "id": inquiry.id,
                "created_at": timezone.localtime(inquiry.created_at).strftime("%d.%m.%Y %H:%M"),
                "category": inquiry.category,
            },
            "account_url": reverse("account"),
        }
    )


@require_POST
def tryon_api(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _tryon_error_response(
            1001,
            "AI-примерка доступна только зарегистрированным пользователям.",
            status=401,
            login_url=f"{reverse('login')}?next={request.META.get('HTTP_REFERER') or reverse('account')}",
        )

    if _is_master_user(request.user):
        return _tryon_error_response(
            1002,
            "Для администратора AI-примерка отключена. Используйте панель статистики в кабинете.",
            status=403,
        )

    if not _openai_tryon_available():
        return _tryon_error_response(
            1301,
            "AI-примерка временно недоступна: сервер OpenAI не настроен.",
            status=503,
        )

    quota_before = _get_tryon_quota(request.user)
    if quota_before["total_remaining"] <= 0:
        return _tryon_error_response(
            1003,
            (
                "Ежемесячный лимит исчерпан и дополнительных оплаченных генераций пока нет. "
                f"Можно купить доп. генерации на отдельной странице: 1 шт. за {quota_before['extra_price_rub']} ₽."
            ),
            status=403,
            remaining_generations=0,
            purchase_url=reverse("extra_generations"),
            quota=quota_before,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _tryon_error_response(1101, "Тело запроса должно быть JSON.", status=400)

    category = str(payload.get("category", "")).strip().lower()
    summary = str(payload.get("summary", "")).strip()
    selections = payload.get("selections") if isinstance(payload.get("selections"), dict) else {}

    try:
        user_image_data_url = str(payload.get("user_image", ""))
        accessory_image_data_url = str(payload.get("accessory_image", ""))
        user_image_bytes = parse_data_url(user_image_data_url)
        accessory_image_bytes = parse_data_url(accessory_image_data_url)
        result = perform_tryon(
            category=category,
            user_image_bytes=user_image_bytes,
            accessory_image_bytes=accessory_image_bytes,
            summary=summary,
            selections=selections,
        )
    except TryOnError as exc:
        return _tryon_error_response(exc.code, str(exc), status=_status_for_tryon_error_code(exc.code))
    except Exception:
        return _tryon_error_response(1900, "Не удалось выполнить AI-примерку из-за внутренней ошибки сервера.", status=500)

    visible_warnings = [
        item for item in result.warnings
        if item != "Лицо не найдено автоматически, использована приблизительная посадка."
    ]

    generation = TryOnGeneration(
        user=request.user,
        category=category,
        summary=summary,
        selections=selections,
        provider=result.provider,
        used_ai=result.used_ai,
        warnings_text="\n".join(visible_warnings),
        consumed_extra_credit=_generation_will_consume_extra_credit(request.user),
    )
    user_content = _make_uploaded_image_content(user_image_bytes, prefix=f"{category}-user")
    accessory_content = _make_uploaded_image_content(accessory_image_bytes, prefix=f"{category}-accessory")
    result_content = _make_uploaded_image_content(result.image_bytes, prefix=f"{category}-result")
    generation.user_image.save(user_content.name, user_content, save=False)
    generation.accessory_image.save(accessory_content.name, accessory_content, save=False)
    generation.result_image.save(result_content.name, result_content, save=False)
    generation.save()

    quota_after = _get_tryon_quota(request.user)

    return JsonResponse(
        {
            "ok": True,
            "result_image": encode_png_data_url(result.image_bytes),
            "provider": result.provider,
            "used_ai": result.used_ai,
            "warnings": visible_warnings,
            "remaining_generations": quota_after["total_remaining"],
            "quota": quota_after,
            "generation": {
                "id": generation.id,
                "category": generation.category,
                "category_label": generation.category_label,
                "created_at": timezone.localtime(generation.created_at).strftime("%d.%m.%Y %H:%M"),
                "result_image_url": generation.result_image.url,
                "user_image_url": generation.user_image.url,
                "consumed_extra_credit": generation.consumed_extra_credit,
            },
        }
    )


def _make_uploaded_image_content(image_bytes: bytes, *, prefix: str) -> ContentFile:
    image = Image.open(BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image).convert("RGBA")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return ContentFile(buffer.getvalue(), name=f"{prefix}-{uuid4().hex}.png")


def logout(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        auth_logout(request)
        return redirect("home")

    return redirect("account")


def _configure_session_persistence(request: HttpRequest, persist: bool) -> None:
    default_age = getattr(settings, "SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)
    remember_age = getattr(settings, "REMEMBER_ME_AGE", 60 * 60 * 24 * 30)

    expiry = remember_age if persist else default_age
    request.session.set_expiry(expiry)
