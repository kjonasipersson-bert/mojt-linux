# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Human boot summaries and honest phase completion; JSON stays on stdout."""
from contextlib import contextmanager
import sys
import time


def short(value):return value.removeprefix('sha256:')[:12] if value else 'unknown'


def name(row):
    if row.get('state')=='unknown':return 'unknown ('+row.get('reason','no evidence')+')'
    label=row.get('label') or row.get('release') or row.get('version',{}).get('release_id') or 'unknown'
    version=row.get('version',{}).get('release_id')
    return label+(' ('+version+')' if version and version!=label else '')


def combination(record):
    from mpm_boot_status import description
    d=description(record)
    return dict(Base=d['base']['release'],System=d['system']['generation'],Kernel=d['kernel']['release'])


def input_preview(root, before, after, *, before_id=None, after_id=None, running=None):
    print('Target: '+str(root),file=sys.stderr)
    if running is not None:print('Running: '+', '.join(k+' '+v for k,v in combination(running).items()),file=sys.stderr)
    print('Next boot changes:',file=sys.stderr)
    changed=False
    for area,field in (('base','release'),('system','generation'),('kernel','release')):
        a,b=before[area],after[area];different=a['artifact']!=b['artifact'];changed=changed or different
        print('  '+area.capitalize()+': '+(a[field]+' ['+short(a['artifact'])+'] -> '+b[field]+' ['+short(b['artifact'])+']' if different else a[field]+' (unchanged)'),file=sys.stderr)
    if not changed and before_id!=after_id:print('  Boot deployment: '+short(before_id)+' -> '+short(after_id),file=sys.stderr)
    pending=(running['id']!=after_id) if running is not None and after_id is not None else None
    print('Reboot: '+('required to run this deployment' if pending is True else 'not needed; already running this deployment' if pending is False else 'next-boot selection takes effect only after reboot'),file=sys.stderr)
    print('Running processes are not switched. Configuration and user data stay in place. Previous deployment retained. No automatic reboot.',file=sys.stderr,flush=True)


def preview(root,before,after,*,running=None):
    from mpm_boot_status import description
    input_preview(root,description(before),description(after),before_id=before['id'],after_id=after['id'],running=running)


@contextmanager
def phase(label):
    started=time.monotonic()
    print(label+'...',file=sys.stderr,flush=True)
    try:yield
    except BaseException:
        print(label+': failed after %.2f s' % (time.monotonic()-started),file=sys.stderr,flush=True)
        raise
    else:print(label+': done (%.2f s)' % (time.monotonic()-started),file=sys.stderr,flush=True)


def prepared_rows(root,area,installed):
    from mpm_boot_selection import present,available
    from mpm_boot_status import description
    if not root.exists() or not present(root):return []
    rows=[]
    for identifier,item in sorted(available(root)[0].items()):
        d=description(item['record']);entry=d[area]
        rows.append(dict(deployment=identifier,artifact=entry['artifact'],
            label=entry['generation'] if area=='system' else entry['release'],
            version=next((r['version'] for r in installed if r['artifact']==entry['artifact']),{}),
            base_release=d['base']['release'],kernel_release=d['kernel']['release']))
    return rows


def status(area, result):
    print(area.capitalize()+' on:',result['target'])
    for title,key in (('Running','running'),('Next boot','selected')):
        row=result[key]
        print(title+': '+name(row)+(' ['+short(row.get('artifact'))+']' if row.get('state')=='known' else ''))
    running,selected=result['running'],result['selected']
    if running.get('state')==selected.get('state')=='known':
        print('Reboot: '+('not needed; running and next boot match' if running.get('deployment')==selected.get('deployment') else 'pending; next boot differs from running'))
    else:print('Reboot: unknown; running or next boot could not be identified')
    prepared=result.get('staged_deployments',[])
    print('Prepared boot entries:')
    for row in prepared:
        tags=[title for title,key in (('running','running'),('next boot','selected')) if row['deployment']==result[key].get('deployment')]
        print('  '+name(row)+' / Base '+row.get('base_release','?')+' / Linux '+row.get('kernel_release','?')+
              ' ['+short(row['deployment'])+']'+(' ('+', '.join(tags)+')' if tags else ''))
    if not prepared:print('  none')
    print('Installed'+(' (content only)' if not prepared else '')+':')
    for row in result['installed']:
        print('  '+name(row)+' ['+short(row['artifact'])+']'+(' (prepared)' if any(p['artifact']==row['artifact'] for p in prepared) else ' (not prepared)'))
    if not result['installed']:print('  none')
    if result.get('retained'):print('Retained, not installed:',', '.join(short(r['artifact']) for r in result['retained']))
    if result.get('incomplete'):print('Incomplete:',', '.join(result['incomplete']))
