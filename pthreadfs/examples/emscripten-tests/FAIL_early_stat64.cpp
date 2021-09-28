/*
 * Copyright 2021 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>

int main() {
  puts("Running main().");
  return EXIT_SUCCESS;
}


class EarlyObject {
 public:
  EarlyObject() {
    puts("This test is a warning: Do not use syscalls in objects before main is called!");
    puts("Start constructing EarlyObject.");
    int err;
    struct stat s;
    err = stat("persistent/", &s);
    assert(!err);
  }
};

EarlyObject obj;