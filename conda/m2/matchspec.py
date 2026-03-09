# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
"""Context-free MatchSpec parser and wrapper implementation.

This module provides a MatchSpec implementation that does not require access to
``context.plugin_manager`` to parse package extensions, and does not require
``context.known_subdirs`` for channel/subdir disambiguation. Both are passed in
explicitly (or use local defaults).
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from os.path import basename

from ..base.constants import (
    CONDA_PACKAGE_EXTENSION_V1,
    CONDA_PACKAGE_EXTENSION_V2,
    KNOWN_SUBDIRS,
)
from ..common.path import expand, strip_pkg_extension, url_to_path
from ..common.url import is_url, path_to_url, unquote
from ..exceptions import InvalidMatchSpec, InvalidSpec
from ..m2.version import BuildNumberMatch, VersionSpec
from ..models.channel import Channel
from ..models.match_spec import (
    CaseInsensitiveStrMatch,
    ChannelMatch,
    FeatureMatch,
    GlobLowerStrMatch,
    GlobStrMatch,
)
from ..models.match_spec import MatchSpec as _LegacyMatchSpec

_DEFAULT_PACKAGE_EXTENSIONS = (CONDA_PACKAGE_EXTENSION_V2, CONDA_PACKAGE_EXTENSION_V1)


def _normalize_known_subdirs(
    known_subdirs: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if known_subdirs is None:
        return tuple(KNOWN_SUBDIRS)
    return tuple(known_subdirs)


def _normalize_package_extensions(
    package_extensions: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if package_extensions is None:
        return _DEFAULT_PACKAGE_EXTENSIONS
    return tuple(package_extensions)


def _has_package_extension(spec_str: str, package_extensions: tuple[str, ...]) -> bool:
    for ext in package_extensions:
        if spec_str.endswith(ext):
            return True
    return False


def _parse_version_plus_build(v_plus_b):
    parts = re.search(
        r"((?:.+?)[^><!,|]?)(?:(?<![=!|,<>~])(?:[ =])([^-=,|<>~]+?))?$", v_plus_b
    )
    if parts:
        version, build = parts.groups()
        build = build and build.strip()
    else:
        version, build = v_plus_b, None
    return version and version.replace(" ", ""), build


def _parse_legacy_dist(dist_str):
    dist_str, _ = strip_pkg_extension(dist_str)
    name, version, build = dist_str.rsplit("-", 2)
    return name, version, build


def _parse_channel(channel_val):
    if not channel_val:
        return None, None
    chn = Channel(channel_val)
    channel_name = chn.name or chn.base_url
    return channel_name, chn.subdir


def _sanitize_version_str(version: str, build: str | None) -> str:
    if version in ("==", "="):
        return version

    if not version.startswith("="):
        return version

    version_without_equals = version.lstrip("=")

    if version.startswith("==") and build is None:
        return version_without_equals

    if not any(char in version_without_equals for char in "=,|"):
        if build is None and not version_without_equals.endswith("*"):
            return version_without_equals + "*"
        return version_without_equals

    return version


_PARSE_CACHE = {}


def _parse_spec_str(
    spec_str,
    known_subdirs: tuple[str, ...] | list[str] | None = None,
    package_extensions: tuple[str, ...] | list[str] | None = None,
):
    known_subdirs_t = _normalize_known_subdirs(known_subdirs)
    package_extensions_t = _normalize_package_extensions(package_extensions)
    cache_key = (spec_str, known_subdirs_t, package_extensions_t)
    cached_result = _PARSE_CACHE.get(cache_key)
    if cached_result:
        return cached_result

    original_spec_str = spec_str

    if spec_str.endswith("@"):
        feature_name = spec_str[:-1]
        result = {
            "name": "*",
            "track_features": (feature_name,),
        }
        _PARSE_CACHE[cache_key] = result
        return result

    if "#" in spec_str:
        ndx = spec_str.index("#")
        spec_str, _ = spec_str[:ndx], spec_str[ndx:]
        spec_str.strip()

    spec_split = spec_str.split(" if ", 1)
    spec_str = spec_split[0]

    if _has_package_extension(spec_str, package_extensions_t):
        if not is_url(spec_str):
            spec_str = unquote(path_to_url(expand(spec_str)))

        channel = Channel(spec_str)
        if channel.subdir:
            name, version, build = _parse_legacy_dist(channel.package_filename)
            result = {
                "channel": channel.canonical_name,
                "subdir": channel.subdir,
                "name": name,
                "version": version,
                "build": build,
                "fn": channel.package_filename,
                "url": spec_str,
            }
        else:
            if spec_str.startswith("file://"):
                path_or_url = url_to_path(spec_str)
            else:
                path_or_url = spec_str

            result = {
                "name": "*",
                "fn": basename(path_or_url),
                "url": spec_str,
            }
        _PARSE_CACHE[cache_key] = result
        return result

    brackets = {}
    m3 = re.match(r".*(?:(\[.*\]))", spec_str)
    if m3:
        brackets_str = m3.groups()[0]
        spec_str = spec_str.replace(brackets_str, "")
        brackets_str = brackets_str[1:-1]
        m3b = re.finditer(
            r'([a-zA-Z0-9_-]+?)=(["\']?)([^\'\"]*?)(\2)(?:[, ]|$)', brackets_str
        )
        for match in m3b:
            key, _, value, _ = match.groups()
            if not key or not value:
                raise InvalidMatchSpec(
                    original_spec_str, "key-value mismatch in brackets"
                )
            if key == "version" and value:
                value = _sanitize_version_str(value, match.groupdict().get("build"))
            brackets[key] = value

    m4 = re.match(r".*(?:(\(.*\)))", spec_str)
    parens = {}
    if m4:
        parens_str = m4.groups()[0]
        spec_str = spec_str.replace(parens_str, "")
        parens_str = parens_str[1:-1]
        m4b = re.finditer(
            r'([a-zA-Z0-9_-]+?)=(["\']?)([^\'\"]*?)(\2)(?:[, ]|$)', parens_str
        )
        for match in m4b:
            key, _, value, _ = match.groups()
            parens[key] = value
        if "optional" in parens_str:
            parens["optional"] = True

    m5 = spec_str.rsplit(":", 2)
    m5_len = len(m5)
    if m5_len == 3:
        channel_str, namespace, spec_str = m5
    elif m5_len == 2:
        namespace, spec_str = m5
        channel_str = None
    elif m5_len:
        spec_str = m5[0]
        channel_str, namespace = None, None
    else:
        raise NotImplementedError()
    channel, subdir = _parse_channel(channel_str)
    if "channel" in brackets:
        b_channel, b_subdir = _parse_channel(brackets.pop("channel"))
        if b_channel:
            channel = b_channel
        if b_subdir:
            subdir = b_subdir
    if "subdir" in brackets:
        subdir = brackets.pop("subdir")

    m3 = re.match(r"([^ =<>!~]+)?([><!=~ ].+)?", spec_str)
    if m3:
        name, spec_str = m3.groups()
        if name is None:
            raise InvalidMatchSpec(
                original_spec_str, f"no package name found in '{spec_str}'"
            )
    else:
        raise InvalidMatchSpec(original_spec_str, "no package name found")

    spec_str = spec_str and spec_str.strip()
    if spec_str:
        if "[" in spec_str:
            raise InvalidMatchSpec(
                original_spec_str, "multiple brackets sections not allowed"
            )

        version, build = _parse_version_plus_build(spec_str)
        version = _sanitize_version_str(version, build)
    else:
        version, build = None, None

    components = {}
    components["name"] = name or "*"

    if channel is not None:
        components["channel"] = channel
    if subdir is not None:
        components["subdir"] = subdir
    if namespace is not None:
        pass
    if version is not None:
        components["version"] = version
    if build is not None:
        components["build"] = build

    if "name" in components and "name" in brackets:
        msg = (
            f"'name' specified both inside ({brackets['name']}) and outside "
            f"({components['name']}) of brackets. The value outside of brackets "
            f"({components['name']}) will be used."
        )
        warnings.warn(msg, UserWarning)
        del brackets["name"]
    components.update(brackets)
    components["_original_spec_str"] = original_spec_str
    _PARSE_CACHE[cache_key] = components
    return components


class MatchSpec:
    FIELD_NAMES = _LegacyMatchSpec.FIELD_NAMES
    FIELD_NAMES_SET = _LegacyMatchSpec.FIELD_NAMES_SET
    _MATCHER_CACHE = _LegacyMatchSpec._MATCHER_CACHE
    _default_known_subdirs = tuple(KNOWN_SUBDIRS)
    _default_package_extensions = _DEFAULT_PACKAGE_EXTENSIONS

    def __new__(cls, spec_arg=None, **kwargs):
        if isinstance(spec_arg, cls) and not kwargs:
            return spec_arg
        return super().__new__(cls)

    def __init__(self, spec_arg=None, **kwargs):
        if "_inner" in self.__dict__:
            return

        known_subdirs = kwargs.pop("known_subdirs", None)
        package_extensions = kwargs.pop("package_extensions", None)
        known_subdirs_t = (
            _normalize_known_subdirs(known_subdirs)
            if known_subdirs is not None
            else self._default_known_subdirs
        )
        package_extensions_t = (
            _normalize_package_extensions(package_extensions)
            if package_extensions is not None
            else self._default_package_extensions
        )
        self._known_subdirs = known_subdirs_t
        self._package_extensions = package_extensions_t

        try:
            if spec_arg is not None:
                if isinstance(spec_arg, MatchSpec) and not kwargs:
                    self._inner = spec_arg._inner
                elif isinstance(spec_arg, MatchSpec):
                    self._inner = _LegacyMatchSpec(spec_arg._inner, **kwargs)
                elif isinstance(spec_arg, str):
                    parsed = _parse_spec_str(
                        spec_arg,
                        known_subdirs=known_subdirs_t,
                        package_extensions=package_extensions_t,
                    )
                    if kwargs:
                        parsed = dict(parsed, **kwargs)
                        if set(kwargs) - {"optional", "target"}:
                            parsed.pop("_original_spec_str", None)
                    self._inner = _LegacyMatchSpec(**parsed)
                elif isinstance(spec_arg, Mapping):
                    parsed = dict(spec_arg, **kwargs)
                    self._inner = _LegacyMatchSpec(**parsed)
                elif hasattr(spec_arg, "to_match_spec"):
                    spec = spec_arg.to_match_spec()
                    if isinstance(spec, MatchSpec):
                        self._inner = _LegacyMatchSpec(spec._inner, **kwargs)
                    else:
                        self._inner = _LegacyMatchSpec(spec, **kwargs)
                else:
                    self._inner = _LegacyMatchSpec(spec_arg, **kwargs)
            else:
                self._inner = _LegacyMatchSpec(**kwargs)
        except InvalidSpec as e:
            msg = ""
            if spec_arg is not None:
                msg += f"{spec_arg}"
            if kwargs:
                msg += " " + ", ".join(f"{k}={v}" for k, v in kwargs.items())
            raise InvalidMatchSpec(msg, details=e) from e

    @classmethod
    def configure_parser(
        cls,
        *,
        known_subdirs: tuple[str, ...] | list[str] | None = None,
        package_extensions: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        if known_subdirs is not None:
            cls._default_known_subdirs = _normalize_known_subdirs(known_subdirs)
        if package_extensions is not None:
            cls._default_package_extensions = _normalize_package_extensions(
                package_extensions
            )

    @classmethod
    def from_dist_str(
        cls,
        dist_str,
        *,
        known_subdirs: tuple[str, ...] | list[str] | None = None,
        package_extensions: tuple[str, ...] | list[str] | None = None,
    ):
        known_subdirs_t = (
            _normalize_known_subdirs(known_subdirs)
            if known_subdirs is not None
            else cls._default_known_subdirs
        )
        package_extensions_t = (
            _normalize_package_extensions(package_extensions)
            if package_extensions is not None
            else cls._default_package_extensions
        )

        parts = {}
        for ext in package_extensions_t:
            if dist_str.endswith(ext):
                dist_str = dist_str[: -len(ext)]
                break

        if "::" in dist_str:
            channel_subdir_str, dist_str = dist_str.split("::", 1)
            if "/" in channel_subdir_str:
                channel_str, subdir = channel_subdir_str.rsplit("/", 1)
                if subdir not in known_subdirs_t:
                    channel_str = channel_subdir_str
                    subdir = None
                parts["channel"] = channel_str
                if subdir:
                    parts["subdir"] = subdir
            else:
                parts["channel"] = channel_subdir_str

        name, version, build = dist_str.rsplit("-", 2)
        parts.update(
            {
                "name": name,
                "version": version,
                "build": build,
            }
        )
        return cls(
            **parts,
            known_subdirs=known_subdirs_t,
            package_extensions=package_extensions_t,
        )

    @classmethod
    def _from_inner(cls, inner):
        obj = cls.__new__(cls)
        obj._inner = inner
        obj._known_subdirs = cls._default_known_subdirs
        obj._package_extensions = cls._default_package_extensions
        return obj

    @classmethod
    def merge(cls, match_specs, union=False):
        inners = tuple(cls(s)._inner for s in match_specs if s)
        merged = _LegacyMatchSpec.merge(inners, union=union)
        return tuple(cls._from_inner(s) for s in merged)

    @classmethod
    def union(cls, match_specs):
        return cls.merge(match_specs, union=True)

    @property
    def _match_components(self):
        return self._inner._match_components

    def __contains__(self, field):
        return field in self._inner

    def __str__(self):
        return str(self._inner)

    def __repr__(self):
        return repr(self._inner)

    def __eq__(self, other):
        if isinstance(other, MatchSpec):
            return self._inner == other._inner
        return False

    def __hash__(self):
        return hash(self._inner)

    def __getattr__(self, item):
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(item)
        return getattr(inner, item)

    def _merge(self, other, union=False):
        other_inner = MatchSpec(other)._inner
        merged = self._inner._merge(other_inner, union=union)
        return self._from_inner(merged)


_implementors = {
    "channel": ChannelMatch,
    "name": GlobLowerStrMatch,
    "version": VersionSpec,
    "build": GlobStrMatch,
    "build_number": BuildNumberMatch,
    "track_features": FeatureMatch,
    "features": FeatureMatch,
    "license": CaseInsensitiveStrMatch,
    "license_family": CaseInsensitiveStrMatch,
}
