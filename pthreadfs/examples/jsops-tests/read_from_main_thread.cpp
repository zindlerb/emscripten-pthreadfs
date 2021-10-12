/*
 * Copyright 2013 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "emscripten.h"

void create_file(const char* path, const char* buffer, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err == (sizeof(char) * strlen(buffer)));

  close(fd);
}

void test_file_contents(const char* path) {
  MAIN_THREAD_ASYNC_EM_ASM({
    (async() => {
      let path = UTF8ToString($0);
      await PThreadFS.init("persistent");
      let content = await PThreadFS.readFile(path);
      content = new TextDecoder().decode(content);
      if (content != "file_contents :)") {
        throw new Error('Incorrect contents read: ' + content);
      }
      console.log("Success");
    })();
  }, path);
}

int main() {
  const char* path = "persistent/read_from_main_file.txt";
  create_file(path, "file_contents :)", 0777);

  test_file_contents(path);

  puts("Check the console for success");
  return EXIT_SUCCESS;
}
