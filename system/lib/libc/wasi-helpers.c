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

int  __wasi_fd_is_valid(__wasi_fd_t fd) {
  __wasi_fdstat_t statbuf;
  int err = __wasi_fd_fdstat_get(fd, &statbuf);
  if (err != __WASI_ESUCCESS) {
    errno = err;
    return 0;
  }
  return 1;
}

#include <fcntl.h>
#include <string.h>

// Replaces __fmodeflags

__wasi_errno_t __wasi_flags_from_modestr(const char *mode,
                                         __wasi_fdflags_t& fdflags) {
  fdflags = 0;
  if (strchr(mode, '+')) flags = O_RDWR;
  else if (*mode == 'r') flags = O_RDONLY;
  else flags = O_WRONLY;
  if (strchr(mode, 'x')) flags |= O_EXCL;
  if (strchr(mode, 'e')) flags |= O_CLOEXEC;
  if (*mode != 'r') flags |= O_CREAT;
  if (*mode == 'w') flags |= O_TRUNC;
  if (*mode == 'a') fdflags |= __WASI_FDFLAG_APPEND;
  return flags;
}

typedef uint16_t __wasi_oflags_t;
#define __WASI_O_CREAT     (UINT16_C(0x0001))
#define __WASI_O_DIRECTORY (UINT16_C(0x0002))
#define __WASI_O_EXCL      (UINT16_C(0x0004))
#define __WASI_O_TRUNC     (UINT16_C(0x0008))

typedef uint16_t __wasi_fdflags_t;
#define __WASI_FDFLAG_APPEND   (UINT16_C(0x0001))
#define __WASI_FDFLAG_DSYNC    (UINT16_C(0x0002))
#define __WASI_FDFLAG_NONBLOCK (UINT16_C(0x0004))
#define __WASI_FDFLAG_RSYNC    (UINT16_C(0x0008))
#define __WASI_FDFLAG_SYNC     (UINT16_C(0x0010))

typedef uint64_t __wasi_rights_t;
#define __WASI_RIGHT_FD_DATASYNC           (UINT64_C(0x0000000000000001))
#define __WASI_RIGHT_FD_READ               (UINT64_C(0x0000000000000002))
#define __WASI_RIGHT_FD_SEEK               (UINT64_C(0x0000000000000004))
#define __WASI_RIGHT_FD_FDSTAT_SET_FLAGS   (UINT64_C(0x0000000000000008))
#define __WASI_RIGHT_FD_SYNC               (UINT64_C(0x0000000000000010))
#define __WASI_RIGHT_FD_TELL               (UINT64_C(0x0000000000000020))
#define __WASI_RIGHT_FD_WRITE              (UINT64_C(0x0000000000000040))
#define __WASI_RIGHT_FD_ADVISE             (UINT64_C(0x0000000000000080))
#define __WASI_RIGHT_FD_ALLOCATE           (UINT64_C(0x0000000000000100))
#define __WASI_RIGHT_PATH_CREATE_DIRECTORY (UINT64_C(0x0000000000000200))
#define __WASI_RIGHT_PATH_CREATE_FILE      (UINT64_C(0x0000000000000400))
#define __WASI_RIGHT_PATH_LINK_SOURCE      (UINT64_C(0x0000000000000800))
#define __WASI_RIGHT_PATH_LINK_TARGET      (UINT64_C(0x0000000000001000))
#define __WASI_RIGHT_PATH_OPEN             (UINT64_C(0x0000000000002000))
#define __WASI_RIGHT_FD_READDIR            (UINT64_C(0x0000000000004000))
#define __WASI_RIGHT_PATH_READLINK         (UINT64_C(0x0000000000008000))
#define __WASI_RIGHT_PATH_RENAME_SOURCE    (UINT64_C(0x0000000000010000))
#define __WASI_RIGHT_PATH_RENAME_TARGET    (UINT64_C(0x0000000000020000))
#define __WASI_RIGHT_PATH_FILESTAT_GET       (UINT64_C(0x0000000000040000))
#define __WASI_RIGHT_PATH_FILESTAT_SET_SIZE  (UINT64_C(0x0000000000080000))
#define __WASI_RIGHT_PATH_FILESTAT_SET_TIMES (UINT64_C(0x0000000000100000))
#define __WASI_RIGHT_FD_FILESTAT_GET        (UINT64_C(0x0000000000200000))
#define __WASI_RIGHT_FD_FILESTAT_SET_SIZE   (UINT64_C(0x0000000000400000))
#define __WASI_RIGHT_FD_FILESTAT_SET_TIMES  (UINT64_C(0x0000000000800000))
#define __WASI_RIGHT_PATH_SYMLINK          (UINT64_C(0x0000000001000000))
#define __WASI_RIGHT_PATH_REMOVE_DIRECTORY (UINT64_C(0x0000000002000000))
#define __WASI_RIGHT_PATH_UNLINK_FILE      (UINT64_C(0x0000000004000000))
#define __WASI_RIGHT_POLL_FD_READWRITE     (UINT64_C(0x0000000008000000))
#define __WASI_RIGHT_SOCK_SHUTDOWN         (UINT64_C(0x0000000010000000))

