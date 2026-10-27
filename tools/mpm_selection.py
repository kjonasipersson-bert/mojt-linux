# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure MPM release selection. No backend commands, files, paths or state writes.

Backend identities/integrity records are opaque JSON data. Adapters provide
finite catalogs; this module owns selectors, release ordering and upgrade policy.
"""
import copy
from dataclasses import dataclass
from functools import cmp_to_key
import hashlib
import json
import re

NAME = r"[A-Za-z_][A-Za-z0-9_+-]*(?:\.[A-Za-z_][A-Za-z0-9_+-]*)*"
COMPONENT = r"(?:0|[1-9][0-9]*)"
DOTTED = COMPONENT + r"(?:\." + COMPONENT + r")*"
RELEASE = r"[A-Za-z0-9][A-Za-z0-9._+-]*"
FORMAT = "mpm-release-catalog-v1"


class SelectorError(ValueError):
    pass


class CatalogError(ValueError):
    pass


class ResolutionError(ValueError):
    pass


class AmbiguousSelection(ResolutionError):
    pass


def require(condition, message, error=CatalogError):
    if not condition:
        raise error(message)


def text(value):
    return isinstance(value, str) and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as error:
        raise CatalogError("catalog must contain finite JSON data") from error


def components(value):
    require(isinstance(value, str) and re.fullmatch(DOTTED, value),
            "dotted-v1 requires numeric components without leading zeros")
    return tuple(int(part) for part in value.split("."))


@dataclass(frozen=True)
class Selector:
    name: str
    kind: str
    value: tuple = ()

    def to_dict(self):
        result = dict(name=self.name, kind=self.kind)
        if self.kind == "series":
            result["components"] = list(self.value)
        elif self.kind == "exact":
            result["release_id"] = self.value[0]
        return result


def parse_selector(value):
    require(isinstance(value, str), "selector must be text", SelectorError)
    parts = value.split("@")
    require(len(parts) in (1, 2) and re.fullmatch(NAME, parts[0]),
            "invalid package name or selector", SelectorError)
    if len(parts) == 1:
        return Selector(parts[0], "latest")
    suffix = parts[1]
    if suffix.startswith("="):
        release = suffix[1:]
        require(re.fullmatch(RELEASE, release), "invalid exact release identifier", SelectorError)
        return Selector(parts[0], "exact", (release,))
    require(re.fullmatch(DOTTED, suffix), "invalid numeric release series", SelectorError)
    return Selector(parts[0], "series", tuple(int(p) for p in suffix.split(".")))


@dataclass(frozen=True)
class Candidate:
    name: str
    release_id: str
    upstream_version: str
    version_scheme: str
    revision_scheme: object
    package_revision: object
    stability: str
    source: str
    backend: str
    artifact: str
    integrity: dict
    compatibility: str = "unknown"
    preferred: bool = False

    @property
    def key(self):
        return self.backend, self.artifact

    @property
    def release_metadata(self):
        return (self.upstream_version, self.version_scheme, self.revision_scheme,
                self.package_revision, self.stability)

    def to_dict(self):
        return copy.deepcopy(self.__dict__)


@dataclass(frozen=True)
class Catalog:
    area: str
    name: str
    channel: str
    platform: str
    sources: dict
    candidates: tuple
    source_preference: tuple
    digest: str

    @classmethod
    def from_dict(cls, value):
        require(isinstance(value, dict), "catalog must be an object")
        required = {"format", "area", "name", "channel", "platform", "sources", "candidates"}
        require(required <= set(value) <= required | {"source_preference"}, "invalid catalog fields")
        require(value["format"] == FORMAT, "unsupported release catalog format")
        for field in ("area", "name", "channel", "platform"):
            require(text(value[field]), "missing catalog " + field)
        require(isinstance(value["sources"], dict) and value["sources"], "catalog needs named sources")
        sources = copy.deepcopy(value["sources"])
        for name, source in sources.items():
            require(text(name) and isinstance(source, dict) and set(source) == {"backend", "identity"},
                    "invalid source record")
            require(text(source["backend"]) and isinstance(source["identity"], dict) and source["identity"],
                    "source needs backend and opaque identity evidence")
        preferred = value.get("source_preference", [])
        require(isinstance(preferred, list) and all(isinstance(s, str) and s in sources for s in preferred)
                and len(set(preferred)) == len(preferred), "invalid source preference")
        require(isinstance(value["candidates"], list), "candidates must be a list")
        candidates, releases, artifacts, compatibility = [], {}, {}, {}
        fields = {"name", "release_id", "upstream_version", "version_scheme", "stability",
                  "source", "artifact", "integrity"}
        optional = {"revision_scheme", "package_revision", "compatibility", "preferred"}
        for raw in value["candidates"]:
            require(isinstance(raw, dict) and fields <= set(raw) <= fields | optional,
                    "invalid candidate fields")
            require(isinstance(raw["name"], str) and re.fullmatch(NAME, raw["name"]), "invalid candidate name")
            require(isinstance(raw["release_id"], str) and re.fullmatch(RELEASE, raw["release_id"]),
                    "invalid canonical release identifier")
            require(text(raw["upstream_version"]) and raw["version_scheme"] in ("dotted-v1", "opaque-v1"),
                    "unknown version adapter")
            require(raw["stability"] in ("stable", "preview", "unknown"), "invalid stability classification")
            require(isinstance(raw["source"], str) and raw["source"] in sources, "unknown source")
            require(text(raw["artifact"]) and isinstance(raw["integrity"], dict) and raw["integrity"],
                    "artifact needs identity and opaque integrity evidence")
            require(raw.get("compatibility", "unknown") in ("verified", "unknown", "incompatible"),
                    "invalid declared compatibility")
            require(type(raw.get("preferred", False)) is bool, "preferred must be boolean")
            rev, scheme = raw.get("package_revision"), raw.get("revision_scheme")
            require((rev is None and scheme is None) or
                    (type(rev) is int and rev >= 0 and scheme == "mojt-r-v1"), "unsupported revision adapter")
            if raw["version_scheme"] == "dotted-v1":
                components(raw["upstream_version"])
            expected = raw["upstream_version"] + ("-r" + str(rev) if rev is not None else "")
            require(raw["release_id"] == expected, "release identifier differs from declared version/revision")
            row = dict(raw, backend=sources[raw["source"]]["backend"],
                       revision_scheme=scheme, package_revision=rev)
            row["integrity"] = copy.deepcopy(row["integrity"])
            candidate = Candidate(**row)
            release_key = candidate.name, candidate.release_id
            require(release_key not in releases or releases[release_key] == candidate.release_metadata,
                    "contradictory metadata for one package release")
            releases[release_key] = candidate.release_metadata
            signature = canonical(candidate.integrity)
            require(candidate.key not in artifacts or artifacts[candidate.key] == signature,
                    "conflicting integrity evidence for one backend artifact")
            artifacts[candidate.key] = signature
            require(candidate.key not in compatibility or compatibility[candidate.key] == candidate.compatibility,
                    "conflicting compatibility declarations for one backend artifact")
            compatibility[candidate.key] = candidate.compatibility
            candidates.append(candidate)
        digest = hashlib.sha256(canonical(value).encode()).hexdigest()
        return cls(value["area"], value["name"], value["channel"], value["platform"], sources,
                   tuple(candidates), tuple(preferred), "sha256:" + digest)


def compare_releases(a, b):
    require(a.version_scheme == b.version_scheme == "dotted-v1",
            "version ordering requires a supported adapter; choose an exact release", ResolutionError)
    require(a.revision_scheme == b.revision_scheme, "cannot compare unrelated revision schemes", ResolutionError)
    left, right = list(components(a.upstream_version)), list(components(b.upstream_version))
    size = max(len(left), len(right))
    left += [0] * (size - len(left))
    right += [0] * (size - len(right))
    left = (left, a.package_revision if a.package_revision is not None else 0)
    right = (right, b.package_revision if b.package_revision is not None else 0)
    return (left > right) - (left < right)


@dataclass(frozen=True)
class Selection:
    selector: Selector
    area: str
    catalog_name: str
    channel: str
    platform: str
    catalog_digest: str
    candidate: Candidate
    provenance: tuple

    def to_dict(self):
        return dict(selector=self.selector.to_dict(),
                    catalog=dict(area=self.area, name=self.catalog_name, channel=self.channel,
                                 platform=self.platform, digest=self.catalog_digest),
                    candidate=self.candidate.to_dict(), provenance=copy.deepcopy(list(self.provenance)),
                    note="Declared catalog evidence; runtime compatibility is not verified by resolution.")

    @classmethod
    def from_dict(cls, value):
        require(isinstance(value, dict) and set(value) ==
                {"selector", "catalog", "candidate", "provenance", "note"}, "invalid saved selection")
        selector = selector_from_dict(value["selector"])
        binding, row, provenance = value["catalog"], value["candidate"], value["provenance"]
        require(isinstance(binding, dict) and set(binding) == {"area", "name", "channel", "platform", "digest"},
                "invalid saved catalog binding")
        require(isinstance(binding["digest"], str) and re.fullmatch(r"sha256:[0-9a-f]{64}", binding["digest"]),
                "invalid saved catalog digest")
        require(isinstance(provenance, list) and provenance, "missing saved provenance")
        sources = {}
        for p in provenance:
            require(isinstance(p, dict) and set(p) == {"source", "backend", "identity"}
                    and isinstance(p["source"], str) and p["source"] not in sources, "invalid saved provenance")
            sources[p["source"]] = dict(backend=p["backend"], identity=p["identity"])
        require(isinstance(row, dict) and row.get("source") in sources and
                row.get("backend") == sources[row["source"]]["backend"], "saved artifact backend differs")
        raw = {k: v for k, v in row.items() if k != "backend"}
        catalog = Catalog.from_dict(dict(format=FORMAT, **{k: binding[k] for k in
            ("area", "name", "channel", "platform")}, sources=sources, candidates=[raw]))
        chosen = resolve(catalog, selector)
        require(all(p["backend"] == chosen.candidate.backend for p in provenance), "saved provenance backend differs")
        return cls(selector, catalog.area, catalog.name, catalog.channel, catalog.platform,
                   binding["digest"], chosen.candidate, tuple(copy.deepcopy(provenance)))


def selector_from_dict(value):
    require(isinstance(value, dict), "invalid saved selector", SelectorError)
    kind = value.get("kind")
    fields = {"name", "kind"} | ({"components"} if kind == "series" else
                                  {"release_id"} if kind == "exact" else set())
    require(set(value) == fields, "invalid saved selector fields", SelectorError)
    parts = value.get("components", [])
    require(isinstance(parts, list), "invalid saved series", SelectorError)
    selector = Selector(value["name"], kind,
                        tuple(parts) if kind == "series" else
                        (value["release_id"],) if kind == "exact" else ())
    return parse_selector(render_selector(selector))


def installed_view(catalog, selections):
    """Construct an installed-only view. Old build preferences never break ties."""
    sources, candidates = {}, []
    for selection in selections:
        require((selection.area, selection.catalog_name, selection.channel, selection.platform) ==
                (catalog.area, catalog.name, catalog.channel, catalog.platform), "installed catalog binding differs")
        for p in selection.provenance:
            sid = hashlib.sha256(canonical(p).encode()).hexdigest()
            sources[sid] = dict(backend=p["backend"], identity=copy.deepcopy(p["identity"]))
            row = selection.candidate.to_dict()
            row.pop("backend")
            row.update(source=sid, preferred=False)
            candidates.append(row)
    # Empty views still need a source record for the normal catalog validator.
    return Catalog.from_dict(dict(format=FORMAT, area=catalog.area, name=catalog.name,
        channel=catalog.channel, platform=catalog.platform, sources=sources or catalog.sources,
        candidates=candidates))


def resolve(catalog, request, *, platform=None):
    require(isinstance(catalog, Catalog), "expected a validated Catalog")
    selector = parse_selector(request) if isinstance(request, str) else request
    require(isinstance(selector, Selector) and parse_selector(render_selector(selector)) == selector,
            "invalid structured selector", SelectorError)
    require(platform is None or platform == catalog.platform, "catalog platform differs from request", ResolutionError)
    matches = []
    for c in catalog.candidates:
        if c.name != selector.name or c.compatibility == "incompatible":
            continue
        if selector.kind == "exact":
            eligible = c.release_id == selector.value[0]
        elif c.stability != "stable":
            eligible = False
        elif selector.kind == "latest":
            eligible = True
        else:
            eligible = (c.version_scheme == "dotted-v1" and
                        components(c.upstream_version)[:len(selector.value)] == selector.value)
        if eligible:
            matches.append(c)
    require(matches, "no eligible catalog release for " + render_selector(selector), ResolutionError)
    if selector.kind != "exact":
        # Validate every pair, not just sort's comparisons: heterogeneous revision
        # models or opaque versions must not be quietly discarded by list order.
        schemes = {(c.version_scheme, c.revision_scheme) for c in matches}
        require(len(schemes) == 1 and next(iter(schemes))[0] == "dotted-v1",
                "version ordering requires a common supported adapter; choose an exact release", ResolutionError)
        best = max(matches, key=cmp_to_key(compare_releases))
        matches = [c for c in matches if compare_releases(c, best) == 0]
        require(len({c.release_id for c in matches}) == 1,
                "equal ordering keys for different exact releases; choose an exact release", AmbiguousSelection)
    # Choose build only AFTER choosing the release. No backend digest sorting.
    preferred = [c for c in matches if c.preferred]
    if preferred:
        require(len({c.key for c in preferred}) == 1, "multiple preferred builds for one release", AmbiguousSelection)
        chosen = preferred[0]
    elif len({c.key for c in matches}) == 1:
        chosen = matches[0]
    else:
        chosen = None
        for source in catalog.source_preference:
            rows = [c for c in matches if c.source == source]
            if rows:
                require(len({c.key for c in rows}) == 1,
                        "preferred source contains multiple builds", AmbiguousSelection)
                chosen = rows[0]
                break
        require(chosen is not None, "multiple builds; catalog needs an explicit build/source preference", AmbiguousSelection)
    rows = [c for c in matches if c.key == chosen.key]
    # A contradiction in the declared host status is not evidence of success.
    require(len({c.compatibility for c in rows}) == 1,
            "conflicting compatibility declarations for one artifact", AmbiguousSelection)
    provenance = tuple(dict(source=s, **copy.deepcopy(catalog.sources[s])) for s in sorted({c.source for c in rows}))
    return Selection(selector, catalog.area, catalog.name, catalog.channel, catalog.platform,
                     catalog.digest, chosen, provenance)


def render_selector(selector):
    require(isinstance(selector, Selector) and isinstance(selector.name, str) and
            isinstance(selector.value, tuple), "invalid structured selector", SelectorError)
    if selector.kind == "latest" and selector.value == ():
        return selector.name
    if selector.kind == "exact" and len(selector.value) == 1 and isinstance(selector.value[0], str):
        return selector.name + "@=" + selector.value[0]
    if selector.kind == "series" and selector.value and all(type(p) is int and p >= 0 for p in selector.value):
        return selector.name + "@" + ".".join(map(str, selector.value))
    raise SelectorError("invalid structured selector")


@dataclass(frozen=True)
class UpgradePlan:
    before: Selection
    after: Selection
    changed: bool
    reason: str


def plan_upgrade(catalog, current):
    require(isinstance(catalog, Catalog), "expected a validated Catalog")
    require(isinstance(current, Selection), "upgrade needs a resolved current selection")
    require((catalog.area, catalog.name, catalog.channel, catalog.platform) ==
            (current.area, current.catalog_name, current.channel, current.platform),
            "catalog binding changed; adopt it explicitly", ResolutionError)
    if current.selector.kind == "exact":
        return UpgradePlan(current, current, False, "exact artifact and closure pinned")
    candidate = resolve(catalog, current.selector)
    order = compare_releases(candidate.candidate, current.candidate)
    require(order >= 0, "catalog proposes a downgrade", ResolutionError)
    require(order != 0 or candidate.candidate.release_id == current.candidate.release_id,
            "equal ordering keys for different exact releases; choose explicitly", AmbiguousSelection)
    if candidate.candidate.key == current.candidate.key:
        require(canonical(candidate.candidate.integrity) == canonical(current.candidate.integrity),
                "integrity changed for retained backend artifact", ResolutionError)
        if candidate.candidate.release_id == current.candidate.release_id:
            return UpgradePlan(current, current, False, "same retained artifact")
    return UpgradePlan(current, candidate, True, "release upgrade" if order else "same-release build replacement")
