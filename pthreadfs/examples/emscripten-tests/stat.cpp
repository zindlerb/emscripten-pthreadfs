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
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <utime.h>

void create_file(const char* path, const char* buffer, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err == (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  mkdir("persistent/folder", 0777);
  create_file("persistent/folder/file", "abcdef", 0777);
}

void cleanup() {
  rmdir("persistent/folder/subdir");
  unlink("persistent/folder/file");
  rmdir("persistent/folder");
}

void test() {
  int err;
  struct stat s;

  // non-existent
  err = stat("persistent/does_not_exist", &s);
  assert(err == -1);
  assert(errno == ENOENT);

  // stat a folder
  memset(&s, 0, sizeof(s));
  err = stat("persistent/folder", &s);
  assert(!err);
  assert(s.st_dev);
  assert(s.st_ino);
  assert(S_ISDIR(s.st_mode));
  assert(s.st_nlink);
  assert(s.st_rdev == 0);
  assert(s.st_size);
  // assert(s.st_atime == 1200000000);
  // assert(s.st_mtime == 1200000000);
  assert(s.st_ctime);
  assert(s.st_blksize == 4096);
  assert(s.st_blocks == 1);

  // stat the persistent folder
  memset(&s, 0, sizeof(s));
  err = stat("persistent", &s);
  assert(!err);
  assert(s.st_dev);
  assert(s.st_ino);
  assert(S_ISDIR(s.st_mode));
  assert(s.st_nlink);
  assert(s.st_rdev == 0);
  assert(s.st_size);
  assert(s.st_atime);
  assert(s.st_mtime);
  assert(s.st_ctime);
  assert(s.st_blksize == 4096);
  assert(s.st_blocks == 1);

  // stat a file
  memset(&s, 0, sizeof(s));
  err = stat("persistent/folder/file", &s);
  assert(!err);
  assert(s.st_dev);
  assert(s.st_ino);
  assert(S_ISREG(s.st_mode));
  assert(s.st_nlink);
  assert(s.st_rdev == 0);
  assert(s.st_size == 6);
  // assert(s.st_atime == 1200000000);
  // assert(s.st_mtime == 1200000000);
  // assert(s.st_ctime);
#ifdef __EMSCRIPTEN__
  assert(s.st_blksize == 4096);
  assert(s.st_blocks == 1);
#endif

  // fstat a file (should match file stat from above)
  memset(&s, 0, sizeof(s));
  int fd = open("persistent/folder/file", O_RDONLY);
  err = fstat(fd, &s);
  assert(!err);
  assert(s.st_dev);
  assert(s.st_ino);
  assert(S_ISREG(s.st_mode));
  assert(s.st_nlink);
  assert(s.st_rdev == 0);
  assert(s.st_size == 6);
  // assert(s.st_atime == 1200000000);
  // assert(s.st_mtime == 1200000000);
  // assert(s.st_ctime);
#ifdef __EMSCRIPTEN__
  assert(s.st_blksize == 4096);
  assert(s.st_blocks == 1);
#endif
  err = close(fd);
  assert(!err);

  // stat a device
  memset(&s, 0, sizeof(s));
  err = stat("/dev/null", &s);
  assert(!err);
  assert(s.st_dev);
  assert(s.st_ino);
  assert(S_ISCHR(s.st_mode));
  assert(s.st_nlink);
#ifndef __APPLE__
  // mac uses makedev(3, 2) for /dev/null
  assert(s.st_rdev == makedev(1, 3));
#endif
  assert(!s.st_size);
  assert(s.st_atime);
  assert(s.st_mtime);
  assert(s.st_ctime);
#ifdef __EMSCRIPTEN__
  assert(s.st_blksize == 4096);
  assert(s.st_blocks == 0);
#endif
  puts("success");
}

int main() {
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}
