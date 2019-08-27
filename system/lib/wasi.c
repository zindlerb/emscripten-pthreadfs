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

#include <emscripten.h>
#include <string.h>

// libc

void exit(int status) {
  extern void __wasi_proc_exit(int);
  __wasi_proc_exit(status);
  __builtin_unreachable();
}

void abort() {
  exit(1);
}

// Musl lock internals. As we assume wasi is single-threaded for now, these
// are no-ops.

void __lock(void* ptr) {}
void __unlock(void* ptr) {}

// Emscripten additions

void *emscripten_memcpy_big(void *restrict dest, const void *restrict src, size_t n) {
  // This normally calls out into JS which can do a single fast operation,
  // but with wasi we can't do that. As this is called when n >= 8192, we
  // can just split into smaller calls.
  // TODO optimize, maybe build our memcpy with a wasi variant?
  const int CHUNK = 8192;
  unsigned char* d = (unsigned char*)dest;
  unsigned char* s = (unsigned char*)src;
  while (n > 0) {
    size_t curr_n = n;
    if (curr_n > CHUNK) curr_n = CHUNK;
    memcpy(d, s, curr_n);
    d += CHUNK;
    s += CHUNK;
    n -= curr_n;
  }
  return dest;
}

// I/O syscalls - we support printf etc., but no filesystem access for now.

static int* _vararg;

static void set_vararg(int vararg) {
  _vararg = (int*)vararg;
}

static int get_vararg_i32() {
  return *vararg++;
}

int __syscall6(int id, int vararg) { // close
  return 0;
}

int __syscall54(int id, int vararg) { // ioctl
  EM_ASM({
    console.log("syscall54:", $1);
  }, vararg);
  return 0;
}

int __syscall140(int id, int vararg) { // llseek
  EM_ASM({
    console.log("syscall140:", $1);
  }, vararg);
  return 0;
}

struct Iov {
  unsigned char* ptr;
  int len;
};

int __syscall146(int id, int vararg) { // writev
  // hack to support printf, similar to library_syscalls.js handling of SYSCALLS_REQUIRE_FILESYSTEM=0
  int stream = get_vararg_i32();
  Iov* iov = (Iov*)get_vararg_i32();
  int iovcnt = get_vararg_i32();
  int ret = 0;
  for (int i = 0; i < iovcnt; i++) {
    int ptr = iov->ptr;
    int len = iov->len;
    iov++;
    for (int j = 0; j < len; j++) {
      SYSCALLS.printChar(stream, HEAPU8[ptr+j]);
    }
    ret += len;
  }
  return ret;
}
