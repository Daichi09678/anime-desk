"""Character identity and expression aliases; artwork is loaded on demand."""

from dataclasses import dataclass
from pathlib import Path



EXPRESSION_LABELS = {
    "neutral": "Netral", "happy": "Senang", "talking": "Berbicara",
    "thinking": "Berpikir", "surprised": "Terkejut", "sleepy": "Memejamkan mata",
}
EXPRESSION_STATES = {
    "neutral": "idle", "happy": "pleased", "talking": "talking",
    "thinking": "thinking", "surprised": "thinking_lookup", "sleepy": "sleeping",
}
PRODUCTION_POSES = {
    "idle":"idle", "idle_cozy":"idle", "idle_sleepy":"sleepy", "idle_reading":"reading",
    "idle_dancing":"signature", "idle_tea":"tea", "thinking":"thinking",
    "thinking_lookup":"surprised", "thinking_tilt":"thinking", "thinking_hmmm":"thinking",
    "action_laptop":"working", "action_magic":"signature", "talking":"talking",
    "talking_explain":"explaining", "pleased":"happy", "pleased_wave":"happy",
    "needs_tea":"tea", "needs_hungry":"idle", "needs_sleepy":"sleepy",
    "needs_stretch":"stretch", "sleeping":"sleepy", "sleepy_yawn":"sleepy",
}


@dataclass(frozen=True)
class CharacterProfile:
    id: str
    name: str
    description: str
    persona: str
    taps: tuple[str, ...]
    colours: dict[str, str]

    @property
    def voice_preview(self):
        return self.voice_taps[0]

    def portrait_frame(self, pose):
        """Portrait window (x, y, width, height) on the 384×448 production sheets.

        Match Frieren's eye line (~23% from the top), not the outer edges of
        dresses, hair or raised hands. Facial animation uses the same window.
        """
        if self.id == "beatrice":
            return (120, 105, 136, 146) if pose == "idle" else (107, 106, 174, 184)
        if self.id == "waguri_kaoruko":
            return (28, 108, 310, 324)
        return None

    @property
    def voice_taps(self):
        """Japanese counterparts of taps, in matching order."""
        return {"frieren":("ここにいるよ。一つずつ進めていこう。", "疲れたら、少し休んでもいいんだよ。"),
                "beatrice":("さて、今度はどの謎を解こうか。", "よく確かめよう。小さな手がかりこそ大切なのだ。"),
                "waguri_kaoruko":("こんにちは。何から始めましょうか？", "声をかけてくれて、ありがとうございます。一緒に考えましょう。")}[self.id]

    def production_folder(self, base_dir):
        folder = Path(base_dir) / "assets/characters" / self.id
        updated = folder / "production_reference"
        return updated if self.id == "beatrice" and (updated / "manifest.json").is_file() else folder / "production"

    def assets(self, base_dir: Path):
        from sprite_helper import STATES, ensure_sprites
        if self.id == "frieren":
            sprites = ensure_sprites(base_dir / "assets/sprites")
            folder = base_dir / "assets/characters/frieren/blink"
            blink = {state: folder / f"{state}.png" for state in sprites if (folder / f"{state}.png").is_file()}
            return sprites, blink
        production = self.production_folder(base_dir)
        if (production / "manifest.json").is_file():
            return ({state:production/f"{pose}.png" for state,pose in PRODUCTION_POSES.items()},
                    {state:production/f"{pose}_blink.png" for state,pose in PRODUCTION_POSES.items()})
        raise ValueError(f"Paket ilustrasi produksi {self.name} belum tersedia.")

    def mouth_frames(self, base_dir):
        folder = self.production_folder(base_dir)
        if self.id == "frieren":
            return {state:folder/f"{state}_mouth.png" for state in ("talking","talking_explain")
                    if (folder/f"{state}_mouth.png").is_file()}
        return {state:folder/f"{pose}_mouth.png" for state,pose in PRODUCTION_POSES.items()
                if (folder/f"{pose}_mouth.png").is_file()}

    def available(self, base_dir):
        production = self.production_folder(base_dir)
        if (production/"manifest.json").is_file():
            return all((production/f"{pose}.png").is_file() for pose in set(PRODUCTION_POSES.values()))
        return self.id == "frieren"


PROFILES = {
    "frieren": CharacterProfile(
        "frieren", "Frieren", "Tenang · putih & abu-abu",
        "Kamu adalah Frieren, penyihir elf yang tenang, hangat, dan bijaksana. Subtitle dalam bahasa Indonesia; dubbing VOICE_JA dalam bahasa Jepang alami; "
        "gunakan 私, kalimat pendek tenang, sesekali ～だね atau ～かな, tanpa berlebihan. Sesuaikan istilah dengan topik.",
        ("Aku di sini. Kita lanjutkan satu per satu, ya.", "Kalau lelah, boleh istirahat sebentar."),
        {"background":"#eee9de", "surface":"#f8f4eb", "field":"#fffdf7", "text":"#403727",
         "muted":"#756a58", "accent":"#737e66", "hover":"#e6dfce", "border":"#b39b6c", "selection":"#dcdcca"}),
    "beatrice": CharacterProfile(
        "beatrice", "Beatrice", "Anggun · emas",
        "Kamu adalah Beatrice dari Umineko, penyihir emas yang elegan, percaya diri, dan sedikit teatrikal. "
        "Subtitle dalam bahasa Indonesia. Untuk dubbing VOICE_JA gunakan bahasa Jepang anggun dan sedikit teatrikal: 妾（わらわ）, ～であろう, ～だな secara wajar; "
        "istilah teknis tetap jelas dan modern. Jangan tertawa berlebihan atau mengejek pengguna. "
        "Saat fokus jelaskan secara runtut dan tegas; saat senang tersenyum puas tanpa berlebihan. "
        "Tetap akurat tentang hasil tool; jangan mengaku sebagai Frieren atau mengklaim aksi yang belum selesai.",
        ("Nah, misteri apa yang akan kita pecahkan kali ini?", "Mari periksa dengan teliti. Petunjuk kecil pun penting."),
        {"background":"#241c12", "surface":"#302619", "field":"#1d180f", "text":"#fff1ce",
         "muted":"#d1bd8c", "accent":"#c9a14c", "hover":"#594623", "border":"#8e7139", "selection":"#6b5127"}),
    "waguri_kaoruko": CharacterProfile(
        "waguri_kaoruko", "Waguri Kaoruko", "Hangat · ungu",
        "Kamu adalah Waguri Kaoruko, pendamping yang lembut, ramah, penuh perhatian, dan suportif. "
        "Subtitle dalam bahasa Indonesia. Untuk dubbing VOICE_JA gunakan bahasa Jepang sopan, hangat, natural: 私, bentuk です／ます, sesekali ～ですね; kalimat mudah diikuti. "
        "Saat berpikir bersikap penasaran; saat membantu jelaskan langkah kecil; saat berhasil beri semangat tulus. "
        "Hindari tawa/manja berlebihan. Jujur tentang hasil pekerjaan; jangan mengaku sebagai Frieren.",
        ("Halo. Kita mulai dari mana?", "Terima kasih sudah menyapaku. Mari kita pikirkan bersama."),
        {"background":"#261e35", "surface":"#332744", "field":"#1f182c", "text":"#f5edff",
         "muted":"#c7b5dd", "accent":"#ad87dd", "hover":"#57416e", "border":"#82639f", "selection":"#654a81"}),
}


def get_profile(identifier):
    return PROFILES.get(identifier, PROFILES["frieren"])
