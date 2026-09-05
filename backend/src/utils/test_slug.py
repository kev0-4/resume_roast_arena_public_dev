from backend.src.utils.slug import generate_slug, _ALPHABET, _SLUG_LENGTH


class TestGenerateSlug:
    def test_length(self):
        assert len(generate_slug()) == _SLUG_LENGTH

    def test_charset(self):
        slug = generate_slug()
        assert all(c in _ALPHABET for c in slug)

    def test_no_ambiguous_characters(self):
        slug = generate_slug()
        assert not any(c in slug for c in "0o1li")

    def test_statistically_unique_across_many_calls(self):
        slugs = {generate_slug() for _ in range(10_000)}
        # 32^8 possibility space -- 10k draws should not collide in practice
        assert len(slugs) == 10_000

    def test_lowercase_only(self):
        slug = generate_slug()
        assert slug == slug.lower()
