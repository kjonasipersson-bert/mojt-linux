# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fresh serial UEFI images from verified native Base and installed Kernel inputs."""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace

import mojt_artifact as artifact
import mojt_boot as boot
import mojt_system as system
import mojt_system_manifest as manifest_model
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel as kernel

MAX_INITRAMFS = 256 * 1024**2


def require(value, message):
    if not value:
        raise ValueError(message)


def preview(args):
    """Read explicit local inputs; no imports, images or output directories."""
    package = Path(os.path.abspath(args.base_package))
    with deployment.local_file(package):
        pass
    body = artifact.verify(package, args.base_artifact)
    require(body["kind"] == "base" and body["name"] == "mojt" and body["platform"] == "x86_64-linux",
            "native image requires an x86_64-linux mojt Base artifact")
    require(not body["dependencies"] and not body["requirements"], "unsupported Base requirements/dependencies")
    require(all(r["type"] in ("file", "directory") and len(r["path"].split("/")) <= 64 and
                len(os.fsencode(r["path"])) <= 4096 for r in body["files"]), "unsupported native Base package entries")
    payload = {r["path"] for r in body["files"] if r["path"].startswith("payload/")}
    require({"payload/manifest.toml", "payload/rootfs.tar.zst"} <= payload and all(
            len(r["path"].split("/")) == 2 and r["type"] == "file" for r in body["files"]
            if r["path"].startswith("payload/")), "native Base image subset requires a flat regular release")
    reference = dict(artifact=body["id"], release=body["version"]["upstream"])
    bounds = catalog.base_context(deployment.read_json(args.base_context))
    require(bounds["base"] == reference and bounds["platform"] == body["platform"], "Base bounds identity/platform differs")
    root = kernel.root_path(args.kernel_registry)
    require(kernel.inspect_root(root), "installed Kernel registry required")
    obj = root / "installed" / kernel.identifier(args.kernel_artifact)
    require(kernel.directory(obj).st_uid == root.stat().st_uid, "Kernel owner differs from registry")
    candidate, record = kernel.object_record(obj, args.kernel_artifact, verify=True)
    version = candidate["version"]
    require(version["scheme"] == "dotted-v1" and candidate["platform"] == body["platform"] and
            catalog.compare_versions(version["upstream"], bounds["kernel_min"]) >= 0 and
            catalog.compare_versions(version["upstream"], bounds["kernel_max"]) <= 0,
            "Kernel outside explicit Base bounds/platform; no fallback")
    source = Path(os.path.abspath(args.system_payload))
    require(source == source.resolve(), "System payload path must not traverse symlinks")
    payload_record = system.load_payload(source)
    require(payload_record["step"] >= 6, "native image requires System step 6+ kmod integration")
    boot.generation(args.system_generation)
    output = Path(os.path.abspath(args.output))
    require(output == output.resolve() and not os.path.lexists(output), "output must be a new nonsymlink directory")
    require(not any(output == p or p in output.parents or output in p.parents for p in (root, source, package)),
            "output must be separate from all input trees/files")
    return dict(base=body, kernel=candidate, bounds=bounds, system_record=payload_record,
                source_archive=dict(sha256=artifact.file_sha(package), size=package.stat().st_size),
                kernel_installation_digest=artifact.digest(record))


def unpack_base(path, body, target):
    """Only regular wrapper files; the existing Base installer audits the inner tar."""
    target.mkdir()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["zstd", "-q", "-d", "-c", "--", str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                root, descriptor = archive.next(), archive.next()
                require(root.name == "./base" and descriptor.name == "./base/artifact.json", "Base wrapper differs")
                for row in body["files"]:
                    member = archive.next()
                    require(member is not None and member.name == "./base/" + row["path"] and
                            (member.isdir() if row["type"] == "directory" else member.isfile()), "Base member differs")
                    dest = target / row["path"]
                    if row["type"] == "directory":
                        dest.mkdir(mode=0o700)
                    else:
                        require(member.size == row["size"], "Base file size differs")
                        digest = hashlib.sha256()
                        with dest.open("xb") as out:
                            origin = archive.extractfile(member)
                            while chunk := origin.read(128 * 1024):
                                digest.update(chunk)
                                out.write(chunk)
                        require(digest.hexdigest() == row["sha256"], "Base file content differs")
                require(archive.next() is None, "extra Base archive entry")
                while archive.fileobj.read(128 * 1024):
                    pass
            while process.stdout.read(128 * 1024):
                pass
            require(process.wait() == 0, "Base decompression failed")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()


def fresh_login_state(target):
    """New image only: never inherit a publisher's password or console allowlist."""
    for name in ("shadow", "gshadow", "securetty"):
        path = target / "state/etc" / name
        if os.path.lexists(path):
            require(stat.S_ISREG(path.lstat().st_mode), "unsafe fresh-image authentication default")
            path.unlink()


def stage(tree, context, base):
    source = Path(context["registry"])
    destination = tree / "kernel"
    shutil.copytree(source, destination, symlinks=False)
    key = kernel.identifier(context["kernel"]["id"])
    copied, unused = kernel.object_record(destination / "installed" / key, context["kernel"]["id"], verify=True)
    require(copied == context["kernel"], "copied Kernel artifact differs")
    # The new image mounts this independent native module tree, never System/kernel.
    point = system.virtual_file(tree / "base" / base, "/lib/modules")
    require((tree / "base" / base / "lib/modules").resolve() == point,
            "Base module mountpoint has an absolute or escaping guest symlink")
    require(not point.is_symlink() and (not point.exists() or point.is_dir() and not any(point.iterdir())),
            "Base /lib/modules mountpoint conflicts")
    point.mkdir(parents=True, exist_ok=True)


def base_inventory(root):
    rows, links = {}, {}
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        row = dict(mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid,
                   xattrs={name: os.getxattr(path, name, follow_symlinks=False).hex()
                           for name in sorted(os.listxattr(path, follow_symlinks=False))})
        if stat.S_ISLNK(info.st_mode):
            row.update(type="link", target=os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            row.update(type="directory")
        else:
            require(stat.S_ISREG(info.st_mode), "special file in installed Base")
            row.update(type="file", sha256=artifact.file_sha(path))
            identity = info.st_dev, info.st_ino
            if identity in links:
                row["hardlink_to"] = links[identity]
            else:
                links[identity] = path.relative_to(root).as_posix()
        rows[path.relative_to(root).as_posix()] = row
    return rows


def check_base_copy(root, original):
    actual = base_inventory(root)
    require(all(actual.get(name) == row for name, row in original.items()), "assembled Base content/metadata changed")
    module_point = system.virtual_file(root, "/lib/modules").relative_to(root)
    allowed = {"home", "root", "nix", "run", "tmp", str(module_point),
               *(str(p) for p in module_point.parents if str(p) != ".")}
    extra = sorted(set(actual) - set(original))
    require(all(name in allowed and actual[name]["type"] == "directory" for name in extra),
            "unexpected addition to immutable Base")
    return dict(original=artifact.digest(original), assembled=artifact.digest(actual), added_scaffolding=extra)


def verify_profile(path, manifest):
    actual = {}
    for item in sorted(path.rglob("*")):
        name = item.relative_to(path).as_posix()
        if name == "manifest.json":
            continue
        if item.is_symlink():
            actual[name] = dict(link=os.readlink(item))
        elif item.is_dir():
            actual[name] = dict(directory=True, mode=stat.S_IMODE(item.stat().st_mode))
        else:
            require(item.is_file(), "special System profile entry")
            actual[name] = dict(sha256=artifact.file_sha(item), mode=stat.S_IMODE(item.stat().st_mode))
    require(actual == manifest["description"]["profile"], "assembled System profile differs from manifest")


def init_script(script, identifier, release, base, selected_system):
    key = kernel.identifier(identifier)
    boot.generation(release)
    boot.generation(base)
    boot.generation(selected_system)
    hook = 'mount --bind /sysroot/nix /newroot/nix || panic "cannot attach Nix store"'
    identity = 'mkdir /newroot/run/mojt || panic "cannot create runtime identity directory"'
    require(script.count(hook) == script.count(identity) == 1, "native Kernel init hooks need review")
    mount = "/sysroot/kernel/installed/" + key + "/payload/lib/modules"
    script = script.replace(hook, hook + f'''
IFS= read -r mojt_native_release </proc/sys/kernel/osrelease || panic "cannot identify native Kernel"
[ "$mojt_native_release" = "{release}" ] || panic "running Kernel differs from native selection"
[ ! -L /sysroot/kernel ] && [ -d {mount}/{release} ] || panic "native Kernel modules missing"
mount --bind {mount} /newroot/lib/modules || panic "cannot attach native Kernel modules"
# Supply both paths: BusyBox's one-path remount searches /proc/mounts by
# spelling, while a merged-/usr Base records /newroot/usr/lib/modules.
mount -o remount,bind,ro {mount} /newroot/lib/modules || panic "cannot protect native Kernel modules"''')
    record = "/sysroot/boot/mojt/" + selected_system + "/" + base + "/deployment.json"
    return script.replace(identity, identity + f'''
cp {record} /newroot/run/mojt/deployment.json || panic "missing native deployment record"
printf '%s\\n' '{identifier}' >/newroot/run/mojt/native-kernel-artifact || panic "cannot record native Kernel"''')


def init_inventory(root):
    rows = {}
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        name = "." if path == root else "./" + path.relative_to(root).as_posix()
        if stat.S_ISREG(info.st_mode):
            content = path.read_bytes()
        elif stat.S_ISLNK(info.st_mode):
            content = os.fsencode(os.readlink(path))
        else:
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISCHR(info.st_mode), "unsupported initramfs node")
            content = b""
        rows[name] = (info.st_mode, info.st_uid, info.st_gid, os.major(info.st_rdev), os.minor(info.st_rdev),
                      len(content), hashlib.sha256(content).hexdigest())
    return rows


def inspect_initramfs(data, root):
    """Independently compare actual gzip/newc members to our complete private tree."""
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        raw = stream.read(MAX_INITRAMFS + 1)
    require(len(raw) <= MAX_INITRAMFS, "initramfs exceeds inspection limit")
    offset, found = 0, {}
    while True:
        require(len(raw) >= offset + 110 and raw[offset:offset + 6] == b"070701", "invalid/truncated newc header")
        try:
            values = [int(raw[offset + 6 + 8*i:offset + 14 + 8*i], 16) for i in range(13)]
        except ValueError as error:
            raise ValueError("invalid newc numbers") from error
        mode, uid, gid, size, rmajor, rminor, length = [values[i] for i in (1, 2, 3, 6, 9, 10, 11)]
        require(0 < length <= 4096 and offset + 110 + length <= len(raw), "invalid newc filename")
        encoded = raw[offset + 110:offset + 110 + length]
        require(encoded[-1:] == b"\0" and b"\0" not in encoded[:-1], "invalid newc name encoding")
        name = os.fsdecode(encoded[:-1])
        start = (offset + 110 + length + 3) & ~3
        require(start + size <= len(raw), "truncated newc file")
        content = raw[start:start + size]
        offset = (start + size + 3) & ~3
        if name == "TRAILER!!!":
            require(size == 0 and not any(raw[offset:]), "extra initramfs archive data")
            break
        # GNU cpio normalizes './name' to 'name' in newc headers.
        if name != ".":
            name = "./" + artifact.relative(name[2:] if name.startswith("./") else name)
        require(name not in found, "duplicate newc member")
        found[name] = (mode, uid, gid, rmajor, rminor, size, hashlib.sha256(content).hexdigest())
    require(found == init_inventory(root), "initramfs contents differ from generated init/module tree")
    return artifact.digest({name: list(row) for name, row in sorted(found.items())})


def complete(tree, result, context, *, base, selected_system, root_uuid, console, initramfs, initroot, modules, script,
             decode_module):
    key = kernel.identifier(context["kernel"]["id"])
    obj = tree / "kernel/installed" / key
    body, unused = kernel.object_record(obj, context["kernel"]["id"], verify=True)
    require(body == context["kernel"], "staged Kernel changed")
    require((initroot / "init").read_bytes() == script.encode("ascii"), "generated init script differs")
    early = []
    for index, source in enumerate(modules):
        row = next((r for r in body["files"] if r["path"] == "payload/" + str(source.relative_to(Path(context["payload"])))), None)
        require(row is not None and artifact.file_sha(source) == row["sha256"], "early module is outside selected Kernel")
        decoded = hashlib.sha256(decode_module(source)).hexdigest()
        require(artifact.file_sha(initroot / "modules" / f"{index:04d}.ko") == decoded,
                "early module bytes differ from selected Kernel")
        early.append(dict(path=row["path"], stored_sha256=row["sha256"], initramfs_sha256=decoded))
    inventory_digest = inspect_initramfs(initramfs, initroot)
    current = artifact.read_json(tree / "system" / selected_system / "manifest.json")
    manifest_model.validate(current)
    verify_profile(tree / "system" / selected_system, current)
    base_copy = check_base_copy(tree / "base" / base, context["base_inventory"])
    for item in context["system_record"]["objects"]:
        path = tree / "nix/store" / Path(item["path"]).name
        require(system.tree_hash(path) == item["tree_sha256"], "copied System object differs")
    require({p.name for p in (tree / "nix/store").iterdir()} ==
            {Path(item["path"]).name for item in context["system_record"]["objects"]},
            "unexpected copied System store object")
    require((tree / "releases" / f"base-{base}.toml").read_bytes() == Path(context["base_manifest"]).read_bytes(),
            "committed Base release manifest differs")
    base_ref = dict(artifact=context["base"]["id"], release=base)
    selected_ref = dict(manifest=current["id"], generation=selected_system)
    boot_ref = dict(root_uuid=root_uuid, console=console, cmdline=boot.cmdline(root_uuid, selected_system, base, console))
    archive = dict(sha256=hashlib.sha256(initramfs).hexdigest(), size=len(initramfs))
    binding = deployment.create(dict(platform=body["platform"], base=base_ref, system=selected_ref,
        kernel=deployment.kernel_identity(body), boot=boot_ref, archive=archive), deployment.BINDING)
    selected = deployment.create(dict(platform=body["platform"], base=base_ref, system=selected_ref,
        kernel=deployment.kernel_identity(body), boot=boot_ref, initramfs=dict(archive=archive, binding=binding["id"])))
    # Facts describe only this newly installed/copied private image, not an existing boot choice.
    spec = importlib.util.spec_from_file_location("native_image_inspection", Path(__file__).with_name("mojt-system-inspect.py"))
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    facts = dict(format=deployment.CONTEXT, selected=selected["id"], base=base_ref, root_uuid=root_uuid,
                 facts=inspector.context_from_target(tree, base))
    plan = deployment.compose(selected, body, context["bounds"], current, facts, binding, archive)
    plan["evidence"]["kernel_integrity"] = "verified-now"
    receipt = dict(format="mojt-native-image-inputs-v1", selection_origin="fresh-image-bootstrap",
        base_artifact=context["base"]["id"], base_archive=context["source_archive"],
        base_copy=base_copy,
        kernel_artifact=body["id"], system_record_digest=artifact.digest(context["system_record"]),
        system_manifest=current["id"], initramfs_inventory=inventory_digest, early_modules=early,
        status="assembled; owner boot acceptance pending; no existing installation updated")
    files = {"deployment.json": selected, "selected-deployment.json": selected, "initramfs-binding.json": binding,
             "kernel-plan.json": plan, "base-context.json": context["bounds"], "system-context.json": facts,
             "system-manifest.json": current, "base-artifact.json": context["base"], "kernel-artifact.json": body,
             "native-build-inputs.json": receipt}
    boot_path = tree / "boot/mojt" / selected_system / base
    record = artifact.read_json(boot_path / "boot.json")
    require(record["kernel_sha256"] == selected["description"]["kernel"]["image_sha256"] and
            record["initramfs_sha256"] == archive["sha256"], "staged boot files differ from native deployment")
    for name, value in files.items():
        raw = artifact.canonical(value) + b"\n"
        (boot_path / name).write_bytes(raw)
        (result / name).write_bytes(raw)
    request = dict(format=deployment.REQUEST, kernel=body["id"], selected="selected-deployment.json",
        base_context="base-context.json", system_manifest="system-manifest.json", system_context="system-context.json",
        initramfs="initramfs.cpio.gz", initramfs_binding="initramfs-binding.json")
    (result / "kernel-plan-request.json").write_bytes(artifact.canonical(request) + b"\n")


def build(args, vm=None):
    evidence = preview(args)
    if args.dry_run:
        return dict(format="mojt-native-image-preview-v1", base=evidence["base"]["id"],
                    kernel=evidence["kernel"]["id"], imports=False, image_written=False)
    require(os.geteuid() == 0, "image assembly requires root; use --dry-run for unprivileged preview")
    if vm is None:
        spec = importlib.util.spec_from_file_location("native_vm_builder", Path(__file__).with_name("mojt-vm-build.py"))
        vm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vm)
    output = Path(os.path.abspath(args.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mojt-native-inputs-") as work, \
            tempfile.TemporaryDirectory(prefix=".mojt-native-image-", dir=output.parent) as publish:
        work, publish = Path(work), Path(publish)
        frozen = work / "base.tar.zst"
        digest, size = kernel.frozen_copy(args.base_package, frozen)
        require(dict(sha256=digest, size=size) == evidence["source_archive"] and
                artifact.verify(frozen, args.base_artifact) == evidence["base"], "Base input changed after preview")
        release = work / "base-release"
        unpack_base(frozen, evidence["base"], release)
        target = work / "target"
        subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).with_name("mojt-base-install")),
                        "install", str(release / "payload"), "--target", str(target)], check=True)
        if args.login_mode == "password":
            fresh_login_state(target)
        registry = work / "kernel-registry"
        source = kernel.root_path(args.kernel_registry) / "installed" / kernel.identifier(args.kernel_artifact)
        kernel.install(registry, source / "archive.tar.zst", args.kernel_artifact, yes=True)
        obj = registry / "installed" / kernel.identifier(args.kernel_artifact)
        copied, unused = kernel.object_record(obj, args.kernel_artifact, verify=True)
        require(copied == evidence["kernel"], "Kernel input changed after preview")
        payload = work / "system-payload"
        shutil.copytree(args.system_payload, payload, symlinks=True)
        require(system.load_payload(payload) == evidence["system_record"], "System payload changed after preview")
        busybox = work / "busybox"
        shutil.copyfile(args.busybox, busybox)
        busybox.chmod(0o755)
        base = evidence["base"]["version"]["upstream"]
        context = dict(evidence, registry=str(registry), payload=str(obj / "payload"),
            base_manifest=str(release / "payload/manifest.toml"), base_inventory=base_inventory(target / "base" / base))
        options = SimpleNamespace(target=target, output=publish / "image", kernel=obj / "payload/boot" /
            ("vmlinuz-" + copied["metadata"]["kernel_release"]), modules_dir=obj / "payload/lib/modules" /
            copied["metadata"]["kernel_release"], busybox=busybox, boot_mode="uefi", hardware_profile=None,
            firmware_root=None, system_payload=payload, disk_size_mib=args.disk_size_mib, login_mode=args.login_mode,
            root_shell="/run/mojt-system/bin/bash", base_generation=base, system_generation=args.system_generation,
            additional_generations=None, native_context=context)
        vm.build(options)
        # Re-run the portable planner on the output files before publishing any result.
        checked = deployment.plan(options.output / "kernel-plan-request.json", registry)
        require(checked["no_change"] and not checked["boot_ready"], "native image plan differs")
        require(not os.path.lexists(output), "output appeared during build; not overwriting")
        options.output.rename(output)
    return dict(format="mojt-native-image-result-v1", output=str(output), base=evidence["base"]["id"],
                kernel=evidence["kernel"]["id"], status="fresh image built; owner boot acceptance pending")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base-package", "base-context", "kernel-registry", "system-payload", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("base-artifact", "kernel-artifact", "system-generation"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    parser.add_argument("--disk-size-mib", type=int, default=8192)
    parser.add_argument("--login-mode", choices=("password", "development"), default="password")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args), indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, RecursionError, EOFError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print("mojt-native-image: " + str(error), file=sys.stderr)
        return 1
    return 0

