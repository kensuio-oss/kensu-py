""" Diagnostics tool for integration

This script attempts to list all functions called by Python files in a directory

# TODO
# [ ] document use cases
# [ ]   when to run dynamic diags (trace) or static diags (this)
# [ ]   csv file or Kensu API to send json (In Databricks it's difficult to retrieve info)
# [ ] dyn: access to env/venv for resolution: execute within context

# [ ] json output for api
# [ ] ?¿ csv output for local (easy to manipulate in excel)
# [ ] make it run on kensu-py as example

# [ ] rename functions with unclear names
# [ ] explain process, ... doc

# https://stackoverflow.com/questions/54325116/can-i-handle-imports-in-an-abstract-syntax-tree

"""

from glob import glob
import logging
import os
import sys
import ast
from typing import Set, List, Dict
import importlib
import logging
import pandas
from argparse import ArgumentParser
from inspect import getmembers, isfunction

logger = logging.getLogger(__name__)
args = None


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


def get_imports(py_file_content: str) -> (Set[str], Set[str]):
    """
    Collect imports from a given python file content.
    Does not yet support partial imports such as `from a import b` where b is a callable
    """
    parsed = ast.parse(py_file_content)
    imports = set()
    funcs = set()
    funcdefs = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            for name in node.names:
                if args.debug:
                    print(f" -- ast.Import name: {name.name} as: {name.asname}")
                imports.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # TODO check for relative imports
                # node.module.split('.')
                if args.debug:
                    print("     -- relative import first name: {}".format(node.names[0].name))
            if args.debug:
                print(f" -- ast.ImportFrom module: {node.module} names: {node.names} level: {node.level}")
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            fname = None
            if isinstance(node.func, ast.Attribute):
                fname = node.func.value
                if isinstance(fname, ast.Name):
                    fname = fname.id
            elif isinstance(node.func, ast.Name):
                fname = node.func.id
            if args.debug:
                print(f" -- CALL: {fname} ARGS: {node.args} KWS: {node.keywords}")
            funcs.add(fname)
        elif isinstance(node, ast.FunctionDef):
            #   handle scopes in the visitor
            #   multi pass to resolve inherited methods
            print(f"node is FUNCDEF {node.name}")
            funcdefs.add(node.name)
        else:
            if args.debug:
                print(f"    --- node is {node}")
            pass
    return imports, funcs, funcdefs


def analyze_multi(filenames: List[str]) -> (Set, Dict, Set):
    all_imports = set()
    all_funcs = set()
    imports_per_file = dict()
    for fname in filenames:
        if args.debug:
            print(f"file: {fname}")
        with open(os.path.join(fname), "rb") as f:
            content = f.read()
            s, funcs, _ = get_imports(content)
            imports_per_file[fname] = s
            all_imports.update(s)
            all_funcs.update(funcs)
        if args.verbose:
            print(f"    imports: {s}")
            print(f"    funcs: {funcs}")
            print(" ---°-°-°-° °-°°---------\n")
    return all_imports, imports_per_file, all_funcs


def analyze_multi2(filenames: List[str]) -> (Set, Dict, Set):
    lib_imports = dict()
    file2imp2func2count = dict()
    flat = []
    for filename in filenames:
        if args.debug:
            print(f"file: {filename}")
        with open(os.path.join(filename), "rb") as f:
            content = f.read()

        parsed = ast.parse(content)

        imports = set()
        func_calls = []
        func_defs = set()

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if args.debug:
                        print(f" -- ast.Import name: {name.name} as: {name.asname}")
                    imports.add(name.name)
                    if name.name not in lib_imports.keys():
                        try:
                            mo = importlib.import_module(name.name)
                            g = getmembers(mo, isfunction)
                            if args.debug:
                                print(f"real_imports_per_file_with_inspect {name.name}: {g}")
                            lib_imports[name.name] = [v[0] for v in g]
                        except ImportError:
                            print(f"couldn't import {name.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    # TODO check for relative imports
                    # node.module.split('.')
                    if args.debug:
                        print("     -- relative import first name: {}".format(node.names[0].name))
                if args.debug:
                    print(f" -- ast.ImportFrom module: {node.module} names: {node.names} level: {node.level}")
                imports.add(node.module)
                if node.module not in lib_imports.keys():
                    try:
                        mo = importlib.import_module(node.module)
                        g = getmembers(mo, isfunction)
                        if args.debug:
                            print(f"real_imports_per_file_with_inspect {node.module}: {g}")
                        lib_imports[node.module] = [v[0] for v in g]
                    except ImportError:
                        print(f"couldn't import {name.name}")

            elif isinstance(node, ast.Call):
                func_name = None
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                    if isinstance(func_name, ast.Name):
                        func_name = func_name.id
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if args.debug:
                    print(f" -- CALL: {func_name} ARGS: {node.args} KWS: {node.keywords}")
                func_calls.append(func_name)

            elif isinstance(node, ast.FunctionDef):
                #   handle scopes in the visitor
                #   multi pass to resolve inherited methods
                print(f"node is FUNCDEF {node.name}")
                func_defs.add(node.name)
            else:
                if args.debug:
                    print(f"    --- node is {node}")
                pass
            # return imports, funcs, funcdefs

            # imports_per_file[filename] = imps
            #all_imports.update(imps)
            # all_funcs.update(funcs)
        if args.verbose:
            print(f"    imports: {imports}")
            print(f"    calls: {func_calls}")
            print(f"    defs: {func_defs}")
            print(" ---°-°-°-° °-°°---------\n")

        for cal in func_calls:
            if cal in func_defs:
                if args.debug:
                    print(f"    - not counting locally defined func call: {cal}")
                pass
            # find call in imports
            for i in imports:
                if i not in lib_imports.keys():
                    print(f" ^$ù`=+/:^$ù`=+/: haven't found lib {i} in lib_imports {lib_imports.keys()}")
                if cal in lib_imports[i]:
                    print(f"COUNTING A CALL {cal} for {lib_imports[i]} in {filename}")
                    # if defined ? file2imp2func2count[filename]
                    if filename in file2imp2func2count\
                        and i in file2imp2func2count[filename]:
                        cal = file2imp2func2count[filename][i]
                        count = file2imp2func2count[filename][i][cal]
                        if count is None or not isinstance(count, int):
                            print(f"yikes count is {count}")
                            file2imp2func2count[filename][i][cal] = 1
                        else:
                            file2imp2func2count[filename][i][cal] = count + 1

        # file2imp2func2count[fname]
        print("analyze_multi2 end")
    return file2imp2func2count


def real_imports_per_file_with_inspect(module_name: str):
    # check if not loaded already?
    try:
        mo = importlib.import_module(module_name)
        g = getmembers(mo, isfunction)
        if args.debug:
            print(f"real_imports_per_file_with_inspect {module_name}: {g}")
        return [v[0] for v in g], None
    except ImportError:
        return None, module_name


def all_imports_flattened(imports:dict):
    #importz2 = dict()
    allz = set()
    for k, v in imports.items():
        #importz2[k] = dir(v)
        allz.update(dir(v))
    return allz


def main(cli_args=None):
    usage = """python diagnostics.py <DIR> [options] [--csv]"""
    desc = ("""Attempts to report all functions used per imported modules in python files
        sdfsdf
        """)
    global args

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
        # TODO check that Python version is compatible with imports from pythonpath!
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
    if len(unspecified) == 1:
        thefilesrex = get_dir_file_regex(unspecified[0])
    else:
        # thefilesrex = get_dir_file_regex(os.getcwd() + "/tests/diags_test_code")
        # thefilesrex = get_dir_file_regex("/Users/stan/src/pyan/tests/test_code_diags_simple")
        thefilesrex = get_dir_file_regex("../../tests/unit/data/diags_test_code")

    if args.verbose:
        print(f"thefilesrex: {thefilesrex}")

    filenames = get_files_from_regex_string(thefilesrex)
    if args.verbose:
        print(f"filenames: {filenames}")

    r = analyze_multi2(filenames)
    print(f"analyze_multi2: {r}")
    print("TODO remove above")
    if 1 == 1:
        sys.exit(0)

    all_imports, imports_per_file, all_funcs = analyze_multi(filenames)
    if args.verbose:
        print(f"\n\nAll imports flat: {all_imports}")
        print("\n\n")

    allz = set()
    errz = set()
    for imp in all_imports:
        ok, ko = real_imports_per_file_with_inspect(imp)
        if ok is not None:
            allz.update(ok)
        if ko is not None:
            errz.update(ko)

    #flats = all_imports_flattened(allz)
    #if 'execle' in funcz:
    #    print("VIIIIIKTOREYYYY execle is in funcz")

    if 'execle' in allz:
        print("VIIIIIKTOREYYYY execle is in allz")

    print("done")
    # TODO Json plutôt que csv


if __name__ == '__main__':
    main()



"""
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

"""