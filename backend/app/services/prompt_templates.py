"""Prompt templates for AI content generation.

Templates live here so API routes and the worker stay free of prompt text.
Each template returns a (system_prompt, user_prompt) pair.
"""

from dataclasses import dataclass

from app.models import AIContentType, AIPlatform

# Shared honesty/natural-language guardrails applied to every template.
_CORE_RULES = """\
Aturan wajib (WAJIB dipatuhi):
1. Tulis dalam Bahasa Indonesia yang natural, seperti orang Indonesia asli menulis di media sosial.
2. Hindari kata-kata kaku/robotik ("dapatkan sekarang juga", "produk ini sangat luar biasa").
3. JANGAN membuat testimoni palsu atau mengaku sudah memakai produknya.
4. JANGAN membuat klaim yang tidak didukung fakta.
5. JANGAN mengarang spesifikasi produk (bahan, ukuran, fitur) yang tidak diberikan.
6. JANGAN mengarang diskon, harga promo, atau bonus yang tidak disebutkan.
7. JANGAN menjamin hasil tertentu (misalnya "dijamin sukses", "pasti sembuh").
8. Tetap persuasif tapi jujur. Gunakan bahasa yang mengundang, bukan memaksa.
9. Setiap variasi harus benar-benar berbeda satu sama lain (sudut pandang, pembuka, gaya bahasa, struktur).
10. Jangan menambahkan penjelasan, komentar, atau label di luar hasil itu sendiri.
11. Jangan menggunakan emoji berlebihan (maksimal 2 emoji per variasi)."""

_JSON_INSTRUCTION = """\
{count_instruction}

Keluarkan HANYA JSON yang valid dengan format berikut, tanpa teks pembuka atau penutup:
{{"variations": ["variasi 1", "variasi 2"]}}

Jumlah elemen pada "variations" harus tepat {count}. Keluarkan JSON saja."""

_LENGTH_HINT = {
    AIContentType.caption: "Panjang tiap caption 1-3 kalimat. Sertakan slot ajakan (CTA) yang halus.",
    AIContentType.hook: "Tiap hook maksimal 1-2 kalimat, harus memancing rasa penasaran di 3 detik pertama.",
    AIContentType.short_video_script: (
        "Tiap script berisi urutan sederhana dengan penanda [HOOK], [ISI], [CTA]. "
        "Total 3-6 baris per variasi."
    ),
    AIContentType.product_description: (
        "Tiap deskripsi 2-5 kalimat, fokus pada manfaat dan siapa yang cocok memakainya."
    ),
    AIContentType.cta: "Tiap CTA 1 kalimat singkat, jelas, dan tidak memaksa.",
}

_PLATFORM_HINT = {
    AIPlatform.tiktok: "Gaya TikTok: santai, cepat, kasual, cocok untuk audio/video pendek.",
    AIPlatform.instagram: "Gaya Instagram: rapi, estetis, cocok untuk carousel atau reels.",
    AIPlatform.facebook: "Gaya Facebook: sedikit lebih naratif dan informatif, cocok untuk grup.",
    AIPlatform.threads: "Gaya Threads: conversational dan mengundang diskusi.",
    AIPlatform.x: "Gaya X/Twitter: singkat, padat, maksimal 280 karakter per variasi.",
}

TEMPLATE_VERSIONS = {
    AIContentType.caption: "affiliate_caption_v1",
    AIContentType.hook: "affiliate_hook_v1",
    AIContentType.short_video_script: "short_video_script_v1",
    AIContentType.product_description: "product_description_v1",
    AIContentType.cta: "cta_v1",
}


@dataclass(frozen=True)
class BuiltPrompt:
    system_prompt: str
    user_prompt: str
    template: str


class PromptTemplateService:
    """Builds system/user prompts from a content type, platform and context."""

    def template_name(self, content_type: AIContentType) -> str:
        return TEMPLATE_VERSIONS[content_type]

    def build(
        self,
        *,
        content_type: AIContentType,
        platform: AIPlatform,
        prompt: str,
        variations: int,
        product_name: str | None = None,
        product_description: str | None = None,
        affiliate_url: str | None = None,
    ) -> BuiltPrompt:
        system_prompt = self._system_prompt(content_type)
        user_prompt = self._user_prompt(
            content_type=content_type,
            platform=platform,
            prompt=prompt,
            variations=variations,
            product_name=product_name,
            product_description=product_description,
            affiliate_url=affiliate_url,
        )
        return BuiltPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            template=self.template_name(content_type),
        )

    def _system_prompt(self, content_type: AIContentType) -> str:
        role = {
            AIContentType.caption: "copywriter affiliate yang menulis caption media sosial",
            AIContentType.hook: "copywriter yang ahli membuat hook pembuka yang memancing",
            AIContentType.short_video_script: "scriptwriter untuk video pendek (TikTok/Reels/Shorts)",
            AIContentType.product_description: "copywriter katalog produk",
            AIContentType.cta: "copywriter yang ahli menulis ajakan bertindak (CTA)",
        }[content_type]

        return (
            f"Kamu adalah {role} untuk kebutuhan affiliate marketing di Indonesia.\n\n"
            f"{_CORE_RULES}"
        )

    def _user_prompt(
        self,
        *,
        content_type: AIContentType,
        platform: AIPlatform,
        prompt: str,
        variations: int,
        product_name: str | None,
        product_description: str | None,
        affiliate_url: str | None,
    ) -> str:
        sections = [
            f"Jenis konten: {content_type.value}",
            f"Platform: {platform.value}",
            f"Panduan platform: {_PLATFORM_HINT[platform]}",
            f"Panduan panjang: {_LENGTH_HINT[content_type]}",
            f"Jumlah variasi: {variations}",
        ]

        if product_name:
            sections.append(f"Nama produk: {product_name}")
        if product_description:
            sections.append(f"Deskripsi produk (satu-satunya sumber fakta produk): {product_description}")
        if affiliate_url:
            sections.append(f"Link affiliate (jangan diubah): {affiliate_url}")

        sections.append(f"Brief dari pengguna: {prompt}")
        sections.append(
            "Gunakan HANYA informasi produk yang diberikan di atas. "
            "Jika informasi tidak tersedia, jangan mengarang."
        )
        sections.append(
            _JSON_INSTRUCTION.format(
                count=variations,
                count_instruction="Buat beberapa variasi yang berbeda.",
            )
        )

        return "\n".join(sections)


prompt_template_service = PromptTemplateService()
