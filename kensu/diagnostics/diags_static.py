""" Diagnostics tool for integration

A tool to assess the packages and function usages for rapid customer's usage of libraries and related functions.
During pre-sales, integration or the inital contact with a customer we want to quickly assess
the libraries and functions used by that customer as to have an idea (a scan, a diagnostic) of their
usages, to direct the initial and subsequent implementations strategically.

It helps having a quantified ideas on their python codebase.

v1.0

local lingo:
- DF: short for DataFrame (pandas)
- FBW: Feature, Bug or Workaround (can be later split into FEAT, BUG, WKRND)
- AST: abstract syntax tree (compiler theory)
- node: an AST node, in this script as returned by Python's own parser in the "ast" library
- scope: in compilers, a context. Inside a scope we can talk of the visibility of a variable within
    a function for example, or visibility of a sub-function within a class. As scope is that context where
    local symbols are visible and shadowing superscope syms with the same qualifier. A super defined sym can still
    eventually be accessed through its FQN. Blocs in Java have their own scopes.


This script attempts to list all functions called by Python files in a directory

# TODO
[ ] json output: option to flatten all files (like merge function)
[ ] csv file or Kensu API to send json (In Databricks it's difficult to retrieve info)
[ ] ?¿ csv output for local (easy to manipulate in excel)
[ ] make it run on kensu-py as example

# extra bugs, features or workarounds:
[ ] merging the results has side effects, so counts gets added for file if function seen previously:
    merge_multi2 with 2 identical files different names and one of them will have
[ ] FBW005 keep a list of already imported superclasses (we loop several times over __mro__, in pandas several
    datatypes inherit from Numerical NumericDtype.
[ ] FBW006 make sure when checking for superclasses we don't check for obvious ones like builtins 'object' and 'type'
    [ ] probably related: DataFrame.describe is not found in flattened imports

# https://stackoverflow.com/questions/54325116/can-i-handle-imports-in-an-abstract-syntax-tree

--------------------------------------------------------------------------------

"ideal" approach:
Make a full Python parser/grammar with a full semantic layer for symbolic resolution (symres) with
type resolution (typeres) and code flow for linking function uses to the imports.
Or use Python's internal mecahnism if such exists

ex:
```from pandas import *
df = DataFrame()
df.describe()
from kensu.pandas import *
df = DataFrame()
df.describe()
```
in this example we should track the fact DF is from imported pandas, assigned to df, then describe called in that df
as to log that describe() is from pandas.
Then notice in the same way that the subsequent describe belongs to the kensu lib.

--------------------------------------------------------------------------------

20211220 current approach:
    We can't *quickly* make a full symres and code flow, so we go for approximations.
    A full symres (type resolution) and flow would require lots of work in this complex loosely typed language
    that is Python.
    There might be several overlaps in function names, "add" can be found in pandas DF, in python arrays, ...
    So for flattened recursive (full) imports matched against the list of all locally called functions we could
    have ambiguity. A simple disambiguation alert can be raised by warning the potential dual use we could detect.
    We don't import python's builtins, so an array "add" could be wrongly attributed to a pandas add if pandas is
    flatly imported in that python file context.
    Ambiguity is shown as the potential match (belonging) of a function to two or more packages.

    To simplify the approach we state that
    - FBW001:  All imports are considered equal:
        - we just import recursively the imports and flatten them into the packages:
            "import pandas.*; from pandas import DataFrame" will put DF "describe" and "add" into "pandas" package.
        - The "from x import y" becomes from x. This can easily be made right later by proper handling of
            the ImportFrom nodes.
            Until then "from pandas.DataFrame import add; from kensu.pandas.Dataframe import describe"
            will fuzzily match "add" and "describe" to both kensu and pands packages.
    - FBW002: Locally defined functions are skipped for now, we match them with FuncDef calls
        [ ] TODO: report them in the ambiguous package attribution if need be:
        ```def add(a, b):
         return a ++ b
        from pandas import DataFrame
        df1 = DataFrame()
        df2 = DataFrame()
        df1.add(df2)```
        For now in V1.0 we don't report ambiguity. WE just skip, so add is is the locally defined functions,
        shadowing DF.add
    - FBW003 no handling of scopes
        if an import is performed in a sub scope (indented part of code, inside a function, ... then it is not reachable
        to the superscope normally.
        So in this case:
        ``` from a import a
        def b:
            from c import d
            d
        b()
        d()
        ```
        we wrongly consider d is reachable outside of b.

    note:
    - FBW004: TODO: ensure we don't save members inherited from other packages, such as base types 'object' and 'type'
        by integrating superclass symbols we shouldn't import classes outside the package at hand for inheritance?
        everyone extend 'object' or 'type' in Python


TODO USAGE:
pip install kensu-py
# the absolute or relative path to the source file you want to analyze
python -m kensu.diagnostics.diags_static ../src/anyproject

or download script and
python diags_static.py -v -d  # by default "." path is assumed
python diags_static.py -ppath /path_to_pythonpath sourcedir/

run the unit tests in kenspy/tests/unit/test_diagnostics_static.py

--------------------------------------------------------------------------------

"""

from glob import glob
import json
import os
import sys
import ast
from typing import Set, List, Dict
from types import BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType
import importlib
import logging
from argparse import ArgumentParser
from inspect import getmembers, isfunction, isclass, ismethod, ismodule

logger = logging.getLogger(__name__)
args = None
conf = None


def get_dir_file_regex(dir_name: str):
    if not os.path.exists(dir_name):
        sys.stderr.write(f"Path does not exist: {dir_name}")
        sys.exit(-1)
    if not os.path.isdir(dir_name):
        sys.stderr.write(f"Path is not a directory: {dir_name}")
        sys.exit(-1)
    # TODO this is necessary because of a bug in pyan:1.2.1 disabling relative paths
    # https://github.com/Technologicat/pyan/issues/70
    if not os.path.isabs(dir_name):
        absp = os.path.abspath(dir_name)
        if not os.path.isabs(absp):
            sys.stderr.write(f"Please provide an absolute path to: {dir_name}")
            sys.exit(-1)
        dir_name = absp
    # can add a "." path resolution
    return f"{dir_name}/**/*.py"


def get_files_from_regex_string(rex: str) -> List[str]:
    return glob(rex, recursive=True)


def merge_file2imp2func2count(d1: dict, d2: dict):
    for f in d2:
        if f not in d1.keys():
            d1[f] = dict()
        for i in d2[f]:
            if i not in d1[f].keys():
                d1[f][i] = dict()
            for fun in d2[f][i]:
                if fun in d1[f][i].keys():
                    d1[f][i][fun] = d1[f][i][fun] + d2[f][i][fun]
                else:
                    d1[f][i][fun] = d2[f][i][fun]
    return d1


def analyze_multi2(filenames: List[str]) -> (Set, Dict, Set):
    file2imp2func2count = dict()
    flat = []
    for filename in filenames:
        if args.debug:
            print(f"file: {filename}")
        with open(os.path.join(filename), "rb") as f:
            content = f.read()
        res = parse_single_file_content(filename, content, file2imp2func2count)
        file2imp2func2count = merge_file2imp2func2count(file2imp2func2count, res)
    return file2imp2func2count


def parse_single_file_content(filename: str, content: str, file2imp2func2count: Dict = None):

    # when testing single files
    if file2imp2func2count is None:
        file2imp2func2count = dict()

    parsed = ast.parse(content)

    imports = set()
    func_calls = []
    func_defs = set()
    lib_imports = dict()

    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for name in node.names:
                conf.debug and print(f" -- ast.Import name: {name.name} as: {name.asname}")
                imports.add(name.name)
                # TODO bug here, should update not assign
                li = imports_flat(name.name, lib_imports)  # FBW003
                for imp in li.keys():
                    if imp in lib_imports.keys():
                        lib_imports[imp] = list(set(li[imp] + lib_imports[imp]))
                    else:
                        lib_imports[imp] = li[imp]

        elif isinstance(node, ast.ImportFrom):  # FBW001
            if node.level > 0:
                # TODO check for relative imports
                # node.module.split('.')
                conf.debug and print("     -- relative import first name: {}".format(node.names[0].name))
            conf.debug and print(f" -- ast.ImportFrom module: {node.module} names: {node.names} level: {node.level}")
            imports.add(node.module)
            # TODO bug here, should update not assign
            li = imports_flat(node.module, lib_imports)  # FBW003
            for imp in li.keys():
                if imp in lib_imports.keys():
                    lib_imports[imp] = list(set(li[imp] + lib_imports[imp]))
                else:
                    lib_imports[imp] = li[imp]

        elif isinstance(node, ast.Call):
            func_name = None
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
                if isinstance(func_name, ast.Name):
                    func_name = func_name.id
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id
            conf.debug and print(f" -- CALL: {func_name} ARGS: {node.args} KWS: {node.keywords}")
            func_calls.append(func_name)

        elif isinstance(node, ast.FunctionDef):
            #   handle scopes in the visitor
            #   multi pass to resolve inherited methods
            conf.debug and print(f"node is FUNCDEF {node.name}")
            func_defs.add(node.name)
        else:
            conf.debug and print(f"    --- node is {node}")
            pass

    if conf.verbose:
        print(f"    imports: {imports}")
        print(f"    calls: {func_calls}")
        print(f"    defs: {func_defs}")
        print(f"    lib_imports: {lib_imports}")
        print(" ---°-°-°-° °-°°---------\n")

    for func_called in func_calls:
        if func_called in func_defs:
            conf.debug and print(f"    - V1.0 FBW002 not counting locally defined func call: {func_called}")
            pass  # FBW002
        # find call in imports
        for i in imports:
            if conf.debug and i not in lib_imports.keys():
                print(f" ^$ù`=+/:^$ù`=+/: haven't found lib {i} in lib_imports {lib_imports.keys()}")
            if func_called in lib_imports[i]:
                conf.verbose and print(f"Counting a call: {func_called} for {lib_imports[i]} in {filename}")
                if filename not in file2imp2func2count:
                    file2imp2func2count[filename] = dict()
                if i not in file2imp2func2count[filename]:
                    file2imp2func2count[filename][i] = dict()
                count = None
                if func_called in file2imp2func2count[filename][i]:
                    count = file2imp2func2count[filename][i][func_called]
                if count is None or not isinstance(count, int):
                    file2imp2func2count[filename][i][func_called] = 1
                else:
                    file2imp2func2count[filename][i][func_called] = count + 1
            else:
                conf.debug and print(f"NOT func_called {func_called} in lib_imports[{i}]: NOT {func_called} in {lib_imports[i]}")
    conf.debug and print("parse_single_file_content end")
    return file2imp2func2count


def import_non_recursive(g):

    def list_of_tuples_to_dict(lt):
        return {item[0]: item[1] for item in lt}

    processed = dict()
    to_process = list_of_tuples_to_dict(getmembers(g))

    count_already_in_processed = dict()  # TODO remove: gives some indication of duplication for development phase

    while len(to_process) > 0:
        to_delete = []
        to_process_next = dict()
        for k, v in to_process.items():
            if k.startswith('_') and k in to_process:
                to_delete.append(k)
            elif k in processed.keys():
                if k not in count_already_in_processed.keys():
                    count_already_in_processed[k] = 1
                else:
                    count_already_in_processed[k] = count_already_in_processed[k] + 1
                if k in to_process:
                    to_delete.append(k)
            else:
                processed[k] = v
                if isclass(v) or ismodule(v):
                    # rec = import_recursive(v)
                    rec = list_of_tuples_to_dict(getmembers(v))
                    to_process_next.update(rec)
                    # TODO FBW004 ensure we don't save members inherited from other packages, such as base types
                    # 'object' and 'type'
                    """
                    # TODO check getmembers takes care of superclasses (mro() or __mro__)
                    if hasattr(v, '__mro__'):
                        for superclass in v.__mro__:
                            if superclass not in processed.keys():
                                keys = [m[0] for m in to_process]
                                if superclass not in keys:
                                    conf.debug and print(f"  class {v} has __mro__: {superclass}")
                                    # rec = import_recursive(v)
                                    rec = list_of_tuples_to_dict(getmembers(superclass))
                                    # to_process.update(rec)
                                    to_process_next.update(rec)
                    """
        for k in to_delete:
            del to_process[k]
        to_process.update(to_process_next)
    conf.verbose and print(f"final count:\n  count_already_in_processed {count_already_in_processed}\n"
                           f"   processed: {processed}")
    return processed


def is_a_callable_type(f):
    return isinstance(f, FunctionType) or isinstance(f, MethodType) or \
           isinstance(f, BuiltinMethodType) or isinstance(f, BuiltinFunctionType)


def imports_flat(module_name: str, lib_imports: Dict):  # FBW003

    if module_name not in lib_imports.keys():
        try:
            mo = importlib.import_module(module_name)
            mems = import_non_recursive(mo)  # FBW003 FWB001
            ms = {k: v for k, v in mems.items() if is_a_callable_type(v) and not k.startswith('__')}

            conf.debug and print(f"imports_flat {module_name}: {ms}")

            if module_name in lib_imports:
                lib_imports[module_name] = lib_imports[module_name] + [k for k, v in ms.items()]
            else:
                lib_imports[module_name] = [k for k, v in ms.items()]
        except ImportError:
            print(f"couldn't import {module_name}")
    return lib_imports


class DiagsConf:

    def __init__(self, verbose=False, debug=False, pythonpath=None,
                 csv=False, json=False, files_dir="."):  # , files_regex = None

        self.verbose = verbose
        self.debug = debug
        self.pythonpath = pythonpath
        self.csv = csv
        self.json = json
        self.files_dir = files_dir
        self.files_regex = None

        if pythonpath is not None:
            # TODO check that Python version is compatible with imports from pythonpath!
            print("PYTHONPATH argument --pythonpath is not implemented yet")
            sys.exit(-1)
            # TODO set PYTHONPATH
            # if os.path.isdir(args.ppath):
            #   env['PYTHONPATH'] = os.path.dirname(args.ppath)
            # else raise exeception and exit

        if self.csv and self.debug:
            print("outputting to csv: out.csv")

        if self.verbose:
            logger.setLevel(logging.INFO)
        elif self.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARN)

        if files_dir is not None:
            self.files_regex = get_dir_file_regex(files_dir)
            if self.verbose:
                print(f"DiagsConf: files_regex: {self.files_regex}")


    @property
    def name(self):
        return "Diagnostics configuration class "

    def __repr__(self):
        return '<%s values: %s>' % (self.__class__.__name__, self.__dict__)


def main(cli_args=None):
    usage = """python diagnostics.py <DIR> [options] [--csv]"""
    desc = ("""Attempts to report all functions used per imported modules in python files
        sdfsdf
        """)
    global args, conf
    # TODO document arguments and usage
    parser = ArgumentParser(usage=usage, description=desc)
    parser.add_argument("-v", "--verbose", action="store_true", default=False, dest="verbose", help="verbose debugging")
    parser.add_argument("-d", "--debug", action="store_true", default=False, dest="debug", help="debug prints")
    parser.add_argument("-l", "--log", dest="logname", help="write log to LOG", metavar="LOG")
    parser.add_argument("-p", "--pythonpath", dest="ppath", default=None, help="Pythonpath if not set in in "
                                                                               "run environment for this script")
    parser.add_argument("--csv", action="store_true", default=False, help="write report as .csv file")
    parser.add_argument("--json", action="store_true", default=False, help="write report as .csv file")

    args, varargs = parser.parse_known_args(cli_args)

    files_dir = None
    if len(varargs) == 1:
        files_dir = varargs[0]
    conf = DiagsConf(verbose=args.verbose, debug=args.debug, pythonpath=args.ppath,
                     # csv=args.csv, json=args.json, files_dir=files_dir or ".")
                     csv=args.csv, json=args.json, files_dir=files_dir if files_dir is not None else ".")

    filenames = get_files_from_regex_string(conf.files_regex)
    if args.verbose:
        print(f"filenames: {filenames}")

    file2imp2func2count = analyze_multi2(filenames)

    print(json.dumps(file2imp2func2count, indent=4))



if __name__ == '__main__':
    main()




"""
# import recursive replaced with import_non_recursive 
# led to call stack issues (bug, loops, circular imports?) 
def import_recursive(g):
    members = dict()
    ms = getmembers(g)

    for member in ms:
        if not member[0].startswith('__') or member[0] == '__init__':
            if member[0] not in members.keys():
                members[member[0]] = member[1]
                if isclass(member[1]) or ismodule(member[1]):
                    print(member[1])
                    rec = import_recursive(member[1])
                    members.update(rec)
                    # TODO FBW004 ensure we don't save members inherited from other packages, such as base types
                    # 'object' and 'type'
                    if hasattr(member[1], '__mro__'):
                        for superclass in member[1].__mro__:
                            if member[0] not in members.keys():
                                conf.debug and print(f"  class {member[1]} has __mro__: {superclass}")
                                rec = import_recursive(member[1])
                                members.update(rec)
    return members

"""