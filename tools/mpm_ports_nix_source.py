# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Project the installed, pinned Nix source into the provider-neutral Ports view.

Discovery evaluates only requested attributes. Binary acquisition is explicit and
temporary; the normal profile transaction owns durable retention and activation.
No channel refresh, source build or legacy Ports state is involved.
"""
import copy
import importlib.util
from pathlib import Path
import tempfile
import tomllib

import mpm_ui as ui
import mpm_request_plan as planning
import mpm_requests as wishes
from mpm_selection import Catalog, parse_selector, resolve

NAME = 'nixpkgs'
POLICY = 'system-pinned-nixpkgs-v1'
require = wishes.require


from mpm_nix_binary import NixBinaryAdapter


class NixPortsAdapter(NixBinaryAdapter):
    def documentation(self,ref,source,role):
        output=self.identity(ref)['output'];catalog=source['catalogs'][role];metadata=[]
        for name,row in catalog['sources'].items():
            identity=row['identity']
            if identity.get('manual_policy')=='exact-output-manuals-v1' and any(
                    c['source']==name and c['artifact']==output for c in catalog['candidates']):
                metadata.append(identity)
        if not metadata:return None
        require(len(metadata)==1,'ambiguous manual source')
        docs=metadata[0];require(type(docs['manual_outputs']) is list,'invalid manual output inventory')
        references=[]
        for path in docs['manual_outputs']:
            found=[o['reference'] for o in source['offers'] if o['artifact']==path and o['backend']=='nix']
            require(len(found)==1,'missing exact manual output')
            self.identity(found[0]);references.append(found[0])
        program=docs['manual_program']
        require(program is None or type(program) is str,'invalid manual program')
        return dict(references=references,program=program)


def exporter():
    spec = importlib.util.spec_from_file_location('_ports_catalog_export',
        Path(__file__).with_name('mpm-nix-catalog.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_view(catalogs, offers):
    view = dict(catalogs=catalogs, offers=offers)
    return dict(snapshot=wishes.digest(dict(format='mojt-ports-source-view-v1', **view)), **view)


def prepare(runtime, args, sources, platform):
    """Return discovery inputs, without fetching payloads or writing any files.

    Explicit finite bundles always take precedence. A previously accepted
    external catalog is never silently supplemented by the System's provider.
    """
    if runtime is None or args.sources is not None or args.action not in ('install', 'update'):
        return None
    if not sources and getattr(args, 'source', None) not in (None, NAME):
        return None
    if sources and (set(sources) != {NAME} or getattr(args, 'source', None) not in (None, NAME)):
        return None
    selected = [parse_selector(s) for s in args.names] if args.action == 'install' else []
    missing = sorted({p.name for p in selected} - set(sources.get(NAME, {}).get('catalogs', {})))
    refresh=sorted({p.name for p in selected if p.name in sources.get(NAME,{}).get('catalogs',{})
        and any(i['identity'].get('discovery')==POLICY and i['identity'].get('manual_policy')!='exact-output-manuals-v1'
                for i in sources[NAME]['catalogs'][p.name]['sources'].values())})
    if args.action == 'install' and not missing and not refresh:
        return None
    require(runtime.source.is_file(), 'installed System has no pinned Ports source manifest; use --sources FILE')
    module = exporter(); backend = module.load_backend()
    raw = tomllib.loads(runtime.source.read_text())
    require(type(raw.get('format')) is int and raw['format'] == 1 and 'nixpkgs' in raw,
            'unsupported installed Ports source manifest')
    source = backend.source_from_fields(raw['nixpkgs'], runtime.source.parent)
    require(source['system'] == platform, 'installed Ports source targets another platform')
    for catalog in sources.get(NAME, {}).get('catalogs', {}).values():
        identities = [s['identity'] for s in catalog['sources'].values()]
        require(identities and all(i.get('discovery') == POLICY and
                all(i.get(k) == v for k, v in source.items()) for i in identities),
                'accepted Ports metadata has another source pin; use an explicit --sources update')
    manuals=callable(getattr(backend,'resolve_manuals',None))
    if not manuals:refresh=[]
    rows = []
    for name in sorted(set(missing+refresh)):
        row = backend.resolve_package(source, name, name)
        if manuals:row['_manuals']=backend.resolve_manuals(source,name)
        if name in refresh:
            require(any(c['artifact']==row['output'] for c in sources[NAME]['catalogs'][name]['candidates']),
                    'manual refresh would change the accepted binary; use explicit upgrade instead')
        try:
            backend.selection_core().components(row['version']); scheme = 'dotted-v1'
        except ValueError:
            scheme = 'opaque-v1'
        # The installed adapter explicitly supplies the ordinary pinned-source
        # release policy. Opaque releases remain exact-only in the shared resolver.
        candidate = dict(name=name, release_id=row['version'], upstream_version=row['version'],
            version_scheme=scheme, stability='stable', source=NAME, artifact=row['output'],
            integrity=dict(output=row['output']))
        catalog = Catalog.from_dict(dict(format='mpm-release-catalog-v1', area='ports', name=name,
            channel='stable', platform=platform, sources={NAME:dict(backend='nix', identity=source)},
            candidates=[candidate]))
        # Fail unavailable series/exact requests before downloading anything.
        for selector in args.names:
            if parse_selector(selector).name == name:
                resolve(catalog, selector, platform=platform)
        rows.append(row)
    return dict(module=module, backend=backend, source=source, manifest=runtime.source, rows=rows, refresh_manuals=refresh)


def preview(prepared):
    return dict(format='mojt-ports-provider-preview-v1', source=prepared['source'],
        packages=[dict(name=r['name'], release=r['version'], output=r['output'],
            manuals=r.get('_manuals',{}).get('outputs',[])) for r in prepared['rows']],
        binary_only=True, command_inventory='after-binary-acquisition', publication=False)


def materialize(prepared, sources, stack):
    """Acquire only accepted exact binaries; keep temporary roots until commit.

    Caller must obtain consent first. Closure/command inventories are made from
    actual outputs, never guessed from a package's public name or meta.mainProgram.
    """
    module, backend = prepared['module'], prepared['backend']
    catalogs = copy.deepcopy(sources.get(NAME, {}).get('catalogs', {}))
    offers = {wishes.digest(o['reference']):copy.deepcopy(o) for o in sources.get(NAME, {}).get('offers', [])}
    if prepared['rows']:
        work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='mojt-ports-discovery-')))
        for index, row in enumerate(prepared['rows']):
            # argv[0] deliberately remains nix-store, even for a multicall Nix.
            with ui.phase('Acquire '+row['name']+' binaries and manuals'):
                outputs=sorted({row['output'],*row.get('_manuals',{}).get('outputs',[])})
                for number,output in enumerate(outputs):
                    backend.run('nix-store','--realise',output,'--add-root',str(work/(str(index)+'-'+str(number))),
                        '--indirect','--option','max-jobs','0','--option','builders','',
                        '--option','require-sigs','true')
            options=dict(catalog_name=row['name'],stability='stable')
            if '_manuals' in row:options['manuals']=True
            catalog=module.prepare_catalog(backend,[(NAME,prepared['manifest'])],row['name'],row['attribute'],**options)
            identity = catalog['sources'][NAME]['identity']
            require(all(identity.get(k) == v for k,v in prepared['source'].items()), 'provider source changed during acquisition')
            require(len(catalog['candidates']) == 1 and catalog['candidates'][0]['artifact'] == row['output']
                    and catalog['candidates'][0]['release_id'] == row['version'], 'provider output changed during acquisition')
            if '_manuals' in row:
                require(identity['manual_outputs']==[p for p in row['_manuals']['outputs'] if p!=row['output']]
                        and identity['manual_program']==row['_manuals']['main_program'],'manual outputs changed during acquisition')
            identity['discovery'] = POLICY
            bundle = module.prepare_bundle(backend, catalog, row['name'])
            view = bundle['description']['sources']['local']
            catalogs[row['name']] = view['catalogs'][row['name']]
            for offer in view['offers']:
                key = wishes.digest(offer['reference'])
                if key in offers and offers[key]!=offer:
                    old=offers[key]
                    require(all(old[k]==offer[k] for k in old if k!='dependencies')
                            and all(d in offer['dependencies'] for d in old['dependencies']),
                            'conflicting discovered provider offer')
                offers[key] = offer
    return planning.sources_view({NAME:source_view(catalogs, [offers[k] for k in sorted(offers)])})
