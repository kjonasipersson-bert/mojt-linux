# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only complete Kernel deployment plans; no boot publication or selection."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

import mojt_artifact as artifact
import mojt_boot as boot
import mojt_system_manifest as system
import mpm_catalog as catalog
import mpm_kernel as kernel
from mpm_selection import components

DEPLOYMENT = "mojt-boot-deployment-v1"
BINDING = "mojt-initramfs-binding-v1"
CONTEXT = "mpm-deployment-context-v1"
REQUEST = "mpm-kernel-plan-request-v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def fields(value, *names):
    artifact.fields(value, names)


def sha(value, *, prefixed=True):
    require(isinstance(value, str) and re.fullmatch(("sha256:" if prefixed else "") + r"[0-9a-f]{64}", value),
            "require a full SHA256 identity")


def base_reference(value):
    fields(value, "artifact", "release")
    sha(value["artifact"])
    boot.generation(value["release"])


def system_reference(value):
    fields(value, "manifest", "generation")
    sha(value["manifest"])
    boot.generation(value["generation"])


def kernel_reference(value):
    fields(value, "artifact", "release", "image_sha256", "modules_digest")
    sha(value["artifact"])
    boot.generation(value["release"])
    sha(value["image_sha256"], prefixed=False)
    sha(value["modules_digest"])


def boot_reference(value, base, selected_system):
    fields(value, "root_uuid", "console", "cmdline")
    require(value["cmdline"] == boot.cmdline(value["root_uuid"], selected_system["generation"],
                                             base["release"], value["console"]),
            "boot command line differs from explicit Base/System/root/console")


def archive_reference(value):
    fields(value, "sha256", "size")
    sha(value["sha256"], prefixed=False)
    require(type(value["size"]) is int and 0 < value["size"] <= artifact.MAX_CONTENT, "invalid initramfs size")


def identified(value, format_name):
    fields(value, "format", "id", "description")
    require(value["format"] == format_name, "unsupported " + format_name + " format")
    require(value["id"] == artifact.digest(value["description"]), "deployment/binding identity differs")
    return value["description"]


def create(description, format_name=DEPLOYMENT):
    """Content identity only; not a signature or authority to select a deployment."""
    return dict(format=format_name, id=artifact.digest(description), description=copy.deepcopy(description))


def validate_deployment(value):
    d = identified(value, DEPLOYMENT)
    fields(d, "platform", "base", "system", "kernel", "initramfs", "boot")
    require(artifact.token(d["platform"]), "invalid deployment platform")
    base_reference(d["base"])
    system_reference(d["system"])
    kernel_reference(d["kernel"])
    fields(d["initramfs"], "archive", "binding")
    archive_reference(d["initramfs"]["archive"])
    sha(d["initramfs"]["binding"])
    boot_reference(d["boot"], d["base"], d["system"])
    return copy.deepcopy(d)


def kernel_identity(body):
    artifact.validate_descriptor(body)
    require(body["kind"] == "kernel" and body["name"] == "linux", "candidate must be a linux Kernel artifact")
    release = body["metadata"]["kernel_release"]
    image = artifact.regular_row(body["files"], "payload/boot/vmlinuz-" + release)
    prefix = "payload/lib/modules/" + release
    modules = [r for r in body["files"] if r["path"] == prefix or r["path"].startswith(prefix + "/")]
    return dict(artifact=body["id"], release=release, image_sha256=image["sha256"],
                modules_digest=artifact.digest(modules))


def compose(selected, body, bounds, manifest, context, binding, initramfs):
    """Check explicit declarations. Caller separately verifies installed bytes."""
    old = validate_deployment(selected)
    bounds = catalog.base_context(bounds)
    require(bounds["base"] == old["base"], "Kernel bounds do not describe the selected Base")
    require(bounds["platform"] == old["platform"] == body["platform"], "Kernel/Base/deployment platform differs")
    version = body["version"]
    require(version["scheme"] == "dotted-v1" and len(components(version["upstream"])) in (2, 3),
            "Kernel planning requires numeric major.minor[.patch] upstream metadata")
    require(catalog.compare_versions(version["upstream"], bounds["kernel_min"]) >= 0 and
            catalog.compare_versions(version["upstream"], bounds["kernel_max"]) <= 0,
            "candidate Kernel outside selected Base bounds; no Base/policy fallback")

    system.validate(manifest)
    require(old["system"] == dict(manifest=manifest["id"], generation=manifest["description"]["label"]),
            "Kernel plan must preserve the exact selected System userspace")
    fields(context, "format", "selected", "base", "root_uuid", "facts")
    require(context["format"] == CONTEXT and context["selected"] == selected["id"] and
            context["base"] == old["base"] and context["root_uuid"] == old["boot"]["root_uuid"],
            "installation facts are not bound to the explicit selected deployment")
    report = system.check(manifest, context["facts"])
    require(old["platform"] == context["facts"]["architecture"] + "-linux", "System/deployment platform differs")
    require(report["compatible"], "System declaration check failed: " + "; ".join(report["errors"]))

    candidate_kernel = kernel_identity(body)
    require(not body["dependencies"] and not body["requirements"], "unsupported Kernel requirements/dependencies")
    declared = identified(binding, BINDING)
    fields(declared, "platform", "base", "system", "kernel", "boot", "archive")
    archive_reference(declared["archive"])
    expected = dict(platform=old["platform"], base=old["base"], system=old["system"],
                    kernel=candidate_kernel, boot=old["boot"], archive=initramfs)
    require(declared == expected, "initramfs declaration/file does not bind the exact candidate deployment")
    candidate = create(dict(old, kernel=candidate_kernel,
                            initramfs=dict(archive=initramfs, binding=binding["id"])))
    validate_deployment(candidate)
    changes = {key: dict(before=old[key], after=candidate["description"][key])
               for key in ("kernel", "initramfs") if old[key] != candidate["description"][key]}
    return dict(format="mpm-kernel-plan-v1", operation="kernel", candidate=candidate,
                selected=dict(deployment=selected["id"], source="explicit-input", authoritative_lookup=False),
                changes=changes, no_change=candidate["id"] == selected["id"],
                evidence=dict(base_context_digest=artifact.digest(bounds),
                              installation_context_digest=artifact.digest(context), system_check=report,
                              initramfs="declaration and file checksum match; archive contents not inspected"),
                boot_ready=False, writes=False,
                limits=["Explicit local selection/context/binding declarations are not authenticated disk facts.",
                        "Base/System identities are metadata references; their payloads/provider closures are not audited.",
                        "No hardware, firmware, Secure Boot or runtime ABI validation; no boot publication or activation."])


def local_file(value):
    path = Path(os.path.abspath(value))
    require(path == path.resolve(), "plan inputs must not traverse symlinks")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "plan input must be a regular local file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def read_json(path):
    with local_file(path) as stream:
        return artifact.parse_json(stream.read(artifact.MAX_METADATA + 1))


def initramfs_evidence(path):
    with local_file(path) as stream:
        before = os.fstat(stream.fileno())
        require(0 < before.st_size <= artifact.MAX_CONTENT, "invalid initramfs size")
        digest = hashlib.sha256()
        total = 0
        while chunk := stream.read(128 * 1024):
            total += len(chunk)
            require(total <= artifact.MAX_CONTENT, "initramfs exceeds size limit")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        require(total == before.st_size and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "initramfs changed during inspection")
        return dict(sha256=digest.hexdigest(), size=total)


def plan(request_path, registry):
    request_path = Path(os.path.abspath(request_path))
    request = read_json(request_path)
    names = ("selected", "base_context", "system_manifest", "system_context", "initramfs", "initramfs_binding")
    fields(request, "format", "kernel", *names)
    require(request["format"] == REQUEST, "unsupported Kernel plan request format")
    key = kernel.identifier(request["kernel"])
    paths = {}
    for name in names:
        require(artifact.clean_text(request[name]) and "://" not in request[name], "require explicit local input paths")
        paths[name] = request_path.parent / request[name]
    values = {name: read_json(paths[name]) for name in names if name != "initramfs"}
    root = kernel.root_path(registry)
    require(kernel.inspect_root(root, allow_empty=True), "Kernel registry is absent; install the exact candidate first")
    installed = root / "installed" / key
    require(kernel.directory(installed).st_uid == root.stat().st_uid, "installed Kernel owner differs from registry")
    body, record = kernel.object_record(installed, request["kernel"], verify=True)
    result = compose(values["selected"], body, values["base_context"], values["system_manifest"],
                     values["system_context"], values["initramfs_binding"], initramfs_evidence(paths["initramfs"]))
    result["evidence"].update(kernel_integrity="verified-now", installation_record_digest=artifact.digest(record),
                               request_digest=artifact.digest(request))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=kernel.DEFAULT_ROOT)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if sum(a == "--root" or a.startswith("--root=") for a in arguments) > 1:
        parser.error("specify root only once")
    args = parser.parse_args(arguments)
    try:
        result = plan(args.request, args.root)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Candidate deployment:", result["candidate"]["id"])
            print("Selected (explicit input):", result["selected"]["deployment"])
            print("Changes:", ", ".join(result["changes"]) or "none")
            print("Kernel integrity: verified-now; declared compatibility checks passed")
            print("Boot readiness: not established; no selection or boot files written")
            for note in result["limits"]:
                print(note)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("mpm kernel plan: " + str(error), file=sys.stderr)
        return 1
    return 0
