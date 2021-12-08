""" Diagnostics tool for integration

This script attempts to list all functions called by Python files in a directory

# TODO
# [ ] document use cases
# [ ]   when to run dynamic diags (trace) or static diags (this)
# [ ]   csv file or Kensu API to send json (In Databricks it's difficult to retrieve info)
# [ ] dyn: access to env/venv for resolution: execute within context
# if pythonpath !!! car python exec doit être le même pour pouvoir charger les libs avec importlib
# [ ] json output for api
# [ ] csv output for local (easy to manipulate in excel)
# [ ] make it run on kensu-py as example

# [ ] clean scraps at the end
# [ ] rename functions with unclear names
# [ ] explain process, ... doc
"""

from glob import glob
import logging
import os
import sys
import ast
from typing import Set, List
import importlib
import logging
import pandas
from argparse import ArgumentParser
from inspect import getmembers, isfunction

logger = logging.getLogger(__name__)
# https://stackoverflow.com/questions/54325116/can-i-handle-imports-in-an-abstract-syntax-tree
args = None


def get_dir_file_regex(dir_name: str):
    if not os.path.exists(dir_name):
        sys.stderr.write(f"Path does not exist: {dir_name}")
        sys.exit(-1)
    if not os.path.isdir(dir_name):
        sys.stderr.write(f"Path is not a directory: {dir_name}")
        sys.exit(-1)
    # TODO this is necessary because of a bug in pyan:1.2.1
    # https://github.com/Technologicat/pyan/issues/70
    if not os.path.isabs(dir_name):
        sys.stderr.write(f"Please provide an absolute path: {dir_name}")
        sys.exit(-1)
    # can add a "." path resolution
    return f"{dir_name}/**/*.py"


def get_files_from_regex_string(rex: str) -> List[str]:
    return glob(rex, recursive=True)


def get_imports(py_file_content: str) -> Set[str]:
    """
    Collect imports from a given python file content.
    Does not yet support partial imports such as `from a import b` where b is a callable
    """
    parsed = ast.parse(py_file_content)
    imports = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for name in node.names:
                # top_imported.add(name.name.split('.')[0])
                if args.debug:
                    print(f" -- ast.Import name: {name.name} as: {name.asname}")
                imports.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # Relative imports always refer to the current package.
                if args.debug:
                    print("     -- relative import first name: {}".format(node.names[0].name))
                # continue
            # assert node.module
            #top_imported.add(node.module.split('.')[0])
            if args.debug:
                print(f" -- ast.ImportFrom module: {node.module} names: {node.names} level: {node.level}")
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            descr = "TODO"
            if isinstance(node.func, ast.Attribute):
                descr = node.func.value
                if isinstance(descr, ast.Name):
                    descr = descr.id
            elif isinstance(node.func, ast.Name):
                descr = node.func.id
            if args.debug:
                print(f" -- CALL: {descr} ARGS: {node.args} KWS: {node.keywords}")
            # TODO collect in variables
        # elif isinstance(node, ast.FunctionDef):
        # should handle scopes in the visitor
        # multi pass to resolve inherited methods
        else:
            if args.debug:
                print(f"    --- node is {node}")
            pass
    return imports


def analyze_multi(filenames:List[str]) -> Set:
    all_imports = set()
    imports_per_file = dict()
    for fname in filenames:
        print(f"file: {fname}")
        with open(os.path.join(fname), "rb") as f:
            content = f.read()
            s = get_imports(content)
            imports_per_file[fname] = s
            all_imports.update(s)
            print(s)
        if args.verbose:
            print(" ---°-°-°-° °-°°---------\n")
    return all_imports, imports_per_file


def real_imports_per_file_with_importlib(all_imports):
    importz = dict()
    for i in all_imports:
        if i not in importz.keys():  # load only once
            try:
                b = importlib.import_module(i)
                importz[i] = b
            except ImportError as err:
                print('Error loading import: ', err)
                print(f"could load so far: {importz.keys()}")
                print(f"couldn't load: {i}. Exiting")
                sys.exit(-1)
    return importz, all_imports_flattened(importz)


def real_imports_per_file_with_inspect(module_name:str):
    # check if not loaded already?
    try:
        mo = importlib.import_module(module_name)
        g = getmembers(mo, isfunction)
        if args.debug:
            print(f"real_imports_per_file_with_inspect {module_name}: {g}")
        return g, None
    except ImportError:
        return None, module_name


def all_imports_flattened(imports:dict):
    importz2 = dict()
    allz = set()
    for k, v in imports.items():
        importz2[k] = dir(v)
        allz.update(dir(v))
    return allz


def main(cli_args=None):
    usage = """python diagnostics.py <DIR> [options] [--csv]"""
    desc = ("""Attempts to report all functions used per imported modules in python files
        sdfsdf
        """)
    global args

    # TODO Json plutôt que csv
    parser = ArgumentParser(usage=usage, description=desc)
    parser.add_argument("-v", "--verbose", action="store_true", default=False, dest="verbose", help="verbose debugging")
    parser.add_argument("-d", "--debug", action="store_true", default=False, dest="debug", help="debug prints")
    parser.add_argument("-l", "--log", dest="logname", help="write log to LOG", metavar="LOG")
    parser.add_argument("-p", "--pythonpath", dest="ppath", default=None, help="Pythonpath if not set in in "
                                                                               "run environment for this script")
    parser.add_argument("--csv", action="store_true", default=False, help="write report as .csv file")
    parser.add_argument("--json", action="store_true", default=False, help="write report as .csv file")

    args, unspecified = parser.parse_known_args(cli_args)

    if args.ppath is not None:
        print("PYTHONPATH argument --pythonpath is not implemented yet")
        sys.exit(-1)
        # TODO set PYTHONPATH
        # if os.path.isdir(args.ppath):
        #   env['PYTHONPATH'] = os.path.dirname(args.ppath)
        # else raise exeception and exit

    if args.csv and args.debug:
        print("outputting to csv: out.csv")

    if args.verbose:
        logger.setLevel(logging.INFO)
    elif args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARN)

    # TODO resolve from path passed

    # thefilesrex = get_dir_file_regex(os.getcwd() + "/tests/diags_test_code")
    thefilesrex = get_dir_file_regex("/Users/stan/src/pyan/tests/test_code_diags_simple")
    if args.verbose:
        print(f"thefilesrex: {thefilesrex}")

    filenames = get_files_from_regex_string(thefilesrex)
    if args.verbose:
        print(f"filenames: {filenames}")

    # v = CallGraphVisitor(filenames, logger=logger)
    allimportz, importz_per_file = analyze_multi(filenames)
    if args.verbose:
        print(f"\n\nAll imports flat: {allimportz}")
        print("\n\n")

    allz = set()
    errz = set()
    for imp in allimportz:
        ok, ko = real_imports_per_file_with_inspect(imp)
        if ok is not None:
            allz.update(ok)
        if ko is not None:
            errz.update(ko)

    if 'execle' in allz:
        print("VIIIIIKTOREYYYY")
    else:
        print("NEeyeyEYYEyeYEyEYEY")

    for k, v in importz_per_file.items():
        alls = set()
        print(f"DOING: k, v {k} {v}")
        for val in v:
            print(f"doing val {val}")
            r, errr = real_imports_per_file_with_inspect(val)
            if r is not None:
                alls.update(r)
            else:
                print(f" {val}")
        if 'pivot' in alls:
            print(f"VIIIIIKTOREYYYY CategoricalDtype is in imported {k}")
        #else:
        #    print(f"NEeyeyEYYEyeYEyEYEY CategoricalDtype is not in imported module {k} {v}")
    print("done")
    # TODO Json first, csv?


if __name__ == '__main__':
    main()
    sys.exit(0)


def test_1():
    #print(importz)
    #p = importz['pandas']
    #print('\n\n')
    # print(p.__dict__)
    #pp = dir(p)
    #print('\n\n')

    thefilesrex = get_dir_file_regex(os.getcwd() + "/tests/diags_test_code")
    print(f"thefilesrex: {thefilesrex}")
    filenames = get_files_from_regex_string(thefilesrex)
    print(f"filenames: {filenames}")
    # v = CallGraphVisitor(filenames, logger=logging.getLogger())
    imports = analyze_multi(filenames)
    print(f"\n\nimports: {imports}")
    print("\n\n")


    # find pandas.CategoricalDtype for example
    if 'CategoricalDtype' in allz:
        print("VIIIIIKTOREYYYY")
    else:
        print("NEeyeyEYYEyeYEyEYEY")

    for k, v in importz2.items():
        if 'CategoricalDtype' in v:
            print(f"VIIIIIKTOREYYYY CategoricalDtype is in imported {k}")
        else:
            print(f"NEeyeyEYYEyeYEyEYEY CategoricalDtype is not in imported {k}")






























#############################################

from pyan.analyzer import CallGraphVisitor

# Setting up an importer
# For deep customizations of import, you typically want to implement an importer. This means managing both the finder
# and loader side of things. For finders there are two flavours to choose from depending on your needs:
# a meta path finder or a path entry finder. The former is what you would put on sys.meta_path while the latter
# is what you create using a path entry hook on sys.path_hooks which works with sys.path entries
# to potentially create a finder.
# This example will show you how to register your own importers so that import will use them
# (for creating an importer for yourself, read the documentation for the appropriate classes defined
# within this package):

import importlib.machinery
import sys

# For illustrative purposes only.
SpamMetaPathFinder = importlib.machinery.PathFinder
SpamPathEntryFinder = importlib.machinery.FileFinder
loader_details = (importlib.machinery.SourceFileLoader,
                  importlib.machinery.SOURCE_SUFFIXES)

# Setting up a meta path finder.
# Make sure to put the finder in the proper location in the list in terms of
# priority.
sys.meta_path.append(SpamMetaPathFinder)

# Setting up a path entry finder.
# Make sure to put the path hook in the proper location in the list in terms
# of priority.
sys.path_hooks.append(SpamPathEntryFinder.path_hook(loader_details))

# Approximating importlib.import_module()
# Import itself is implemented in Python code, making it possible to expose most of the import machinery through
# importlib. The following helps illustrate the various APIs that importlib exposes by providing an approximate
# implementation of importlib.import_module() (Python 3.4 and newer for the importlib usage,
# Python 3.6 and newer for other parts of the code).

import importlib.util
import sys


def import_module(name, package=None):
    """An approximate implementation of import."""
    absolute_name = importlib.util.resolve_name(name, package)
    try:
        return sys.modules[absolute_name]
    except KeyError:
        pass

    path = None
    if '.' in absolute_name:
        parent_name, _, child_name = absolute_name.rpartition('.')
        parent_module = import_module(parent_name)
        path = parent_module.__spec__.submodule_search_locations
    for finder in sys.meta_path:
        spec = finder.find_spec(absolute_name, path)
        if spec is not None:
            break
    else:
        msg = f'No module named {absolute_name!r}'
        raise ModuleNotFoundError(msg, name=absolute_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[absolute_name] = module
    spec.loader.exec_module(module)
    if path is not None:
        setattr(parent_module, child_name, module)
    return module

#########################################################################################################
#########################################################################################################
#########################################################################################################
#########################################################################################################
#########################################################################################################
#########################################################################################################

sys.exit()


v = CallGraphVisitor(filenames, logger=logging.getLogger())
print(f"v: {v}")
cg = callgraph()
print(f"cg: {cg}")
a = [(n.name, n.ast_node, n.flavor, n.defined) for n in v.uses_edges]
print(f"a: {a}")

"""
#############################################################################################################
"""
# 1 get for each module Node the imports
# 2 resolve the imports with pythonpath among others
# 3 for every sub of those modules resolves those imports
# 4 count the f() calls

# 1 get for each module Node the imports
# imports = [e for e in v.uses_edges]
imports = [e for e in v.uses_edges]
print(imports)
# imports[0].ast_node.body
"""Out[31]: 
[<_ast.Import at 0x10c00a280>,
 <_ast.Import at 0x10c00a4f0>,
 <_ast.ImportFrom at 0x10c00a520>,
 <_ast.Assign at 0x10c00af70>,
 <_ast.FunctionDef at 0x10c00a7f0>]"""


"""
imports[0].ast_node.body[0].names[0].name
for imp in imports:
    for nod in imp.ast_node.body:
        if isinstance(nod, ast.Import):
            pass
            print(f"isinstance(nod, ast.Import): names {nod.names}: True")
        if isinstance(nod, ast.ImportFrom):
            pass
            print(f"isinstance(nod, ast.ImportFrom): names: {nod.module} {nod.names} {nod.level}: True")
"""

# 2 resolve the imports with pythonpath among others


def isimport(nod):
    return isinstance(nod, ast.Import) or isinstance(nod, ast.ImportFrom)


def get_name(nod):
    if isimport(nod):
        names = [n.name.name for n in nod.names]
        r = []
        for n in names:
            if isinstance(n, ast.alias):
                print("ST_____AAAAAAAAn" + n.__class__)
                r.append("name {}, asname {}".format(n.name, n.asname))
            else:
                print("STAAAAAAAAn" + n.__class__)
                r.append(n.__str__)
        return "///".join(r)
    return None


# imports = [e for e in v.uses_edges if isimport(e)]

a = importlib.import_module('os')
try:
    b = importlib.import_module('pandas.DataFrame')
except ImportError as err:
    print('Error, importing classes nto allowed:', err)

c = importlib.import_module('')


for imp in imports:
    for nod in imp.ast_node.body:
        if isinstance(nod, ast.Import):
            print("isinstance(nod, ast.Import): names: {}".format(get_name(nod)))
            # importlib.import_module('.c', 'a.b')
            # importlib.import_module('a.b.c')
            im = importlib.import_module('test_code.subpackage1.submodule1')

        if isinstance(nod, ast.ImportFrom):
            print(f"isinstance(nod, ast.ImportFrom): names: {nod.module} {get_name(nod)} {nod.level}: True")
        else:
            print("WRONG")
# 3 for every sub of those modules resolves those imports

# 4 count the f() calls




import sys
sys.exit(0)

# def test_resolve_package_with_known_root():
dirname = test_dir
filenames = glob(os.path.join(dirname, "test_code/**/*.py"), recursive=True)
print(filenames)
callgraph = CallGraphVisitor(filenames, logger=logging.getLogger(), root=dirname)
dirname_base = os.path.basename(dirname)
print(dirname_base)
defines = get_in_dict(cg.defines_edges, f"{dirname_base}.test_code_diags.subpackage2.submodule_hidden1")
print(defines)
n = get_node(defines, f"{dirname_base}.test_code_diags.subpackage2.submodule_hidden1.test_func1")
print(n)



"""
#############################################################################################################
"""
import sys
sys.exit(0)

"""
dirname = os.path.dirname(os.getcwd() + "/tests")
print(dirname)
filenames = glob(os.path.join(dirname, "test_code/**/*.py"), recursive=True)
print(filenames)
callgraph = CallGraphVisitor(filenames, logger=logging.getLogger(), root=dirname)
dirname_base = os.path.basename(dirname)
print(dirname_base)
defines = get_in_dict(callgraph.defines_edges, f"{dirname_base}.test_code_diags.subpackage2.submodule_hidden1")
print(defines)
n = get_node(defines, f"{dirname_base}.test_code_diags.subpackage2.submodule_hidden1.test_func1")
print(n)



test_resolve_import_as()
test_import_relative()
test_resolve_use_in_class()
test_resolve_use_in_function()
test_resolve_package_without___init__()
test_resolve_package_with_known_root()
"""

import imp
import ast

# TODO hardcoded example
# /Users/stan/src/pyan/pyan/main.py
# path_to_config = srcs_dir + "/main.py"
path_to_config = None
_package_paths = {}


# (*) imp.find_module() is deprecated for Python 3 code.
# On Python 3 you would use importlib.util.find_spec() to get the module loader spec,
# and then use the ModuleSpec.origin attribute to get the filename.
# importlib.util.find_spec() knows how to handle packages.


def _is_admissible_node(script_object):
    # for now everything is admissible, it's just a sample code taken from SO, to be adapted without this function
    return True


def find_module(module):
    # imp.find_module can't handle package paths, so we need to do this ourselves
    # returns an open file object, the filename, and a flag indicating if this
    # is a package directory with __init__.py file.
    path = None
    if '.' in module:
        # resolve the package path first
        parts = module.split('.')
        module = parts.pop()
        for i, part in enumerate(parts, 1):
            name = '.'.join(parts[:i])
            if name in _package_paths:
                path = [_package_paths[name]]
            else:
                _, filename, (_, _, type_) = imp.find_module(part, path)
                if type_ is not imp.PKG_DIRECTORY:
                    # no Python source code for this package, abort search
                    return None, None
                _package_paths[name] = filename
                path = [filename]
    source, filename, (_, _, type_) = imp.find_module(module, path)
    is_package = False
    if type_ is imp.PKG_DIRECTORY:
        # load __init__ file in package
        source, filename, (_, _, type_) = imp.find_module('__init__', [filename])
        is_package = True
    if type_ is not imp.PY_SOURCE:
        return None, None, False
    return source, filename, is_package

if 1 == 2:
    with open(path_to_config) as config_file:
        # stack consists of (modulename, ast) tuples
        stack = [('', ast.parse(config_file.read()))]

    seen = set()
    while stack:
        modulename, ast_tree = stack.pop()
        for script_object in ast_tree.body:
            if isinstance(script_object, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in script_object.names]
                from_names = []
                if hasattr(script_object, 'level'):  # ImportFrom
                    from_names = names
                    name = script_object.module
                    if script_object.level:
                        package = modulename.rsplit('.', script_object.level - 1)[0]
                        if script_object.module:
                            name = "{}.{}".format(name, script_object.module)
                        else:
                            name = package
                    names = [name]
                for name in names:
                    if name in seen:
                        continue
                    seen.add(name)
                    source, filename, is_package = find_module(name)
                    if source is None:
                        continue
                    if is_package and from_names:
                        # importing from a package, assume the imported names
                        # are modules
                        names += ('{}.{}'.format(name, fn) for fn in from_names)
                        continue
                    with source:
                        module_ast = ast.parse(source.read(), filename)
                    stack.append((name, module_ast))

            elif not _is_admissible_node(script_object):
                raise Exception("Config file '%s' contains unacceptable statements" % path_to_config)



# https://docs.python.org/3/library/importlib.html#examples
# To programmatically import a module, use importlib.import_module().
import importlib
itertools = importlib.import_module('itertools')
"""
Checking if a module can be imported
If you need to find out if a module can be imported without actually doing the import, then you should use importlib.util.find_spec().
"""
import importlib.util
import sys

# For illustrative purposes.
name = 'itertools'

if name in sys.modules:
    print(f"{name!r} already in sys.modules")
elif (spec := importlib.util.find_spec(name)) is not None:
    # If you chose to perform the actual import ...
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    print(f"{name!r} has been imported")
else:
    print(f"can't find the {name!r} module")
# Importing a source file directly
# To import a Python source file directly, use the following recipe (Python 3.5 and newer only):
import importlib.util
import sys
# For illustrative purposes.
import tokenize
file_path = tokenize.__file__
module_name = tokenize.__name__

spec = importlib.util.spec_from_file_location(module_name, file_path)
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)

# Implementing lazy imports
# The example below shows how to implement lazy imports:
import importlib.util
import sys
def lazy_import(name):
    spec = importlib.util.find_spec(name)
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module

lazy_typing = lazy_import("typing")
#lazy_typing is a real module object,
#but it is not loaded in memory yet.
lazy_typing.TYPE_CHECKING
# False
