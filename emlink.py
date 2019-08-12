#!/usr/bin/env python2
# Copyright 2013 The Emscripten Authors.  All rights reserved.
# Emscripten is available under two separate licenses, the MIT license and the
# University of Illinois/NCSA Open Source License.  Both these licenses can be
# found in the LICENSE file.

"""Emscripten linker.

This tool take object files (or bitcode files) as input and produces wasm and/or
js output.

Normally this tools is run by the emcc compiler driver rather than directly.
"""

from __future__ import print_function

import argparse
import json
import logging
import os
import re
import shlex
import shutil
import sys
import subprocess
import time

import emscripten
from tools import shared, js_optimizer, client_mods
from tools.shared import run_process, DEBUG, exit_with_error
from tools.shared import read_and_preprocess, safe_copy, jsrun, asbytes
from tools.shared import safe_move, unsuffixed, unsuffixed_basename
from tools.shared import BITCODE_ENDINGS, DYNAMICLIB_ENDINGS, STATICLIB_ENDINGS
import tools.line_endings
from tools.toolchain_profiler import ToolchainProfiler
if __name__ == '__main__':
  ToolchainProfiler.record_process_start()

try:
  from urllib.parse import quote
except ImportError:
  # Python 2 compatibility
  from urllib import quote

logger = logging.getLogger('emlink')
final = None
WASM_ENDINGS = ('.wasm', '.wast')


# If set to 1, we will run the autodebugger (the automatic debugging tool, see
# tools/autodebugger).  Note that this will disable inclusion of libraries. This
# is useful because including dlmalloc makes it hard to compare native and js
# builds
AUTODEBUG = os.environ.get('EMCC_AUTODEBUG')

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


class Intermediate(object):
  counter = 0


# this function uses the global 'final' variable, which contains the current
# final output file. if a method alters final, and calls this method, then it
# must modify final globally (i.e. it can't receive final as a param and
# return it)
# TODO: refactor all this, a singleton that abstracts over the final output
#       and saving of intermediates
def save_intermediate(name, suffix='js'):
  if not DEBUG:
    return
  name = os.path.join(shared.get_emscripten_temp_dir(), 'emcc-%d-%s.%s' % (Intermediate.counter, name, suffix))
  if isinstance(final, list):
    logger.debug('(not saving intermediate %s because deferring linking)' % name)
    return
  shutil.copyfile(final, name)
  Intermediate.counter += 1


def save_intermediate_with_wasm(name, wasm_binary):
  if not DEBUG:
    return
  save_intermediate(name) # save the js
  name = os.path.join(shared.get_emscripten_temp_dir(), 'emcc-%d-%s.wasm' % (Intermediate.counter - 1, name))
  shutil.copyfile(wasm_binary, name)


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


def do_binaryen(target, asm_target, options, memfile, wasm_binary_target,
                wasm_text_target, wasm_source_map_target, misc_temp_files,
                optimizer):
  global final
  logger.debug('using binaryen')
  binaryen_bin = shared.Building.get_binaryen_bin()
  # whether we need to emit -g (function name debug info) in the final wasm
  debug_info = options.debug_level >= 2 or options.profiling_funcs
  # whether we need to emit -g in the intermediate binaryen invocations (but not necessarily at the very end).
  # this is necessary for emitting a symbol map at the end.
  intermediate_debug_info = bool(debug_info or options.emit_symbol_map or shared.Settings.ASYNCIFY_WHITELIST or shared.Settings.ASYNCIFY_BLACKLIST)
  emit_symbol_map = options.emit_symbol_map or shared.Settings.CYBERDWARF
  # finish compiling to WebAssembly, using asm2wasm, if we didn't already emit WebAssembly directly using the wasm backend.
  if not shared.Settings.WASM_BACKEND:
    if DEBUG:
      # save the asm.js input
      shared.safe_copy(asm_target, os.path.join(shared.get_emscripten_temp_dir(), os.path.basename(asm_target)))
    cmd = [os.path.join(binaryen_bin, 'asm2wasm'), asm_target, '--total-memory=' + str(shared.Settings.TOTAL_MEMORY)]
    if shared.Settings.BINARYEN_TRAP_MODE not in ('js', 'clamp', 'allow'):
      exit_with_error('invalid BINARYEN_TRAP_MODE value: ' + shared.Settings.BINARYEN_TRAP_MODE + ' (should be js/clamp/allow)')
    cmd += ['--trap-mode=' + shared.Settings.BINARYEN_TRAP_MODE]
    if shared.Settings.BINARYEN_IGNORE_IMPLICIT_TRAPS:
      cmd += ['--ignore-implicit-traps']
    # pass optimization level to asm2wasm (if not optimizing, or which passes we should run was overridden, do not optimize)
    if options.opt_level > 0:
      cmd.append(shared.Building.opt_level_to_str(options.opt_level, options.shrink_level))
    # import mem init file if it exists, and if we will not be using asm.js as a binaryen method (as it needs the mem init file, of course)
    mem_file_exists = options.memory_init_file and os.path.exists(memfile)
    import_mem_init = mem_file_exists and shared.Settings.MEM_INIT_IN_WASM
    if import_mem_init:
      cmd += ['--mem-init=' + memfile]
      if not shared.Settings.RELOCATABLE:
        cmd += ['--mem-base=' + str(shared.Settings.GLOBAL_BASE)]
    # various options imply that the imported table may not be the exact size as
    # the wasm module's own table segments
    if shared.Settings.RELOCATABLE or shared.Settings.RESERVED_FUNCTION_POINTERS > 0 or shared.Settings.EMULATED_FUNCTION_POINTERS:
      cmd += ['--table-max=-1']
    if shared.Settings.SIDE_MODULE:
      cmd += ['--mem-max=-1']
    elif shared.Settings.WASM_MEM_MAX >= 0:
      cmd += ['--mem-max=' + str(shared.Settings.WASM_MEM_MAX)]
    if shared.Settings.LEGALIZE_JS_FFI != 1:
      cmd += ['--no-legalize-javascript-ffi']
    if shared.Building.is_wasm_only():
      cmd += ['--wasm-only'] # this asm.js is code not intended to run as asm.js, it is only ever going to be wasm, an can contain special fastcomp-wasm support
    if shared.Settings.USE_PTHREADS:
      cmd += ['--enable-threads']
    if intermediate_debug_info:
      cmd += ['-g']
    if emit_symbol_map:
      cmd += ['--symbolmap=' + target + '.symbols']
    # we prefer to emit a binary, as it is more efficient. however, when we
    # want full debug info support (not just function names), then we must
    # emit text (at least until wasm gains support for debug info in binaries)
    target_binary = options.debug_level < 3
    if target_binary:
      cmd += ['-o', wasm_binary_target]
    else:
      cmd += ['-o', wasm_text_target, '-S']
    cmd += shared.Building.get_binaryen_feature_flags()
    logger.debug('asm2wasm (asm.js => WebAssembly): ' + ' '.join(cmd))
    TimeLogger.update()
    shared.check_call(cmd)

    if not target_binary:
      cmd = [os.path.join(binaryen_bin, 'wasm-as'), wasm_text_target, '-o', wasm_binary_target, '--all-features', '--disable-bulk-memory']
      if intermediate_debug_info:
        cmd += ['-g']
        if use_source_map(options):
          cmd += ['--source-map=' + wasm_source_map_target]
          cmd += ['--source-map-url=' + options.source_map_base + os.path.basename(wasm_binary_target) + '.map']
      logger.debug('wasm-as (text => binary): ' + ' '.join(cmd))
      shared.check_call(cmd)
    if import_mem_init:
      # remove the mem init file in later processing; it does not need to be prefetched in the html, etc.
      if DEBUG:
        safe_move(memfile, os.path.join(shared.get_emscripten_temp_dir(), os.path.basename(memfile)))
      else:
        os.unlink(memfile)
    log_time('asm2wasm')
  if options.binaryen_passes:
    if DEBUG:
      shared.safe_copy(wasm_binary_target, os.path.join(shared.get_emscripten_temp_dir(), os.path.basename(wasm_binary_target) + '.pre-byn'))
    cmd = [os.path.join(binaryen_bin, 'wasm-opt'), wasm_binary_target, '-o', wasm_binary_target] + options.binaryen_passes
    cmd += shared.Building.get_binaryen_feature_flags()
    if intermediate_debug_info:
      cmd += ['-g'] # preserve the debug info
    if use_source_map(options):
      cmd += ['--input-source-map=' + wasm_source_map_target]
      cmd += ['--output-source-map=' + wasm_source_map_target]
      cmd += ['--output-source-map-url=' + options.source_map_base + os.path.basename(wasm_binary_target) + '.map']
      if DEBUG:
        shared.safe_copy(wasm_source_map_target, os.path.join(shared.get_emscripten_temp_dir(), os.path.basename(wasm_source_map_target) + '.pre-byn'))
    logger.debug('wasm-opt on binaryen passes: %s', cmd)
    shared.print_compiler_stage(cmd)
    shared.check_call(cmd)
  if shared.Settings.BINARYEN_SCRIPTS:
    binaryen_scripts = os.path.join(shared.BINARYEN_ROOT, 'scripts')
    script_env = os.environ.copy()
    root_dir = os.path.abspath(os.path.dirname(__file__))
    if script_env.get('PYTHONPATH'):
      script_env['PYTHONPATH'] += ':' + root_dir
    else:
      script_env['PYTHONPATH'] = root_dir
    for script in shared.Settings.BINARYEN_SCRIPTS.split(','):
      logger.debug('running binaryen script: ' + script)
      shared.check_call([shared.PYTHON, os.path.join(binaryen_scripts, script), final, wasm_text_target], env=script_env)
  if shared.Settings.EVAL_CTORS:
    if DEBUG:
      save_intermediate_with_wasm('pre-eval-ctors', wasm_binary_target)
    shared.Building.eval_ctors(final, wasm_binary_target, binaryen_bin, debug_info=intermediate_debug_info)

  # after generating the wasm, do some final operations
  if shared.Settings.SIDE_MODULE and not shared.Settings.WASM_BACKEND:
    wso = shared.WebAssembly.make_shared_library(final, wasm_binary_target, shared.Settings.RUNTIME_LINKED_LIBS)
    # replace the wasm binary output with the dynamic library.
    # TODO: use a specific suffix for such files?
    shutil.move(wso, wasm_binary_target)
    if not DEBUG:
      os.unlink(asm_target) # we don't need the asm.js, it can just confuse

  # after generating the wasm, do some final operations
  if shared.Settings.EMIT_EMSCRIPTEN_METADATA:
    shared.WebAssembly.add_emscripten_metadata(final, wasm_binary_target)

  if shared.Settings.SIDE_MODULE:
    sys.exit(0) # and we are done.

  # pthreads memory growth requires some additional JS fixups
  if shared.Settings.USE_PTHREADS and shared.Settings.ALLOW_MEMORY_GROWTH:
    final = shared.Building.apply_wasm_memory_growth(final)

  if options.opt_level >= 2 and options.debug_level <= 2:
    # minify the JS
    optimizer.do_minify() # calculate how to minify
    save_intermediate_with_wasm('preclean', wasm_binary_target)
    final = shared.Building.minify_wasm_js(js_file=final,
                                           wasm_file=wasm_binary_target,
                                           expensive_optimizations=will_metadce(options),
                                           minify_whitespace=optimizer.minify_whitespace,
                                           debug_info=intermediate_debug_info)
    save_intermediate_with_wasm('postclean', wasm_binary_target)

  def run_closure_compiler(final):
    final = shared.Building.closure_compiler(final, pretty=not optimizer.minify_whitespace,
                                             extra_closure_args=options.closure_args)
    save_intermediate_with_wasm('closure', wasm_binary_target)
    return final

  if options.use_closure_compiler:
    final = run_closure_compiler(final)

  symbols_file = target + '.symbols' if options.emit_symbol_map else None

  if shared.Settings.WASM2JS:
    final = shared.Building.wasm2js(final,
                                    wasm_binary_target,
                                    opt_level=options.opt_level,
                                    minify_whitespace=optimizer.minify_whitespace,
                                    use_closure_compiler=options.use_closure_compiler,
                                    debug_info=intermediate_debug_info,
                                    symbols_file=symbols_file)
    save_intermediate('wasm2js')

    shared.try_delete(wasm_binary_target)

  # emit the final symbols, either in the binary or in a symbol map.
  # this will also remove debug info if we only kept it around in the intermediate invocations.
  # note that wasm2js handles the symbol map itself (as it manipulates and then
  # replaces the wasm with js)
  if intermediate_debug_info and not shared.Settings.WASM2JS:
    shared.Building.handle_final_wasm_symbols(wasm_file=wasm_binary_target, symbols_file=symbols_file, debug_info=debug_info)
    save_intermediate_with_wasm('symbolmap', wasm_binary_target)

  # replace placeholder strings with correct subresource locations
  if shared.Settings.SINGLE_FILE:
    js = open(final).read()
    for target, replacement_string, should_embed in (
        (wasm_binary_target,
         shared.FilenameReplacementStrings.WASM_BINARY_FILE,
         True),
        (asm_target,
         shared.FilenameReplacementStrings.ASMJS_CODE_FILE,
         False),
      ):
      if should_embed and os.path.isfile(target):
        js = js.replace(replacement_string, shared.JS.get_subresource_location(target))
      else:
        js = js.replace(replacement_string, '')
      shared.try_delete(target)
    with open(final, 'w') as f:
      f.write(js)


def do_emscripten(infile, memfile, js_libraries):
  if shared.path_from_root() not in sys.path:
    sys.path += [shared.path_from_root()]
  # Run Emscripten
  outfile = infile + '.o.js'
  with ToolchainProfiler.profile_block('emscripten.py'):
    emscripten.run(infile, outfile, memfile, js_libraries)

  # Detect compilation crashes and errors
  assert os.path.exists(outfile), 'Emscripten failed to generate .js'
  return outfile


def use_source_map(options):
  return options.debug_level >= 4


def will_metadce(options):
  return options.opt_level >= 3 or options.shrink_level >= 1


def embed_memfile(options):
  return (shared.Settings.SINGLE_FILE or
          (shared.Settings.MEM_INIT_METHOD == 0 and
           (not shared.Settings.MAIN_MODULE and
            not shared.Settings.SIDE_MODULE and
            not use_source_map(options))))


def emterpretify(js_target, optimizer, options):
  global final
  optimizer.flush('pre-emterpretify')
  logger.debug('emterpretifying')
  blacklist = shared.Settings.EMTERPRETIFY_BLACKLIST
  whitelist = shared.Settings.EMTERPRETIFY_WHITELIST
  synclist = shared.Settings.EMTERPRETIFY_SYNCLIST
  if type(blacklist) == list:
    blacklist = json.dumps(blacklist)
  if type(whitelist) == list:
    whitelist = json.dumps(whitelist)
  if type(synclist) == list:
    synclist = json.dumps(synclist)

  args = [shared.PYTHON,
          shared.path_from_root('tools', 'emterpretify.py'),
          js_target,
          final + '.em.js',
          blacklist,
          whitelist,
          synclist,
          str(shared.Settings.SWAPPABLE_ASM_MODULE)]
  if shared.Settings.EMTERPRETIFY_ASYNC:
    args += ['ASYNC=1']
  if shared.Settings.EMTERPRETIFY_ADVISE:
    args += ['ADVISE=1']
  if options.profiling or options.profiling_funcs:
    args += ['PROFILING=1']
  if shared.Settings.ASSERTIONS:
    args += ['ASSERTIONS=1']
  if shared.Settings.PRECISE_F32:
    args += ['FROUND=1']
  if shared.Settings.ALLOW_MEMORY_GROWTH:
    args += ['MEMORY_SAFE=1']
  if shared.Settings.EMTERPRETIFY_FILE:
    args += ['FILE="' + shared.Settings.EMTERPRETIFY_FILE + '"']

  try:
    # move temp js to final position, alongside its mem init file
    shutil.move(final, js_target)
    shared.check_call(args)
  finally:
    shared.try_delete(js_target)

  final = final + '.em.js'

  if shared.Settings.EMTERPRETIFY_ADVISE:
    logger.warning('halting compilation due to EMTERPRETIFY_ADVISE')
    sys.exit(0)

  # minify (if requested) after emterpreter processing, and finalize output
  logger.debug('finalizing emterpreted code')
  shared.Settings.FINALIZE_ASM_JS = 1
  if not shared.Settings.WASM:
    optimizer.do_minify()
  optimizer.queue += ['last']
  optimizer.flush('finalizing-emterpreted-code')

  # finalize the original as well, if we will be swapping it in (TODO: add specific option for this)
  if shared.Settings.SWAPPABLE_ASM_MODULE:
    real = final
    original = js_target + '.orig.js' # the emterpretify tool saves the original here
    final = original
    logger.debug('finalizing original (non-emterpreted) code at ' + final)
    if not shared.Settings.WASM:
      optimizer.do_minify()
    optimizer.queue += ['last']
    optimizer.flush('finalizing-original-code')
    safe_copy(final, original)
    final = real


def emit_js_source_maps(target, js_transform_tempfiles):
  logger.debug('generating source maps')
  jsrun.run_js_tool(shared.path_from_root('tools', 'source-maps', 'sourcemapper.js'),
                    shared.NODE_JS, js_transform_tempfiles +
                    ['--sourceRoot', os.getcwd(),
                     '--mapFileBaseName', target,
                     '--offset', '0'])


def separate_asm_js(final, asm_target):
  """Separate out the asm.js code, if asked. Or, if necessary for another option"""
  logger.debug('separating asm')
  shared.check_call([shared.PYTHON, shared.path_from_root('tools', 'separate_asm.py'), final, asm_target, final, shared.Settings.SEPARATE_ASM_MODULE_NAME])

  # extra only-my-code logic
  if shared.Settings.ONLY_MY_CODE:
    temp = asm_target + '.only.js'
    jsrun.run_js_tool(shared.path_from_root('tools', 'js-optimizer.js'), shared.NODE_JS, jsargs=[asm_target, 'eliminateDeadGlobals', 'last', 'asm'], stdout=open(temp, 'w'))
    shutil.move(temp, asm_target)


def modularize():
  global final
  logger.debug('Modularizing, assigning to var ' + shared.Settings.EXPORT_NAME)
  src = open(final).read()

  # TODO: exports object generation for MINIMAL_RUNTIME
  exports_object = '{}' if shared.Settings.MINIMAL_RUNTIME else shared.Settings.EXPORT_NAME

  src = '''
function(%(EXPORT_NAME)s) {
  %(EXPORT_NAME)s = %(EXPORT_NAME)s || {};

%(src)s

  return %(exports_object)s
}
''' % {
    'EXPORT_NAME': shared.Settings.EXPORT_NAME,
    'src': src,
    'exports_object': exports_object
  }

  if not shared.Settings.MODULARIZE_INSTANCE:
    if shared.Settings.MINIMAL_RUNTIME and not shared.Settings.USE_PTHREADS:
      # Single threaded MINIMAL_RUNTIME programs do not need access to
      # document.currentScript, so a simple export declaration is enough.
      src = 'var %s=%s' % (shared.Settings.EXPORT_NAME, src)
    else:
      # When MODULARIZE this JS may be executed later,
      # after document.currentScript is gone, so we save it.
      # (when MODULARIZE_INSTANCE, an instance is created
      # immediately anyhow, like in non-modularize mode)
      # In EXPORT_ES6 + USE_PTHREADS the 'thread' is actually an ES6 module webworker running in strict mode,
      # so doesn't have access to 'document'. In this case use 'import.meta' instead.
      if shared.Settings.EXPORT_ES6 and shared.Settings.USE_PTHREADS:
        script_url = "import.meta.url"
      else:
        script_url = "typeof document !== 'undefined' && document.currentScript ? document.currentScript.src : undefined"
      src = '''
var %(EXPORT_NAME)s = (function() {
  var _scriptDir = %(script_url)s;
  return (%(src)s);
})();
''' % {
        'EXPORT_NAME': shared.Settings.EXPORT_NAME,
        'src': src,
        'script_url': script_url
      }
  else:
    # Create the MODULARIZE_INSTANCE instance
    # Note that we notice the global Module object, just like in normal
    # non-MODULARIZE mode (while MODULARIZE has the user create the instances,
    # and the user can decide whether to use Module there or something
    # else etc.).
    src = '''
var %(EXPORT_NAME)s = (%(src)s)(typeof %(EXPORT_NAME)s === 'object' ? %(EXPORT_NAME)s : {});
''' % {
      'EXPORT_NAME': shared.Settings.EXPORT_NAME,
      'src': src
    }

  final = final + '.modular.js'
  with open(final, 'w') as f:
    f.write(src)

    # Export using a UMD style export, or ES6 exports if selected

    if shared.Settings.EXPORT_ES6:
      f.write('''export default %s;''' % shared.Settings.EXPORT_NAME)
    elif not shared.Settings.MINIMAL_RUNTIME:
      f.write('''if (typeof exports === 'object' && typeof module === 'object')
      module.exports = %(EXPORT_NAME)s;
    else if (typeof define === 'function' && define['amd'])
      define([], function() { return %(EXPORT_NAME)s; });
    else if (typeof exports === 'object')
      exports["%(EXPORT_NAME)s"] = %(EXPORT_NAME)s;
    ''' % {
        'EXPORT_NAME': shared.Settings.EXPORT_NAME
      })

  save_intermediate('modularized')


def module_export_name_substitution():
  global final
  logger.debug('Private module export name substitution with ' + shared.Settings.EXPORT_NAME)
  src = open(final).read()
  final = final + '.module_export_name_substitution.js'
  if shared.Settings.MINIMAL_RUNTIME:
    # In MINIMAL_RUNTIME the Module object is always present to provide the .asm.js/.wasm content
    replacement = shared.Settings.EXPORT_NAME
  else:
    replacement = "typeof %(EXPORT_NAME)s !== 'undefined' ? %(EXPORT_NAME)s : {}" % {"EXPORT_NAME": shared.Settings.EXPORT_NAME}
  with open(final, 'w') as f:
    src = src.replace(shared.JS.module_export_name_substitution_pattern, replacement)
    # For Node.js and other shell environments, create an unminified Module object so that
    # loading external .asm.js file that assigns to Module['asm'] works even when Closure is used.
    if shared.Settings.MINIMAL_RUNTIME and (shared.Settings.target_environment_may_be('node') or
                                            shared.Settings.target_environment_may_be('shell')):
      src = 'if(typeof Module==="undefined"){var Module={};}' + src
    f.write(src)
  save_intermediate('module_export_name_substitution')


def generate_minimal_runtime_html(target, options, js_target, target_basename,
                                  asm_target, wasm_binary_target,
                                  memfile, optimizer):
  logger.debug('generating HTML for minimal runtime')
  shell = read_and_preprocess(options.shell_path)
  if re.search(r'{{{\s*SCRIPT\s*}}}', shell):
    exit_with_error('--shell-file "' + options.shell_path + '": MINIMAL_RUNTIME uses a different kind of HTML page shell file than the traditional runtime! Please see $EMSCRIPTEN/src/shell_minimal_runtime.html for a template to use as a basis.')

  shell = shell.replace('{{{ TARGET_BASENAME }}}', target_basename)
  shell = shell.replace('{{{ EXPORT_NAME }}}', shared.Settings.EXPORT_NAME)
  shell = tools.line_endings.convert_line_endings(shell, '\n', options.output_eol)
  with open(target, 'wb') as f:
    f.write(asbytes(shell))


def generate_traditional_runtime_html(target, options, js_target, target_basename,
                                      asm_target, wasm_binary_target,
                                      memfile, optimizer):
  script = ScriptSource()

  shell = read_and_preprocess(options.shell_path)
  assert '{{{ SCRIPT }}}' in shell, 'HTML shell must contain  {{{ SCRIPT }}}  , see src/shell.html for an example'
  base_js_target = os.path.basename(js_target)

  asm_mods = []

  if options.proxy_to_worker:
    proxy_worker_filename = (shared.Settings.PROXY_TO_WORKER_FILENAME or target_basename) + '.js'
    worker_js = worker_js_script(proxy_worker_filename)
    script.inline = ('''
  var filename = '%s';
  if ((',' + window.location.search.substr(1) + ',').indexOf(',noProxy,') < 0) {
    console.log('running code in a web worker');
''' % shared.JS.get_subresource_location(proxy_worker_filename)) + worker_js + '''
  } else {
    // note: no support for code mods (PRECISE_F32==2)
    console.log('running code on the main thread');
    var fileBytes = tryParseAsDataURI(filename);
    var script = document.createElement('script');
    if (fileBytes) {
      script.innerHTML = intArrayToString(fileBytes);
    } else {
      script.src = filename;
    }
    document.body.appendChild(script);
  }
'''
  else:
    # Normal code generation path
    script.src = base_js_target

    asm_mods = client_mods.get_mods(shared.Settings,
                                    minified='minifyNames' in optimizer.queue_history,
                                    separate_asm=options.separate_asm)

  if not shared.Settings.SINGLE_FILE:
    if shared.Settings.EMTERPRETIFY_FILE:
      # We need to load the emterpreter file before anything else, it has to be synchronously ready
      script.un_src()
      script.inline = '''
          var emterpretURL = '%s';
          var emterpretXHR = new XMLHttpRequest();
          emterpretXHR.open('GET', emterpretURL, true);
          emterpretXHR.responseType = 'arraybuffer';
          emterpretXHR.onload = function() {
            if (emterpretXHR.status === 200 || emterpretXHR.status === 0) {
              Module.emterpreterFile = emterpretXHR.response;
            } else {
              var emterpretURLBytes = tryParseAsDataURI(emterpretURL);
              if (emterpretURLBytes) {
                Module.emterpreterFile = emterpretURLBytes.buffer;
              }
            }
%s
          };
          emterpretXHR.send(null);
''' % (shared.JS.get_subresource_location(shared.Settings.EMTERPRETIFY_FILE), script.inline)

    if options.memory_init_file and not shared.Settings.MEM_INIT_IN_WASM:
      # start to load the memory init file in the HTML, in parallel with the JS
      script.un_src()
      script.inline = ('''
          var memoryInitializer = '%s';
          memoryInitializer = Module['locateFile'] ? Module['locateFile'](memoryInitializer, '') : memoryInitializer;
          Module['memoryInitializerRequestURL'] = memoryInitializer;
          var meminitXHR = Module['memoryInitializerRequest'] = new XMLHttpRequest();
          meminitXHR.open('GET', memoryInitializer, true);
          meminitXHR.responseType = 'arraybuffer';
          meminitXHR.send(null);
''' % shared.JS.get_subresource_location(memfile)) + script.inline

    # Download .asm.js if --separate-asm was passed in an asm.js build, or if 'asmjs' is one
    # of the wasm run methods.
    if not options.separate_asm or shared.Settings.WASM:
      if len(asm_mods):
         exit_with_error('no --separate-asm means no client code mods are possible')
    else:
      script.un_src()
      if len(asm_mods) == 0:
        # just load the asm, then load the rest
        script.inline = '''
    var filename = '%s';
    var fileBytes = tryParseAsDataURI(filename);
    var script = document.createElement('script');
    if (fileBytes) {
      script.innerHTML = intArrayToString(fileBytes);
    } else {
      script.src = filename;
    }
    script.onload = function() {
      setTimeout(function() {
        %s
      }, 1); // delaying even 1ms is enough to allow compilation memory to be reclaimed
    };
    document.body.appendChild(script);
''' % (shared.JS.get_subresource_location(asm_target), script.inline)
      else:
        # may need to modify the asm code, load it as text, modify, and load asynchronously
        script.inline = '''
    var codeURL = '%s';
    var codeXHR = new XMLHttpRequest();
    codeXHR.open('GET', codeURL, true);
    codeXHR.onload = function() {
      var code;
      if (codeXHR.status === 200 || codeXHR.status === 0) {
        code = codeXHR.responseText;
      } else {
        var codeURLBytes = tryParseAsDataURI(codeURL);
        if (codeURLBytes) {
          code = intArrayToString(codeURLBytes);
        }
      }
      %s
      var blob = new Blob([code], { type: 'text/javascript' });
      codeXHR = null;
      var src = URL.createObjectURL(blob);
      var script = document.createElement('script');
      script.src = src;
      script.onload = function() {
        setTimeout(function() {
          %s
        }, 1); // delaying even 1ms is enough to allow compilation memory to be reclaimed
        URL.revokeObjectURL(script.src);
      };
      document.body.appendChild(script);
    };
    codeXHR.send(null);
''' % (shared.JS.get_subresource_location(asm_target), '\n'.join(asm_mods), script.inline)

    if shared.Settings.WASM and not shared.Settings.WASM_ASYNC_COMPILATION:
      # We need to load the wasm file before anything else, it has to be synchronously ready TODO: optimize
      script.un_src()
      script.inline = '''
          var wasmURL = '%s';
          var wasmXHR = new XMLHttpRequest();
          wasmXHR.open('GET', wasmURL, true);
          wasmXHR.responseType = 'arraybuffer';
          wasmXHR.onload = function() {
            if (wasmXHR.status === 200 || wasmXHR.status === 0) {
              Module.wasmBinary = wasmXHR.response;
            } else {
              var wasmURLBytes = tryParseAsDataURI(wasmURL);
              if (wasmURLBytes) {
                Module.wasmBinary = wasmURLBytes.buffer;
              }
            }
%s
          };
          wasmXHR.send(null);
''' % (shared.JS.get_subresource_location(wasm_binary_target), script.inline)

  # when script.inline isn't empty, add required helper functions such as tryParseAsDataURI
  if script.inline:
    for filename in ('arrayUtils.js', 'base64Utils.js', 'URIUtils.js'):
      content = read_and_preprocess(shared.path_from_root('src', filename))
      script.inline = content + script.inline

    script.inline = 'var ASSERTIONS = %s;\n%s' % (shared.Settings.ASSERTIONS, script.inline)

  # inline script for SINGLE_FILE output
  if shared.Settings.SINGLE_FILE:
    js_contents = script.inline or ''
    if script.src:
      js_contents += open(js_target).read()
    shared.try_delete(js_target)
    script.src = None
    script.inline = js_contents

  html_contents = shell.replace('{{{ SCRIPT }}}', script.replacement())
  html_contents = tools.line_endings.convert_line_endings(html_contents, '\n', options.output_eol)
  with open(target, 'wb') as f:
    f.write(asbytes(html_contents))


def minify_html(filename, options):
  opts = []
  # -g1 and greater retain whitespace and comments in source
  if options.debug_level == 0:
    opts += ['--collapse-whitespace',
             '--collapse-inline-tag-whitespace',
             '--remove-comments',
             '--remove-tag-whitespace',
             '--sort-attributes',
             '--sort-class-name']
  # -g2 and greater do not minify HTML at all
  if options.debug_level <= 1:
    opts += ['--decode-entities',
             '--collapse-boolean-attributes',
             '--remove-attribute-quotes',
             '--remove-redundant-attributes',
             '--remove-script-type-attributes',
             '--remove-style-link-type-attributes',
             '--use-short-doctype',
             '--minify-css', 'true',
             '--minify-js', 'true']

  # html-minifier also has the following options, but they look unsafe for use:
  # '--remove-optional-tags': removes e.g. <head></head> and <body></body> tags from the page.
  #                           (Breaks at least browser.test_sdl2glshader)
  # '--remove-empty-attributes': removes all attributes with whitespace-only values.
  #                              (Breaks at least browser.test_asmfs_hello_file)
  # '--remove-empty-elements': removes all elements with empty contents.
  #                            (Breaks at least browser.test_asm_swapping)

  if options.debug_level >= 2:
    return

  logger.debug('minifying HTML file ' + filename)
  size_before = os.path.getsize(filename)
  start_time = time.time()
  run_process(shared.NODE_JS + [shared.path_from_root('third_party', 'html-minifier', 'cli.js'), filename, '-o', filename] + opts)
  elapsed_time = time.time() - start_time
  size_after = os.path.getsize(filename)
  delta = size_after - size_before
  logger.debug('HTML minification took {:.2f}'.format(elapsed_time) + ' seconds, and shrunk size of ' + filename + ' from ' + str(size_before) + ' to ' + str(size_after) + ' bytes, delta=' + str(delta) + ' ({:+.2f}%)'.format(delta * 100.0 / size_before))


def generate_html(target, options, js_target, target_basename,
                  asm_target, wasm_binary_target,
                  memfile, optimizer):
  logger.debug('generating HTML')

  if shared.Settings.MINIMAL_RUNTIME:
    generate_minimal_runtime_html(target, options, js_target, target_basename, asm_target,
                                  wasm_binary_target, memfile, optimizer)
  else:
    generate_traditional_runtime_html(target, options, js_target, target_basename, asm_target,
                                      wasm_binary_target, memfile, optimizer)

  if shared.Settings.MINIFY_HTML and (options.opt_level >= 1 or options.shrink_level >= 1):
    minify_html(target, options)


def generate_worker_js(target, js_target, target_basename):
  # compiler output is embedded as base64
  if shared.Settings.SINGLE_FILE:
    proxy_worker_filename = shared.JS.get_subresource_location(js_target)

  # compiler output goes in .worker.js file
  else:
    shutil.move(js_target, unsuffixed(js_target) + '.worker.js')
    worker_target_basename = target_basename + '.worker'
    proxy_worker_filename = (shared.Settings.PROXY_TO_WORKER_FILENAME or worker_target_basename) + '.js'

  target_contents = worker_js_script(proxy_worker_filename)
  open(target, 'w').write(target_contents)


def worker_js_script(proxy_worker_filename):
  web_gl_client_src = open(shared.path_from_root('src', 'webGLClient.js')).read()
  idb_store_src = open(shared.path_from_root('src', 'IDBStore.js')).read()
  proxy_client_src = (
    open(shared.path_from_root('src', 'proxyClient.js')).read()
    .replace('{{{ filename }}}', proxy_worker_filename)
    .replace('{{{ IDBStore.js }}}', idb_store_src)
  )

  return web_gl_client_src + '\n' + proxy_client_src


class ScriptSource(object):
  def __init__(self):
    self.src = None # if set, we have a script to load with a src attribute
    self.inline = None # if set, we have the contents of a script to write inline in a script

  def un_src(self):
    """Use this if you want to modify the script and need it to be inline."""
    if self.src is None:
      return
    self.inline = '''
          var script = document.createElement('script');
          script.src = "%s";
          document.body.appendChild(script);
''' % self.src
    self.src = None

  def replacement(self):
    """Returns the script tag to replace the {{{ SCRIPT }}} tag in the target"""
    assert (self.src or self.inline) and not (self.src and self.inline)
    if self.src:
      return '<script async type="text/javascript" src="%s"></script>' % quote(self.src)
    else:
      return '<script>\n%s\n</script>' % self.inline


class JSOptimizer(object):
  def __init__(self, target, options, js_transform_tempfiles, in_temp):
    self.queue = []
    self.extra_info = {}
    self.queue_history = []
    self.blacklist = os.environ.get('EMCC_JSOPT_BLACKLIST', '').split(',')
    self.minify_whitespace = False
    self.cleanup_shell = False

    self.target = target
    self.opt_level = options.opt_level
    self.debug_level = options.debug_level
    self.emit_symbol_map = options.emit_symbol_map
    self.profiling_funcs = options.profiling_funcs
    self.use_closure_compiler = options.use_closure_compiler
    self.closure_args = options.closure_args

    self.js_transform_tempfiles = js_transform_tempfiles
    self.in_temp = in_temp

  def flush(self, title='js_opts'):
    self.queue = [p for p in self.queue if p not in self.blacklist]

    assert not shared.Settings.WASM_BACKEND, 'JSOptimizer should not run with pure wasm output'

    if self.extra_info is not None and len(self.extra_info) == 0:
      self.extra_info = None

    if len(self.queue) and not(not shared.Settings.ASM_JS and len(self.queue) == 1 and self.queue[0] == 'last'):
      passes = self.queue[:]

      if DEBUG != 2 or len(passes) < 2:
        # by assumption, our input is JS, and our output is JS. If a pass is going to run in the native optimizer in C++, then we
        # must give it JSON and receive from it JSON
        chunks = []
        curr = []
        for p in passes:
          if len(curr) == 0:
            curr.append(p)
          else:
            native = js_optimizer.use_native(p, source_map=use_source_map(self))
            last_native = js_optimizer.use_native(curr[-1], source_map=use_source_map(self))
            if native == last_native:
              curr.append(p)
            else:
              curr.append('emitJSON')
              chunks.append(curr)
              curr = ['receiveJSON', p]
        if len(curr):
          chunks.append(curr)
        if len(chunks) == 1:
          self.run_passes(chunks[0], title, just_split=False, just_concat=False)
        else:
          for i, chunk in enumerate(chunks):
            self.run_passes(chunk, 'js_opts_' + str(i),
                            just_split='receiveJSON' in chunk,
                            just_concat='emitJSON' in chunk)
      else:
        # DEBUG 2, run each pass separately
        extra_info = self.extra_info
        for p in passes:
          self.queue = [p]
          self.flush(p)
          self.extra_info = extra_info # flush wipes it
          log_time('part of js opts')
      self.queue_history += self.queue
      self.queue = []
    self.extra_info = {}

  def run_passes(self, passes, title, just_split, just_concat):
    global final
    passes = ['asm'] + passes
    if shared.Settings.PRECISE_F32:
      passes = ['asmPreciseF32'] + passes
    if (self.emit_symbol_map or shared.Settings.CYBERDWARF) and 'minifyNames' in passes:
      passes += ['symbolMap=' + self.target + '.symbols']
    if self.profiling_funcs and 'minifyNames' in passes:
      passes += ['profilingFuncs']
    if self.minify_whitespace and 'last' in passes:
      passes += ['minifyWhitespace']
    if self.cleanup_shell and 'last' in passes:
      passes += ['cleanup']
    logger.debug('applying js optimization passes: %s', ' '.join(passes))
    final = shared.Building.js_optimizer(final, passes, use_source_map(self),
                                         self.extra_info, just_split=just_split,
                                         just_concat=just_concat,
                                         output_filename=self.in_temp(os.path.basename(final) + '.jsopted.js'),
                                         extra_closure_args=self.closure_args)
    self.js_transform_tempfiles.append(final)
    save_intermediate(title, suffix='js' if 'emitJSON' not in passes else 'json')

  def do_minify(self):
    """minifies the code.

    this is also when we do certain optimizations that must be done right before or after minification
    """
    if self.opt_level >= 2:
      if self.debug_level < 2 and not self.use_closure_compiler == 2:
        self.queue += ['minifyNames']
      if self.debug_level == 0:
        self.minify_whitespace = True

    if self.use_closure_compiler == 1:
      self.queue += ['closure']
    elif self.debug_level <= 2 and shared.Settings.FINALIZE_ASM_JS and not self.use_closure_compiler:
      self.cleanup_shell = True


def link(options, input_files, target):
  global final

  def in_temp(name):
    return os.path.join(temp_dir, os.path.basename(name))

  def optimizing(opts):
    return '-O0' not in opts

  def suffix(name):
    """Return the file extension"""
    return os.path.splitext(name)[1]

  misc_temp_files = shared.configuration.get_temp_files()
  temp_dir = shared.get_emscripten_temp_dir()
  final_suffix = suffix(target)
  shared.Settings.TARGET_BASENAME = target_basename = unsuffixed_basename(target)

  if options.verbose:
    shared.VERBOSE = True

  options.post_js = [open(f).read() + '\n' for f in options.post_js]
  options.pre_js = [open(f).read() + '\n' for f in options.pre_js]

  # MINIMAL_RUNTIME always use separate .asm.js file for best performance and memory usage
  if shared.Settings.MINIMAL_RUNTIME and not shared.Settings.WASM:
    options.separate_asm = True

  if final_suffix == '.html' and not options.separate_asm and 'PRECISE_F32=2' in options.settings:
    options.separate_asm = True
    logger.warning('forcing separate asm output (--separate-asm), because -s PRECISE_F32=2 was passed.')

  if options.opt_level:
    if options.opt_level == 's':
      options.llvm_opts = ['-Os']
      options.opt_level = 2
      options.shrink_level = 1
      options.settings.append('INLINING_LIMIT=50')
    elif options.opt_level == 'z':
      options.llvm_opts = ['-Oz']
      options.opt_level = 2
      options.shrink_level = 2
      options.settings.append('INLINING_LIMIT=25')
  else:
    options.shrink_level = 1

  if options.shrink_level >= 2:
    shared.Settings.EVAL_CTORS = True

  with ToolchainProfiler.profile_block('parse arguments and setup'):
    ## Parse args

    if options.output_eol:
      if options.output_eol.lower() == 'windows':
        options.output_eol = '\r\n'
      elif options.output_eol.lower() == 'linux':
        options.output_eol = '\n'
      else:
        exit_with_error('Invalid value "' + options.output_eol + '" to --output_eol!')
    else:
      # Specifies the line ending format to use for all generated text files.
      # Defaults to using the native EOL on each platform (\r\n on Windows, \n on
      # Linux & MacOS)
      options.output_eol = os.linesep

    expanded_closure_args = [shlex.split(a) for a in options.closure_args]
    options.closure_args = []
    for l in expanded_closure_args:
      options.closure_args += l

    if options.emit_symbol_map:
      shared.Settings.EMIT_SYMBOL_MAP = 1

    if options.cpu_profiler:
      options.post_js += open(shared.path_from_root('src', 'cpuprofiler.js')).read() + '\n'

    if options.threadprofiler:
      options.post_js += open(shared.path_from_root('src', 'threadprofiler.js')).read() + '\n'
      options.settings.append('PTHREADS_PROFILING=1')

    # target is now finalized, can finalize other _target s
    if final_suffix == '.mjs':
      shared.Settings.EXPORT_ES6 = 1
      shared.Settings.MODULARIZE = 1
      js_target = target
    else:
      js_target = unsuffixed(target) + '.js'

    asm_target = unsuffixed(js_target) + '.asm.js' # might not be used, but if it is, this is the name
    wasm_text_target = asm_target.replace('.asm.js', '.wast') # ditto, might not be used
    wasm_binary_target = asm_target.replace('.asm.js', '.wasm') # ditto, might not be used
    wasm_source_map_target = wasm_binary_target + '.map'

    if shared.Settings.STRICT:
      shared.Settings.ERROR_ON_MISSING_LIBRARIES = 1

    if AUTODEBUG:
      shared.Settings.AUTODEBUG = 1

    if shared.Settings.MODULARIZE:
      assert not options.proxy_to_worker, '-s MODULARIZE=1 and -s MODULARIZE_INSTANCE=1 are not compatible with --proxy-to-worker (if you want to run in a worker with -s MODULARIZE=1, you likely want to do the worker side setup manually)'
      # MODULARIZE's .then() method uses onRuntimeInitialized currently, so make sure
      # it is expected to be used.
      shared.Settings.INCOMING_MODULE_JS_API += ['onRuntimeInitialized']

    if shared.Settings.SIDE_MODULE and shared.Settings.GLOBAL_BASE != -1:
      exit_with_error('Cannot set GLOBAL_BASE when building SIDE_MODULE')

    if options.proxy_to_worker:
      shared.Settings.PROXY_TO_WORKER = 1

    if options.debug_level > 1 and options.use_closure_compiler:
      logger.warning('disabling closure because debug info was requested')
      options.use_closure_compiler = False

    assert not (shared.Settings.EMTERPRETIFY_FILE and shared.Settings.SINGLE_FILE), 'cannot have both EMTERPRETIFY_FILE and SINGLE_FILE enabled at the same time'

    assert not (not shared.Settings.DYNAMIC_EXECUTION and options.use_closure_compiler), 'cannot have both NO_DYNAMIC_EXECUTION and closure compiler enabled at the same time'

    if shared.Settings.MAIN_MODULE:
      assert not shared.Settings.SIDE_MODULE
      if shared.Settings.MAIN_MODULE != 2:
        shared.Settings.INCLUDE_FULL_LIBRARY = 1
    elif shared.Settings.SIDE_MODULE:
      assert not shared.Settings.MAIN_MODULE
      options.memory_init_file = False # memory init file is not supported with asm.js side modules, must be executable synchronously (for dlopen)

    if shared.Settings.MAIN_MODULE or shared.Settings.SIDE_MODULE:
      assert shared.Settings.ASM_JS, 'module linking requires asm.js output (-s ASM_JS=1)'
      if shared.Settings.MAIN_MODULE != 2 and shared.Settings.SIDE_MODULE != 2:
        shared.Settings.LINKABLE = 1
      shared.Settings.RELOCATABLE = 1
      assert not options.use_closure_compiler, 'cannot use closure compiler on shared modules'
      # shared modules need memory utilities to allocate their memory
      shared.Settings.EXPORTED_RUNTIME_METHODS += [
        'allocate',
        'getMemory',
      ]

    if shared.Settings.RELOCATABLE:
      shared.Settings.ALLOW_TABLE_GROWTH = 1

    # Reconfigure the cache now that settings have been applied. Some settings
    # such as WASM_OBJECT_FILES and SIDE_MODULE/MAIN_MODULE effect which cache
    # directory we use.
    shared.reconfigure_cache()

    if shared.Settings.USE_PTHREADS:
      # These runtime methods are called from worker.js
      shared.Settings.EXPORTED_RUNTIME_METHODS += ['establishStackSpace', 'dynCall_ii']

    if shared.Settings.MODULARIZE_INSTANCE:
      shared.Settings.MODULARIZE = 1

    if shared.Settings.FORCE_FILESYSTEM and not shared.Settings.MINIMAL_RUNTIME:
      # when the filesystem is forced, we export by default methods that filesystem usage
      # may need, including filesystem usage from standalone file packager output (i.e.
      # file packages not built together with emcc, but that are loaded at runtime
      # separately, and they need emcc's output to contain the support they need)
      if not shared.Settings.ASMFS:
        shared.Settings.EXPORTED_RUNTIME_METHODS += [
          'FS_createFolder',
          'FS_createPath',
          'FS_createDataFile',
          'FS_createPreloadedFile',
          'FS_createLazyFile',
          'FS_createLink',
          'FS_createDevice',
          'FS_unlink'
        ]

      shared.Settings.EXPORTED_RUNTIME_METHODS += [
        'getMemory',
        'addRunDependency',
        'removeRunDependency',
        'calledRun',
      ]

    if shared.Settings.USE_PTHREADS:
      # To ensure allocated thread stacks are aligned:
      shared.Settings.EXPORTED_FUNCTIONS += ['_memalign']

      if shared.Settings.MODULARIZE:
        # MODULARIZE+USE_PTHREADS mode requires extra exports out to Module so that worker.js
        # can access them:

        # general threading variables:
        shared.Settings.EXPORTED_RUNTIME_METHODS += ['PThread', 'ExitStatus']

        # pthread stack setup:
        shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE += ['$establishStackSpaceInJsModule']
        shared.Settings.EXPORTED_FUNCTIONS += ['establishStackSpaceInJsModule']

        # stack check:
        if shared.Settings.STACK_OVERFLOW_CHECK:
          shared.Settings.EXPORTED_RUNTIME_METHODS += ['writeStackCookie', 'checkStackCookie']

      if shared.Settings.LINKABLE:
        exit_with_error('-s LINKABLE=1 is not supported with -s USE_PTHREADS>0!')
      if shared.Settings.SIDE_MODULE:
        exit_with_error('-s SIDE_MODULE=1 is not supported with -s USE_PTHREADS>0!')
      if shared.Settings.MAIN_MODULE:
        exit_with_error('-s MAIN_MODULE=1 is not supported with -s USE_PTHREADS>0!')
      if shared.Settings.EMTERPRETIFY:
        exit_with_error('-s EMTERPRETIFY=1 is not supported with -s USE_PTHREADS>0!')
      if shared.Settings.PROXY_TO_WORKER:
        exit_with_error('--proxy-to-worker is not supported with -s USE_PTHREADS>0! Use the option -s PROXY_TO_PTHREAD=1 if you want to run the main thread of a multithreaded application in a web worker.')
    else:
      if shared.Settings.PROXY_TO_PTHREAD:
        exit_with_error('-s PROXY_TO_PTHREAD=1 requires -s USE_PTHREADS to work!')

    if options.use_preload_plugins or len(options.preload_files) or len(options.embed_files):
      if shared.Settings.NODERAWFS:
        exit_with_error('--preload-file and --embed-file cannot be used with NODERAWFS which disables virtual filesystem')
      # if we include any files, or intend to use preload plugins, then we
      # definitely need filesystem support
      shared.Settings.FORCE_FILESYSTEM = 1

    if shared.Settings.GLOBAL_BASE == -1:
      # default if nothing else sets it
      if shared.Settings.WASM:
        # a higher global base is useful for optimizing load/store offsets, as it
        # enables the --post-emscripten pass
        shared.Settings.GLOBAL_BASE = 1024
      else:
        shared.Settings.GLOBAL_BASE = 8

    if shared.Settings.EXPORT_ES6 and not shared.Settings.MODULARIZE:
      exit_with_error('EXPORT_ES6 requires MODULARIZE to be set')

    # When MODULARIZE option is used, currently declare all module exports
    # individually - TODO: this could be optimized
    if shared.Settings.MODULARIZE and not shared.Settings.DECLARE_ASM_MODULE_EXPORTS:
      shared.Settings.DECLARE_ASM_MODULE_EXPORTS = 1
      logger.warning('Enabling -s DECLARE_ASM_MODULE_EXPORTS=1, since MODULARIZE currently requires declaring asm.js/wasm module exports in full')

    # In MINIMAL_RUNTIME when modularizing, by default output asm.js module
    # under the same name as the JS module. This allows code to share same
    # loading function for both JS and asm.js modules,
    # to save code size. The intent is that loader code captures the function
    # variable from global scope to XHR loader local scope when it finishes
    # loading, to avoid polluting global JS scope with
    # variables. This provides safety via encapsulation. See
    # src/shell_minimal_runtime.html for an example.
    if shared.Settings.MINIMAL_RUNTIME and not shared.Settings.SEPARATE_ASM_MODULE_NAME and not shared.Settings.WASM and shared.Settings.MODULARIZE:
      shared.Settings.SEPARATE_ASM_MODULE_NAME = 'var ' + shared.Settings.EXPORT_NAME

    if shared.Settings.MODULARIZE and shared.Settings.SEPARATE_ASM and not shared.Settings.WASM and not shared.Settings.SEPARATE_ASM_MODULE_NAME:
      exit_with_error('Targeting asm.js with --separate-asm and -s MODULARIZE=1 requires specifying the target variable name to which the asm.js module is loaded into. See https://github.com/emscripten-core/emscripten/pull/7949 for details')
    # Apply default option if no custom name is provided
    if not shared.Settings.SEPARATE_ASM_MODULE_NAME:
      shared.Settings.SEPARATE_ASM_MODULE_NAME = 'Module["asm"]'
    elif shared.Settings.WASM:
      exit_with_error('-s SEPARATE_ASM_MODULE_NAME option only applies to when targeting asm.js, not with WebAssembly!')

    if options.emrun:
      assert not shared.Settings.MINIMAL_RUNTIME, '--emrun is not compatible with -s MINIMAL_RUNTIME=1'
      shared.Settings.EXPORTED_RUNTIME_METHODS.append('addOnExit')

    if options.use_closure_compiler:
      shared.Settings.USE_CLOSURE_COMPILER = options.use_closure_compiler
      if not shared.check_closure_compiler():
        exit_with_error('fatal: closure compiler is not configured correctly')
      if options.use_closure_compiler == 2 and shared.Settings.ASM_JS == 1:
        shared.WarningManager.warn('ALMOST_ASM', 'not all asm.js optimizations are possible with --closure 2, disabling those - your code will be run more slowly')
        shared.Settings.ASM_JS = 2

    if options.emrun:
      options.pre_js += open(shared.path_from_root('src', 'emrun_prejs.js')).read() + '\n'
      options.post_js += open(shared.path_from_root('src', 'emrun_postjs.js')).read() + '\n'
      # emrun mode waits on program exit
      shared.Settings.EXIT_RUNTIME = 1

    if shared.Settings.MINIMAL_RUNTIME:
      # Minimal runtime uses a different default shell file
      if options.shell_path == shared.path_from_root('src', 'shell.html'):
        options.shell_path = shared.path_from_root('src', 'shell_minimal_runtime.html')

      # Remove the default exported functions 'memcpy', 'memset', 'malloc', 'free', etc. - those should only be linked in if used
      shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE = []

      if shared.Settings.ASSERTIONS and shared.Settings.MINIMAL_RUNTIME:
        # In ASSERTIONS-builds, functions UTF8ArrayToString() and stringToUTF8Array() (which are not JS library functions), both
        # use warnOnce(), which in MINIMAL_RUNTIME is a JS library function, so explicitly have to mark dependency to warnOnce()
        # in that case. If string functions are turned to library functions in the future, then JS dependency tracking can be
        # used and this special directive can be dropped.
        shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE += ['$warnOnce']

      # Always use the new HTML5 API event target lookup rules
      shared.Settings.DISABLE_DEPRECATED_FIND_EVENT_TARGET_BEHAVIOR = 1

      # In asm.js always use memory init file to get the best code size, other modes are not currently supported.
      if not shared.Settings.WASM:
        options.memory_init_file = True

    if shared.Settings.MODULARIZE and not shared.Settings.MODULARIZE_INSTANCE and shared.Settings.EXPORT_NAME == 'Module' and final_suffix == '.html' and \
       (options.shell_path == shared.path_from_root('src', 'shell.html') or options.shell_path == shared.path_from_root('src', 'shell_minimal.html')):
      exit_with_error('Due to collision in variable name "Module", the shell file "' + options.shell_path + '" is not compatible with build options "-s MODULARIZE=1 -s EXPORT_NAME=Module". Either provide your own shell file, change the name of the export to something else to avoid the name collision. (see https://github.com/emscripten-core/emscripten/issues/7950 for details)')

    if options.tracing and shared.Settings.ALLOW_MEMORY_GROWTH:
      shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE += ['emscripten_trace_report_memory_layout']

    if options.separate_asm and final_suffix != '.html':
      shared.WarningManager.warn('SEPARATE_ASM')

    if shared.Settings.ONLY_MY_CODE:
      shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE = []
      options.separate_asm = True
      shared.Settings.FINALIZE_ASM_JS = False

    if shared.Settings.WASM:
      if options.separate_asm:
        exit_with_error('cannot --separate-asm when emitting wasm, since not emitting asm.js')

      if not shared.Building.need_asm_js_file():
        asm_target = asm_target.replace('.asm.js', '.temp.asm.js')
        misc_temp_files.note(asm_target)

      if shared.Settings.WASM_BACKEND:
        options.js_opts = None

        # wasm backend output can benefit from the binaryen optimizer (in asm2wasm,
        # we run the optimizer during asm2wasm itself). use it, if not overridden.

        # BINARYEN_PASSES and BINARYEN_EXTRA_PASSES are comma-separated, and we support both '-'-prefixed and unprefixed pass names
        def parse_passes(string):
          passes = string.split(',')
          passes = [('--' + p) if p[0] != '-' else p for p in passes if p]
          return passes

        passes = []
        if 'BINARYEN_PASSES' in options.settings:
          if shared.Settings.BINARYEN_PASSES:
            passes += parse_passes(shared.Settings.BINARYEN_PASSES)
        else:
          if not shared.Settings.EXIT_RUNTIME:
            passes += ['--no-exit-runtime']
          if options.opt_level > 0 or options.shrink_level > 0:
            passes += [shared.Building.opt_level_to_str(options.opt_level, options.shrink_level)]
          passes += ['--post-emscripten']
          if shared.Settings.GLOBAL_BASE >= 1024: # hardcoded value in the binaryen pass
            passes += ['--low-memory-unused']
          if options.debug_level < 3:
            passes += ['--strip-debug']
          if not shared.Settings.EMIT_PRODUCERS_SECTION:
            passes += ['--strip-producers']
          if shared.Settings.AUTODEBUG and shared.Settings.WASM_OBJECT_FILES:
            # adding '--flatten' here may make these even more effective
            passes += ['--instrument-locals']
            passes += ['--log-execution']
            passes += ['--instrument-memory']
            passes += ['--legalize-js-interface']
          if shared.Settings.ASYNCIFY:
            # TODO: allow whitelist as in asyncify
            passes += ['--asyncify']
            if shared.Settings.ASYNCIFY_IGNORE_INDIRECT:
              passes += ['--pass-arg=asyncify-ignore-indirect']
            else:
              # if we are not ignoring indirect calls, then we must treat invoke_* as if
              # they are indirect calls, since that is what they do - we can't see their
              # targets statically.
              shared.Settings.ASYNCIFY_IMPORTS += ['invoke_*']
            # with pthreads we may call main through the __call_main mechanism, which can
            # therefore reach anything in the program, so mark it as possibly causing a
            # sleep (the asyncify analysis doesn't look through JS, just wasm, so it can't
            # see what it itself calls)
            if shared.Settings.USE_PTHREADS:
              shared.Settings.ASYNCIFY_IMPORTS += ['__call_main']
            if shared.Settings.ASYNCIFY_IMPORTS:
              passes += ['--pass-arg=asyncify-imports@%s' % ','.join(['env.' + i for i in shared.Settings.ASYNCIFY_IMPORTS])]

            # shell escaping can be confusing; try to emit useful warnings
            def check_human_readable_list(items):
              for item in items:
                if item.count('(') != item.count(')'):
                  logger.warning('''emcc: ASYNCIFY list contains an item without balanced parentheses ("(", ")"):''')
                  logger.warning('''   ''' + item)
                  logger.warning('''This may indicate improper escaping that led to splitting inside your names.''')
                  logger.warning('''Try to quote the entire argument, like this: -s 'ASYNCIFY_WHITELIST=["foo(int, char)", "bar"]' ''')
                  break

            if shared.Settings.ASYNCIFY_BLACKLIST:
              check_human_readable_list(shared.Settings.ASYNCIFY_BLACKLIST)
              passes += ['--pass-arg=asyncify-blacklist@%s' % ','.join(shared.Settings.ASYNCIFY_BLACKLIST)]
            if shared.Settings.ASYNCIFY_WHITELIST:
              check_human_readable_list(shared.Settings.ASYNCIFY_WHITELIST)
              passes += ['--pass-arg=asyncify-whitelist@%s' % ','.join(shared.Settings.ASYNCIFY_WHITELIST)]
          if shared.Settings.BINARYEN_IGNORE_IMPLICIT_TRAPS:
            passes += ['--ignore-implicit-traps']
        if shared.Settings.BINARYEN_EXTRA_PASSES:
          passes += parse_passes(shared.Settings.BINARYEN_EXTRA_PASSES)
        options.binaryen_passes = passes

        # to bootstrap struct_info, we need binaryen
        os.environ['EMCC_WASM_BACKEND_BINARYEN'] = '1'

      # run safe-heap as a binaryen pass
      if shared.Settings.SAFE_HEAP and shared.Building.is_wasm_only():
        options.binaryen_passes += ['--safe-heap']
      if shared.Settings.EMULATE_FUNCTION_POINTER_CASTS:
        # emulated function pointer casts is emulated in wasm using a binaryen pass
        options.binaryen_passes += ['--fpcast-emu']
        if not shared.Settings.WASM_BACKEND:
          # we also need emulated function pointers for that, as we need a single flat
          # table, as is standard in wasm, and not asm.js split ones.
          shared.Settings.EMULATED_FUNCTION_POINTERS = 1

    if options.separate_asm:
      shared.Settings.SEPARATE_ASM = shared.JS.get_subresource_location(asm_target)

    # wasm outputs are only possible with a side wasm
    if target.endswith(WASM_ENDINGS):
      shared.Settings.EMITTING_JS = 0
      js_target = misc_temp_files.get(suffix='.js').name

    if shared.Settings.WASM:
      if shared.Settings.SINGLE_FILE:
        # placeholder strings for JS glue, to be replaced with subresource locations in do_binaryen
        shared.Settings.WASM_TEXT_FILE = shared.FilenameReplacementStrings.WASM_TEXT_FILE
        shared.Settings.WASM_BINARY_FILE = shared.FilenameReplacementStrings.WASM_BINARY_FILE
        shared.Settings.ASMJS_CODE_FILE = shared.FilenameReplacementStrings.ASMJS_CODE_FILE
      else:
        # set file locations, so that JS glue can find what it needs
        shared.Settings.WASM_TEXT_FILE = shared.JS.escape_for_js_string(os.path.basename(wasm_text_target))
        shared.Settings.WASM_BINARY_FILE = shared.JS.escape_for_js_string(os.path.basename(wasm_binary_target))
        shared.Settings.ASMJS_CODE_FILE = shared.JS.escape_for_js_string(os.path.basename(asm_target))

    if shared.Settings.WASM:
      shared.Settings.ASM_JS = 2 # when targeting wasm, we use a wasm Memory, but that is not compatible with asm.js opts
      if shared.Settings.ELIMINATE_DUPLICATE_FUNCTIONS:
        logger.warning('for wasm there is no need to set ELIMINATE_DUPLICATE_FUNCTIONS, the binaryen optimizer does it automatically')
        shared.Settings.ELIMINATE_DUPLICATE_FUNCTIONS = 0
      # default precise-f32 to on, since it works well in wasm
      shared.Settings.PRECISE_F32 = 1
      if options.js_opts and not options.force_js_opts:
        options.js_opts = None
        logger.debug('asm.js opts not forced by user or an option that depends them, and we do not intend to run the asm.js, so disabling and leaving opts to the binaryen optimizer')
      if options.use_closure_compiler == 2 and not shared.Settings.WASM2JS:
        exit_with_error('closure compiler mode 2 assumes the code is asm.js, so not meaningful for wasm')
      if any(s.startswith('MEM_INIT_METHOD=') for s in options.settings):
        exit_with_error('MEM_INIT_METHOD is not supported in wasm. Memory will be embedded in the wasm binary if threads are not used, and included in a separate file if threads are used.')
      if shared.Settings.WASM2JS:
        # wasm2js does not support passive segments or atomics
        if shared.Settings.USE_PTHREADS:
          exit_with_error('WASM2JS does not yet support pthreads')
        # in wasm2js, keep the mem init in the wasm itself if we can and if the
        # options wouldn't tell a js build to use a separate mem init file
        shared.Settings.MEM_INIT_IN_WASM = not options.memory_init_file
      else:
        # wasm includes the mem init in the wasm binary. The exception is
        # wasm2js, which behaves more like js.
        options.memory_init_file = True
        shared.Settings.MEM_INIT_IN_WASM = True if shared.Settings.WASM_BACKEND else not shared.Settings.USE_PTHREADS

      # WASM_ASYNC_COMPILATION and SWAPPABLE_ASM_MODULE do not have a meaning in MINIMAL_RUNTIME (always async)
      if not shared.Settings.MINIMAL_RUNTIME:
        if shared.Settings.WASM_ASYNC_COMPILATION == 1:
          # async compilation requires a swappable module - we swap it in when it's ready
          shared.Settings.SWAPPABLE_ASM_MODULE = 1
        else:
          # if not wasm-only, we can't do async compilation as the build can run in other
          # modes than wasm (like asm.js) which may not support an async step
          shared.Settings.WASM_ASYNC_COMPILATION = 0
          warning = 'This will reduce performance and compatibility (some browsers limit synchronous compilation), see http://kripken.github.io/emscripten-site/docs/compiling/WebAssembly.html#codegen-effects'
          if 'WASM_ASYNC_COMPILATION=1' in options.settings:
            logger.warning('WASM_ASYNC_COMPILATION requested, but disabled because of user options. ' + warning)
          elif 'WASM_ASYNC_COMPILATION=0' not in options.settings:
            logger.warning('WASM_ASYNC_COMPILATION disabled due to user options. ' + warning)

      if not shared.Settings.DECLARE_ASM_MODULE_EXPORTS:
        # Swappable wasm module/asynchronous wasm compilation requires an indirect stub
        # function generated to each function export from wasm module, so cannot use the
        # concise form of grabbing exports that does not need to refer to each export individually.
        if shared.Settings.SWAPPABLE_ASM_MODULE == 1:
          shared.Settings.DECLARE_ASM_MODULE_EXPORTS = 1
          logger.warning('Enabling -s DECLARE_ASM_MODULE_EXPORTS=1 since -s SWAPPABLE_ASM_MODULE=1 is used')

      # wasm side modules have suffix .wasm
      if shared.Settings.SIDE_MODULE and target.endswith('.js'):
        logger.warning('output suffix .js requested, but wasm side modules are just wasm files; emitting only a .wasm, no .js')

    # TODO: support source maps with js_transform
    if options.js_transform and use_source_map(options):
      logger.warning('disabling source maps because a js transform is being done')
      options.debug_level = 3

    shared.Settings.PROFILING_FUNCS = options.profiling_funcs
    shared.Settings.SOURCE_MAP_BASE = options.source_map_base or ''

  # exit block 'parse arguments and setup'
  log_time('parse arguments and setup')

  def dedup_list(lst):
    rtn = []
    for item in lst:
      if item not in rtn:
        rtn.append(item)
    return rtn

  # Make a final pass over shared.Settings.EXPORTED_FUNCTIONS to remove any
  # duplication between functions added by the driver/libraries and function
  # specified by the user
  shared.Settings.EXPORTED_FUNCTIONS = dedup_list(shared.Settings.EXPORTED_FUNCTIONS)

  with ToolchainProfiler.profile_block('link'):
    # final will be an array if linking is deferred, otherwise a normal string.
    if shared.Settings.WASM_BACKEND:
      DEFAULT_FINAL = in_temp(target_basename + '.wasm')
    else:
      DEFAULT_FINAL = in_temp(target_basename + '.bc')

    def get_final():
      global final
      if isinstance(final, list):
        final = DEFAULT_FINAL
      return final

    # First, combine the bitcode files if there are several. We must also link if we have a singleton .a
    perform_link = len(input_files) > 1 or shared.Settings.WASM_BACKEND
    if not perform_link and not LEAVE_INPUTS_RAW:
      is_bc = suffix(input_files[0]) in BITCODE_ENDINGS
      is_dylib = suffix(input_files[0]) in DYNAMICLIB_ENDINGS
      is_ar = shared.Building.is_ar(input_files[0])
      perform_link = not (is_bc or is_dylib) and is_ar
    if perform_link:
      logger.debug('linking: ' + str(input_files))
      # force archive contents to all be included, if just archives, or if linking shared modules
      force_archive_contents = all(t.endswith(STATICLIB_ENDINGS) for t in input_files) or shared.Settings.LINKABLE

      # if  EMCC_DEBUG=2  then we must link now, so the temp files are complete.
      # if using the wasm backend, we might be using vanilla LLVM, which does not allow our fastcomp deferred linking opts.
      # TODO: we could check if this is a fastcomp build, and still speed things up here
      just_calculate = DEBUG != 2 and not shared.Settings.WASM_BACKEND
      if shared.Settings.WASM_BACKEND:
        # If LTO is enabled then use the -O opt level as the LTO level
        if options.llvm_lto:
          lto_level = options.opt_level
        else:
          lto_level = 0
        final = shared.Building.link_lld(input_files, DEFAULT_FINAL, lto_level=lto_level)
      else:
        final = shared.Building.link(input_files, DEFAULT_FINAL, force_archive_contents=force_archive_contents, just_calculate=just_calculate)
    else:
      logger.debug('skipping linking: ' + str(input_files))
      assert len(input_files) == 1
      input_file = input_files[0]
      if not LEAVE_INPUTS_RAW:
        final = in_temp(target_basename + '.bc')
        shutil.copyfile(input_file, final)
      else:
        final = in_temp(input_file)
        shutil.copyfile(input_file, final)

  # exit block 'link'
  log_time('link')

  if not shared.Settings.WASM_BACKEND:
    with ToolchainProfiler.profile_block('post-link'):
      if DEBUG:
        logger.debug('saving intermediate processing steps to %s', shared.get_emscripten_temp_dir())
        if not LEAVE_INPUTS_RAW:
          save_intermediate('basebc', 'bc')

      # Optimize, if asked to
      if not LEAVE_INPUTS_RAW:
        # remove LLVM debug if we are not asked for it
        link_opts = [] if use_source_map(options) or shared.Settings.CYBERDWARF else ['-strip-debug']
        if not shared.Settings.ASSERTIONS:
          link_opts += ['-disable-verify']
        else:
          # when verifying, LLVM debug info has some tricky linking aspects, and llvm-link will
          # disable the type map in that case. we added linking to opt, so we need to do
          # something similar, which we can do with a param to opt
          link_opts += ['-disable-debug-info-type-map']

        if options.llvm_lto is not None and options.llvm_lto >= 2 and optimizing(options.llvm_opts):
          logger.debug('running LLVM opts as pre-LTO')
          final = shared.Building.llvm_opt(final, options.llvm_opts, DEFAULT_FINAL)
          save_intermediate('opt', 'bc')

        # If we can LTO, do it before dce, since it opens up dce opportunities
        if (not shared.Settings.LINKABLE) and options.llvm_lto and options.llvm_lto != 2:
          if not shared.Building.can_inline():
            link_opts.append('-disable-inlining')
          # add a manual internalize with the proper things we need to be kept alive during lto
          link_opts += shared.Building.get_safe_internalize() + ['-std-link-opts']
          # execute it now, so it is done entirely before we get to the stage of legalization etc.
          final = shared.Building.llvm_opt(final, link_opts, DEFAULT_FINAL)
          save_intermediate('lto', 'bc')
          link_opts = []
        else:
          # At minimum remove dead functions etc., this potentially saves a
          # lot in the size of the generated code (and the time to compile it)
          link_opts += shared.Building.get_safe_internalize() + ['-globaldce']

        if options.cfi:
          link_opts.append("-wholeprogramdevirt")
          link_opts.append("-lowertypetests")

        if AUTODEBUG:
          # let llvm opt directly emit ll, to skip writing and reading all the bitcode
          link_opts += ['-S']
          final = shared.Building.llvm_opt(final, link_opts, get_final() + '.link.ll')
          save_intermediate('linktime', 'll')
        else:
          if len(link_opts) > 0:
            final = shared.Building.llvm_opt(final, link_opts, DEFAULT_FINAL)
            save_intermediate('linktime', 'bc')
          if options.save_bc:
            shutil.copyfile(final, options.save_bc)

      # Prepare .ll for Emscripten
      if options.save_bc:
        save_intermediate('ll', 'll')

      if AUTODEBUG:
        logger.debug('autodebug')
        next = get_final() + '.ad.ll'
        run_process([shared.PYTHON, shared.AUTODEBUGGER, final, next])
        final = next
        save_intermediate('autodebug', 'll')

      assert not isinstance(final, list), 'we must have linked the final files, if linking was deferred, by this point'

    # exit block 'post-link'
    log_time('post-link')

  with ToolchainProfiler.profile_block('emscript'):
    # Emscripten
    logger.debug('LLVM => JS')
    js_libraries = [os.path.abspath(lib) for lib in options.js_libraries]
    if options.memory_init_file:
      shared.Settings.MEM_INIT_METHOD = 1
    else:
      assert shared.Settings.MEM_INIT_METHOD != 1

    if embed_memfile(options):
      shared.Settings.SUPPORT_BASE64_EMBEDDING = 1

    final = do_emscripten(final, target + '.mem', js_libraries)
    save_intermediate('original')

    if shared.Settings.WASM_BACKEND:
      # we also received wast and wasm at this stage
      temp_basename = unsuffixed(final)
      wasm_temp = temp_basename + '.wasm'
      shutil.move(wasm_temp, wasm_binary_target)
      if use_source_map(options):
        shutil.move(wasm_temp + '.map', wasm_source_map_target)

    if shared.Settings.CYBERDWARF:
      cd_target = final + '.cd'
      shutil.move(cd_target, target + '.cd')

  # exit block 'emscript'
  log_time('emscript (llvm => executable code)')

  with ToolchainProfiler.profile_block('source transforms'):
    # Embed and preload files
    if len(options.preload_files) or len(options.embed_files):

      # Also, MEMFS is not aware of heap resizing feature in wasm, so if MEMFS and memory growth are used together, force
      # no_heap_copy to be enabled.
      if shared.Settings.ALLOW_MEMORY_GROWTH and not options.no_heap_copy:
        logger.info('Enabling --no-heap-copy because -s ALLOW_MEMORY_GROWTH=1 is being used with file_packager.py (pass --no-heap-copy to suppress this notification)')
        options.no_heap_copy = True

      logger.debug('setting up files')
      file_args = ['--from-emcc', '--export-name=' + shared.Settings.EXPORT_NAME]
      if len(options.preload_files):
        file_args.append('--preload')
        file_args += options.preload_files
      if len(options.embed_files):
        file_args.append('--embed')
        file_args += options.embed_files
      if len(options.exclude_files):
        file_args.append('--exclude')
        file_args += options.exclude_files
      if options.use_preload_cache:
        file_args.append('--use-preload-cache')
      if options.no_heap_copy:
        file_args.append('--no-heap-copy')
      if shared.Settings.LZ4:
        file_args.append('--lz4')
      if options.use_preload_plugins:
        file_args.append('--use-preload-plugins')
      file_code = run_process([shared.PYTHON, shared.FILE_PACKAGER, unsuffixed(target) + '.data'] + file_args, stdout=subprocess.PIPE).stdout
      options.pre_js = file_code + options.pre_js

    # Apply pre and postjs files
    if options.pre_js or options.post_js:
      logger.debug('applying pre/postjses')
      src = open(final).read()
      final += '.pp.js'
      if shared.WINDOWS: # Avoid duplicating \r\n to \r\r\n when writing out.
        if options.pre_js:
          options.pre_js = options.pre_js.replace('\r\n', '\n')
        if options.post_js:
          options.post_js = options.post_js.replace('\r\n', '\n')
      with open(final, 'w') as f:
        # pre-js code goes right after the Module integration code (so it
        # can use Module), we have a marker for it
        f.write(src.replace('// {{PRE_JSES}}', options.pre_js))
        f.write(options.post_js)
      options.pre_js = src = options.post_js = None
      save_intermediate('pre-post')

    # Apply a source code transformation, if requested
    if options.js_transform:
      shutil.copyfile(final, final + '.tr.js')
      final += '.tr.js'
      posix = not shared.WINDOWS
      logger.debug('applying transform: %s', options.js_transform)
      shared.check_call(shared.Building.remove_quotes(shlex.split(options.js_transform, posix=posix) + [os.path.abspath(final)]))
      save_intermediate('transformed')

    js_transform_tempfiles = [final]

  # exit block 'source transforms'
  log_time('source transforms')

  with ToolchainProfiler.profile_block('memory initializer'):
    memfile = None
    if (not shared.Settings.WASM_BACKEND and (shared.Settings.MEM_INIT_METHOD > 0 or embed_memfile(options))) or \
       (shared.Settings.WASM_BACKEND and not shared.Settings.MEM_INIT_IN_WASM):
      if shared.Settings.MINIMAL_RUNTIME:
        # Independent of whether user is doing -o a.html or -o a.js, generate the mem init file as a.mem (and not as a.html.mem or a.js.mem)
        memfile = target.replace('.html', '.mem').replace('.js', '.mem')
      else:
        memfile = target + '.mem'

    if memfile:
      if shared.Settings.WASM_BACKEND:
        # For the wasm backend, we don't have any memory info in JS. All we need to do
        # is set the memory initializer url.
        src = open(final).read()
        src = src.replace('var memoryInitializer = null;', 'var memoryInitializer = "%s";' % os.path.basename(memfile))
        open(final + '.mem.js', 'w').write(src)
        final += '.mem.js'
      else:
        # Non-wasm backend path: Strip the memory initializer out of the asmjs file
        shared.try_delete(memfile)

        def repl(m):
          # handle chunking of the memory initializer
          s = m.group(1)
          if len(s) == 0:
            return '' # don't emit 0-size ones
          membytes = [int(x or '0') for x in s.split(',')]
          while membytes and membytes[-1] == 0:
            membytes.pop()
          if not membytes:
            return ''
          if shared.Settings.MEM_INIT_METHOD == 2:
            # memory initializer in a string literal
            return "memoryInitializer = '%s';" % shared.JS.generate_string_initializer(membytes)
          open(memfile, 'wb').write(bytearray(membytes))
          if DEBUG:
            # Copy into temp dir as well, so can be run there too
            shared.safe_copy(memfile, os.path.join(shared.get_emscripten_temp_dir(), os.path.basename(memfile)))
          if not shared.Settings.WASM or not shared.Settings.MEM_INIT_IN_WASM:
            return 'memoryInitializer = "%s";' % shared.JS.get_subresource_location(memfile, embed_memfile(options))
          else:
            return ''

        src = re.sub(shared.JS.memory_initializer_pattern, repl, open(final).read(), count=1)
        open(final + '.mem.js', 'w').write(src)
        final += '.mem.js'
        src = None
        js_transform_tempfiles[-1] = final # simple text substitution preserves comment line number mappings
        if os.path.exists(memfile):
          save_intermediate('meminit')
          logger.debug('wrote memory initialization to %s', memfile)
        else:
          logger.debug('did not see memory initialization')

    if shared.Settings.USE_PTHREADS:
      target_dir = os.path.dirname(os.path.abspath(target))
      worker_output = os.path.join(target_dir, shared.Settings.PTHREAD_WORKER_FILE)
      with open(worker_output, 'w') as f:
        f.write(shared.read_and_preprocess(shared.path_from_root('src', 'worker.js'), expand_macros=True))

    # Generate the fetch.js worker script for multithreaded emscripten_fetch() support if targeting pthreads.
    if shared.Settings.FETCH and shared.Settings.USE_PTHREADS:
      if shared.Settings.WASM_BACKEND:
        logger.warning('Bug/TODO: Blocking calls to the fetch API do not currently work under WASM backend (https://github.com/emscripten-core/emscripten/issues/7024)')
      else:
        shared.make_fetch_worker(final, shared.Settings.FETCH_WORKER_FILE)

  # exit block 'memory initializer'
  log_time('memory initializer')

  optimizer = JSOptimizer(
    target=target,
    options=options,
    js_transform_tempfiles=js_transform_tempfiles,
    in_temp=in_temp,
  )
  with ToolchainProfiler.profile_block('js opts'):
    # It is useful to run several js optimizer passes together, to save on unneeded unparsing/reparsing
    if shared.Settings.DEAD_FUNCTIONS:
      optimizer.queue += ['eliminateDeadFuncs']
      optimizer.extra_info['dead_functions'] = shared.Settings.DEAD_FUNCTIONS

    if options.opt_level >= 1 and options.js_opts:
      logger.debug('running js post-opts')

      if DEBUG == 2:
        # Clean up the syntax a bit
        optimizer.queue += ['noop']

      def get_eliminate():
        if shared.Settings.ALLOW_MEMORY_GROWTH:
          return 'eliminateMemSafe'
        else:
          return 'eliminate'

      if options.opt_level >= 2:
        optimizer.queue += [get_eliminate()]

        if shared.Settings.AGGRESSIVE_VARIABLE_ELIMINATION:
          # note that this happens before registerize/minification, which can obfuscate the name of 'label', which is tricky
          optimizer.queue += ['aggressiveVariableElimination']

        optimizer.queue += ['simplifyExpressions']

        if shared.Settings.EMTERPRETIFY:
          # emterpreter code will not run through a JS optimizing JIT, do more work ourselves
          optimizer.queue += ['localCSE']

    if options.proxy_to_worker or options.use_preload_plugins:
      shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE += ['$Browser']

    if not shared.Settings.MINIMAL_RUNTIME:
      # In non-MINIMAL_RUNTIME, the core runtime depends on these functions to be present. (In MINIMAL_RUNTIME, they are
      # no longer always bundled in)
      shared.Settings.DEFAULT_LIBRARY_FUNCS_TO_INCLUDE += ['$demangle', '$demangleAll', '$jsStackTrace', '$stackTrace']

    if shared.Settings.EMTERPRETIFY:
      # add explicit label setting, as we will run aggressiveVariableElimination late, *after* 'label' is no longer notable by name
      optimizer.queue += ['safeLabelSetting']

    if options.opt_level >= 1 and options.js_opts:
      if options.opt_level >= 2:
        # simplify ifs if it is ok to make the code somewhat unreadable,
        # with commaified code breaks late aggressive variable elimination)
        # do not do this with binaryen, as commaifying confuses binaryen call type detection (FIXME, in theory, but unimportant)
        debugging = options.debug_level == 0 or options.profiling
        if shared.Settings.SIMPLIFY_IFS and debugging and not shared.Settings.WASM:
          optimizer.queue += ['simplifyIfs']

        if shared.Settings.PRECISE_F32:
          optimizer.queue += ['optimizeFrounds']

    if options.js_opts:
      if shared.Settings.SAFE_HEAP and not shared.Building.is_wasm_only():
        optimizer.queue += ['safeHeap']

      if options.opt_level >= 2 and options.debug_level < 3:
        if options.opt_level >= 3 or options.shrink_level > 0:
          optimizer.queue += ['registerizeHarder']
        else:
          optimizer.queue += ['registerize']

      # NOTE: Important that this comes after registerize/registerizeHarder
      if shared.Settings.ELIMINATE_DUPLICATE_FUNCTIONS and options.opt_level >= 2:
        optimizer.flush()
        shared.Building.eliminate_duplicate_funcs(final)
        save_intermediate('dfe')

    if shared.Settings.EVAL_CTORS and options.memory_init_file and not use_source_map(options) and not shared.Settings.WASM:
      optimizer.flush()
      shared.Building.eval_ctors(final, memfile)
      save_intermediate('eval-ctors')

    if options.js_opts:
      # some compilation modes require us to minify later or not at all
      if not shared.Settings.EMTERPRETIFY and not shared.Settings.WASM:
        optimizer.do_minify()

      if options.opt_level >= 2:
        optimizer.queue += ['asmLastOpts']

      if shared.Settings.FINALIZE_ASM_JS:
        optimizer.queue += ['last']

      optimizer.flush()

    if options.use_closure_compiler == 2 and not shared.Settings.WASM_BACKEND:
      optimizer.flush()

      logger.debug('running closure')
      # no need to add this to js_transform_tempfiles, because closure and
      # debug_level > 0 are never simultaneously true
      final = shared.Building.closure_compiler(final, pretty=options.debug_level >= 1,
                                               extra_closure_args=options.closure_args)
      save_intermediate('closure')

  log_time('js opts')

  with ToolchainProfiler.profile_block('final emitting'):
    if shared.Settings.EMTERPRETIFY:
      emterpretify(js_target, optimizer, options)

    # Remove some trivial whitespace
    # TODO: do not run when compress has already been done on all parts of the code
    # src = open(final).read()
    # src = re.sub(r'\n+[ \n]*\n+', '\n', src)
    # open(final, 'w').write(src)

    # Bundle symbol data in with the cyberdwarf file
    if shared.Settings.CYBERDWARF:
      run_process([shared.PYTHON, shared.path_from_root('tools', 'emdebug_cd_merger.py'), target + '.cd', target + '.symbols'])

    if use_source_map(options) and not shared.Settings.WASM:
      emit_js_source_maps(target, optimizer.js_transform_tempfiles)

    # track files that will need native eols
    generated_text_files_with_native_eols = []

    if (options.separate_asm or shared.Settings.WASM) and not shared.Settings.WASM_BACKEND:
      separate_asm_js(final, asm_target)
      generated_text_files_with_native_eols += [asm_target]

    if shared.Settings.WASM:
      do_binaryen(target, asm_target, options, memfile, wasm_binary_target,
                  wasm_text_target, wasm_source_map_target, misc_temp_files,
                  optimizer)

    if shared.Settings.MODULARIZE:
      modularize()

    module_export_name_substitution()

    # Run a final regex pass to clean up items that were not possible to optimize by Closure, or unoptimalities that were left behind
    # by processing steps that occurred after Closure.
    if shared.Settings.MINIMAL_RUNTIME == 2 and shared.Settings.USE_CLOSURE_COMPILER and options.debug_level == 0:
      # Process .js runtime file
      shared.run_process([shared.PYTHON, shared.path_from_root('tools', 'hacky_postprocess_around_closure_limitations.py'), final])
      # Process .asm.js file
      if not shared.Settings.WASM:
        shared.run_process([shared.PYTHON, shared.path_from_root('tools', 'hacky_postprocess_around_closure_limitations.py'), asm_target])

    # The JS is now final. Move it to its final location
    shutil.move(final, js_target)

    generated_text_files_with_native_eols += [js_target]

    # If we were asked to also generate HTML, do that
    if final_suffix == '.html':
      generate_html(target, options, js_target, target_basename,
                    asm_target, wasm_binary_target,
                    memfile, optimizer)
    else:
      if options.proxy_to_worker:
        generate_worker_js(target, js_target, target_basename)

    if embed_memfile(options) and memfile:
      shared.try_delete(memfile)

    for f in generated_text_files_with_native_eols:
      tools.line_endings.convert_line_endings_in_file(f, os.linesep, options.output_eol)

  log_time('final emitting')
  return 0


def main(argv):
  parser = argparse.ArgumentParser(description='emscripten linker.')
  parser.add_argument('-o', dest='output', metavar='FILE', help='output file', required=True)
  parser.add_argument('-O', dest='opt_level', const=2, action='store_const')
  parser.add_argument('-O0', dest='opt_level', const=0, action='store_const')
  parser.add_argument('-O1', dest='opt_level', const=1, action='store_const')
  parser.add_argument('-O2', dest='opt_level', const=2, action='store_const')
  parser.add_argument('-O3', dest='opt_level', const=3, action='store_const')
  parser.add_argument('-Oz', dest='opt_level', const='z', action='store_const')
  parser.add_argument('-Os', dest='opt_level', const='s', action='store_const')
  parser.add_argument('-g', dest='debug_level', const=2, action='store_const')
  parser.add_argument('-g0', dest='debug_level', const=0, action='store_const')
  parser.add_argument('-g1', dest='debug_level', const=1, action='store_const')
  parser.add_argument('-g2', dest='debug_level', const=2, action='store_const')
  parser.add_argument('-g3', dest='debug_level', const=3, action='store_const')
  parser.add_argument('-g4', dest='debug_level', const=3, action='store_const')
  parser.add_argument('--preload-file', dest='preload_files', action='append', default=[])
  parser.add_argument('--embed-file', dest='embed_files', action='append', default=[])
  parser.add_argument('--closure-args', action='append', default=[])
  parser.add_argument('--source-map-base', metavar='URL')
  parser.add_argument('--emrun', action='store_true')
  parser.add_argument('--separate-asm', action='store_true')
  parser.add_argument('--emit-symbol-map', action='store_true')
  parser.add_argument('--proxy-to-worker', action='store_true')
  parser.add_argument('--use-preload-plugins', action='store_true')
  parser.add_argument('--use-preload-cache', action='store_true')
  parser.add_argument('--use-closure-compiler', action='store_true')
  parser.add_argument('--cpu-profiler', action='store_true')
  parser.add_argument('--threadprofiler', action='store_true')
  parser.add_argument('--profiling-funcs', action='store_true')
  parser.add_argument('--llvm-lto', metavar='LEVEL')
  parser.add_argument('--pre-js', metavar='LEVEL', action='append', default=[])
  parser.add_argument('--post-js', metavar='LEVEL', action='append', default=[])
  parser.add_argument('--output-eol', metavar='STYLE')
  parser.add_argument('--tracing', action='store_true')
  parser.add_argument('--memory-init-file', metavar='MODE', type=int)
  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('--js-library', metavar='JSLIB', dest='js_libraries', action='append', default=[])
  parser.add_argument('--js-transform', metavar='JSTRANSFORM')
  parser.add_argument('-s', dest='settings', metavar='SETTING=X', default=[], help='set emscripten settings', action='append')
  args, inputs = parser.parse_known_args(argv)
  print(args.settings)
  return link(args, inputs, args.output)


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
