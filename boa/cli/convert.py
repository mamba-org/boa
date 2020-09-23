# convert between recipe.yaml and meta.yaml
import ruamel
from ruamel.yaml.representer import RoundTripRepresenter
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml import YAML
from collections import OrderedDict
from pprint import pprint
import collections
import os
import sys
import re

class MyRepresenter(RoundTripRepresenter):
    pass
ruamel.yaml.add_representer(OrderedDict, MyRepresenter.represent_dict, representer=MyRepresenter)

def main(docname):

    with open(docname, 'r') as fi:
        lines = fi.readlines()
    context = {}
    rest_lines = []
    for line in lines:
        # print(line)
        if '{%' in line:
            set_expr = re.search('{%(.*)%}', line)
            set_expr = set_expr.group(1)
            set_expr = set_expr.replace('set', '', 1).strip()
            exec(set_expr, globals(), context)
        else:
            rest_lines.append(line)

    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    yaml.width = 1000
    yaml.Representer = MyRepresenter
    yaml.Loader = ruamel.yaml.RoundTripLoader

    result_yaml = CommentedMap()
    result_yaml['context'] = context

    quoted_lines = []

    def check_if_quoted(s):
        s = s.strip()
        return (s.startswith('"') or s.startswith("'"))

    for line in rest_lines:
        if '{{' in line:
            # make sure that jinja stuff is quoted
            if line.strip().startswith('-'):
                idx = line.find('-')
            else:
                idx = line.find(':')
            rest = line[idx + 1:]

            if not check_if_quoted(rest):
                if '\'' in rest:
                    rest = rest.replace('\'', '\"')

                line = line[:idx + 1] + f" \'{rest.strip()}\'\n"
        quoted_lines.append(line)

    def has_selector(s):
        return s.strip().endswith(']')

    rest_lines = quoted_lines

    quoted_lines = []
    for line in rest_lines:
        if has_selector(line):
            selector_start = line.rfind('[')
            selector_end = line.rfind(']')
            selector_content = line[selector_start + 1:selector_end]

            if line.strip().startswith('-'):
                line = line[:line.find('-') + 1] + f' sel({selector_content}): ' + line[line.find('-') + 1:min(line.rfind('#'), line.rfind('['))].strip() + '\n'
        quoted_lines.append(line)
    rest_lines = quoted_lines

    result_yaml.update(ruamel.yaml.load(''.join(rest_lines), ruamel.yaml.RoundTripLoader))

    data = ruamel.yaml.load(''.join(rest_lines), ruamel.yaml.RoundTripLoader)
    from io import StringIO
    output = StringIO()
    yaml.dump(result_yaml, output)

    # Hacky way to insert an empty line after the context-key-object
    context_output = StringIO()
    yaml.dump(context, context_output)
    context_output = context_output.getvalue()
    context_output_len = len(context_output.split('\n'))

    final_result = output.getvalue()
    final_result_lines = final_result.split('\n')
    final_result_lines.insert(context_output_len, '')

    print('\n'.join(final_result_lines))