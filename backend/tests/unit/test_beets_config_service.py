"""Unit tests for BeetsConfigService save/round-trip behaviour.

Regression coverage for the config editor dropping non-modeled plugin options
on save (e.g. ``replaygain.backend``), which broke library configs by leaving
beets unable to initialize the replaygain plugin. See issue #134.
"""

import textwrap

import yaml

from app.services.beets_config_service import BeetsConfigService


def _write(path, body):
    path.write_text(textwrap.dedent(body))
    return str(path)


def _round_trip(svc, config_path):
    """Mirror the editor flow: load (GET) then save (PUT) unchanged."""
    config = svc.parse_yaml_config(config_path)
    svc.save_config(config_path, config)
    return yaml.safe_load(open(config_path))


class TestSavePreservesNonModeledKeys:
    """Saving must not drop keys the schema doesn't model."""

    def test_replaygain_backend_survives_round_trip(self, tmp_path):
        path = _write(
            tmp_path / "kids-audio.yaml",
            """
            directory: /music/kids
            library: /config/kids.db
            plugins: replaygain
            replaygain:
              auto: no
              backend: ffmpeg
              overwrite: yes
              threads: 4
            """,
        )
        svc = BeetsConfigService()

        after = _round_trip(svc, path)

        assert after["replaygain"]["backend"] == "ffmpeg"
        assert after["replaygain"]["overwrite"] is True
        assert after["replaygain"]["threads"] == 4
        assert after["replaygain"]["auto"] is False

    def test_other_plugins_non_modeled_keys_survive(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: convert lastgenre embedart
            convert:
              auto: no
              format: mp3
              embed: yes
            lastgenre:
              auto: yes
              source: album
              count: 3
              whitelist: /config/genres.txt
            embedart:
              auto: yes
              maxwidth: 1000
            """,
        )
        svc = BeetsConfigService()

        after = _round_trip(svc, path)

        assert after["convert"]["format"] == "mp3"
        assert after["convert"]["embed"] is True
        assert after["lastgenre"]["count"] == 3
        assert after["lastgenre"]["whitelist"] == "/config/genres.txt"
        assert after["embedart"]["maxwidth"] == 1000

    def test_unmodeled_top_level_section_survives(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            musicbrainz:
              host: musicbrainz.example
              ratelimit: 3
            id3v23: yes
            """,
        )
        svc = BeetsConfigService()

        after = _round_trip(svc, path)

        assert after["musicbrainz"] == {"host": "musicbrainz.example", "ratelimit": 3}
        assert after["id3v23"] is True


class TestSaveDoesNotInjectDefaults:
    """An unchanged save must not materialize modeled defaults the user never set."""

    def test_convert_defaults_not_injected(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: convert
            convert:
              auto: no
              format: mp3
            """,
        )
        svc = BeetsConfigService()

        after = _round_trip(svc, path)

        # Only the keys the file actually had — no ffmpeg/opts/max_bitrate/threads.
        assert after["convert"] == {"auto": False, "format": "mp3"}

    def test_absent_replaygain_section_not_created(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: fetchart
            """,
        )
        svc = BeetsConfigService()

        after = _round_trip(svc, path)

        # The model defaults `replaygain.auto: False`, but an unchanged save
        # must not write a section that wasn't in the file.
        assert "replaygain" not in after


class TestSaveAppliesEdits:
    """Genuine edits must persist while extras are preserved."""

    def test_modeled_edit_applied_extras_kept(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            replaygain:
              auto: no
              backend: ffmpeg
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.replaygain.auto = True  # user flips the toggle in the UI
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["replaygain"]["auto"] is True  # edit applied
        assert after["replaygain"]["backend"] == "ffmpeg"  # extra preserved

    def test_plugins_list_edit_replaced_wholesale(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain convert lastgenre
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.plugins = ["replaygain", "convert"]  # user removes lastgenre
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["plugins"] == ["replaygain", "convert"]

    def test_edit_preserves_unmodeled_top_level_key(self, tmp_path):
        # Editing a modeled field must not collaterally drop a sibling the
        # schema doesn't model.
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            threaded: yes
            id3v23: yes
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.threaded = False  # change a modeled scalar
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["threaded"] is False
        assert after["id3v23"] is True  # unmodeled sibling preserved

    def test_replace_rules_preserved_on_noop_and_removable(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            r"""
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            replace:
              '[\\/]': _
              '^\.': _
            """,
        )
        svc = BeetsConfigService()

        # No-op save keeps the user's exact replace map.
        after = _round_trip(svc, path)
        assert after["replace"] == {"[\\\\/]": "_", "^\\.": "_"}

        # Removing a rule via the model propagates (atomic wholesale replace).
        config = svc.parse_yaml_config(path)
        config.replace = [r for r in config.replace if r.pattern != "^\\."]
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))
        assert "^\\." not in after["replace"]
        assert after["replace"]["[\\\\/]"] == "_"

    def test_clearing_all_replace_rules_round_trips(self, tmp_path):
        # Emptying the replace map must persist AND reload empty — not silently
        # resurrect the built-in defaults. (An absent `replace:` key still seeds
        # defaults; an explicit empty one does not.)
        path = _write(
            tmp_path / "lib.yaml",
            r"""
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            replace:
              '[\\/]': _
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.replace = []  # user clears every rule
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))
        assert after["replace"] == {}  # stays empty on disk

        # And reloading does not re-inject defaults.
        reloaded = svc.parse_yaml_config(path)
        assert reloaded.replace == []

    def test_absent_replace_key_still_seeds_defaults(self, tmp_path):
        # The convenience default-seeding for brand-new/hand-written configs
        # without any `replace:` block must remain intact.
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        assert len(config.replace) > 0  # defaults seeded when key absent

    def test_clearing_import_log_removes_the_key(self, tmp_path):
        # The modeled-key deletion path: a cleared optional `import.log` must be
        # dropped from the file while sibling import keys survive.
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            import:
              write: yes
              log: /config/import.log
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        assert config.import_.log == "/config/import.log"
        config.import_.log = None  # user clears the log path
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert "log" not in after["import"]
        assert after["import"]["write"] is True  # sibling survives

    def test_edit_in_absent_section_adds_only_that_key(self, tmp_path):
        # Boundary between bug #134 (default injection) and the fix: flipping a
        # key in a section the file lacks must add exactly that key, no defaults.
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.replaygain.auto = True
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["replaygain"] == {"auto": True}

    def test_adding_a_plugin_propagates(self, tmp_path):
        path = _write(
            tmp_path / "lib.yaml",
            """
            directory: /music
            library: /config/lib.db
            plugins: replaygain
            """,
        )
        svc = BeetsConfigService()

        config = svc.parse_yaml_config(path)
        config.plugins = ["replaygain", "convert"]  # user adds convert
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["plugins"] == ["replaygain", "convert"]


class TestSaveRefusesToClobberUnparseable:
    """A corrupt existing file must not be silently overwritten (data loss)."""

    def test_unparseable_existing_raises(self, tmp_path):
        path = _write(tmp_path / "broken.yaml", "directory: /music\n  : : bad\n")
        svc = BeetsConfigService()
        config = svc.get_default_config(directory="/music", library="/config/lib.db")

        import pytest

        with pytest.raises(ValueError):
            svc.save_config(path, config)


class TestSaveNewFile:
    """With no existing file, the full model is written (provisioning fallback)."""

    def test_writes_full_config_when_absent(self, tmp_path):
        path = str(tmp_path / "nested" / "new.yaml")
        svc = BeetsConfigService()

        config = svc.get_default_config(directory="/music", library="/config/new.db")
        svc.save_config(path, config)
        after = yaml.safe_load(open(path))

        assert after["directory"] == "/music"
        assert after["library"] == "/config/new.db"
        assert "replaygain" in after  # full scaffold present for a brand-new file
