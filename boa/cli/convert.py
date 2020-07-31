# convert between recipe.yaml and meta.yaml

from ruamel.yaml import YAML
from pprint import pprint
import collections
import os
import sys


def to_oldstyle_selectors(ydoc):
    if isinstance(ydoc, str):
        return ydoc

    if isinstance(ydoc, collections.Mapping):
        has_sel = any(k.startswith("sel(") for k in ydoc.keys())
        if has_sel:
            for k, v in ydoc.items():
            	return f"{v}  [{k[4:-1]}]"

        for k, v in ydoc.items():
            ydoc[k] = to_oldstyle_selectors(v)

    elif isinstance(ydoc, collections.Iterable):
        to_delete = []
        for idx, el in enumerate(ydoc):
            res = to_oldstyle_selectors(el)
            ydoc[idx] = res

        # flatten lists if necessary
        # if any([isinstance(x, list) for x in ydoc]):
        #     final_list = []
        #     for x in ydoc:
        #         if isinstance(x, list):
        #             final_list += x
        #         else:
        #             final_list.append(x)
        #     ydoc = final_list

    return ydoc


def main(docname):
	yaml = YAML(typ='safe')   # default, if not specfied, is 'rt' (round-trip)
	yaml.preserve_quotes = True
	with open(docname, 'r') as fi:
		x = yaml.load(fi)

	if x.get('outputs'):
		for o in x['outputs']:
			o['name'] = o['package']['name']
			if o['package'].get('version'):
				o['version'] = o['package']['version']
			del o['package']

			if o.get('build'):
				if o['build'].get('script'):
					o['script'] = o['build'].get('script')
					del o['build']['script']
				if not o['build']:
					del o['build']

	x = to_oldstyle_selectors(x)
	yaml.default_flow_style = False

	# yaml.default_style = "\""

	with open(os.path.join(os.path.dirname(docname), 'meta.yaml'), 'w') as fo:
		yaml.dump(x, fo)
