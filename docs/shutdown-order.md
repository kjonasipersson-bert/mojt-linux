<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Image mount lifetime and final shutdown

The native Kernel boot/rollback test exposed three real early unmount failures:
`/run/mojt-system`, `/usr/lib/modules` and `/var` returned EBUSY/status 32.
The owner observed udev mappings of the System hwdb and Kernel module indexes,
and journald's shared writable mapping of the persistent journal.

The problem is the lifetime boundary, not a reason to discard journal output or
force/lazily detach a busy data filesystem. These binds are established by Mojt's
early boot before PID 1 starts, but systemd discovered them as ordinary mounts
with default shutdown dependencies. It tried to stop them at `umount.target`,
while early services could still hold their files. Journald and udev normally
survive into the final shutdown process-kill phase.

## Corrected order

1. Stop ordinary services and sessions normally. Keep the image-owned Base state,
   System/store, module/firmware and backing-disk mounts available to the remaining
   early services and shutdown executable.
2. Enter systemd's final shutdown phase, send the remaining processes their final
   signals, and close their mapped-file references. systemd can release mounts
   that are no longer used by PID 1.
3. Pivot into the RAM-backed `/run/initramfs` and exec the copied static BusyBox
   shutdown script. This also releases the old dynamic loader/library mappings.
4. Sync, then unmount `/oldroot` children before parents, including stacked
   mounts, with at most three passes. Keep the new root's `/proc` and `/dev`
   available for inspection and the console. No forced/lazy unmount is used.
5. Verify both that no `/oldroot` mounts remain and that the original backing
   filesystem's device number appears nowhere in the mount table. Sync again,
   report the measured result and power off/reboot.

For an unexpected remaining reference, the script reports an explicit error and
attempts the previous read-only safety fallback after sync. It never calls that
clean-unmount acceptance. It also refuses to report success if no original
`/oldroot` mount could be identified. This is not power-cut recovery.

## Runtime mount policy

The generated initramfs installs small `.mount` drop-ins into the new root's
`/run/systemd/system` before executing PID 1. `DefaultDependencies=no` keeps the
already established Mojt-owned mounts out of the ordinary `umount.target` stop
transaction. Other device/path dependencies and administrator configuration are
not globally disabled. User-created mounts and API filesystems are not included.

The policy covers Mojt's `/etc`, `/var`, `/home`, `/root`, current store mount,
System runtime mount, native backing-disk mount and module/firmware aliases.
Both ordinary and merged-/usr module paths are represented; unused drop-ins do
not create mounts. Literal hyphens in unit names are correctly escaped as `\x2d`.
Startup is unchanged: early boot already creates these mounts before PID 1.

This follows the lifetime distinction described by upstream
[systemd.mount](https://github.com/systemd/systemd/blob/v262/man/systemd.mount.xml)
and the final pivot in
[systemd shutdown](https://github.com/systemd/systemd/blob/v262/src/shutdown/shutdown.c).
Mojt's current experiment disables systemd generators and creates its binds
directly, so it installs an explicit runtime policy rather than relying on an
fstab generator or an unrecorded `x-initrd.mount` option.

The policy and shutdown script belong to the generated initramfs/deployment.
Retained System profiles, Base content, package identities and old initramfs
files are not edited in place. A newly generated image or staged deployment
gets the correction; booting a retained older deployment keeps its old behavior.
The selected static BusyBox must provide `sort` and `printf` in addition to its
previous shutdown applets; this is checked before assembly.

## Automated evidence

`tests/test_shutdown_order.py` executes the real shutdown shell control flow with
isolated mount-table/command doubles. It covers child/parent order, API retention,
stacked mounts, escaped whitespace/backslashes, bounded retry, a device alias
outside `/oldroot`, missing initial state and explicit read-only fallback.

`tests/run-shutdown-smoke.py` boots a new regular-file ext4 image with a real
host-systemd userspace and a matching test kernel in QEMU. A small fixture service
maps the hwdb/module indexes and a writable file under `/var`; real journald is
flushed to persistent storage and its mapping is observed before shutdown.
The fixture uses the same early-boot layout and shutdown code as the builder.

- With the legacy lifetime policy and `umount -a -r` path, the persistent journal
  records all three original EBUSY/status-32 failures. The console also reproduces
  the late busy/read-only fallback messages.
- With the correction, PID 1 reports the three mount policies as
  `DefaultDependencies=no`. No unmount fails, the static exitrd reports the old
  root and backing filesystem fully unmounted, QEMU powers off normally, and an
  offline `e2fsck -fn` succeeds.

The local reproduction used Ubuntu systemd 255 and Linux 6.8 under TCG. CI repeats
both modes using its matching installed test kernel and retains serial, unmount
journal and filesystem-check logs. This is synthetic layout/holder evidence,
not full Mojt/Nix-systemd-262 acceptance or a new libc compatibility test.

## Owner shutdown acceptance: 2026-10-30

At functional revision `d0aa861d7280d22409c658421d8ac59977277c95`,
both CI jobs passed. The owner then supplied the complete poweroff console
output from the focused Mojt image test. Ordinary sessions, user manager,
network services, login sessions and D-Bus stopped before final shutdown.
The transient privileged and temporary mounts unmounted normally.

The console contained no failed unmount, busy/read-only fallback or cleanup
error. After reaching the system poweroff target, it reported:

```text
Mojt shutdown: entered static exitrd
Mojt shutdown: old root and backing filesystem fully unmounted
reboot: Power down
```

This closes the observed shutdown-order finding for the tested Mojt image.
The result establishes the script's mount-table verification and normal poweroff;
it is not an owner-run offline filesystem check, power-cut test or general
hardware/libc compatibility proof. The separate automated fixture includes its
own successful offline ext4 check.

No full install/stage/select/rollback or account loop was repeated.
Verification-performance work remains separate and unchanged.
