"""PromptTemplateService tests: all templates build and carry the guardrails."""

import pytest

from app.models import AIContentType, AIPlatform
from app.services.prompt_templates import TEMPLATE_VERSIONS, prompt_template_service

ALL_TYPES = list(AIContentType)


@pytest.mark.parametrize("content_type", ALL_TYPES)
def test_template_name_mapping(content_type):
    name = prompt_template_service.template_name(content_type)
    assert name == TEMPLATE_VERSIONS[content_type]


@pytest.mark.parametrize(
    "expected",
    [
        "affiliate_caption_v1",
        "affiliate_hook_v1",
        "short_video_script_v1",
        "product_description_v1",
        "cta_v1",
    ],
)
def test_all_required_templates_exist(expected):
    assert expected in TEMPLATE_VERSIONS.values()


@pytest.mark.parametrize("content_type", ALL_TYPES)
def test_build_returns_system_and_user_prompt(content_type):
    built = prompt_template_service.build(
        content_type=content_type,
        platform=AIPlatform.tiktok,
        prompt="prompt pengguna",
        variations=3,
    )
    assert built.system_prompt
    assert built.user_prompt
    assert "prompt pengguna" in built.user_prompt
    assert "Jumlah variasi: 3" in built.user_prompt
    assert built.template == TEMPLATE_VERSIONS[content_type]


@pytest.mark.parametrize("content_type", ALL_TYPES)
def test_system_prompt_contains_honesty_rules(content_type):
    system = prompt_template_service.build(
        content_type=content_type,
        platform=AIPlatform.instagram,
        prompt="x",
        variations=1,
    ).system_prompt

    assert "Bahasa Indonesia" in system
    assert "robotik" in system
    assert "testimoni palsu" in system
    assert "klaim" in system
    assert "spesifikasi produk" in system
    assert "diskon" in system
    assert "menjamin hasil" in system
    assert "persuasif" in system
    assert "berbeda" in system


@pytest.mark.parametrize("platform", list(AIPlatform))
def test_platform_hint_is_included(platform):
    built = prompt_template_service.build(
        content_type=AIContentType.caption,
        platform=platform,
        prompt="x",
        variations=1,
    )
    assert f"Platform: {platform.value}" in built.user_prompt


def test_product_context_is_included_and_scoped():
    built = prompt_template_service.build(
        content_type=AIContentType.product_description,
        platform=AIPlatform.facebook,
        prompt="jelaskan produk",
        variations=2,
        product_name="Kopi Gayo",
        product_description="Kopi arabika single origin",
        affiliate_url="https://example.com/aff",
    )
    assert "Kopi Gayo" in built.user_prompt
    assert "Kopi arabika single origin" in built.user_prompt
    assert "https://example.com/aff" in built.user_prompt
    assert "jangan mengarang" in built.user_prompt.lower()


def test_json_instruction_requests_exact_count():
    built = prompt_template_service.build(
        content_type=AIContentType.cta,
        platform=AIPlatform.x,
        prompt="x",
        variations=7,
    )
    assert "tepat 7" in built.user_prompt
    assert '"variations"' in built.user_prompt
