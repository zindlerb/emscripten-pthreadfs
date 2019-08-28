/*
 * Copyright 2019 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 *
 * C++ exception handling support stubs. This is included when exception
 * throwing is disabled - so no exceptions should exist at all. If the code still
 * uses them, these stubs will throw at runtime.
 */

mergeInto(LibraryManager.library, {
  __wasi_proc_exit__deps: ['exit'],
  __wasi_proc_exit: function(code) {
    return _exit(code);
  },

  __wasi_fd_write: function(fd, iovs, num, written) {
    throw 'waka';
  },
});
