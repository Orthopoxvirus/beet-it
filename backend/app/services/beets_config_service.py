"""Service for parsing and serializing beets configuration files."""

import logging
import os
from typing import Any

import yaml

from app.schemas.beets_config import (
    BeetsConfigSchema,
    ImportConfig,
    PathsConfig,
    ConvertConfig,
    LastgenreConfig,
    EmbedartConfig,
    FetchartConfig,
    ReplaygainConfig,
    ScrubConfig,
    ReplaceRule,
    EmbyConfig,
    DiscogsConfig,
    PermissionsConfig,
    MatchConfig,
    DEFAULT_PLUGINS,
    DEFAULT_REPLACE_RULES,
    DEFAULT_ITEM_FIELDS,
)

logger = logging.getLogger(__name__)


_UNSET = object()


class BeetsConfigService:
    """Service for managing beets configuration files.

    This service handles:
    - Parsing YAML config files into Pydantic models
    - Serializing Pydantic models back to YAML
    - Creating default configurations
    - Reading and writing config files

    On save, the modeled schema is intentionally a subset of beets' real option
    set. To avoid dropping the keys the schema does not model (e.g.
    ``replaygain.backend``), saves are applied as a three-way merge onto the
    existing on-disk YAML rather than regenerated purely from the model. See
    :meth:`save_config`.
    """

    # Top-level keys whose value is a user-controlled collection that must be
    # replaced wholesale when it changes (so removals propagate), never
    # deep-merged key-by-key.
    _ATOMIC_KEYS = frozenset({"plugins", "replace"})

    def parse_yaml_config(self, config_path: str) -> BeetsConfigSchema:
        """Parse a YAML config file into a BeetsConfigSchema model.

        Args:
            config_path: Path to the beets YAML config file.

        Returns:
            BeetsConfigSchema model with parsed configuration.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            ValueError: If the YAML is invalid or can't be parsed.
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r") as f:
            try:
                raw_config = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Failed to parse YAML: {e}")

        return self._yaml_dict_to_schema(raw_config)

    def _yaml_dict_to_schema(self, raw_config: dict[str, Any]) -> BeetsConfigSchema:
        """Convert a raw YAML dictionary to a BeetsConfigSchema.

        Args:
            raw_config: Dictionary loaded from YAML.

        Returns:
            BeetsConfigSchema model.
        """
        # Extract and process replace rules - YAML format is {"pattern": "replacement"}
        # Distinguish an absent `replace:` key (seed sensible defaults) from one
        # explicitly emptied by the user (keep it empty) — otherwise clearing all
        # replace rules in the editor silently resurrects the defaults on reload.
        replace_rules = []
        raw_replace = raw_config.get("replace", _UNSET)
        if raw_replace is _UNSET:
            replace_rules = [ReplaceRule(**r) for r in DEFAULT_REPLACE_RULES]
        elif isinstance(raw_replace, dict):
            for pattern, replacement in raw_replace.items():
                replace_rules.append(
                    ReplaceRule(pattern=pattern, replacement=replacement or "")
                )
        elif isinstance(raw_replace, list):
            # Already in list format from our own serialization
            for rule in raw_replace:
                if isinstance(rule, dict) and "pattern" in rule:
                    replace_rules.append(
                        ReplaceRule(
                            pattern=rule["pattern"], replacement=rule.get("replacement", "")
                        )
                    )

        # Extract import config
        raw_import = raw_config.get("import", {})
        import_config = ImportConfig(
            write=raw_import.get("write", True),
            copy=raw_import.get("copy", True),
            move=raw_import.get("move", False),
            resume=raw_import.get("resume", True),
            incremental=raw_import.get("incremental", False),
            quiet_fallback=raw_import.get("quiet_fallback", "skip"),
            timid=raw_import.get("timid", False),
            log=raw_import.get("log"),
        )

        # Extract paths config
        raw_paths = raw_config.get("paths", {})
        paths_config = PathsConfig(
            default=raw_paths.get("default", PathsConfig().default),
            singleton=raw_paths.get("singleton", PathsConfig().singleton),
            comp=raw_paths.get("comp", PathsConfig().comp),
            albumtype_soundtrack=raw_paths.get(
                "albumtype:soundtrack", PathsConfig().albumtype_soundtrack
            ),
        )

        # Extract convert config
        raw_convert = raw_config.get("convert", {})
        convert_config = ConvertConfig(
            auto=raw_convert.get("auto", False),
            ffmpeg=raw_convert.get("ffmpeg", "/usr/bin/ffmpeg"),
            opts=raw_convert.get("opts", "-ab 320k -ac 2 -ar 48000"),
            max_bitrate=raw_convert.get("max_bitrate", 320),
            threads=raw_convert.get("threads", 1),
        )

        # Extract lastgenre config
        raw_lastgenre = raw_config.get("lastgenre", {})
        lastgenre_config = LastgenreConfig(
            auto=raw_lastgenre.get("auto", True),
            source=raw_lastgenre.get("source", "album"),
        )

        # Extract embedart config
        raw_embedart = raw_config.get("embedart", {})
        embedart_config = EmbedartConfig(auto=raw_embedart.get("auto", True))

        # Extract fetchart config
        raw_fetchart = raw_config.get("fetchart", {})
        fetchart_config = FetchartConfig(auto=raw_fetchart.get("auto", True))

        # Extract replaygain config
        raw_replaygain = raw_config.get("replaygain", {})
        replaygain_config = ReplaygainConfig(auto=raw_replaygain.get("auto", False))

        # Extract scrub config
        raw_scrub = raw_config.get("scrub", {})
        scrub_config = ScrubConfig(auto=raw_scrub.get("auto", True))

        # Extract emby config
        raw_emby = raw_config.get("emby", {})
        emby_config = EmbyConfig(
            host=raw_emby.get("host", ""),
            port=raw_emby.get("port", 8096),
            userid=raw_emby.get("userid", ""),
            apikey=raw_emby.get("apikey", ""),
        )

        # Extract discogs config
        raw_discogs = raw_config.get("discogs", {})
        discogs_config = DiscogsConfig(user_token=raw_discogs.get("user_token", ""))

        # Extract permissions config
        raw_permissions = raw_config.get("permissions", {})
        permissions_config = PermissionsConfig(
            file=raw_permissions.get("file", 664),
            dir=raw_permissions.get("dir", 775),
        )

        # Extract match config
        raw_match = raw_config.get("match", {})
        match_config = MatchConfig(
            strong_rec_thresh=raw_match.get("strong_rec_thresh", 0.04)
        )

        # Extract plugins - handle string format (space-separated) or list
        raw_plugins = raw_config.get("plugins", DEFAULT_PLUGINS.copy())
        if isinstance(raw_plugins, str):
            plugins = raw_plugins.split()
        elif isinstance(raw_plugins, list):
            plugins = raw_plugins
        else:
            plugins = DEFAULT_PLUGINS.copy()

        # Extract inline-plugin item_fields (values are Python expressions,
        # kept as strings). Missing key falls back to the defaults so the
        # $multidisc path-template field stays defined.
        raw_item_fields = raw_config.get("item_fields", DEFAULT_ITEM_FIELDS.copy())
        if isinstance(raw_item_fields, dict):
            item_fields = {str(k): str(v) for k, v in raw_item_fields.items()}
        else:
            item_fields = DEFAULT_ITEM_FIELDS.copy()

        return BeetsConfigSchema(
            directory=raw_config.get("directory", ""),
            library=raw_config.get("library", ""),
            art_filename=raw_config.get("art_filename", "albumart"),
            threaded=raw_config.get("threaded", True),
            original_date=raw_config.get("original_date", False),
            per_disc_numbering=raw_config.get("per_disc_numbering", False),
            plugins=plugins,
            item_fields=item_fields,
            **{"import": import_config},
            paths=paths_config,
            convert=convert_config,
            lastgenre=lastgenre_config,
            embedart=embedart_config,
            fetchart=fetchart_config,
            replaygain=replaygain_config,
            scrub=scrub_config,
            replace=replace_rules,
            emby=emby_config,
            discogs=discogs_config,
            permissions=permissions_config,
            match=match_config,
        )

    def serialize_config(self, config: BeetsConfigSchema) -> str:
        """Serialize a BeetsConfigSchema model to YAML string.

        Args:
            config: The BeetsConfigSchema to serialize.

        Returns:
            YAML string representation suitable for beets.
        """
        yaml_dict = self._schema_to_yaml_dict(config)
        return yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _schema_to_yaml_dict(self, config: BeetsConfigSchema) -> dict[str, Any]:
        """Convert a BeetsConfigSchema to a YAML-compatible dictionary.

        Args:
            config: The BeetsConfigSchema to convert.

        Returns:
            Dictionary ready for YAML serialization.
        """
        # Convert replace rules to beets YAML format: {"pattern": "replacement"}
        replace_dict = {}
        for rule in config.replace:
            replace_dict[rule.pattern] = rule.replacement

        # Build the YAML structure in a logical order
        yaml_dict: dict[str, Any] = {
            "directory": config.directory,
            "library": config.library,
            "art_filename": config.art_filename,
            "threaded": config.threaded,
            "original_date": config.original_date,
            "per_disc_numbering": config.per_disc_numbering,
            "plugins": config.plugins,
            "item_fields": config.item_fields,
            "import": {
                "write": config.import_.write,
                "copy": config.import_.copy,
                "move": config.import_.move,
                "resume": config.import_.resume,
                "incremental": config.import_.incremental,
                "quiet_fallback": config.import_.quiet_fallback,
                "timid": config.import_.timid,
            },
            "paths": {
                "default": config.paths.default,
                "singleton": config.paths.singleton,
                "comp": config.paths.comp,
                "albumtype:soundtrack": config.paths.albumtype_soundtrack,
            },
            "convert": {
                "auto": config.convert.auto,
                "ffmpeg": config.convert.ffmpeg,
                "opts": config.convert.opts,
                "max_bitrate": config.convert.max_bitrate,
                "threads": config.convert.threads,
            },
            "lastgenre": {
                "auto": config.lastgenre.auto,
                "source": config.lastgenre.source,
            },
            "embedart": {"auto": config.embedart.auto},
            "fetchart": {"auto": config.fetchart.auto},
            "replaygain": {"auto": config.replaygain.auto},
            "scrub": {"auto": config.scrub.auto},
            "replace": replace_dict,
            "emby": {
                "host": config.emby.host,
                "port": config.emby.port,
                "userid": config.emby.userid,
                "apikey": config.emby.apikey,
            },
            "discogs": {"user_token": config.discogs.user_token},
            "permissions": {
                "file": config.permissions.file,
                "dir": config.permissions.dir,
            },
            "match": {"strong_rec_thresh": config.match.strong_rec_thresh},
        }

        # Add import log if present
        if config.import_.log:
            yaml_dict["import"]["log"] = config.import_.log

        return yaml_dict

    def _merge_changes(
        self,
        base_raw: dict[str, Any],
        baseline: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply the editor's changes onto the raw on-disk config.

        Performs a three-way merge: ``baseline`` is the modeled view of the
        existing file (exactly what the editor received on load), ``incoming``
        is the modeled view the editor sent back, and ``base_raw`` is the
        untouched file structure (which still carries keys the schema does not
        model). Only leaves that actually differ between ``incoming`` and
        ``baseline`` are written onto ``base_raw``.

        This preserves non-modeled keys, never injects modeled defaults the
        user did not change, and propagates removals.

        Args:
            base_raw: Raw dict loaded from the existing YAML file.
            baseline: ``_schema_to_yaml_dict`` of the file's parsed model.
            incoming: ``_schema_to_yaml_dict`` of the model being saved.

        Returns:
            A new dict ready for serialization.
        """
        result = dict(base_raw)

        for key, inc_val in incoming.items():
            base_val = baseline.get(key, _UNSET)
            if (
                key not in self._ATOMIC_KEYS
                and isinstance(inc_val, dict)
                and isinstance(base_val, dict)
            ):
                section_present = isinstance(result.get(key), dict)
                existing_sub = dict(result[key]) if section_present else {}
                merged_sub = self._merge_changes(existing_sub, base_val, inc_val)
                if merged_sub or section_present:
                    result[key] = merged_sub
                # else: section was absent and unchanged — don't create it empty.
            elif inc_val != base_val:
                # Changed leaf (or atomic collection): take the editor's value.
                result[key] = inc_val
            # Unchanged: leave whatever the raw file held (or its absence) intact.

        # A modeled key present in the baseline but absent from the incoming
        # payload means the user cleared it (e.g. an optional `import.log`).
        for key in baseline:
            if key not in incoming and key in result:
                del result[key]

        return result

    def save_config(self, config_path: str, config: BeetsConfigSchema) -> None:
        """Write a configuration to a YAML file.

        When a config file already exists, the model is merged onto it so that
        options the schema does not model (e.g. ``replaygain.backend``) survive
        the round-trip. Only the fields the editor actually changed are applied;
        everything else in the file — modeled or not — is left untouched. A
        brand-new file (none on disk yet) is written in full from the model.

        Args:
            config_path: Path to write the config file.
            config: The configuration to save.

        Raises:
            OSError: If the file cannot be written.
            ValueError: If an existing config file cannot be parsed for merge.
        """
        incoming = self._schema_to_yaml_dict(config)

        existing_raw: dict[str, Any] = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                try:
                    loaded = yaml.safe_load(f)
                except yaml.YAMLError as e:
                    # Refuse to clobber a file we can't parse — that would drop
                    # the very keys this merge exists to preserve.
                    raise ValueError(
                        f"Failed to parse existing config for merge: {e}"
                    )
            if isinstance(loaded, dict):
                existing_raw = loaded

        if existing_raw:
            baseline = self._schema_to_yaml_dict(
                self._yaml_dict_to_schema(existing_raw)
            )
            merged = self._merge_changes(existing_raw, baseline, incoming)
            yaml_content = yaml.dump(
                merged,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        else:
            # No existing file (or empty/non-mapping): write the full model.
            yaml_content = self.serialize_config(config)

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, "w") as f:
            f.write(yaml_content)

        logger.info(f"Saved beets config to: {config_path}")

    def get_default_config(
        self, directory: str = "", library: str = ""
    ) -> BeetsConfigSchema:
        """Create a configuration with all default values.

        Args:
            directory: Path to the music library directory.
            library: Path to the beets database file.

        Returns:
            BeetsConfigSchema with all defaults populated.
        """
        return BeetsConfigSchema(
            directory=directory,
            library=library,
        )
