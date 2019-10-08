/*
 * Copyright 2019 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <errno.h>
#include <stdlib.h>
#include <wasi/wasi.h>
#include <wasi/wasi-helpers.h>

int __wasi_syscall_ret(__wasi_errno_t code) {
  if (code == __WASI_ESUCCESS) return 0;
  // We depend on the fact that wasi codes are identical to our errno codes.
  errno = code;
  return -1;
}

// Preopen support: For now we just assume a single preopened singleton
// "root", which can be e.g. the current dir in which the executable is in,
// etc. This should let a lot of stuff work, and avoids the ~1K overhead that
// full preopening currently has in the wasi SDK. TODO: full support as an
// option.

// TODO read this singleton. for now, use 3 which is after stdin, stdout, stderr
static __wasi_fd_t __preopened_singleton = 3;

// Musl "flags" must be converted into wasi oflags and fdflags; each flag
// goes into one of them.
#define ALL_WASI_OFLAGS (O_CREAT | O_EXCL | O_TRUNC | O_DIRECTORY)

int __wasi_helper_sys_open(const char *filename, int flags, mode_t mode) {
  // Silently ignore non-supported musl flags for now (like our JS
  // impl always did) FIXME
  __wasi_fdflags_t fdflags = 0;
  if (fdflags & O_APPEND)   fdflags |= __WASI_FDFLAG_APPEND;
  if (fdflags & O_DSYNC)    fdflags |= __WASI_FDFLAG_DSYNC;
  if (fdflags & O_NONBLOCK) fdflags |= __WASI_FDFLAG_NONBLOCK;
  if (fdflags & O_RSYNC)    fdflags |= __WASI_FDFLAG_RSYNC;
  if (fdflags & O_SYNC)     fdflags |= __WASI_FDFLAG_SYNC;
  // For now, ask for all the rights FIXME
  __wasi_rights_t rights = -1;

  __wasi_fd_t fd;
  __wasi_errno_t err = __wasi_path_open(
      __preopened_singleton,
      0,
      filename,
      strlen(filename),
      flags & ALL_WASI_OFLAGS,
      rights,
      rights,
      fdflags,
      &fd);
  if (__wasi_syscall_ret(err)) {
    return -1;
  }
  return fd;
}
