"""User-facing Telegram copy (Indonesian) and inline keyboards."""

from typing import Any

from app.core.config import settings
from app.services.telegram.state import OPTIONAL_STEPS, AddStep

SKIP_COMMAND = "/skip"
CANCEL_COMMAND = "/cancel"

_MD_SPECIAL = ("_", "*", "`", "[")


def escape_md(value: Any) -> str:
    """Escape user-supplied text for Telegram legacy Markdown parse mode."""
    text = "" if value is None else str(value)
    for char in _MD_SPECIAL:
        text = text.replace(char, f"\\{char}")
    return text

UNAUTHORIZED_TEXT = (
    "⛔ Maaf, Anda tidak memiliki akses ke bot ini.\n"
    "Hubungi administrator untuk mendapatkan izin."
)

WELCOME_TEXT = (
    "👋 *Selamat datang di Affiliate AI Bot*\n\n"
    "Saya membantu Anda menambahkan produk affiliate dan membuat konten "
    "promosi dengan AI.\n\n"
    "*Perintah tersedia:*\n"
    "/add — tambah produk baru (bertahap)\n"
    "/products — daftar produk terakhir\n"
    "/stats — ringkasan statistik\n"
    "/help — bantuan\n"
    "/cancel — batalkan proses yang sedang berjalan"
)

HELP_TEXT = (
    "📖 *Bantuan*\n\n"
    "*Perintah:*\n"
    "/add — tambah produk baru (bertahap)\n"
    "/products — daftar produk terakhir\n"
    "/stats — ringkasan statistik\n"
    "/help — bantuan\n"
    "/cancel — batalkan proses yang berjalan\n\n"
    "*Menambah produk:*\n"
    "1. Kirim /add\n"
    "2. Bot akan menanyakan data satu per satu\n"
    "3. Kirim /skip untuk melewati kolom opsional\n"
    "4. Kirim foto/video produk, lalu /done bila selesai\n\n"
    "*Field wajib:* nama produk, minimal 1 media (gambar atau video)\n"
    "*Field opsional:* link affiliate, harga, komisi, kategori, target audiens, "
    "deskripsi\n\n"
    "*Setelah produk tersimpan*, Anda dapat langsung:\n"
    "• Analyze with AI — buat deskripsi produk\n"
    "• Generate Content — buat konten promosi\n"
    "• Open Dashboard — lihat semua data di web"
)

STEP_PROMPTS: dict[AddStep, str] = {
    AddStep.name: (
        "1/8 📝 *Nama produk*\n\nKirim nama produk.\n_(wajib, tidak bisa di-skip)_"
    ),
    AddStep.affiliate_url: (
        "2/8 🔗 *Link affiliate*\n\nKirim URL affiliate produk.\n"
        "Ketik /skip untuk melewati."
    ),
    AddStep.price: (
        "3/8 💰 *Harga*\n\nKirim harga produk dalam Rupiah, contoh: `150000` "
        "atau `150000.50`.\nKetik /skip untuk melewati."
    ),
    AddStep.commission: (
        "4/8 📊 *Komisi*\n\nKirim nominal komisi dalam Rupiah, contoh: `15000`.\n"
        "Ketik /skip untuk melewati."
    ),
    AddStep.category: (
        "5/8 🏷️ *Kategori*\n\nKirim kategori produk, contoh: `Skincare`, "
        "`Elektronik`.\nKetik /skip untuk melewati."
    ),
    AddStep.target_audience: (
        "6/8 🎯 *Target audiens*\n\nSiapa target pembelinya? Contoh: "
        "`Ibu muda 25-35 tahun`.\nKetik /skip untuk melewati."
    ),
    AddStep.description: (
        "7/8 📄 *Deskripsi produk*\n\nKirim deskripsi singkat produk.\n"
        "Ketik /skip untuk melewati."
    ),
    AddStep.media: (
        "8/8 🖼️ *Media produk*\n\nKirim foto dan/atau video produk.\n"
        "Anda bisa mengirim beberapa file.\n\n"
        f"Ketik `/done` bila sudah selesai (wajib minimal 1 file),\n"
        f"atau /cancel untuk membatalkan."
    ),
}

MEDIA_HINT = (
    "Kirim foto atau video produk.\n"
    f"Format didukung: JPG, PNG, WEBP, GIF, MP4, MOV, WEBM "
    f"(maks {settings.media_max_file_size_mb} MB per file).\n"
    "Ketik /done bila sudah selesai."
)

UNKNOWN_INPUT_TEXT = (
    "🤔 Saya tidak mengerti pesan itu.\n"
    "Kirim /add untuk menambah produk, /products untuk daftar produk, "
    "atau /help untuk bantuan."
)

NO_ACTIVE_FLOW_TEXT = "ℹ️ Tidak ada proses yang sedang berjalan. Kirim /add untuk mulai."


def skip_buttons(step: AddStep) -> dict[str, Any] | None:
    """Inline keyboard offering skip/cancel for optional steps."""
    if step not in OPTIONAL_STEPS:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "⏭️ Skip", "callback_data": "add:skip"},
                {"text": "❌ Cancel", "callback_data": "add:cancel"},
            ]
        ]
    }


def media_buttons() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Selesai", "callback_data": "add:done"},
                {"text": "❌ Cancel", "callback_data": "add:cancel"},
            ]
        ]
    }


def product_actions(product_id: str) -> dict[str, Any]:
    """Post-save action buttons."""
    dashboard = f"{settings.frontend_base_url.rstrip('/')}/products"
    return {
        "inline_keyboard": [
            [
                {"text": "🤖 Analyze with AI", "callback_data": f"ai:analyze:{product_id}"},
                {"text": "✍️ Generate Content", "callback_data": f"ai:generate:{product_id}"},
            ],
            [
                {"text": "🌐 Open Dashboard", "url": dashboard},
            ],
        ]
    }


def product_actions_with_media_retry(product_id: str) -> dict[str, Any]:
    """Same actions plus a retry button for media that failed to download."""
    keyboard = product_actions(product_id)
    keyboard["inline_keyboard"].append(
        [
            {
                "text": "🔄 Retry Media",
                "callback_data": f"add:retry_media:{product_id}",
            }
        ]
    )
    return keyboard


def analyze_type_buttons(product_id: str) -> dict[str, Any]:
    """Content types offered for the 'Generate Content' action."""
    options = [
        ("caption", "📝 Caption"),
        ("hook", "🪝 Hook"),
        ("short_video_script", "🎬 Script Video"),
        ("cta", "📣 CTA"),
    ]
    rows = [
        [{"text": label, "callback_data": f"ai:run:{product_id}:{value}"}]
        for value, label in options
    ]
    rows.append([{"text": "❌ Batal", "callback_data": "ai:cancel"}])
    return {"inline_keyboard": rows}


def generation_result_buttons(product_id: str) -> dict[str, Any]:
    dashboard = f"{settings.frontend_base_url.rstrip('/')}/dashboard/queue"
    return {
        "inline_keyboard": [
            [
                {"text": "🔁 Regenerate", "callback_data": f"ai:generate:{product_id}"},
                {"text": "🌐 Lihat di Dashboard", "url": dashboard},
            ]
        ]
    }


def generation_failed_buttons(product_id: str, generation_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔁 Retry",
                    "callback_data": f"ai:retry:{generation_id}",
                },
                {
                    "text": "✍️ Generate ulang",
                    "callback_data": f"ai:generate:{product_id}",
                },
            ]
        ]
    }
