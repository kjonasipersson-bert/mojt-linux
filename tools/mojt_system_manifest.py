# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pure System content description and declared compatibility checks; no I/O/backend."""
import copy
import hashlib
import json
import re

FORMAT = "mojt-system-manifest-v1"
CONTEXT = "mojt-system-context-v1"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode()).hexdigest()


def fields(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys.split()), "invalid " + label + " fields")


def word(value):
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 for c in value)


def validate(value):
    fields(value, "format id description", "System manifest")
    require(value["format"] == FORMAT, "unsupported System manifest format")
    d = value["description"]
    fields(d, "label architecture requirements support provides artifacts provenance profile", "System description")
    require(word(d["label"]) and word(d["architecture"]), "missing System identity/architecture")
    fields(d["requirements"], "base_abi state_layout", "requirements")
    require(isinstance(d["requirements"]["base_abi"], dict) and d["requirements"]["base_abi"], "missing declared Base ABI")
    require(type(d["requirements"]["state_layout"]) is int and d["requirements"]["state_layout"] > 0, "invalid state layout")
    fields(d["support"], "ports", "support")
    ports = d["support"]["ports"]
    fields(ports, "read write capabilities", "Ports support")
    for key in ("read", "write"):
        require(isinstance(ports[key], list) and all(type(n) is int and n > 0 for n in ports[key])
                and len(ports[key]) == len(set(ports[key])), "invalid supported Ports formats")
    require(isinstance(ports["capabilities"], list) and all(word(x) for x in ports["capabilities"]), "invalid Ports capabilities")
    require(isinstance(d["provides"], list) and all(isinstance(p, str) and p.startswith("/run/mojt-system/")
            and ".." not in p.split("/") for p in d["provides"]), "invalid provided System paths")
    for name in ("artifacts", "provenance"):
        require(isinstance(d[name], dict) and d[name], "missing opaque " + name)
    require(isinstance(d["profile"], dict) and all(word(k) and isinstance(v, dict) for k,v in d["profile"].items()),
            "invalid profile inventory")
    require(value["id"] == digest(d), "System manifest identity differs from contents")
    canonical(value)
    return copy.deepcopy(value)


def create(description):
    return validate(dict(format=FORMAT, id=digest(description), description=copy.deepcopy(description)))


def validate_context(value):
    fields(value, "format architecture base_abi state_layout ports required_system_paths", "compatibility context")
    require(value["format"] == CONTEXT, "unsupported compatibility context format")
    require(word(value["architecture"]) and isinstance(value["base_abi"], dict) and value["base_abi"], "invalid Base context")
    require(type(value["state_layout"]) is int and value["state_layout"] > 0, "invalid context state layout")
    require(isinstance(value["required_system_paths"], list) and all(word(p) for p in value["required_system_paths"]),
            "invalid required paths")
    if value["ports"] is not None:
        fields(value["ports"], "format capabilities", "current Ports metadata")
        require(type(value["ports"]["format"]) is int and value["ports"]["format"] > 0, "invalid current Ports format")
        caps = value["ports"]["capabilities"]
        require(isinstance(caps, dict) and set(caps) <= {"reader", "writer"} and all(word(c) for c in caps.values()),
                "invalid current Ports capabilities")
        if value["ports"]["format"] == 3:
            require(set(caps) == {"reader", "writer"}, "format 3 requires explicit reader/writer capabilities")
    return value


def check(manifest, context):
    d = validate(manifest)["description"]
    validate_context(context)
    errors = []
    for label, actual, wanted in (
        ("architecture", context["architecture"], d["architecture"]),
        ("declared Base ABI", context["base_abi"], d["requirements"]["base_abi"]),
        ("state layout", context["state_layout"], d["requirements"]["state_layout"]),
    ):
        if actual != wanted:
            errors.append(f"{label} differs: installation={actual!r}, candidate={wanted!r}")
    p = context["ports"]
    support = d["support"]["ports"]
    if p is not None:
        for operation in ("read", "write"):
            if p["format"] not in support[operation]:
                errors.append(f"Ports format {p['format']} not supported for {operation}")
        for operation, cap in p["capabilities"].items():
            if cap not in support["capabilities"]:
                errors.append(f"Ports {operation} capability unsupported: {cap}")
    for path in context["required_system_paths"]:
        if path not in d["provides"]:
            errors.append("required System path missing: " + path)
    return dict(compatible=not errors, errors=errors,
                scope="Declared metadata compatibility only; no runtime ABI or boot validation.")


def compare(candidate, running=None, selected=None):
    """Never infer a selected deployment from a running label/current symlink."""
    candidate = validate(candidate)
    for value in (running, selected):
        if value is not None:
            validate(value)
    result = dict(candidate=candidate["id"], running=running["id"] if running else None,
                  selected=selected["id"] if selected else None, changes={})
    if running:
        a, b = running["description"], candidate["description"]
        result["changes"] = {k: dict(before=a[k], after=b[k]) for k in b if a[k] != b[k]}
    return result
