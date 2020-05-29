import sys
from ruamel.yaml import YAML
import jinja2
import collections

def render_recursive(dict_or_array, context_dict, jenv):
	# check if it's a dict?
	if isinstance(dict_or_array, collections.Mapping):
		for key, value in dict_or_array.items():
			if isinstance(value, str):
				tmpl = jenv.from_string(value)
				dict_or_array[key] = tmpl.render(context_dict)
			elif isinstance(value, collections.Mapping):
				render_recursive(dict_or_array[key], context_dict, jenv)
			elif isinstance(value, collections.Iterable):
				render_recursive(dict_or_array[key], context_dict, jenv)

	elif isinstance(dict_or_array, collections.Iterable):
		for i in range(len(dict_or_array)):
			value = dict_or_array[i]
			if isinstance(value, str):
				tmpl = jenv.from_string(value)
				dict_or_array[i] = tmpl.render(context_dict)
			elif isinstance(value, collections.Mapping):
				render_recursive(value, context_dict, jenv)
			elif isinstance(value, collections.Iterable):
				render_recursive(value, context_dict, jenv)

def pin_subpackage(name, exact=False, max_pin='x.x.x.x.x'):
	return "Not implemented yet."

def jinja_functions():
	return {
		'pin_subpackage': pin_subpackage
	}

def main():
	fn = sys.argv[1]
	# step 1: parse YAML
	with open(fn) as fi:
		loader = YAML(typ='safe')
		ydoc = loader.load(fi)
	print(ydoc)

	# step 2: fill out context dict
	context_dict = ydoc.get("context") or {}
	jenv = jinja2.Environment()
	for key, value in context_dict.items():
		if isinstance(value, str):
			tmpl = jenv.from_string(value)
			context_dict[key] = tmpl.render(context_dict)
	del ydoc["context"]
	# step 3: recursively loop over the entire recipe and render jinja with context
	jenv.globals.update(jinja_functions())
	for key in ydoc:
		render_recursive(ydoc[key], context_dict, jenv)

	loader.dump(ydoc, sys.stdout)

if __name__ == '__main__':
	main()