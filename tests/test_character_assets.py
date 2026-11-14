from pathlib import Path
import unittest

from PIL import Image, ImageChops

from character_profiles import PROFILES


class CharacterAssetTests(unittest.TestCase):
    def test_expression_and_blink_frames_have_identical_alpha_and_valid_aliases(self):
        root = Path(__file__).resolve().parents[1]
        for identifier in ("beatrice","waguri_kaoruko"):
            profile = PROFILES[identifier]
            self.assertTrue(profile.available(root))
            sprites, blink = profile.assets(root)
            self.assertTrue(all(p.is_file() for p in sprites.values()))
            self.assertTrue(all(p.is_file() for p in blink.values()))
            folder = profile.production_folder(root)
            hashes = set()
            for base in set(sprites.values()):
                alpha = Image.open(base).getchannel("A")
                self.assertIsNotNone(alpha.getbbox())
                for suffix in ("","_blink","_mouth","_mouth_blink"):
                    with Image.open(folder / f"{base.stem}{suffix}.png") as image:
                        self.assertEqual(image.size,(384,448))
                        self.assertEqual(image.mode,"RGBA")
                        self.assertIsNone(ImageChops.difference(alpha,image.getchannel("A")).getbbox())
                        if not suffix:
                            hashes.add(image.tobytes())
            self.assertEqual(len(hashes),12)


if __name__ == "__main__":
    unittest.main()
