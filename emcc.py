#!/usr/bin/env python2
# Copyright 2011 The Emscripten Authors.  All rights reserved.
# Emscripten is available under two separate licenses, the MIT license and the
# University of Illinois/NCSA Open Source License.  Both these licenses can be
# found in the LICENSE file.

"""emcc - compiler helper script
=============================

emcc is a drop-in replacement for a compiler like gcc or clang.

See  emcc --help  for details.

emcc can be influenced by a few environment variables:

  EMCC_DEBUG - "1" will log out useful information during compilation, as well as
               save each compiler step as an emcc-* file in the temp dir
               (by default /tmp/emscripten_temp). "2" will save additional emcc-*
               steps, that would normally not be separately produced (so this
               slows down compilation).

  EMMAKEN_NO_SDK - Will tell emcc *not* to use the emscripten headers. Instead
                   your system headers will be used.

  EMMAKEN_COMPILER - The compiler to be used, if you don't want the default clang.
"""

from __future__ import print_function

import logging
import os
import shlex
import shutil
import stat
import sys
import time
from subprocess import PIPE

from tools import shared, system_libs, colored_logger
from tools.shared import unsuffixed, unsuffixed_basename, safe_move, run_process, exit_with_error, DEBUG
from tools.shared import BITCODE_ENDINGS, DYNAMICLIB_ENDINGS, STATICLIB_ENDINGS
from tools.response_file import substitute_response_files
from tools.toolchain_profiler import ToolchainProfiler
if __name__ == '__main__':
  ToolchainProfiler.record_process_start()

logger = logging.getLogger('emcc')

# endings = dot + a suffix, safe to test by  filename.endswith(endings)
C_ENDINGS = ('.c', '.C', '.i')
CXX_ENDINGS = ('.cpp', '.cxx', '.cc', '.c++', '.CPP', '.CXX', '.CC', '.C++', '.ii')
OBJC_ENDINGS = ('.m', '.mi')
OBJCXX_ENDINGS = ('.mm', '.mii')
SPECIAL_ENDINGLESS_FILENAMES = ('/dev/null',)

SOURCE_ENDINGS = C_ENDINGS + CXX_ENDINGS + OBJC_ENDINGS + OBJCXX_ENDINGS + SPECIAL_ENDINGLESS_FILENAMES
C_ENDINGS = C_ENDINGS + SPECIAL_ENDINGLESS_FILENAMES # consider the special endingless filenames like /dev/null to be C

JS_CONTAINING_ENDINGS = ('.js', '.mjs', '.html')
ASSEMBLY_ENDINGS = ('.ll',)
HEADER_ENDINGS = ('.h', '.hxx', '.hpp', '.hh', '.H', '.HXX', '.HPP', '.HH')

SUPPORTED_LINKER_FLAGS = (
    '--start-group', '--end-group',
    '-(', '-)',
    '--whole-archive', '--no-whole-archive',
    '-whole-archive', '-no-whole-archive')

LIB_PREFIXES = ('', 'lib')

# Mapping of emcc opt levels to llvm opt levels. We use llvm opt level 3 in emcc
# opt levels 2 and 3 (emcc 3 is unsafe opts, so unsuitable for the only level to
# get llvm opt level 3, and speed-wise emcc level 2 is already the slowest/most
# optimizing level)
LLVM_OPT_LEVEL = {
  0: ['-O0'],
  1: ['-O1'],
  2: ['-O3'],
  3: ['-O3'],
}

# Do not compile .ll files into .bc, just compile them with emscripten directly
# Not recommended, this is mainly for the test runner, or if you have some other
# specific need.
# One major limitation with this mode is that libc and libc++ cannot be
# added in. Also, LLVM optimizations will not be done, nor dead code elimination
LEAVE_INPUTS_RAW = int(os.environ.get('EMCC_LEAVE_INPUTS_RAW', '0'))

# If emcc is running with LEAVE_INPUTS_RAW and then launches an emcc to build
# something like the struct info, then we don't want LEAVE_INPUTS_RAW to be
# active in that emcc subprocess.
if LEAVE_INPUTS_RAW:
  del os.environ['EMCC_LEAVE_INPUTS_RAW']

UBSAN_SANITIZERS = {
  'alignment',
  'bool',
  'builtin',
  'bounds',
  'enum',
  'float-cast-overflow',
  'float-divide-by-zero',
  'function',
  'implicit-unsigned-integer-truncation',
  'implicit-signed-integer-truncation',
  'implicit-integer-sign-change',
  'integer-divide-by-zero',
  'nonnull-attribute',
  'null',
  'nullability-arg',
  'nullability-assign',
  'nullability-return',
  'object-size',
  'pointer-overflow',
  'return',
  'returns-nonnull-attribute',
  'shift',
  'signed-integer-overflow',
  'unreachable',
  'unsigned-integer-overflow',
  'vla-bound',
  'vptr',
  'undefined',
  'undefined-trap',
  'implicit-integer-truncation',
  'implicit-integer-arithmetic-value-change',
  'implicit-conversion',
  'integer',
  'nullability',
}


class TimeLogger(object):
  last = time.time()

  @staticmethod
  def update():
    TimeLogger.last = time.time()


def log_time(name):
  """Log out times for emcc stages"""
  if DEBUG:
    now = time.time()
    logger.debug('emcc step "%s" took %.2f seconds', name, now - TimeLogger.last)
    TimeLogger.update()


class EmccOptions(object):
  def __init__(self):
    self.opt_level = 0
    self.debug_level = 0
    self.requested_debug = ''
    self.profiling = False
    self.tracing = False
    self.emit_symbol_map = False
    self.js_opts = None
    self.force_js_opts = False
    self.llvm_opts = None
    self.llvm_lto = None
    self.default_cxx_std = '-std=c++03' # Enforce a consistent C++ standard when compiling .cpp files, if user does not specify one on the cmdline.
    self.use_closure_compiler = None
    self.closure_args = []
    self.preload_files = []
    self.embed_files = []
    self.exclude_files = []
    self.ignore_dynamic_linking = False
    self.shell_path = shared.path_from_root('src', 'shell.html')
    self.js_libraries = []
    self.thread_profiler = False
    self.memory_profiler = False
    self.save_bc = False
    self.memory_init_file = None
    self.no_heap_copy = False
    self.default_object_extension = '.o'
    self.valid_abspaths = []
    self.cfi = False
    self.binaryen_passes = []
    # Whether we will expand the full path of any input files to remove any
    # symlinks.
    self.expand_symlinks = True
    self.link_flags = []


def use_source_map(options):
  return options.debug_level >= 4


def find_output_arg(args):
  """Find and remove any -o arguments.  The final one takes precedence.
  Return the final -o target along with the remaining (non-o) arguments.
  """
  outargs = []
  specified_target = None
  use_next = False
  for arg in args:
    if use_next:
      specified_target = arg
      use_next = False
      continue
    if arg == '-o':
      use_next = True
    elif arg.startswith('-o'):
      specified_target = arg[2:]
    else:
      outargs.append(arg)
  return specified_target, outargs


#
# Main run() function
#
def run(args):
  target = None

  # Additional compiler flags that we treat as if they were passed to us on the
  # commandline
  EMCC_CFLAGS = os.environ.get('EMCC_CFLAGS')
  if DEBUG:
    cmd = ' '.join(args)
    if EMCC_CFLAGS:
      cmd += ' + ' + EMCC_CFLAGS
    logger.warning('invocation: ' + cmd + '  (in ' + os.getcwd() + ')')
  if EMCC_CFLAGS:
    args.extend(shlex.split(EMCC_CFLAGS))

  # Strip args[0] (program name)
  args = args[1:]

  if DEBUG and LEAVE_INPUTS_RAW:
    logger.warning('leaving inputs raw')

  if '--emscripten-cxx' in args:
    run_via_emxx = True
    args = [x for x in args if x != '--emscripten-cxx']
  else:
    run_via_emxx = False

  misc_temp_files = shared.configuration.get_temp_files()

  # Handle some global flags

  # read response files very early on
  args = substitute_response_files(args)

  if '--help' in args:
    # Documentation for emcc and its options must be updated in:
    #    site/source/docs/tools_reference/emcc.rst
    # A prebuilt local version of the documentation is available at:
    #    site/build/text/docs/tools_reference/emcc.txt
    #    (it is read from there and printed out when --help is invoked)
    # You can also build docs locally as HTML or other formats in site/
    # An online HTML version (which may be of a different version of Emscripten)
    #    is up at http://kripken.github.io/emscripten-site/docs/tools_reference/emcc.html

    print('''%s

------------------------------------------------------------------

emcc: supported targets: llvm bitcode, javascript, NOT elf
(autoconf likes to see elf above to enable shared object support)
''' % (open(shared.path_from_root('site', 'build', 'text', 'docs', 'tools_reference', 'emcc.txt')).read()))
    return 0

  if '--version' in args:
    try:
      revision = run_process(['git', 'show'], stdout=PIPE, stderr=PIPE, cwd=shared.path_from_root()).stdout.splitlines()[0]
    except Exception:
      revision = '(unknown revision)'
    print('''emcc (Emscripten gcc/clang-like replacement) %s (%s)
Copyright (C) 2014 the Emscripten authors (see AUTHORS.txt)
This is free and open source software under the MIT license.
There is NO warranty; not even for MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
  ''' % (shared.EMSCRIPTEN_VERSION, revision))
    return 0

  if len(args) == 1 and args[0] == '-v': # -v with no inputs
    # autoconf likes to see 'GNU' in the output to enable shared object support
    print('emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) %s' % shared.EMSCRIPTEN_VERSION, file=sys.stderr)
    code = run_process([shared.CLANG_CC, '-v'], check=False).returncode
    shared.check_sanity(force=True)
    return code

  shared.check_sanity(force=DEBUG)

  # This check comes after check_sanity because test_sanity expects this.
  if not args:
    logger.warning('no input files')
    return 1

  if '-dumpmachine' in args:
    print(shared.get_llvm_target())
    return 0

  if '-dumpversion' in args: # gcc's doc states "Print the compiler version [...] and don't do anything else."
    print(shared.EMSCRIPTEN_VERSION)
    return 0

  if '--cflags' in args:
    # fake running the command, to see the full args we pass to clang
    debug_env = os.environ.copy()
    args = [x for x in args if x != '--cflags']
    with misc_temp_files.get_file(suffix='.o') as temp_target:
      input_file = 'hello_world.c'
      cmd = [shared.PYTHON, sys.argv[0], shared.path_from_root('tests', input_file), '-v', '-c', '-o', temp_target] + args
      proc = run_process(cmd, stderr=PIPE, env=debug_env, check=False)
      if proc.returncode != 0:
        print(proc.stderr)
        exit_with_error('error getting cflags')
      lines = [x for x in proc.stderr.splitlines() if shared.CLANG_CC in x and input_file in x]
      parts = shlex.split(lines[0].replace('\\', '\\\\'))
      parts = [x for x in parts if x not in ['-c', '-o', '-v', '-emit-llvm'] and input_file not in x and temp_target not in x]
      print(' '.join(shared.Building.doublequote_spaces(parts[1:])))
    return 0

  # Default to using C++ even when run as `emcc`.
  # This means that emcc will act as a C++ linker when no source files are
  # specified.  However, when a C source is specified we do default to C.
  # This differs to clang and gcc where the default is always C unless run as
  # clang++/g++.
  use_cxx = True

  def get_language_mode(args):
    return_next = False
    for item in args:
      if return_next:
        return item
      if item == '-x':
        return_next = True
        continue
      if item.startswith('-x'):
        return item[2:]
    return None

  def has_c_source(args):
    for a in args:
      if a[0] != '-' and a.endswith(C_ENDINGS + OBJC_ENDINGS):
        return True
    return False

  language_mode = get_language_mode(args)
  has_fixed_language_mode = language_mode is not None
  if language_mode == 'c':
    use_cxx = False

  if not has_fixed_language_mode:
    if not run_via_emxx and has_c_source(args):
      use_cxx = False

  def is_minus_s_for_emcc(args, i):
    # -s OPT=VALUE or -s OPT are interpreted as emscripten flags.
    # -s by itself is a linker option (alias for --strip-all)
    assert args[i] == '-s'
    if len(args) > i + 1:
      arg = args[i + 1]
      if arg.split('=')[0].isupper():
        return True

    logger.debug('treating -s as linker option and not as -s OPT=VALUE for js compilation')
    return False

  # If this is a configure-type thing, do not compile to JavaScript, instead use clang
  # to compile to a native binary (using our headers, so things make sense later)
  CONFIGURE_CONFIG = (os.environ.get('EMMAKEN_JUST_CONFIGURE') or 'conftest.c' in args) and not os.environ.get('EMMAKEN_JUST_CONFIGURE_RECURSE')
  CMAKE_CONFIG = 'CMakeFiles/cmTryCompileExec.dir' in ' '.join(args)# or 'CMakeCCompilerId' in ' '.join(args)
  if CONFIGURE_CONFIG or CMAKE_CONFIG:
    # XXX use this to debug configure stuff. ./configure's generally hide our
    # normal output including stderr so we write to a file
    debug_configure = 0

    # Whether we fake configure tests using clang - the local, native compiler -
    # or not. if not we generate JS and use node with a shebang
    # Neither approach is perfect, you can try both, but may need to edit
    # configure scripts in some cases
    # By default we configure in js, which can break on local filesystem access,
    # etc., but is otherwise accurate so we
    # disable this if we think we have to. A value of '2' here will force JS
    # checks in all cases. In summary:
    # 0 - use native compilation for configure checks
    # 1 - use js when we think it will work
    # 2 - always use js for configure checks
    use_js = int(os.environ.get('EMCONFIGURE_JS', '2'))

    if debug_configure:
      tempout = '/tmp/emscripten_temp/out'
      if not os.path.exists(tempout):
        open(tempout, 'w').write('//\n')

    src = None
    for arg in args:
      if arg.endswith(SOURCE_ENDINGS):
        try:
          src = open(arg).read()
          if debug_configure:
            open(tempout, 'a').write('============= ' + arg + '\n' + src + '\n=============\n\n')
        except IOError:
          pass
      elif arg.endswith('.s'):
        if debug_configure:
          open(tempout, 'a').write('(compiling .s assembly, must use clang\n')
        if use_js == 1:
          use_js = 0
      elif arg == '-E' or arg == '-M' or arg == '-MM':
        if use_js == 1:
          use_js = 0

    if src:
      if 'fopen' in src and '"w"' in src:
        if use_js == 1:
          use_js = 0 # we cannot write to files from js!
        if debug_configure:
          open(tempout, 'a').write('Forcing clang since uses fopen to write\n')

    # if CONFIGURE_CC is defined, use that. let's you use local gcc etc. if you need that
    compiler = os.environ.get('CONFIGURE_CC')
    if not compiler:
      compiler = shared.EMXX if use_js else shared.CLANG_CPP
    if 'CXXCompiler' not in ' '.join(args) and not use_cxx:
      compiler = shared.to_cc(compiler)

    def filter_emscripten_options(argv):
      skip_next = False
      for idx, arg in enumerate(argv):
        if skip_next:
          skip_next = False
          continue
        if not use_js and arg == '-s' and is_minus_s_for_emcc(argv, idx):
          # skip -s X=Y if not using js for configure
          skip_next = True
          continue
        if use_js or arg != '--tracing':
          yield arg

    if compiler in (shared.EMCC, shared.EMXX):
      compiler = [shared.PYTHON, compiler]
    else:
      compiler = [compiler]
    cmd = compiler + list(filter_emscripten_options(args))
    if not use_js:
      cmd += shared.EMSDK_OPTS + ['-D__EMSCRIPTEN__']
      # The preprocessor define EMSCRIPTEN is deprecated. Don't pass it to code
      # in strict mode. Code should use the define __EMSCRIPTEN__ instead.
      if not shared.Settings.STRICT:
        cmd += ['-DEMSCRIPTEN']
    if use_js:
      # configure tests want a more shell-like style, where we emit return codes on exit()
      cmd += ['-s', 'NO_EXIT_RUNTIME=0']
      # use node.js raw filesystem access, to behave just like a native executable
      cmd += ['-s', 'NODERAWFS=1']

    logger.debug('just configuring: ' + ' '.join(cmd))
    if debug_configure:
      open(tempout, 'a').write('emcc, just configuring: ' + ' '.join(cmd) + '\n\n')

    if not use_js:
      return run_process(cmd, check=False).returncode

    only_object = '-c' in cmd
    for i in reversed(range(len(cmd) - 1)): # Last -o directive should take precedence, if multiple are specified
      if cmd[i] == '-o':
        if not only_object:
          cmd[i + 1] += '.js'
        target = cmd[i + 1]
        break
    if not target:
      target = 'a.out.js'
    os.environ['EMMAKEN_JUST_CONFIGURE_RECURSE'] = '1'
    ret = run_process(cmd, check=False).returncode
    os.environ['EMMAKEN_JUST_CONFIGURE_RECURSE'] = ''
    if not os.path.exists(target):
      # note that emcc -c will cause target to have the wrong value here;
      # but then, we don't care about bitcode outputs anyhow, below, so
      # skipping returning early is fine
      return ret
    if target.endswith('.js'):
      shutil.copyfile(target, unsuffixed(target))
      target = unsuffixed(target)
    if not target.endswith(BITCODE_ENDINGS):
      src = open(target).read()
      full_node = ' '.join(shared.NODE_JS)
      if os.path.sep not in full_node:
        full_node = '/usr/bin/' + full_node # TODO: use whereis etc. And how about non-*NIX?
      open(target, 'w').write('#!' + full_node + '\n' + src) # add shebang
      try:
        os.chmod(target, stat.S_IMODE(os.stat(target).st_mode) | stat.S_IXUSR) # make executable
      except OSError:
        pass # can fail if e.g. writing the executable to /dev/null
    return ret

  CXX = os.environ.get('EMMAKEN_COMPILER', shared.CLANG_CPP)
  CC = shared.to_cc(CXX)

  EMMAKEN_CFLAGS = os.environ.get('EMMAKEN_CFLAGS')
  if EMMAKEN_CFLAGS:
    args += shlex.split(EMMAKEN_CFLAGS)

  # ---------------- Utilities ---------------

  def suffix(name):
    """Return the file extension"""
    return os.path.splitext(name)[1]

  seen_names = {}

  def uniquename(name):
    if name not in seen_names:
      seen_names[name] = str(len(seen_names))
    return unsuffixed(name) + '_' + seen_names[name] + suffix(name)

  # ---------------- End configs -------------

  # Check if a target is specified on the command line
  specified_target, args = find_output_arg(args)

  # specified_target is the user-specified one, target is what we will generate
  if specified_target:
    target = specified_target
    # check for the existence of the output directory now, to avoid having
    # to do so repeatedly when each of the various output files (.mem, .wasm,
    # etc) are written. This gives a more useful error message than the
    # IOError and python backtrace that users would otherwise see.
    dirname = os.path.dirname(target)
    if dirname and not os.path.isdir(dirname):
      exit_with_error("specified output file (%s) is in a directory that does not exist" % target)
  else:
    target = 'a.out.js'

  target_basename = unsuffixed_basename(target)
  final_suffix = suffix(target)

  temp_dir = shared.get_emscripten_temp_dir()

  def in_temp(name):
    return os.path.join(temp_dir, os.path.basename(name))

  def get_file_suffix(filename):
    """Parses the essential suffix of a filename, discarding Unix-style version
    numbers in the name. For example for 'libz.so.1.2.8' returns '.so'"""
    if filename in SPECIAL_ENDINGLESS_FILENAMES:
      return filename
    while filename:
      filename, suffix = os.path.splitext(filename)
      if not suffix[1:].isdigit():
        return suffix
    return ''

  def optimizing(opts):
    return '-O0' not in opts

  with ToolchainProfiler.profile_block('parse arguments and setup'):
    ## Parse args

    newargs = list(args)

    # Scan and strip emscripten specific cmdline warning flags.
    # This needs to run before other cmdline flags have been parsed, so that
    # warnings are properly printed during arg parse.
    newargs = shared.WarningManager.capture_warnings(newargs)

    for i in range(len(newargs)):
      if newargs[i] in ('-l', '-L', '-I'):
        # Scan for individual -l/-L/-I arguments and concatenate the next arg on
        # if there is no suffix
        newargs[i] += newargs[i + 1]
        newargs[i + 1] = ''

    options, settings_changes, newargs = parse_args(newargs)

    if use_cxx:
      clang_compiler = CXX
      # If user did not specify a default -std for C++ code, specify the emscripten default.
      if options.default_cxx_std:
        newargs += [options.default_cxx_std]
    else:
      # Compiling C code with .c files, don't enforce a default C++ std.
      clang_compiler = CC

    if '-print-search-dirs' in newargs:
      return run_process([clang_compiler, '-print-search-dirs'], check=False).returncode

    if options.memory_profiler:
      shared.Settings.MEMORYPROFILER = 1

    if options.js_opts is None:
      options.js_opts = options.opt_level >= 2

    if options.llvm_opts is None:
      options.llvm_opts = LLVM_OPT_LEVEL[options.opt_level]
    elif type(options.llvm_opts) == int:
      options.llvm_opts = ['-O%d' % options.llvm_opts]

    if options.memory_init_file is None:
      options.memory_init_file = options.opt_level >= 2

    if DEBUG:
      start_time = time.time() # done after parsing arguments, which might affect debug state

    for i in range(len(newargs)):
      if newargs[i] == '-s':
        if is_minus_s_for_emcc(newargs, i):
          key = newargs[i + 1]
          # If not = is specified default to 1
          if '=' not in key:
            key += '=1'
          settings_changes.append(key)
          newargs[i] = newargs[i + 1] = ''
          if key == 'WASM_BACKEND=1':
            exit_with_error('do not set -s WASM_BACKEND, instead set EMCC_WASM_BACKEND=1 in the environment')
    newargs = [arg for arg in newargs if arg != '']

    settings_key_changes = set()
    for s in settings_changes:
      key, value = s.split('=', 1)
      settings_key_changes.add(key)

    # Find input files

    # These three arrays are used to store arguments of different types for
    # type-specific processing. In order to shuffle the arguments back together
    # after processing, all of these arrays hold tuples (original_index, value).
    # Note that the index part of the tuple can have a fractional part for input
    # arguments that expand into multiple processed arguments, as in -Wl,-f1,-f2.
    input_files = []
    libs = []
    link_flags = options.link_flags

    # All of the above arg lists entries contain indexes into the full argument
    # list. In order to add extra implicit args (embind.cc, etc) below, we keep a
    # counter for the next index that should be used.
    next_arg_index = len(newargs)

    has_source_inputs = False
    has_header_inputs = False
    lib_dirs = [shared.path_from_root('system', 'local', 'lib'),
                shared.path_from_root('system', 'lib')]

    # find input files this a simple heuristic. we should really analyze
    # based on a full understanding of gcc params, right now we just assume that
    # what is left contains no more |-x OPT| things
    for i in range(len(newargs)):
      arg = newargs[i]
      if i > 0:
        prev = newargs[i - 1]
        if prev in ('-MT', '-MF', '-MQ', '-D', '-U', '-o', '-x',
                    '-Xpreprocessor', '-include', '-imacros', '-idirafter',
                    '-iprefix', '-iwithprefix', '-iwithprefixbefore',
                    '-isysroot', '-imultilib', '-A', '-isystem', '-iquote',
                    '-install_name', '-compatibility_version',
                    '-current_version', '-I', '-L', '-include-pch'):
          continue # ignore this gcc-style argument

      if options.expand_symlinks and os.path.islink(arg) and get_file_suffix(os.path.realpath(arg)) in SOURCE_ENDINGS + BITCODE_ENDINGS + DYNAMICLIB_ENDINGS + ASSEMBLY_ENDINGS + HEADER_ENDINGS:
        arg = os.path.realpath(arg)

      if not arg.startswith('-'):
        if not os.path.exists(arg):
          exit_with_error('%s: No such file or directory ("%s" was expected to be an input file, based on the commandline arguments provided)', arg, arg)

        file_suffix = get_file_suffix(arg)
        if file_suffix in SOURCE_ENDINGS + BITCODE_ENDINGS + DYNAMICLIB_ENDINGS + ASSEMBLY_ENDINGS + HEADER_ENDINGS or shared.Building.is_ar(arg): # we already removed -o <target>, so all these should be inputs
          newargs[i] = ''
          if file_suffix.endswith(SOURCE_ENDINGS):
            input_files.append((i, arg))
            has_source_inputs = True
          elif file_suffix.endswith(HEADER_ENDINGS):
            input_files.append((i, arg))
            has_header_inputs = True
          elif file_suffix.endswith(ASSEMBLY_ENDINGS) or shared.Building.is_bitcode(arg) or shared.Building.is_ar(arg):
            input_files.append((i, arg))
          elif shared.Building.is_wasm(arg):
            if not shared.Settings.WASM_BACKEND:
              exit_with_error('fastcomp is not compatible with wasm object files:' + arg)
            input_files.append((i, arg))
          elif file_suffix.endswith(STATICLIB_ENDINGS + DYNAMICLIB_ENDINGS):
            # if it's not, and it's a library, just add it to libs to find later
            libname = unsuffixed_basename(arg)
            for prefix in LIB_PREFIXES:
              if not prefix:
                continue
              if libname.startswith(prefix):
                libname = libname[len(prefix):]
                break
            libs.append((i, libname))
            newargs[i] = ''
          else:
            logger.warning(arg + ' is not a valid input file')
        elif file_suffix.endswith(STATICLIB_ENDINGS):
          if not shared.Building.is_ar(arg):
            if shared.Building.is_bitcode(arg):
              message = arg + ': File has a suffix of a static library ' + str(STATICLIB_ENDINGS) + ', but instead is an LLVM bitcode file! When linking LLVM bitcode files, use one of the suffixes ' + str(BITCODE_ENDINGS)
            else:
              message = arg + ': Unknown format, not a static library!'
            exit_with_error(message)
        else:
          if has_fixed_language_mode:
            newargs[i] = ''
            input_files.append((i, arg))
            has_source_inputs = True
          else:
            exit_with_error(arg + ": Input file has an unknown suffix, don't know what to do with it!")
      elif arg.startswith('-L'):
        lib_dirs.append(arg[2:])
        newargs[i] = ''
      elif arg.startswith('-l'):
        libs.append((i, arg[2:]))
        newargs[i] = ''
      elif arg.startswith('-Wl,'):
        # Multiple comma separated link flags can be specified. Create fake
        # fractional indices for these: -Wl,a,b,c,d at index 4 becomes:
        # (4, a), (4.25, b), (4.5, c), (4.75, d)
        link_flags_to_add = arg.split(',')[1:]
        for flag_index, flag in enumerate(link_flags_to_add):
          if flag.startswith('-l'):
            libs.append((i, flag[2:]))
          elif flag.startswith('-L'):
            lib_dirs.append(flag[2:])
          else:
            link_flags.append((i + float(flag_index) / len(link_flags_to_add), flag))

        newargs[i] = ''
      elif arg == '-s':
        # -s and some other compiler flags are normally passed onto the linker
        # TODO(sbc): Pass this and other flags through when using lld
        # link_flags.append((i, arg))
        newargs[i] = ''

    original_input_files = input_files[:]

    newargs = [a for a in newargs if a != '']

    has_dash_c = '-c' in newargs
    has_dash_S = '-S' in newargs
    if has_dash_c or has_dash_S:
      assert has_source_inputs or has_header_inputs, 'Must have source code or header inputs to use -c or -S'
      if has_dash_c:
        if '-emit-llvm' in newargs:
          final_suffix = '.bc'
        else:
          final_suffix = '.o'
      elif has_dash_S:
        if '-emit-llvm' in newargs:
          final_suffix = '.ll'
        else:
          final_suffix = '.s'
      target = target_basename + final_suffix

    if '-E' in newargs:
      final_suffix = '.eout' # not bitcode, not js; but just result from preprocessing stage of the input file
    if '-M' in newargs or '-MM' in newargs:
      final_suffix = '.mout' # not bitcode, not js; but just dependency rule of the input file

    # Libraries are searched before settings_changes are applied, so apply the
    # value for STRICT and ERROR_ON_MISSING_LIBRARIES from command line already
    # now.

    def get_last_setting_change(setting):
      return ([None] + [x for x in settings_changes if x.startswith(setting + '=')])[-1]

    strict_cmdline = get_last_setting_change('STRICT')
    if strict_cmdline:
      shared.Settings.STRICT = int(strict_cmdline.split('=', 1)[1])

    if not shared.Settings.STRICT:
      # The preprocessor define EMSCRIPTEN is deprecated. Don't pass it to code
      # in strict mode. Code should use the define __EMSCRIPTEN__ instead.
      shared.COMPILER_OPTS += ['-DEMSCRIPTEN']

    error_on_missing_libraries_cmdline = get_last_setting_change('ERROR_ON_MISSING_LIBRARIES')
    if error_on_missing_libraries_cmdline:
      shared.Settings.ERROR_ON_MISSING_LIBRARIES = int(error_on_missing_libraries_cmdline[len('ERROR_ON_MISSING_LIBRARIES='):])

    settings_changes.append(process_libraries(libs, lib_dirs, input_files))

    # If not compiling to JS, then we are compiling to an intermediate bitcode objects or library, so
    # ignore dynamic linking, since multiple dynamic linkings can interfere with each other
    if get_file_suffix(target) not in JS_CONTAINING_ENDINGS or options.ignore_dynamic_linking:
      def check(input_file):
        if get_file_suffix(input_file) in DYNAMICLIB_ENDINGS:
          if not options.ignore_dynamic_linking:
            logger.warning('ignoring dynamic library %s because not compiling to JS or HTML, remember to link it when compiling to JS or HTML at the end', os.path.basename(input_file))
          return False
        else:
          return True
      input_files = [f for f in input_files if check(f[1])]

    if len(input_files) == 0:
      exit_with_error('no input files\nnote that input files without a known suffix are ignored, make sure your input files end with one of: ' + str(SOURCE_ENDINGS + BITCODE_ENDINGS + DYNAMICLIB_ENDINGS + STATICLIB_ENDINGS + ASSEMBLY_ENDINGS + HEADER_ENDINGS))

    newargs = shared.COMPILER_OPTS + newargs

    # Apply optimization level settings
    shared.Settings.apply_opt_level(opt_level=options.opt_level)

    # For users that opt out of WARN_ON_UNDEFINED_SYMBOLS we assume they also
    # want to opt out of ERROR_ON_UNDEFINED_SYMBOLS.
    if 'WARN_ON_UNDEFINED_SYMBOLS=0' in settings_changes:
      shared.Settings.ERROR_ON_UNDEFINED_SYMBOLS = 0

    # Set ASM_JS default here so that we can override it from the command line.
    shared.Settings.ASM_JS = 1 if options.opt_level > 0 else 2

    # Apply -s settings in newargs here (after optimization levels, so they can override them)
    shared.apply_settings(settings_changes)

    # Note the exports the user requested
    shared.Building.user_requested_exports = shared.Settings.EXPORTED_FUNCTIONS[:]

    # -s ASSERTIONS=1 implies the heaviest stack overflow check mode. Set the implication here explicitly to avoid having to
    # do preprocessor "#if defined(ASSERTIONS) || defined(STACK_OVERFLOW_CHECK)" in .js files, which is not supported.
    if shared.Settings.ASSERTIONS:
      shared.Settings.STACK_OVERFLOW_CHECK = 2

    if shared.Settings.WASM_OBJECT_FILES and not shared.Settings.WASM_BACKEND:
      if 'WASM_OBJECT_FILES=1' in settings_changes:
        exit_with_error('WASM_OBJECT_FILES can only be used with wasm backend')
      shared.Settings.WASM_OBJECT_FILES = 0

    if shared.Settings.STRICT:
      shared.Settings.DISABLE_DEPRECATED_FIND_EVENT_TARGET_BEHAVIOR = 1

    # Use settings

    if shared.Settings.EMULATE_FUNCTION_POINTER_CASTS:
      shared.Settings.ALIASING_FUNCTION_POINTERS = 0

    if shared.Settings.LEGACY_VM_SUPPORT:
      # legacy vms don't have wasm
      assert not shared.Settings.WASM or shared.Settings.WASM2JS, 'LEGACY_VM_SUPPORT is only supported for asm.js, and not wasm. Build with -s WASM=0'
      shared.Settings.POLYFILL_OLD_MATH_FUNCTIONS = 1
      shared.Settings.WORKAROUND_IOS_9_RIGHT_SHIFT_BUG = 1
      shared.Settings.WORKAROUND_OLD_WEBGL_UNIFORM_UPLOAD_IGNORED_OFFSET_BUG = 1

    # Silently drop any individual backwards compatibility emulation flags that are known never to occur on browsers that support WebAssembly.
    if shared.Settings.WASM and not shared.Settings.WASM2JS:
      shared.Settings.POLYFILL_OLD_MATH_FUNCTIONS = 0
      shared.Settings.WORKAROUND_IOS_9_RIGHT_SHIFT_BUG = 0
      shared.Settings.WORKAROUND_OLD_WEBGL_UNIFORM_UPLOAD_IGNORED_OFFSET_BUG = 0

    if shared.Settings.STB_IMAGE and final_suffix in JS_CONTAINING_ENDINGS:
      input_files.append((next_arg_index, shared.path_from_root('third_party', 'stb_image.c')))
      next_arg_index += 1
      shared.Settings.EXPORTED_FUNCTIONS += ['_stbi_load', '_stbi_load_from_memory', '_stbi_image_free']
      # stb_image 2.x need to have STB_IMAGE_IMPLEMENTATION defined to include the implementation when compiling
      newargs.append('-DSTB_IMAGE_IMPLEMENTATION')

    forced_stdlibs = []

    if shared.Settings.ASMFS and final_suffix in JS_CONTAINING_ENDINGS:
      forced_stdlibs.append('libasmfs')
      newargs.append('-D__EMSCRIPTEN_ASMFS__=1')
      next_arg_index += 1
      shared.Settings.FILESYSTEM = 0
      shared.Settings.SYSCALLS_REQUIRE_FILESYSTEM = 0
      shared.Settings.FETCH = 1
      options.js_libraries.append(shared.path_from_root('src', 'library_asmfs.js'))

    if shared.Settings.FETCH and final_suffix in JS_CONTAINING_ENDINGS:
      forced_stdlibs.append('libfetch')
      next_arg_index += 1
      options.js_libraries.append(shared.path_from_root('src', 'library_fetch.js'))
      if shared.Settings.USE_PTHREADS:
        shared.Settings.FETCH_WORKER_FILE = unsuffixed(os.path.basename(target)) + '.fetch.js'

    if shared.Settings.DEMANGLE_SUPPORT:
      shared.Settings.EXPORTED_FUNCTIONS += ['___cxa_demangle']
      forced_stdlibs.append('libc++abi')

    if shared.Settings.EMBIND:
      forced_stdlibs.append('libembind')

    if not shared.Settings.ONLY_MY_CODE and not shared.Settings.MINIMAL_RUNTIME:
      # Always need malloc and free to be kept alive and exported, for internal use and other modules
      shared.Settings.EXPORTED_FUNCTIONS += ['_malloc', '_free']
      if shared.Settings.WASM_BACKEND:
        # setjmp/longjmp and exception handling JS code depends on this so we
        # include it by default.  Should be eliminated by meta-DCE if unused.
        shared.Settings.EXPORTED_FUNCTIONS += ['_setThrew']

    if shared.Settings.RELOCATABLE and not shared.Settings.DYNAMIC_EXECUTION:
      exit_with_error('cannot have both DYNAMIC_EXECUTION=0 and RELOCATABLE enabled at the same time, since RELOCATABLE needs to eval()')

    if shared.Settings.RELOCATABLE:
      if 'EMULATED_FUNCTION_POINTERS' not in settings_key_changes and not shared.Settings.WASM_BACKEND:
        shared.Settings.EMULATED_FUNCTION_POINTERS = 2 # by default, use optimized function pointer emulation
      shared.Settings.ERROR_ON_UNDEFINED_SYMBOLS = 0
      shared.Settings.WARN_ON_UNDEFINED_SYMBOLS = 0

    if shared.Settings.ASYNCIFY:
      if not shared.Settings.WASM_BACKEND:
        exit_with_error('ASYNCIFY has been removed from fastcomp. There is a new implementation which can be used in the upstream wasm backend.')

    if shared.Settings.EMTERPRETIFY:
      shared.Settings.FINALIZE_ASM_JS = 0
      shared.Settings.SIMPLIFY_IFS = 0 # this is just harmful for emterpreting
      shared.Settings.EXPORTED_FUNCTIONS += ['emterpret']
      if not options.js_opts:
        logger.debug('enabling js opts for EMTERPRETIFY')
        options.js_opts = True
      options.force_js_opts = True
      if options.use_closure_compiler == 2:
         exit_with_error('EMTERPRETIFY requires valid asm.js, and is incompatible with closure 2 which disables that')
      assert not use_source_map(options), 'EMTERPRETIFY is not compatible with source maps (maps are not useful in emterpreted code, and splitting out non-emterpreted source maps is not yet implemented)'

    if shared.Settings.DISABLE_EXCEPTION_THROWING and not shared.Settings.DISABLE_EXCEPTION_CATCHING:
      exit_with_error("DISABLE_EXCEPTION_THROWING was set (probably from -fno-exceptions) but is not compatible with enabling exception catching (DISABLE_EXCEPTION_CATCHING=0). If you don't want exceptions, set DISABLE_EXCEPTION_CATCHING to 1; if you do want exceptions, don't link with -fno-exceptions")

    if shared.Settings.DEAD_FUNCTIONS:
      if not options.js_opts:
        logger.debug('enabling js opts for DEAD_FUNCTIONS')
        options.js_opts = True
      options.force_js_opts = True

    if shared.Settings.FILESYSTEM and not shared.Settings.ONLY_MY_CODE:
      if shared.Settings.SUPPORT_ERRNO:
        shared.Settings.EXPORTED_FUNCTIONS += ['___errno_location'] # so FS can report errno back to C
      # to flush streams on FS exit, we need to be able to call fflush
      # we only include it if the runtime is exitable, or when ASSERTIONS
      # (ASSERTIONS will check that streams do not need to be flushed,
      # helping people see when they should have disabled NO_EXIT_RUNTIME)
      if shared.Settings.EXIT_RUNTIME or shared.Settings.ASSERTIONS:
        shared.Settings.EXPORTED_FUNCTIONS += ['_fflush']

    if shared.Settings.USE_PTHREADS:
      if shared.Settings.USE_PTHREADS == 2:
        exit_with_error('USE_PTHREADS=2 is not longer supported')
      if shared.Settings.ALLOW_MEMORY_GROWTH:
        if not shared.Settings.WASM:
          exit_with_error('Memory growth is not supported with pthreads without wasm')
        else:
          logging.warning('USE_PTHREADS + ALLOW_MEMORY_GROWTH may run non-wasm code slowly, see https://github.com/WebAssembly/design/issues/1271')
      # UTF8Decoder.decode doesn't work with a view of a SharedArrayBuffer
      shared.Settings.TEXTDECODER = 0
      options.js_libraries.append(shared.path_from_root('src', 'library_pthread.js'))
      newargs.append('-D__EMSCRIPTEN_PTHREADS__=1')
      if shared.Settings.WASM_BACKEND:
        newargs += ['-pthread']
        # some pthreads code is in asm.js library functions, which are auto-exported; for the wasm backend, we must
        # manually export them
        shared.Settings.EXPORTED_FUNCTIONS += ['_emscripten_get_global_libc', '___pthread_tsd_run_dtors', '__register_pthread_ptr', '_pthread_self', '___emscripten_pthread_data_constructor']

      # set location of worker.js
      shared.Settings.PTHREAD_WORKER_FILE = unsuffixed(os.path.basename(target)) + '.worker.js'
    else:
      options.js_libraries.append(shared.path_from_root('src', 'library_pthread_stub.js'))

    # Enable minification of asm.js imports on -O1 and higher if -g1 or lower is used.
    if options.opt_level >= 1 and options.debug_level < 2 and not shared.Settings.WASM:
      shared.Settings.MINIFY_ASMJS_IMPORT_NAMES = 1

    if shared.Settings.WASM:
      if shared.Settings.TOTAL_MEMORY % 65536 != 0:
        exit_with_error('For wasm, TOTAL_MEMORY must be a multiple of 64KB, was ' + str(shared.Settings.TOTAL_MEMORY))
    else:
      if shared.Settings.TOTAL_MEMORY < 16 * 1024 * 1024:
        exit_with_error('TOTAL_MEMORY must be at least 16MB, was ' + str(shared.Settings.TOTAL_MEMORY))
      if shared.Settings.TOTAL_MEMORY % (16 * 1024 * 1024) != 0:
        exit_with_error('For asm.js, TOTAL_MEMORY must be a multiple of 16MB, was ' + str(shared.Settings.TOTAL_MEMORY))
    if shared.Settings.TOTAL_MEMORY < shared.Settings.TOTAL_STACK:
      exit_with_error('TOTAL_MEMORY must be larger than TOTAL_STACK, was ' + str(shared.Settings.TOTAL_MEMORY) + ' (TOTAL_STACK=' + str(shared.Settings.TOTAL_STACK) + ')')
    if shared.Settings.WASM_MEM_MAX != -1 and shared.Settings.WASM_MEM_MAX % 65536 != 0:
      exit_with_error('WASM_MEM_MAX must be a multiple of 64KB, was ' + str(shared.Settings.WASM_MEM_MAX))
    if shared.Settings.MEMORY_GROWTH_STEP != -1 and shared.Settings.MEMORY_GROWTH_STEP % 65536 != 0:
      exit_with_error('MEMORY_GROWTH_STEP must be a multiple of 64KB, was ' + str(shared.Settings.MEMORY_GROWTH_STEP))
    if shared.Settings.USE_PTHREADS and shared.Settings.WASM and shared.Settings.ALLOW_MEMORY_GROWTH and shared.Settings.WASM_MEM_MAX == -1:
      exit_with_error('If pthreads and memory growth are enabled, WASM_MEM_MAX must be set')

    if shared.Settings.WASM2JS:
      if not shared.Settings.WASM_BACKEND:
        exit_with_error('wasm2js is only available in the upstream wasm backend path')
      if use_source_map(options):
        exit_with_error('wasm2js does not support source maps yet (debug in wasm for now)')
      logger.warning('emcc: JS support in the upstream LLVM+wasm2js path is very experimental currently (best to use fastcomp for asm.js for now)')

    if shared.Settings.EVAL_CTORS:
      if not shared.Settings.WASM:
        # for asm.js: this option is not a js optimizer pass, but does run the js optimizer internally, so
        # we need to generate proper code for that (for wasm, we run a binaryen tool for this)
        shared.Settings.RUNNING_JS_OPTS = 1

    # memory growth does not work in dynamic linking, except for wasm
    if not shared.Settings.WASM and (shared.Settings.MAIN_MODULE or shared.Settings.SIDE_MODULE):
      assert not shared.Settings.ALLOW_MEMORY_GROWTH, 'memory growth is not supported with shared asm.js modules'

    if shared.Settings.MINIMAL_RUNTIME:
      if shared.Settings.ALLOW_MEMORY_GROWTH:
        logging.warning('-s ALLOW_MEMORY_GROWTH=1 is not yet supported with -s MINIMAL_RUNTIME=1')

      if shared.Settings.EMTERPRETIFY:
        exit_with_error('-s EMTERPRETIFY=1 is not supported with -s MINIMAL_RUNTIME=1')

      if shared.Settings.USE_PTHREADS:
        exit_with_error('-s USE_PTHREADS=1 is not yet supported with -s MINIMAL_RUNTIME=1')

      if shared.Settings.PRECISE_F32 == 2:
        exit_with_error('-s PRECISE_F32=2 is not supported with -s MINIMAL_RUNTIME=1')

      if shared.Settings.SINGLE_FILE:
        exit_with_error('-s SINGLE_FILE=1 is not supported with -s MINIMAL_RUNTIME=1')

    if shared.Settings.ALLOW_MEMORY_GROWTH and shared.Settings.ASM_JS == 1:
      # this is an issue in asm.js, but not wasm
      if not shared.Settings.WASM:
        shared.WarningManager.warn('ALMOST_ASM')
        shared.Settings.ASM_JS = 2 # memory growth does not validate as asm.js http://discourse.wicg.io/t/request-for-comments-switching-resizing-heaps-in-asm-js/641/23

    # safe heap in asm.js uses the js optimizer (in wasm-only mode we can use binaryen)
    if shared.Settings.SAFE_HEAP and not shared.Building.is_wasm_only():
      if not options.js_opts:
        logger.debug('enabling js opts for SAFE_HEAP')
        options.js_opts = True
      options.force_js_opts = True

    if options.js_opts:
      shared.Settings.RUNNING_JS_OPTS = 1

    if shared.Settings.CYBERDWARF:
      newargs.append('-g')
      options.debug_level = max(options.debug_level, 2)
      shared.Settings.BUNDLED_CD_DEBUG_FILE = target + ".cd"
      options.js_libraries.append(shared.path_from_root('src', 'library_cyberdwarf.js'))
      options.js_libraries.append(shared.path_from_root('src', 'library_debugger_toolkit.js'))

    if shared.Settings.WASM_BACKEND:
      if shared.Settings.SIMD:
        newargs.append('-msimd128')
      if shared.Settings.USE_PTHREADS:
        newargs.append('-pthread')
    else:
      # We leave the -O option in place so that the clang front-end runs in that
      # optimization mode, but we disable the actual optimization passes, as we'll
      # run them separately.
      if options.opt_level > 0:
        newargs.append('-mllvm')
        newargs.append('-disable-llvm-optzns')

    if not shared.Settings.LEGALIZE_JS_FFI:
      assert shared.Building.is_wasm_only(), 'LEGALIZE_JS_FFI incompatible with RUNNING_JS_OPTS.'

    if shared.Settings.WASM_BACKEND:
      sanitize = set()

      for arg in newargs:
        if arg.startswith('-fsanitize='):
          sanitize.update(arg.split('=', 1)[1].split(','))
        elif arg.startswith('-fno-sanitize='):
          sanitize.difference_update(arg.split('=', 1)[1].split(','))

      if sanitize:
        shared.Settings.USE_OFFSET_CONVERTER = 1

        if not shared.Settings.WASM_BACKEND:
          exit_with_error('Sanitizers are not compatible with the fastcomp backend. Please upgrade to the upstream wasm backend by following these instructions: https://v8.dev/blog/emscripten-llvm-wasm#testing')

      if sanitize & UBSAN_SANITIZERS:
        if '-fsanitize-minimal-runtime' in newargs:
          shared.Settings.UBSAN_RUNTIME = 1
        else:
          shared.Settings.UBSAN_RUNTIME = 2

      if 'leak' in sanitize:
        shared.Settings.USE_LSAN = 1
        shared.Settings.EXIT_RUNTIME = 1

      if 'address' in sanitize:
        shared.Settings.USE_ASAN = 1

        shared.Settings.GLOBAL_BASE = shared.Settings.ASAN_SHADOW_SIZE
        shared.Settings.TOTAL_MEMORY += shared.Settings.ASAN_SHADOW_SIZE
        assert shared.Settings.TOTAL_MEMORY < 2**32

        if shared.Settings.SAFE_HEAP:
          # SAFE_HEAP instruments ASan's shadow memory accesses.
          # Since the shadow memory starts at 0, the act of accessing the shadow memory is detected
          # by SAFE_HEAP as a null pointer dereference.
          exit_with_error('ASan does not work with SAFE_HEAP')

      if sanitize and '-g4' in args:
        shared.Settings.LOAD_SOURCE_MAP = 1

    shared.Settings.EMSCRIPTEN_VERSION = shared.EMSCRIPTEN_VERSION
    shared.Settings.OPT_LEVEL = options.opt_level
    shared.Settings.DEBUG_LEVEL = options.debug_level

  # exit block 'parse arguments and setup'
  log_time('parse arguments and setup')

  ## Compile source code
  logger.debug('compiling sources')

  temp_files = []

  if DEBUG:
    # we are about to start using temp dirs. serialize access to the temp dir
    # when using EMCC_DEBUG, since we don't want multiple processes would to
    # use it at once, they might collide if they happen to use the same
    # tempfile names
    shared.Cache.acquire_cache_lock()

  try:
    with ToolchainProfiler.profile_block('compile input files'):
      # Precompiled headers support
      if has_header_inputs:
        headers = [header for _, header in input_files]
        for header in headers:
          assert header.endswith(HEADER_ENDINGS), 'if you have one header input, we assume you want to precompile headers, and cannot have source files or other inputs as well: ' + str(headers) + ' : ' + header
        args = newargs + headers
        if specified_target:
          args += ['-o', specified_target]
        args = system_libs.process_args(args, shared.Settings)
        logger.debug("running (for precompiled headers): " + clang_compiler + ' ' + ' '.join(args))
        return run_process([clang_compiler] + args, check=False).returncode

      def get_object_filename(input_file):
        if final_suffix not in JS_CONTAINING_ENDINGS:
          # no need for a temp file, just emit to the right place
          if len(input_files) == 1:
            # can just emit directly to the target
            if specified_target:
              if specified_target.endswith('/') or specified_target.endswith('\\') or os.path.isdir(specified_target):
                return os.path.join(specified_target, os.path.basename(unsuffixed(input_file))) + options.default_object_extension
              return specified_target
            return unsuffixed(input_file) + final_suffix
          else:
            if has_dash_c:
              return unsuffixed(input_file) + options.default_object_extension
        return in_temp(unsuffixed(uniquename(input_file)) + options.default_object_extension)

      # Request LLVM debug info if explicitly specified, or building bitcode with -g, or if building a source all the way to JS with -g
      if use_source_map(options) or ((final_suffix not in JS_CONTAINING_ENDINGS or (has_source_inputs and final_suffix in JS_CONTAINING_ENDINGS)) and options.requested_debug == '-g'):
        # do not save llvm debug info if js optimizer will wipe it out anyhow (but if source maps are used, keep it)
        if use_source_map(options) or not (final_suffix in JS_CONTAINING_ENDINGS and options.js_opts):
          newargs.append('-g') # preserve LLVM debug info
          options.debug_level = 4
          shared.Settings.DEBUG_LEVEL = 4

      # For asm.js, the generated JavaScript could preserve LLVM value names, which can be useful for debugging.
      if options.debug_level >= 3 and not shared.Settings.WASM:
        newargs.append('-fno-discard-value-names')

      # Bitcode args generation code
      def get_clang_command(input_files):
        args = [clang_compiler] + newargs + input_files
        if not shared.Building.can_inline():
          args.append('-fno-inline-functions')
        # For fastcomp backend, no LLVM IR functions should ever be annotated
        # 'optnone', because that would skip running the SimplifyCFG pass on
        # them, which is required to always run to clean up LandingPadInst
        # instructions that are not needed.
        if not shared.Settings.WASM_BACKEND:
          args += ['-Xclang', '-disable-O0-optnone']
        args = system_libs.process_args(args, shared.Settings)
        return args

      # -E preprocessor-only support
      if '-E' in newargs or '-M' in newargs or '-MM' in newargs or '-fsyntax-only' in newargs:
        input_files = [x[1] for x in input_files]
        cmd = get_clang_command(input_files)
        if specified_target:
          cmd += ['-o', specified_target]
        # Do not compile, but just output the result from preprocessing stage or
        # output the dependency rule. Warning: clang and gcc behave differently
        # with -MF! (clang seems to not recognize it)
        logger.debug(('just preprocessor ' if '-E' in newargs else 'just dependencies: ') + ' '.join(cmd))
        return run_process(cmd, check=False).returncode

      def compile_source_file(i, input_file):
        logger.debug('compiling source file: ' + input_file)
        output_file = get_object_filename(input_file)
        temp_files.append((i, output_file))
        cmd = get_clang_command([input_file]) + ['-c', '-o', output_file]
        if shared.Settings.WASM_BACKEND and shared.Settings.RELOCATABLE:
          cmd.append('-fPIC')
          cmd.append('-fvisibility=default')
        if shared.Settings.WASM_OBJECT_FILES:
          for a in shared.Building.llvm_backend_args():
            cmd += ['-mllvm', a]
        else:
          cmd.append('-emit-llvm')
        shared.print_compiler_stage(cmd)
        shared.check_call(cmd)
        if output_file != '-':
          assert(os.path.exists(output_file))

      # First, generate LLVM bitcode. For each input file, we get base.o with bitcode
      for i, input_file in input_files:
        file_ending = get_file_suffix(input_file)
        if file_ending.endswith(SOURCE_ENDINGS):
          compile_source_file(i, input_file)
        else: # bitcode
          if file_ending.endswith(BITCODE_ENDINGS):
            logger.debug('using bitcode file: ' + input_file)
            temp_files.append((i, input_file))
          elif file_ending.endswith(DYNAMICLIB_ENDINGS) or shared.Building.is_ar(input_file):
            logger.debug('using library file: ' + input_file)
            temp_files.append((i, input_file))
          elif file_ending.endswith(ASSEMBLY_ENDINGS):
            if not LEAVE_INPUTS_RAW:
              logger.debug('assembling assembly file: ' + input_file)
              temp_file = in_temp(unsuffixed(uniquename(input_file)) + '.o')
              shared.Building.llvm_as(input_file, temp_file)
              temp_files.append((i, temp_file))
          else:
            if has_fixed_language_mode:
              compile_source_file(i, input_file)
            else:
              exit_with_error(input_file + ': Unknown file suffix when compiling to LLVM bitcode!')

    # exit block 'bitcodeize inputs'
    log_time('compile input files')

    with ToolchainProfiler.profile_block('process inputs'):
      if not LEAVE_INPUTS_RAW and not shared.Settings.WASM_BACKEND:
        assert len(temp_files) == len(input_files)

        # Optimize source files
        if optimizing(options.llvm_opts):
          for pos, (_, input_file) in enumerate(input_files):
            file_ending = get_file_suffix(input_file)
            if file_ending.endswith(SOURCE_ENDINGS):
              temp_file = temp_files[pos][1]
              logger.debug('optimizing %s', input_file)
              # if DEBUG:
              #   shutil.copyfile(temp_file, os.path.join(shared.configuration.CANONICAL_TEMP_DIR, 'to_opt.bc')) # useful when LLVM opt aborts
              new_temp_file = in_temp(unsuffixed(uniquename(temp_file)) + '.o')
              # after optimizing, lower intrinsics to libc calls so that our linking code
              # will find them (otherwise, llvm.cos.f32() will not link in cosf(), and
              # we end up calling out to JS for Math.cos).
              opts = options.llvm_opts + ['-lower-non-em-intrinsics']
              shared.Building.llvm_opt(temp_file, opts, new_temp_file)
              temp_files[pos] = (temp_files[pos][0], new_temp_file)

      # Decide what we will link
      executable_endings = JS_CONTAINING_ENDINGS + ('.wasm',)
      compile_only = final_suffix not in executable_endings or has_dash_c or has_dash_S

      if compile_only or not shared.Settings.WASM_BACKEND:
        # Filter link flags, keeping only those that shared.Building.link knows
        # how to deal with.  We currently can't handle flags with options (like
        # -Wl,-rpath,/bin:/lib, where /bin:/lib is an option for the -rpath
        # flag).
        def supported(f):
          if f in SUPPORTED_LINKER_FLAGS:
            return True
          logger.warning('ignoring unsupported linker flag: `%s`', f)
          return False
        link_flags = [f for f in link_flags if supported(f[1])]

      linker_inputs = [val for _, val in sorted(temp_files + link_flags)]

      # If we were just compiling stop here
      if compile_only:
        if not specified_target:
          assert len(temp_files) == len(input_files)
          for tempf, inputf in zip(temp_files, input_files):
            safe_move(tempf[1], unsuffixed_basename(inputf[1]) + final_suffix)
        else:
          if len(input_files) == 1:
            input_file = input_files[0][1]
            temp_file = temp_files[0][1]
            bitcode_target = specified_target if specified_target else unsuffixed_basename(input_file) + final_suffix
            if temp_file != input_file:
              safe_move(temp_file, bitcode_target)
            else:
              shutil.copyfile(temp_file, bitcode_target)
            temp_output_base = unsuffixed(temp_file)
            if os.path.exists(temp_output_base + '.d'):
              # There was a .d file generated, from -MD or -MMD and friends, save a copy of it to where the output resides,
              # adjusting the target name away from the temporary file name to the specified target.
              # It will be deleted with the rest of the temporary directory.
              deps = open(temp_output_base + '.d').read()
              deps = deps.replace(temp_output_base + options.default_object_extension, specified_target)
              with open(os.path.join(os.path.dirname(specified_target), os.path.basename(unsuffixed(input_file) + '.d')), "w") as out_dep:
                out_dep.write(deps)
          else:
            assert len(original_input_files) == 1 or not has_dash_c, 'fatal error: cannot specify -o with -c with multiple files' + str(args) + ':' + str(original_input_files)
            # We have a specified target (-o <target>), which is not JavaScript or HTML, and
            # we have multiple files: Link them
            logger.debug('link: ' + str(linker_inputs) + specified_target)
            shared.Building.link_to_object(linker_inputs, specified_target)
        logger.debug('stopping after compile phase')
        if shared.Settings.SIDE_MODULE:
          exit_with_error('SIDE_MODULE must only be used when compiling to an executable shared library, and not when emitting an object file.  That is, you should be emitting a .wasm file (for wasm) or a .js file (for asm.js). Note that when compiling to a typical native suffix for a shared library (.so, .dylib, .dll; which many build systems do) then Emscripten emits an object file, which you should then compile to .wasm or .js with SIDE_MODULE.')
        if final_suffix.lower() in ('.so', '.dylib', '.dll'):
          logger.warning('When Emscripten compiles to a typical native suffix for shared libraries (.so, .dylib, .dll) then it emits an object file. You should then compile that to an emscripten SIDE_MODULE (using that flag) with suffix .wasm (for wasm) or .js (for asm.js). (You may also want to adapt your build system to emit the more standard suffix for a an object file, \'.bc\' or \'.o\', which would avoid this warning.)')
        return 0

    with ToolchainProfiler.profile_block('calculate system libraries'):
      logger.debug('will generate JavaScript')

      extra_files_to_link = []

      # link in ports and system libraries, if necessary
      if not LEAVE_INPUTS_RAW and \
         not shared.Settings.BOOTSTRAPPING_STRUCT_INFO and \
         not shared.Settings.ONLY_MY_CODE and \
         not shared.Settings.SIDE_MODULE: # shared libraries/side modules link no C libraries, need them in parent
        extra_files_to_link = system_libs.get_ports(shared.Settings)
        extra_files_to_link += system_libs.calculate([f for _, f in sorted(input_files)] + extra_files_to_link, in_temp, stdout_=None, stderr_=None, forced=forced_stdlibs)

    # exit block 'calculate system libraries'
    log_time('calculate system libraries')

    ## Continue on to create final Wasm/JavaScript
    link_cmd = [shared.PYTHON, shared.EMLINK, '-o', target] + [i[1] for i in temp_files] + extra_files_to_link
    if '-v' in newargs:
      link_cmd.append('-v')
    link_cmd += ['-s' + s for s in settings_changes]
    shared.print_compiler_stage(link_cmd)
    shared.check_call(link_cmd)
  finally:
    if DEBUG:
      shared.Cache.release_cache_lock()

  if DEBUG:
    logger.debug('total time: %.2f seconds', (time.time() - start_time))

  return 0


def parse_args(newargs):
  options = EmccOptions()
  settings_changes = []
  should_exit = False

  def check_bad_eq(arg):
    if '=' in arg:
      exit_with_error('Invalid parameter (do not use "=" with "--" options)')

  link_args = ['--emrun', '--separate-asm', '--proxy-to-worker', '--cpu-profiler'
               '--use-preload-plugins', '--use-preload-cache', '--tracing',
               '--threadprofiler', '--emit-symbol-map', '--profiling-funcs']
  link_args_with_value = ['--closure', '--pre-js', '--post-js',
               '--js-transform', '--source-map-base', '--closure-args',
               '--output-eol']

  for i in range(len(newargs)):
    if newargs[i] in link_args:
      options.link_flags.append(newargs[i])
      newargs[i] = ''
      continue

    if newargs[i] in link_args_with_value:
      check_bad_eq(newargs[i])
      options.link_flags.append(newargs[i])
      options.link_flags.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
      continue

    # On Windows Vista (and possibly others), excessive spaces in the command line
    # leak into the items in this array, so trim e.g. 'foo.cpp ' -> 'foo.cpp'
    newargs[i] = newargs[i].strip()
    if newargs[i].startswith('-O'):
      # Let -O default to -O2, which is what gcc does.
      options.requested_level = newargs[i][2:] or '2'
      if options.requested_level == 's':
        options.llvm_opts = ['-Os']
        options.requested_level = 2
        options.shrink_level = 1
        settings_changes.append('INLINING_LIMIT=50')
      elif options.requested_level == 'z':
        options.llvm_opts = ['-Oz']
        options.requested_level = 2
        options.shrink_level = 2
        settings_changes.append('INLINING_LIMIT=25')
      options.opt_level = validate_arg_level(options.requested_level, 3, 'Invalid optimization level: ' + newargs[i], clamp=True)
    elif newargs[i].startswith('--js-opts'):
      check_bad_eq(newargs[i])
      options.js_opts = int(newargs[i + 1])
      if options.js_opts:
        options.force_js_opts = True
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--llvm-opts'):
      check_bad_eq(newargs[i])
      options.llvm_opts = shared.parse_value(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--llvm-lto'):
      check_bad_eq(newargs[i])
      options.llvm_lto = int(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--minify'):
      check_bad_eq(newargs[i])
      assert newargs[i + 1] == '0', '0 is the only supported option for --minify; 1 has been deprecated'
      options.debug_level = max(1, options.debug_level)
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('-g'):
      requested_level = newargs[i][2:] or '3'
      options.debug_level = validate_arg_level(requested_level, 4, 'Invalid debug level: ' + newargs[i])
      options.requested_debug = newargs[i]
      newargs[i] = ''
    elif newargs[i] == '-profiling' or newargs[i] == '--profiling':
      options.debug_level = max(options.debug_level, 2)
      options.profiling = True
      newargs[i] = ''
    elif newargs[i] == '--tracing' or newargs[i] == '--memoryprofiler':
      if newargs[i] == '--memoryprofiler':
        options.memory_profiler = True
      newargs[i] = ''
      newargs.append('-D__EMSCRIPTEN_TRACING__=1')
      settings_changes.append("EMSCRIPTEN_TRACING=1")
      options.js_libraries.append(shared.path_from_root('src', 'library_trace.js'))
    elif newargs[i] == '--bind':
      shared.Settings.EMBIND = 1
      newargs[i] = ''
      options.js_libraries.append(shared.path_from_root('src', 'embind', 'emval.js'))
      options.js_libraries.append(shared.path_from_root('src', 'embind', 'embind.js'))
      if options.default_cxx_std:
        # Force C++11 for embind code, but only if user has not explicitly overridden a standard.
        options.default_cxx_std = '-std=c++11'
    elif newargs[i].startswith('-std=') or newargs[i].startswith('--std='):
      # User specified a standard to use, clear Emscripten from specifying it.
      options.default_cxx_std = None
    elif newargs[i].startswith('--embed-file'):
      check_bad_eq(newargs[i])
      options.embed_files.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--preload-file'):
      check_bad_eq(newargs[i])
      options.preload_files.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--exclude-file'):
      check_bad_eq(newargs[i])
      options.exclude_files.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--no-heap-copy'):
      options.no_heap_copy = True
      newargs[i] = ''
    elif newargs[i] == '--ignore-dynamic-linking':
      options.ignore_dynamic_linking = True
      newargs[i] = ''
    elif newargs[i] == '-v':
      shared.COMPILER_OPTS += ['-v']
      shared.VERBOSE = True
      shared.check_sanity(force=True)
      newargs[i] = ''
    elif newargs[i].startswith('--shell-file'):
      check_bad_eq(newargs[i])
      options.shell_path = newargs[i + 1]
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith('--js-library'):
      check_bad_eq(newargs[i])
      options.js_libraries.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i] == '--remove-duplicates':
      logger.warning('--remove-duplicates is deprecated as it is no longer needed. If you cannot link without it, file a bug with a testcase')
      newargs[i] = ''
    elif newargs[i] == '--jcache':
      logger.error('jcache is no longer supported')
      newargs[i] = ''
    elif newargs[i] == '--cache':
      check_bad_eq(newargs[i])
      os.environ['EM_CACHE'] = os.path.normpath(newargs[i + 1])
      shared.reconfigure_cache()
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i] == '--clear-cache':
      logger.info('clearing cache as requested by --clear-cache')
      shared.Cache.erase()
      shared.check_sanity(force=True) # this is a good time for a sanity check
      should_exit = True
    elif newargs[i] == '--clear-ports':
      logger.info('clearing ports and cache as requested by --clear-ports')
      system_libs.Ports.erase()
      shared.Cache.erase()
      shared.check_sanity(force=True) # this is a good time for a sanity check
      should_exit = True
    elif newargs[i] == '--show-ports':
      system_libs.show_ports()
      should_exit = True
    elif newargs[i] == '--save-bc':
      check_bad_eq(newargs[i])
      options.save_bc = newargs[i + 1]
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i] == '--memory-init-file':
      check_bad_eq(newargs[i])
      options.memory_init_file = int(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i] == '--valid-abspath':
      options.valid_abspaths.append(newargs[i + 1])
      newargs[i] = ''
      newargs[i + 1] = ''
    elif newargs[i].startswith(('-I', '-L')):
      options.path_name = newargs[i][2:]
      if os.path.isabs(options.path_name) and not is_valid_abspath(options, options.path_name):
        # Of course an absolute path to a non-system-specific library or header
        # is fine, and you can ignore this warning. The danger are system headers
        # that are e.g. x86 specific and nonportable. The emscripten bundled
        # headers are modified to be portable, local system ones are generally not.
        shared.WarningManager.warn(
            'ABSOLUTE_PATHS', '-I or -L of an absolute path "' + newargs[i] +
            '" encountered. If this is to a local system header/library, it may '
            'cause problems (local system files make sense for compiling natively '
            'on your system, but not necessarily to JavaScript).')
    elif newargs[i] == '-fno-exceptions':
      settings_changes.append('DISABLE_EXCEPTION_THROWING=1')
    elif newargs[i] == '-fexceptions':
      settings_changes.append('DISABLE_EXCEPTION_THROWING=0')
    elif newargs[i] == '--default-obj-ext':
      newargs[i] = ''
      options.default_object_extension = newargs[i + 1]
      if not options.default_object_extension.startswith('.'):
        options.default_object_extension = '.' + options.default_object_extension
      newargs[i + 1] = ''
    elif newargs[i].startswith("-fsanitize=cfi"):
      options.cfi = True
    elif newargs[i] == '--generate-config':
      optarg = newargs[i + 1]
      path = os.path.expanduser(optarg)
      if os.path.exists(path):
        exit_with_error('File ' + optarg + ' passed to --generate-config already exists!')
      else:
        shared.generate_config(optarg)
      should_exit = True
    # Record SIMD setting because it controls whether the autovectorizer runs
    elif newargs[i] == '-msimd128':
      settings_changes.append('SIMD=1')
    elif newargs[i] == '-mno-simd128':
      settings_changes.append('SIMD=0')
    # Record USE_PTHREADS setting because it controls whether --shared-memory is passed to lld
    elif newargs[i] == '-pthread':
      settings_changes.append('USE_PTHREADS=1')
    elif newargs[i] in ('-fno-diagnostics-color', '-fdiagnostics-color=never'):
      colored_logger.disable()
    elif newargs[i] == '-no-canonical-prefixes':
      options.expand_symlinks = False

  if should_exit:
    sys.exit(0)

  newargs = [arg for arg in newargs if arg]
  return options, settings_changes, newargs


def process_libraries(libs, lib_dirs, input_files):
  libraries = []

  # Find library files
  for i, lib in libs:
    logger.debug('looking for library "%s"', lib)
    found = False
    for prefix in LIB_PREFIXES:
      for suff in STATICLIB_ENDINGS + DYNAMICLIB_ENDINGS:
        name = prefix + lib + suff
        for lib_dir in lib_dirs:
          path = os.path.join(lib_dir, name)
          if os.path.exists(path):
            logger.debug('found library "%s" at %s', lib, path)
            input_files.append((i, path))
            found = True
            break
        if found:
          break
      if found:
        break
    if not found:
      libraries += shared.Building.path_to_system_js_libraries(lib)

  return 'SYSTEM_JS_LIBRARIES="' + ','.join(libraries) + '"'


def is_valid_abspath(options, path_name):
  libraries = []

  # Any path that is underneath the emscripten repository root must be ok.
  if shared.path_from_root().replace('\\', '/') in path_name.replace('\\', '/'):
    return True

  def in_directory(root, child):
    # make both path absolute
    root = os.path.realpath(root)
    child = os.path.realpath(child)

    # return true, if the common prefix of both is equal to directory
    # e.g. /a/b/c/d.rst and directory is /a/b, the common prefix is /a/b
    return os.path.commonprefix([root, child]) == root

  for valid_abspath in options.valid_abspaths:
    if in_directory(valid_abspath, path_name):
      return True
  return False


def validate_arg_level(level_string, max_level, err_msg, clamp=False):
  try:
    level = int(level_string)
  except ValueError:
    raise Exception(err_msg)
  if clamp:
    if level > max_level:
      logger.warning("optimization level '-O" + level_string + "' is not supported; using '-O" + str(max_level) + "' instead")
      level = max_level
  if not 0 <= level <= max_level:
    raise Exception(err_msg)
  return level


if __name__ == '__main__':
  try:
    sys.exit(run(sys.argv))
  except KeyboardInterrupt:
    logger.warning("KeyboardInterrupt")
    sys.exit(1)
