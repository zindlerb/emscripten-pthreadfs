/*
 * Copyright 2013 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <utime.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/sysmacros.h>

void create_file(const char *path, const char *buffer, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR , mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  // struct utimbuf t = {1200000000, 1200000000};

  mkdir("pthreadfs/folder", 0777);
  create_file("pthreadfs/folder/file", "abcdef", 0777);
  //symlink("file", "folder/file-link");

  //utime("folder/file", &t);
  //utime("folder", &t);

  puts("success");
}

void cleanup() {
  unlink("pthreadfs/folder/file");
  // unlink("folder/file-link");
  rmdir("pthreadfs/folder");
}

void test() {
  create_file("pthreadfs/folder/file", "blubbbbb", 0777);
}

int main() {
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}
