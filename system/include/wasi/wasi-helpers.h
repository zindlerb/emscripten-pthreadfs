/*
 * Copyright 2019 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#ifndef __wasi_emscripten_helpers_h
#define __wasi_emscripten_helpers_h

#include <sys/stat.h>

// Converts a wasi return code to a musl syscall return code (-1 if
// error, 0 otherwise), and sets errno accordingly.
extern int __wasi_syscall_ret(__wasi_errno_t code);

// Internal helper for opening a file. Returns a negative number on error,
// fd otherwise, just like a musl syscall.
extern int __wasi_helper_sys_open(const char *filename, int flags, mode_t mode);

#endif // __wasi_emscripten_helpers_h
