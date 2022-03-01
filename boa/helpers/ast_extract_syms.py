import ast


class NameCollector(ast.NodeTransformer):
    def __init__(self):
        self.collected_names = []

    def visit_Name(self, node):
        self.collected_names.append(node.id)


def ast_extract_syms(expr):
    nodes = ast.parse(expr)
    transformer = NameCollector()
    transformer.visit(nodes)
    return transformer.collected_names


if __name__ == "__main__":
    print(ast_extract_syms("vc <14"))
    print(ast_extract_syms("python > (3,6)"))
    print(ast_extract_syms("somevar == (3,6)"))
    print(ast_extract_syms("target_platform == 'linux'"))
