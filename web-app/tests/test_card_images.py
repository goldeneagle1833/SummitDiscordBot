"""Tests for the shared card-name to image-filename lookup."""

import pytest

import utils.card_images as card_images

FILENAMES = [
    "got-wuthering_heights-b-s.webp",
    "got-wuthering_heights-b-f.webp",
    "bet-daperyll_vampire-b-f.png",
    "bet-daperyll_vampire-b-s.png",
    "alp-abundance-bt-s-r.png",
    # Names whose separators differ between the card and the file.
    "bet-east_west_dragon-b-s.webp",
    "alp-cave_in-b-s.webp",
    "alp-wills_o_the_wisp-b-s.webp",
    # Printings beyond the common ones.
    "pro-spellslinger-dk-s.webp",
    "pro-relentless_crowd-k-s.webp",
    "alp-ice-b-s.webp",
    "notes.txt",
]


@pytest.fixture()
def images(tmp_path, monkeypatch):
    for name in FILENAMES:
        (tmp_path / name).write_bytes(b"")
    monkeypatch.setattr(card_images, "CARD_IMAGES_DIR", tmp_path)
    card_images.reset_cache()
    yield tmp_path
    card_images.reset_cache()


class TestResolveCardImage:
    def test_finds_the_file_for_a_card(self, images):
        assert card_images.resolve_card_image("Wuthering Heights") == (
            "got-wuthering_heights-b-s.webp"
        )

    def test_prefers_the_standard_printing_over_the_foil(self, images):
        assert card_images.resolve_card_image("Daperyll Vampire").endswith("-b-s.png")

    def test_strips_the_longest_printing_suffix(self, images):
        assert card_images.resolve_card_image("Abundance") == "alp-abundance-bt-s-r.png"

    def test_hyphenated_names_find_their_file(self, images):
        """Cards hyphenate where filenames use underscores."""
        assert card_images.resolve_card_image("East-West Dragon") == (
            "bet-east_west_dragon-b-s.webp"
        )
        assert card_images.resolve_card_image("Cave-In") == "alp-cave_in-b-s.webp"

    def test_apostrophes_do_not_break_the_lookup(self, images):
        assert card_images.resolve_card_image("Wills-o'-the-Wisp") == (
            "alp-wills_o_the_wisp-b-s.webp"
        )

    def test_unusual_printing_markers_are_still_stripped(self, images):
        # Promotional printings use -dk-s and -k-s rather than -b-s.
        assert card_images.resolve_card_image("Spellslinger") == "pro-spellslinger-dk-s.webp"
        assert card_images.resolve_card_image("Relentless Crowd") == (
            "pro-relentless_crowd-k-s.webp"
        )

    def test_a_short_card_name_is_not_mistaken_for_a_printing(self, images):
        assert card_images.resolve_card_image("Ice") == "alp-ice-b-s.webp"

    def test_unknown_cards_resolve_to_nothing(self, images):
        assert card_images.resolve_card_image("Not A Real Card") is None
        assert card_images.resolve_card_image("") is None
        assert card_images.resolve_card_image(None) is None

    def test_non_image_files_are_ignored(self, images):
        assert "notes.txt" not in card_images.get_card_image_map().values()

    def test_a_missing_directory_is_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(card_images, "CARD_IMAGES_DIR", tmp_path / "nope")
        card_images.reset_cache()
        assert card_images.get_card_image_map() == {}
        assert card_images.resolve_card_image("Wuthering Heights") is None


class TestAttachImages:
    def test_replaces_whatever_the_source_supplied(self, images):
        # Curiosa hands back absolute CDN urls, which /card-images cannot serve.
        cards = [
            {"name": "Wuthering Heights", "image": "https://d27a44hjr9gen3.cloudfront.net/x.png"},
            {"name": "Not A Real Card", "image": "https://example.com/y.png"},
        ]
        card_images.attach_images(cards)

        assert cards[0]["image"] == "got-wuthering_heights-b-s.webp"
        assert cards[1]["image"] is None

    def test_reads_an_alternate_name_key(self, images):
        cards = [{"card_name": "Wuthering Heights"}]
        card_images.attach_images(cards, name_key="card_name")
        assert cards[0]["image"] == "got-wuthering_heights-b-s.webp"

    def test_handles_nothing_gracefully(self, images):
        assert card_images.attach_images(None) == []
        assert card_images.attach_images([]) == []
        assert card_images.attach_images(["not a dict"]) == ["not a dict"]
