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
#include <unistd.h>
#include <sys/stat.h>

static void create_file(const char *path, const char *buffer, int mode) {
  int fd = open(path, O_WRONLY | O_CREAT, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  int err;
  err = mkdir("persistent/lowercase", 0777);
  assert(!err);
  err = mkdir("persistent/UPPERCASE", 0777);
  assert(!err);
  err = mkdir("persistent/mixed_case-folder", 0777);
  assert(!err);
  create_file("persistent/lowercase/UPPER.txt", "content UPPER.txt", 0666);
  create_file("persistent/UPPERCASE/bla.BLA_bla", "content bla.BLA_bla\n", 0666);
  create_file("persistent/mixed_case-folder/some file .txt", "content some file .txt", 0666);
}

void cleanup() {
  unlink("persistent/lowercase/UPPER.txt");
  unlink("persistent/UPPERCASE/bla.BLA_bla");
  unlink("persistent/mixed_case-folder/some file .txt");
  rmdir("persistent/lowercase");
  rmdir("persistent/UPPERCASE");
  rmdir("persistent/mixed_case-folder");
}

void test() {
  int err;
  DIR *dir;
  struct dirent *ent;
  int i;

  //
  // do a normal read with readdir
  //
  dir = opendir("persistent/lowercase/");
  assert(dir);
  int seen[3] = { 0, 0, 0 };
  for (i = 0; i < 3; i++) {
    errno = 0;
    ent = readdir(dir);
    //printf("ent, errno: %p, %d\n", ent, errno);
    assert(ent);
    printf("%d file: %s (%d : %lu)\n", i, ent->d_name, ent->d_reclen, sizeof(*ent));
    assert(ent->d_reclen == sizeof(*ent));
    if (!seen[0] && !strcmp(ent->d_name, ".")) {
      assert(ent->d_type & DT_DIR);
      seen[0] = 1;
      continue;
    }
    if (!seen[1] && !strcmp(ent->d_name, "..")) {
      assert(ent->d_type & DT_DIR);
      seen[1] = 1;
      continue;
    }
    if (!seen[2] && !strcmp(ent->d_name, "upper.txt")) {
      assert(ent->d_type & DT_REG);
      seen[2] = 1;
      continue;
    }
    assert(0 && "odd filename");
  }
  ent = readdir(dir);
  if (ent) printf("surprising ent: %p : %s\n", ent, ent->d_name);
  assert(!ent);

  err = closedir(dir);
  assert(!err);

  dir = opendir("persistent/UPPERCASE/");
  assert(dir);
  int seen_2[3] = { 0, 0, 0 };
  for (i = 0; i < 3; i++) {
    errno = 0;
    ent = readdir(dir);
    //printf("ent, errno: %p, %d\n", ent, errno);
    assert(ent);
    printf("%d file: %s (%d : %lu)\n", i, ent->d_name, ent->d_reclen, sizeof(*ent));
    assert(ent->d_reclen == sizeof(*ent));
    if (!seen_2[0] && !strcmp(ent->d_name, ".")) {
      assert(ent->d_type & DT_DIR);
      seen_2[0] = 1;
      continue;
    }
    if (!seen_2[1] && !strcmp(ent->d_name, "..")) {
      assert(ent->d_type & DT_DIR);
      seen_2[1] = 1;
      continue;
    }
    if (!seen_2[2] && !strcmp(ent->d_name, "bla.bla_bla")) {
      assert(ent->d_type & DT_REG);
      seen_2[2] = 1;
      continue;
    }
    assert(0 && "odd filename");
  }
  ent = readdir(dir);
  if (ent) printf("surprising ent: %p : %s\n", ent, ent->d_name);
  assert(!ent);

  err = closedir(dir);
  assert(!err);

  dir = opendir("persistent/mixed_case-folder/");
  assert(dir);
  int seen_3[3] = { 0, 0, 0 };
  for (i = 0; i < 3; i++) {
    errno = 0;
    ent = readdir(dir);
    //printf("ent, errno: %p, %d\n", ent, errno);
    assert(ent);
    printf("%d file: %s (%d : %lu)\n", i, ent->d_name, ent->d_reclen, sizeof(*ent));
    assert(ent->d_reclen == sizeof(*ent));
    if (!seen_3[0] && !strcmp(ent->d_name, ".")) {
      assert(ent->d_type & DT_DIR);
      seen_3[0] = 1;
      continue;
    }
    if (!seen_3[1] && !strcmp(ent->d_name, "..")) {
      assert(ent->d_type & DT_DIR);
      seen_3[1] = 1;
      continue;
    }
    if (!seen_3[2] && !strcmp(ent->d_name, "some file .txt")) {
      assert(ent->d_type & DT_REG);
      seen_3[2] = 1;
      continue;
    }
    assert(0 && "odd filename");
  }
  ent = readdir(dir);
  if (ent) printf("surprising ent: %p : %s\n", ent, ent->d_name);
  assert(!ent);

  err = closedir(dir);
  assert(!err);

  int fd = open("persistent/UPPERCASE/bla.BLA_bla", O_RDONLY, 0777);
  assert(fd >= 0);

  char readbuf[100];

  err = read(fd, readbuf, sizeof(char) * 100);
  assert(err > 0);
  printf("%s",readbuf);

  close(fd);

  puts("success");
}

int main() {
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}