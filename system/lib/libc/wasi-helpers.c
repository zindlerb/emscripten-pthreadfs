/*
 * Copyright 2019 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <wasi/wasi.h>
#include <wasi/wasi-helpers.h>

   #include <stdio.h>

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
printf("sys_open %s %d %d\n", filename, flags, mode);
  // Silently ignore non-supported musl flags for now (like our JS
  // impl always did) FIXME
  __wasi_fdflags_t fs_flags = 0;
  if (flags & O_APPEND)   fs_flags |= __WASI_FDFLAG_APPEND;
  if (flags & O_DSYNC)    fs_flags |= __WASI_FDFLAG_DSYNC;
  if (flags & O_NONBLOCK) fs_flags |= __WASI_FDFLAG_NONBLOCK;
  if (flags & O_RSYNC)    fs_flags |= __WASI_FDFLAG_RSYNC;
  if (flags & O_SYNC)     fs_flags |= __WASI_FDFLAG_SYNC;

  __wasi_rights_t rights = 0;
  int accMode = mode & O_ACCMODE;
  if (accMode == O_RDONLY) rights |= __WASI_RIGHT_FD_READ;
  else if (accMode == O_RDWR)   rights |= __WASI_RIGHT_FD_READ |
                                          __WASI_RIGHT_FD_WRITE;
  else if (accMode == O_WRONLY) rights |= __WASI_RIGHT_FD_WRITE;
  if (mode & O_CREAT) rights |= __WASI_RIGHT_PATH_CREATE_FILE |
                                __WASI_RIGHT_PATH_CREATE_DIRECTORY;

  __wasi_fd_t fd;
  __wasi_errno_t err = __wasi_path_open(
      __preopened_singleton,
      0,
      filename,
      strlen(filename),
      flags & ALL_WASI_OFLAGS,
      rights,
      rights,
      fs_flags,
      &fd);
  if (__wasi_syscall_ret(err)) {
    return -1;
  }
  return fd;
}
