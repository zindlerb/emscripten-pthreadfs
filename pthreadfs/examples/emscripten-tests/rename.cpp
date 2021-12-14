/*
 * Copyright 2013 The Emscripten Authors.  All rights reserved.
 * Emscripten is available under two separate licenses, the MIT license and the
 * University of Illinois/NCSA Open Source License.  Both these licenses can be
 * found in the LICENSE file.
 */

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

// PThreadFS currently does not allow renaming or moving directories.
#define PTHREADFS_NO_DIR_RENAME

void create_file(const char *path, const char *buffer, int mode) {
  int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  create_file("persistent/file", "abcdef", 0777);
  mkdir("persistent/dir", 0777);
  create_file("persistent/dir/file", "abcdef", 0777);
  mkdir("persistent/dir/subdir", 0777);
  mkdir("persistent/dir-readonly", 0555);
  mkdir("persistent/dir-nonempty", 0777);
  mkdir("persistent/dir/subdir3", 0777);
  mkdir("persistent/dir/subdir3/subdir3_1", 0777);
  mkdir("persistent/dir/subdir4/", 0777);
  create_file("persistent/dir-nonempty/file", "abcdef", 0777);
}

void cleanup() {
  // we're hulk-smashing and removing original + renamed files to
  // make sure we get it all regardless of anything failing
  unlink("persistent/file");
  unlink("persistent/dir/file");
  unlink("persistent/dir/file1");
  unlink("persistent/dir/file2");
  rmdir("persistent/dir/subdir");
  rmdir("persistent/dir/subdir1");
  rmdir("persistent/dir/subdir2");
  rmdir("persistent/dir/subdir3/subdir3_1/subdir1 renamed");
  rmdir("persistent/dir/subdir3/subdir3_1");
  rmdir("persistent/dir/subdir3");
  rmdir("persistent/dir/subdir4/");
  rmdir("persistent/dir/subdir5/");
  rmdir("persistent/dir");
  rmdir("persistent/dir-readonly");
  unlink("persistent/dir-nonempty/file");
  rmdir("persistent/dir-nonempty");
}

void test() {
  int err;

  // can't rename something that doesn't exist
  err = rename("persistent/noexist", "persistent/dir");
  assert(err == -1);
  assert(errno == ENOENT);

  // can't overwrite a folder with a file
  err = rename("persistent/file", "persistent/dir");
  assert(err == -1);
  assert(errno == EISDIR);

  // can't overwrite a file with a folder
  err = rename("persistent/dir", "persistent/file");
  assert(err == -1);
  assert(errno == ENOTDIR);

  // can't overwrite a non-empty folder
  err = rename("persistent/dir", "persistent/dir-nonempty");
  assert(err == -1);
  assert(errno == ENOTEMPTY);

  // can't create anything in a read-only directory
  err = rename("persistent/dir", "persistent/dir-readonly/dir");
  assert(err == -1);
  assert(errno == EACCES);

  // source should not be ancestor of target
  err = rename("persistent/dir", "persistent/dir/somename");
  assert(err == -1);
  assert(errno == EINVAL);

  // target should not be an ancestor of source
  err = rename("persistent/dir/subdir", "persistent/dir");
  assert(err == -1);
  assert(errno == ENOTEMPTY);

  // do some valid renaming
  err = rename("persistent/dir/file", "persistent/dir/file1");
  assert(!err);
  err = rename("persistent/dir/file1", "persistent/dir/file2");
  assert(!err);
  err = access("persistent/dir/file2", F_OK);
  assert(!err);

#ifndef PTHREADFS_NO_DIR_RENAME
  err = rename("persistent/dir/subdir", "persistent/dir/subdir1");
  assert(!err);
  err = rename("persistent/dir/subdir1", "persistent/dir/subdir2");
  assert(!err);
  err = access("persistent/dir/subdir2", F_OK);
  assert(!err);

  err = rename("persistent/dir/subdir2", "persistent/dir/subdir3/subdir3_1/subdir1 renamed");
  assert(!err);
  err = access("persistent/dir/subdir3/subdir3_1/subdir1 renamed", F_OK);
  assert(!err);

  // test that non-existant parent during rename generates the correct error code
  err = rename("persistent/dir/hicsuntdracones/empty", "persistent/dir/hicsuntdracones/renamed");
  assert(err == -1);
  assert(errno == ENOENT);
  
  err = rename("persistent/dir/subdir4/", "persistent/dir/subdir5/");
  assert(!err);
#endif  // PTHREADFS_NO_DIR_RENAME

  puts("success");
}

int main() {
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}
