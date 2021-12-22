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
- scope: in compilers, a context. Inside a scope we can talk fo the visibility of a variable within
    a function for example, or visibility of a sub-function within a class. As scope is that context where
    local symbols are visible and shadowing superscope syms with the same qualifier. A super defined sym can still
    eventually be accessed through its FQN. Blocs in Java have their own scopes.


This script attempts to list all functions called by Python files in a directory

# TODO
[ ] document use cases
[ ]   when to run dynamic diags (trace) or static diags (this)
[ ]   csv file or Kensu API to send json (In Databricks it's difficult to retrieve info)
[ ] dyn: access to env/venv for resolution: execute within context
[ ] rename functions with unclear names
[ ] json output for api
[ ] ?¿ csv output for local (easy to manipulate in excel)
[ ] make it run on kensu-py as example

# extra bugs, features or workarounds:
[ ] FBW005 keep a list of already imported superclasses (we loop several times over __mro__, in pandas several
    datatypes inherit from Numerical NumericDtype
[ ] FBW006 make sure when checking for superclasses we don't check for obvious ones like builtins 'object' and 'type'


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
            Until then "from padas.DataFrame import add; from kensu.pandas.Dataframe import describe"
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

--------------------------------------------------------------------------------

"""

from glob import glob
import os
import sys
import ast
from typing import Set, List, Dict
from types import BuiltinFunctionType, BuiltinMethodType
import importlib
import logging
from argparse import ArgumentParser
from inspect import getmembers, isfunction, isclass, ismethod

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


def analyze_multi2(filenames: List[str]) -> (Set, Dict, Set):
    file2imp2func2count = dict()
    flat = []
    for filename in filenames:
        if args.debug:
            print(f"file: {filename}")
        with open(os.path.join(filename), "rb") as f:
            content = f.read()
        file2imp2func2count = parse_single_file_content(filename, content, file2imp2func2count)
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
                lib_imports = imports_flat(name.name, lib_imports)  # FBW003

        elif isinstance(node, ast.ImportFrom):  # FBW001
            if node.level > 0:
                # TODO check for relative imports
                # node.module.split('.')
                conf.debug and print("     -- relative import first name: {}".format(node.names[0].name))
            conf.debug and print(f" -- ast.ImportFrom module: {node.module} names: {node.names} level: {node.level}")
            imports.add(node.module)
            lib_imports = imports_flat(node.module, lib_imports)  # FBW003

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

    for cal in func_calls:
        if cal in func_defs:
            conf.debug and print(f"    - V1.0 FBW002 not counting locally defined func call: {cal}")
            pass  # FBW002
        # find call in imports
        for i in imports:
            if conf.debug and i not in lib_imports.keys():
                print(f" ^$ù`=+/:^$ù`=+/: haven't found lib {i} in lib_imports {lib_imports.keys()}")
            if cal in lib_imports[i]:
                conf.debug and print(f"COUNTING A CALL {cal} for {lib_imports[i]} in {filename}")
                if filename in file2imp2func2count\
                    and i in file2imp2func2count[filename]:
                    cal = file2imp2func2count[filename][i]
                    count = file2imp2func2count[filename][i][cal]
                    if count is None or not isinstance(count, int):
                        conf.debug and print(f"yikes count is {count}")
                        file2imp2func2count[filename][i][cal] = 1
                    else:
                        file2imp2func2count[filename][i][cal] = count + 1
            else:
                conf.debug and print(f"NOT cal in lib_imports[i]: NOT {cal} in {lib_imports[i]}")

    conf.debug and print("parse_single_file_content end")
    return file2imp2func2count


def imports_flat(module_name: str, lib_imports: Dict):  # FBW003

    def import_recursive(g):
        members = dict()
        ms = getmembers(g)
        for member in ms:
            if not member[0].startswith('__'):
                if isclass(member[1]):
                    print(member[1])
                    if member not in members:
                        rec = import_recursive(member[1])
                        members.update(rec)
                        # TODO FBW004 ensure we don't save members inherited from other packages, such as base types
                        # 'object' and 'type'
                        for superclass in member[1].__mro__:
                            conf.debug and print(f"class {member[1]} has __mro__ {superclass}")
                members[member[0]] = member[1]
        return members

    def is_function_or_method(form):
        return True if isfunction(form) or ismethod(form) else False

    if module_name not in lib_imports.keys():
        try:
            mo = importlib.import_module(module_name)
            mems = import_recursive(mo)  # FBW003 FWB001
            ms = {k: v for k, v in mems.items() if isinstance(v, BuiltinFunctionType) or
                 isinstance(v, BuiltinMethodType) and not k.startswith('__')}
            conf.debug and print(f"imports_flat {module_name}: {ms}")

            if module_name in lib_imports:
                lib_imports[module_name] = lib_imports[module_name] + [k for k, v in ms.items()]
            else:
                lib_imports[module_name] = [k for k, v in ms.items()]
            print()
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

    # TODO for UNIT TESTS extract files from analyze so can pass string in unit test
    # TODO unit test all cases from documentation
    file2imp2func2count = analyze_multi2(filenames)
    print(f"analyze_multi2: {file2imp2func2count}")
    print("TODO remove above ----------------------------------------------------------------------------------------")

    # TODO Json plutôt que csv


if __name__ == '__main__':
    main()

