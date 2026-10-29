# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only local discovery and Kernel policy prototype. No provider imports.

The discovery envelope wraps, rather than changes, mpm-release-catalog-v1.
It is metadata, not a verified artifact store, installed database or trust root.
"""
import argparse
import copy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

from mpm_selection import (Catalog, ResolutionError,
                           canonical, components, parse_selector, require, resolve, text)

FORMAT = "mpm-discovery-catalog-v1"
BASE_FORMAT = "mpm-kernel-base-context-v1"
AREAS = ("base", "system", "kernel", "ports")
MAX_METADATA_BYTES = 8 * 1024 * 1024


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    # Open exactly the named local file; never treat URLs as acquisition requests.
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_METADATA_BYTES + 1)
    require(len(raw) <= MAX_METADATA_BYTES, "metadata exceeds prototype size limit")
    value = json.loads(raw, object_pairs_hook=_pairs)
    canonical(value)  # Also reject NaN/Infinity in opaque provider evidence.
    return value


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
            "invalid metadata fields")


def words(value):
    require(isinstance(value, list) and all(text(item) for item in value), "expected text list")
    require(len(set(value)) == len(value), "duplicate text entry")


def folded(value):
    return unicodedata.normalize("NFKC", value).casefold()


def compare_versions(left, right):
    left, right = components(left), components(right)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return (left > right) - (left < right)


@dataclass(frozen=True)
class Package:
    name: str
    summary: str
    description: str
    aliases: tuple
    category: str
    releases: Catalog
    kernel: dict

    def to_dict(self):
        return dict(area=self.releases.area, name=self.name, summary=self.summary,
                    description=self.description, aliases=list(self.aliases), category=self.category,
                    sources=copy.deepcopy(self.releases.sources),
                    channel=self.releases.channel, platform=self.releases.platform)


@dataclass(frozen=True)
class DiscoveryCatalog:
    publisher: str
    revision: str
    packages: tuple
    digest: str

    @classmethod
    def from_dict(cls, value):
        fields(value, ("format", "publisher", "revision", "complete", "packages"))
        require(value["format"] == FORMAT, "unsupported discovery catalog format")
        require(text(value["publisher"]) and text(value["revision"]), "missing publisher/revision")
        require(type(value["complete"]) is bool, "complete must be boolean")
        require(value["complete"], "incomplete local catalog; explicitly acquire metadata first")
        require(isinstance(value["packages"], list), "packages must be a list")
        packages, keys = [], set()
        for row in value["packages"]:
            fields(row, ("name", "summary", "description", "aliases", "category", "releases"), ("kernel",))
            require(all(text(row[key]) for key in ("name", "summary", "description", "category")),
                    "missing searchable package metadata")
            words(row["aliases"])
            releases = Catalog.from_dict(row["releases"])
            require(releases.area in AREAS, "unknown package area")
            require(all(c.name == row["name"] for c in releases.candidates), "mixed package names")
            # Validate names even for an offered package with no current builds.
            require(parse_selector(row["name"]).kind == "latest", "package name must be unqualified")
            key = releases.area, row["name"]
            require(key not in keys, "duplicate package; combine its named sources explicitly")
            keys.add(key)
            kernel = row.get("kernel", {})
            if releases.area == "kernel":
                require(row["name"] == "linux", "prototype Kernel package must be linux")
                fields(kernel, ("releases",))
                require(isinstance(kernel["releases"], dict), "invalid Kernel release metadata")
                require(set(kernel["releases"]) == {c.release_id for c in releases.candidates},
                        "Kernel classifications must cover exactly the offered releases")
                for release_id, policy in kernel["releases"].items():
                    fields(policy, ("active_lts", "upstream_stable"))
                    require(all(type(v) is bool for v in policy.values()), "Kernel labels must be booleans")
                for candidate in releases.candidates:
                    require(candidate.version_scheme == "dotted-v1" and
                            len(components(candidate.upstream_version)) in (2, 3),
                            "prototype Kernel versions must be numeric major.minor[.patch]")
                    policy = kernel["releases"][candidate.release_id]
                    require(not policy["active_lts"] or policy["upstream_stable"],
                            "active LTS must be an upstream stable release")
                    require(not policy["upstream_stable"] or candidate.stability == "stable",
                            "upstream stable classification contradicts release stability")
            else:
                require("kernel" not in row, "Kernel policy on another area")
            packages.append(Package(row["name"], row["summary"], row["description"],
                                    tuple(row["aliases"]), row["category"], releases, copy.deepcopy(kernel)))
        return cls(value["publisher"], value["revision"], tuple(packages), digest(value))

    def package(self, area, name):
        rows = [p for p in self.packages if p.name == name and p.releases.area == area]
        require(rows, "package absent from this complete local catalog", ResolutionError)
        return rows[0]

    def search(self, query, *, area=None, exact=False, description=False):
        require(query and all(text(term) for term in query), "search needs literal text", ResolutionError)
        require(not exact or len(query) == 1, "exact search takes one literal name", ResolutionError)
        terms = [folded(term) for term in query]
        hits = []
        for package in self.packages:
            if area is not None and package.releases.area != area:
                continue
            names = [folded(package.name), *(folded(a) for a in package.aliases)]
            searchable = names + ([folded(package.summary), folded(package.description)] if description else [])
            if exact:
                matched = terms[0] in names
            else:
                matched = all(any(term in field for field in searchable) for term in terms)
            if not matched:
                continue
            rank = (0 if len(terms) == 1 and terms[0] == names[0] else
                    1 if len(terms) == 1 and terms[0] in names else
                    2 if all(any(n.startswith(t) for n in names) for t in terms) else
                    3 if all(any(t in n for n in names) for t in terms) else 4)
            hits.append((rank, package))
        hits.sort(key=lambda pair: (pair[0], folded(pair[1].name), pair[1].name, pair[1].releases.area))
        return [dict(p.to_dict(), match=("name-exact", "alias-exact", "prefix", "substring", "description")[r])
                for r, p in hits]


def base_context(value):
    fields(value, ("format", "base", "platform", "kernel_min", "kernel_max"))
    require(value["format"] == BASE_FORMAT, "unsupported Base context format")
    fields(value["base"], ("release", "artifact"))
    require(all(text(v) for v in value["base"].values()) and text(value["platform"]),
            "Base context needs exact selected identity and platform")
    require(compare_versions(value["kernel_min"], value["kernel_max"]) <= 0,
            "Base kernel range is inverted")
    return copy.deepcopy(value)


def resolve_kernel(catalog, context, policy, *, series=None, release=None):
    """Filter by policy AND declared selected-Base bounds, then reuse the resolver."""
    context = base_context(context)
    package = catalog.package("kernel", "linux")
    view = package.releases
    require(context["platform"] == view.platform, "selected Base platform differs", ResolutionError)
    require(policy in ("pinned", "latest-lts", "latest-upstream"), "unknown Kernel policy", ResolutionError)
    if policy == "pinned":
        require((series is None) != (release is None), "pinned needs exactly one series or release", ResolutionError)
        if series is not None:
            require(len(components(series)) == 2, "pinned series needs major.minor", ResolutionError)
        request = "linux@" + series if series is not None else "linux@=" + release
    else:
        require(series is None and release is None, "tracking policy cannot take a pin", ResolutionError)
        request = "linux"
    pool, excluded = [], []
    for candidate in view.candidates:
        labels = package.kernel["releases"][candidate.release_id]
        eligible = candidate.stability == "stable" and labels["upstream_stable"]
        if policy == "latest-lts":
            eligible = eligible and labels["active_lts"]
        if series is not None:
            eligible = eligible and components(candidate.upstream_version)[:2] == components(series)
        if release is not None:
            eligible = eligible and candidate.release_id == release
        if not eligible:
            continue
        compatible = (compare_versions(candidate.upstream_version, context["kernel_min"]) >= 0 and
                      compare_versions(candidate.upstream_version, context["kernel_max"]) <= 0 and
                      candidate.compatibility != "incompatible")
        if compatible:
            pool.append(candidate)
        else:
            excluded.append(dict(release_id=candidate.release_id, artifact=candidate.artifact,
                                 reason="outside selected Base bounds or declared incompatible"))
    require(pool, "no eligible Kernel for policy and selected Base; no policy/Base fallback", ResolutionError)
    selection = resolve(replace(view, candidates=tuple(pool)), request)
    return dict(policy=policy, request=request, base=context, base_context_digest=digest(context),
                discovery_digest=catalog.digest, selection=selection.to_dict(),
                excluded=excluded,
                note="Read-only declared compatibility plan; no runtime proof, install or activation.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("search", "show", "versions", "resolve-kernel"):
        command = sub.add_parser(action)
        command.add_argument("--catalog", required=True, help="explicit local discovery envelope")
        command.add_argument("--area", choices=AREAS, required=action in ("show", "versions"))
        command.add_argument("--json", action="store_true", help="machine-readable result")
        if action == "search":
            command.add_argument("query", nargs="+")
            command.add_argument("--exact", action="store_true")
            command.add_argument("--description", action="store_true")
        elif action in ("show", "versions"):
            command.add_argument("name")
        else:
            command.add_argument("--base-context", required=True, help="declared selected-Base bounds")
            command.add_argument("--policy", choices=("pinned", "latest-lts", "latest-upstream"), required=True)
            pins = command.add_mutually_exclusive_group()
            pins.add_argument("--series")
            pins.add_argument("--release")
    args = parser.parse_args(argv)
    try:
        catalog = DiscoveryCatalog.from_dict(read_json(args.catalog))
        result = dict(publisher=catalog.publisher, revision=catalog.revision, digest=catalog.digest,
                      note="Local catalog metadata only; payload availability and installed state not probed.")
        if args.action == "search":
            result["matches"] = catalog.search(args.query, area=args.area, exact=args.exact,
                                               description=args.description)
        elif args.action in ("show", "versions"):
            package = catalog.package(args.area, args.name)
            result["package"] = package.to_dict()
            if args.action == "versions":
                result["releases"] = [c.to_dict() for c in package.releases.candidates]
                if package.kernel:
                    result["kernel"] = copy.deepcopy(package.kernel)
        else:
            require(args.area in (None, "kernel"), "Kernel policy needs kernel area")
            result["plan"] = resolve_kernel(catalog, read_json(args.base_context), args.policy,
                                            series=args.series, release=args.release)
        if args.json or args.action != "search":
            print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
        else:
            print(f"Catalog: {catalog.publisher} / {catalog.revision} ({catalog.digest})")
            for row in result["matches"]:
                print(f"{row['area']}/{row['name']}  {row['summary']}  "
                      f"[sources: {', '.join(sorted(row['sources']))}; match: {row['match']}]")
            if not result["matches"]:
                print("No matches in this complete local catalog. Use --description to include descriptions.")
            print(result["note"])
    except (OSError, ValueError, RecursionError) as error:
        print("mpm catalog: " + str(error), file=sys.stderr)
        return 1
    return 0
