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

void create_file(const char* path, const char* contents, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, mode);
  assert(fd >= 0);

  int err = write(fd, contents, sizeof(char) * strlen(contents));
  assert(err == (sizeof(char) * strlen(contents)));

  close(fd);
}

void test_file_contents(const char* path, const char* contents) {
  MAIN_THREAD_ASYNC_EM_ASM({
    (async() => {
      let path = UTF8ToString($0);
      await PThreadFS.init("persistent");
      let content = await PThreadFS.readFile(path);
      content = new TextDecoder().decode(content);
      if (content != UTF8ToString($1)) {
        throw new Error('Incorrect contents read: ' + content);
      }
      await PThreadFS.unlink(path);
      console.log("Success");
    })();
  }, path, contents);
}

int main() {
  const char* path = "persistent/read_from_main_file.txt";
  const char* contents = "file_contents :)";
  create_file(path, contents, 0777);

  test_file_contents(path, contents);

  puts("Check the console for success");
  return EXIT_SUCCESS;
}
