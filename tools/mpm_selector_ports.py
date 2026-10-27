# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure Ports selector state/alias planning; installed records are opaque backend data.

No filesystem access or backend execution. The transaction adapter supplies
resolved (installed-id, record, Selection) tuples and publishes the result.
"""
import copy
import hashlib

import mpm_selection as core

FORMAT = 3
CAPABILITIES = {"reader": "mpm-ports-selectors-v1", "writer": "mpm-ports-selectors-v1"}


def request_id(selection):
    value = dict(selector=selection.selector.to_dict(), area=selection.area,
                 catalog=selection.catalog_name, channel=selection.channel, platform=selection.platform)
    return "selector-" + hashlib.sha256(core.canonical(value).encode()).hexdigest()


def tracked(selection, target):
    return dict(name=selection.selector.name, policy="selector", target=target,
                selector=selection.selector.to_dict(), selection=selection.to_dict())


def validate(state):
    core.require(state.get("capabilities") == CAPABILITIES, "unsupported metadata capabilities")
    catalog = core.Catalog.from_dict(state["release_catalog"])
    core.require(catalog.area == "ports", "catalog belongs to another MPM area")
    for record in state["installed"].values():
        if "release" in record:
            selection = core.Selection.from_dict(record["release"])
            core.require(selection.selector.name == record["name"], "installed release name differs")
    for rid, request in state["requests"].items():
        if request.get("policy") != "selector":
            continue
        core.require(set(request) == {"name", "policy", "target", "selector", "selection"}, "invalid selector request")
        selection = core.Selection.from_dict(request["selection"])
        core.require(rid == request_id(selection) and request["selector"] == selection.selector.to_dict()
                     and request["name"] == selection.selector.name, "selector request identity differs")
        record = state["installed"].get(request["target"])
        core.require(record is not None and "release" in record and record["name"] == request["name"],
                     "selector target missing")
        saved = core.Selection.from_dict(record["release"])
        core.require(saved.candidate.key == selection.candidate.key and
                     saved.candidate.release_id == selection.candidate.release_id and
                     core.canonical(saved.candidate.integrity) == core.canonical(selection.candidate.integrity),
                     "selector target evidence differs")
        core.require((selection.area, selection.catalog_name, selection.channel, selection.platform) ==
                     (catalog.area, catalog.name, catalog.channel, catalog.platform), "request catalog binding differs")


def aliases(state):
    result = {}
    for request in state["requests"].values():
        if request.get("policy") != "selector":
            continue
        selection = core.Selection.from_dict(request["selection"])
        if selection.selector.kind != "series":
            continue
        suffix = ".".join(map(str, selection.selector.value))
        target = request["target"]
        for command in state["installed"][target]["commands"] or []:
            alias = command + "-" + suffix
            core.require(alias not in result, "series alias conflict: " + alias)
            result[alias] = (target, command)
    return result


def keep(state, item):
    key, record, selection = item
    if key in state["installed"]:
        old = state["installed"][key]
        core.require(record["commands"] is None or old["commands"] == record["commands"],
                     "exports for retained object changed")
        if "release" in old:
            saved = core.Selection.from_dict(old["release"])
            core.require(saved.candidate.key == selection.candidate.key and
                         saved.candidate.release_metadata == selection.candidate.release_metadata and
                         core.canonical(saved.candidate.integrity) == core.canonical(selection.candidate.integrity),
                         "release/integrity for retained object changed")
        else:
            old["release"] = selection.to_dict()
    else:
        state["installed"][key] = copy.deepcopy(record)
        state["installed"][key]["release"] = selection.to_dict()
    return key


def metadata(state, catalog, adoptions, attachments):
    """Explicit capability transition; attribute requests stay native unless adopted."""
    result = copy.deepcopy(state)
    result.update(format=FORMAT, capabilities=copy.deepcopy(CAPABILITIES), release_catalog=copy.deepcopy(catalog))
    if "requests" not in result:
        result["requests"] = {}
        result["selection_policy"] = {name: None for name in result["active"]}
    mapping = {}
    for item in attachments:
        core.require(item[0] in result["installed"], "metadata cannot import an artifact")
        keep(result, item)
    for item in adoptions:
        key, record, selection = item
        core.require(key in result["installed"], "adoption target is not installed; install it explicitly")
        core.require(record["name"] == selection.selector.name, "adoption name differs")
        keep(result, item)
        rid = request_id(selection)
        for old_id, request in list(result["requests"].items()):
            if request["name"] == record["name"] and request.get("policy") == "attribute":
                core.require(request["target"] == key, "legacy target differs; activate/install intended target first")
                mapping[old_id] = rid
                del result["requests"][old_id]
        result["requests"][rid] = tracked(selection, key)
        if result["active"].get(record["name"]) == key:
            previous = state.get("selection_policy", {}).get(record["name"])
            # Preserve existing exact pins. Adoption records future request intent,
            # not permission to turn an exact default into a moving default.
            result["selection_policy"][record["name"]] = (
                rid if previous is not None and selection.selector.kind != "exact" else None)
    validate(result)
    return result, mapping


def install(state, items, inactive=False):
    result = copy.deepcopy(state)
    for item in items:
        key, record, selection = item
        first = not any(r["name"] == record["name"] for r in result["installed"].values())
        keep(result, item)
        rid = request_id(selection)
        # Later installs retain artifacts, but do not silently advance an accepted target.
        result["requests"].setdefault(rid, tracked(selection, key))
        if first and not inactive:
            result["active"][record["name"]] = key
            result["selection_policy"][record["name"]] = rid if selection.selector.kind != "exact" else None
    validate(result)
    return result


def activate(state, item, *, literal=False, follow=False):
    result = copy.deepcopy(state)
    key, record, selection = item
    core.require(key in result["installed"], "activation never imports an artifact")
    name = record["name"]
    rid = request_id(selection)
    if literal:
        following = [r for r, request in result["requests"].items()
                     if request["target"] == key and request["name"] == name and
                     (request.get("policy") == "attribute" or request["selector"]["kind"] != "exact")]
        core.require(not follow or len(following) == 1, "--follow needs one unambiguous moving request target")
        policy = following[0] if follow else None
    else:
        core.require(not follow or selection.selector.kind != "exact", "--follow cannot unpin an exact selector")
        keep(result, item)
        result["requests"][rid] = tracked(selection, key)
        policy = rid if selection.selector.kind != "exact" else None
    result["active"][name] = key
    result["selection_policy"][name] = policy
    validate(result)
    return result


def upgrade(state, updates):
    result = copy.deepcopy(state)
    for rid, item in updates.items():
        key = keep(result, item)
        result["requests"][rid] = tracked(item[2], key)
        name = item[1]["name"]
        if state["selection_policy"].get(name) == rid:
            result["active"][name] = key
    validate(result)
    return result
