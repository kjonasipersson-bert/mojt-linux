# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only authoritative boot metadata shared by native area status readers."""
import os
import mpm_base as base
import mojt_artifact as artifact


def unknown(reason):return dict(state='unknown', record=None, reason=reason)


def observation(value):return dict(state='known', record=value, reason=None)


def selected(root, running_record=None):
    path=root/'boot/mojt/grub.cfg'
    if not os.path.lexists(path):return unknown('no boot selection record')
    # This is metadata inspection, not a Kernel/module integrity scrub.
    import mpm_kernel_boot as boot
    import mpm_deployment as deployment
    raw=boot.checked_file(path)
    marker=root/'boot/mpm/format'
    if os.path.lexists(marker):
        base.require(boot.checked_file(marker)==(boot.FORMAT+'\n').encode() and boot.managed_menu(raw),
                     'unsupported/inconsistent managed boot selection')
    if boot.managed_menu(raw):
        lines=raw.decode('ascii').splitlines()
        base.require(len(lines)>1 and lines[1].startswith('# '),'missing selected deployment metadata')
        state=artifact.parse_json(lines[1][2:].encode())
        artifact.fields(state,('format','selected','previous','entries'))
        base.require(type(state['entries']) is dict and 0<len(state['entries'])<=128,'invalid selected deployment entries')
        entries={}
        for identifier,relative in state['entries'].items():
            folder=boot.entry_path(root,relative);record=base.read(folder/'deployment.json')
            deployment.validate_deployment(record)
            base.require(record['id']==identifier,'selected deployment identity differs')
            entries[identifier]=dict(record=record,relative=relative)
        base.require(boot.menu(state,entries)==raw,'boot menu differs from its selected-state records')
        return observation(entries[state['selected']]['record'])
    if running_record is None:return unknown('unmanaged boot menu; exact next boot is not known')
    d=deployment.validate_deployment(running_record)
    relative='boot/mojt/'+d['system']['generation']+'/'+d['base']['release']
    folder=boot.entry_path(root,relative)
    base.require(base.read(folder/'deployment.json')==running_record,'native baseline differs from running evidence')
    expected=boot.boot.terminal('serial')+'set timeout=10\nset default=0\n'
    expected+=(f"menuentry 'Mojt Base {d['base']['release']} / System {d['system']['generation']} "
               f"(Linux {d['kernel']['release']})' {{\n"
               f"    linux /{relative}/vmlinuz {d['boot']['cmdline']}\n"
               f"    initrd /{relative}/initramfs.cpio.gz\n}}\n")
    base.require(raw==expected.encode('ascii'),'native baseline menu differs; next boot cannot be inferred')
    return observation(running_record)

