/*
 * Copyright 2016 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

extern "C" {
int __cxa_thread_atexit(void (*dtor)(void *), void *obj, void *dso_symbol);
}

static void cleanA() { printf("A\n"); }
static void cleanB() { printf("B\n"); }
static void cleanCarg(void* x) { printf("C %d\n", (int)x); }

struct Foo {
  ~Foo() { printf("~Foo thread=%p\n", (void*)pthread_self()); }
  void bar() { printf("bar\n"); }
};

thread_local Foo foo;

void* thread_main(void*) {
  foo.bar();
  return nullptr;
}

int main() {
  __cxa_thread_atexit(cleanCarg, (void*)100, NULL);
  __cxa_thread_atexit(cleanCarg, (void*)234, NULL);
  atexit(cleanA);
  atexit(cleanB);
  pthread_t t;
  printf("main: starting thread\n");
  pthread_create(&t, nullptr, thread_main, nullptr);
  printf("main: joining thread\n");
  pthread_join(t, nullptr);
  printf("main: thread joined\n");
  return 0;
}
