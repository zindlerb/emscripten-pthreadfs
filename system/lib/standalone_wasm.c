/*
 * Copyright 2019 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <emscripten.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <wasi/wasi.h>

/*
 * WASI support code. These are compiled with the program, and call out
 * using wasi APIs, which can be provided either by a wasi VM or by our
 * emitted JS.
 */

// libc

void exit(int status) {
  __wasi_proc_exit(status);
  __builtin_unreachable();
}

void abort() {
  exit(1);
}

// mmap support is nonexistent. TODO: emulate simple mmaps using
// stdio + malloc, which is slow but may help some things?

int __map_file(int x, int y) {
  return ENOSYS;
}

int __syscall91(int x, int y) { // munmap
  return ENOSYS;
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
  // TODO optimize, maybe build our memcpy with a wasi variant, maybe have
  //      a SIMD variant, etc.
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

static const int WASM_PAGE_SIZE = 65536;

// Note that this does not support memory growth in JS because we don't update the JS
// heaps. Wasm and wasi lack a good API for that.
int emscripten_resize_heap(size_t size) {
  size_t result = __builtin_wasm_memory_grow(0, (size + WASM_PAGE_SIZE - 1) / WASM_PAGE_SIZE);
  return result != (size_t)-1;
}

// C++ ABI

// Emscripten disables exception catching by default, but not throwing. That
// allows users to see a clear error if a throw happens, and 99% of the
// overhead is in the catching, so this is a reasonable tradeoff.
// For now, in a standalone build just terminate. TODO nice error message
void
__cxa_throw(void* ptr, void* type, void* destructor) {
  abort();
}

void* __cxa_allocate_exception(size_t thrown_size) {
  abort();
}

// EMCC_AUTODEBUG support. This is normally in JS, which lets it not have
// any side effects inside the wasm module. In standalone wasm we probably
// want to use a separate memory etc. for this eventually. For now, just
// print.

uint32_t get_i32(uint32_t loc, uint32_t index, uint32_t value) {
  printf("get_i32 %u %u %u\n", loc, index, value);
  return value;
}
uint64_t get_i64(uint32_t loc, uint32_t index, uint64_t value) {
  printf("get_i64 %u %u %llu\n", loc, index, value);
  return value;
}
float get_f32(uint32_t loc, uint32_t index, float value) {
  printf("get_f32 %u %u %f\n", loc, index, value);
  return value;
}
double get_f64(uint32_t loc, uint32_t index, double value) {
  printf("get_f64 %u %u %lf\n", loc, index, value);
  return value;
}
uint32_t set_i32(uint32_t loc, uint32_t index, uint32_t value) {
  printf("set_i32 %u %u %u\n", loc, index, value);
  return value;
}
uint64_t set_i64(uint32_t loc, uint32_t index, uint64_t value) {
  printf("set_i64 %u %u %llu\n", loc, index, value);
  return value;
}
float set_f32(uint32_t loc, uint32_t index, float value) {
  printf("set_f32 %u %u %f\n", loc, index, value);
  return value;
}
double set_f64(uint32_t loc, uint32_t index, double value) {
  printf("set_f64 %u %u %lf\n", loc, index, value);
  return value;
}
void log_execution(uint32_t loc) {
  printf("log_execution %u\n", loc);
}
void* load_ptr(uint32_t loc, uint32_t bytes, uint32_t offset, void* ptr) {
  printf("load_ptr %u %u %u %p\n", loc, bytes, offset, ptr);
  return ptr;
}
void* store_ptr(uint32_t loc, uint32_t bytes, uint32_t offset, void* ptr) {
  printf("store_ptr %u %u %u %p\n", loc, bytes, offset, ptr);
  return ptr;
}
uint32_t load_val_i32(uint32_t loc, uint32_t value) {
  printf("load_val_i32 %u %u\n", loc, value);
  return value;
}
uint64_t load_val_i64(uint32_t loc, uint64_t value) {
  printf("load_val_i64 %u %llu\n", loc, value);
  return value;
}
float load_val_f32(uint32_t loc, float value) {
  printf("load_val_f32 %u %f\n", loc, value);
  return value;
}
double load_val_f64(uint32_t loc, double value) {
  printf("load_val_f64 %u %lf\n", loc, value);
  return value;
}
uint32_t store_val_i32(uint32_t loc, uint32_t value) {
  printf("store_val_i32 %u %u\n", loc, value);
  return value;
}
uint64_t store_val_i64(uint32_t loc, uint64_t value) {
  printf("store_val_i64 %u %llu\n", loc, value);
  return value;
}
float store_val_f32(uint32_t loc, float value) {
  printf("store_val_f32 %u %f\n", loc, value);
  return value;
}
double store_val_f64(uint32_t loc, double value) {
  printf("store_val_f64 %u %lf\n", loc, value);
  return value;
}

