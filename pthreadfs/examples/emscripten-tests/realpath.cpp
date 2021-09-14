#include <assert.h>
#include <limits.h> /* PATH_MAX */
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
#include "pthreadfs.h"


static void create_file(const char *path, const char *buffer, int mode) {
  int fd = open(path, O_WRONLY | O_CREAT | O_EXCL, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  int err;
  err = mkdir("emptyfolder", 0777);
  assert(!err);
  err = mkdir("pthreadfs/emptypthreadfsfolder", 0777);
  assert(!err);
  create_file("file.txt", "Some non-pthreadfs file content", 0666);
  create_file("pthreadfs/pthreadfile.txt", "ride into the super dangerous pthreadFS zone", 0666);
}

void cleanup() {
  rmdir("emptyfolder");
  unlink("file.txt");
  unlink("pthreadfs/file.txt");
}

void test() {
  char buf[PATH_MAX];
  char *res = realpath("file.txt", buf);
  assert(res);
  printf("file.txt is at %s.\n", buf);
  res = realpath("doesnotexist.txt", buf);
  assert(!res);
  printf("doesnotexist.txt does not exist.\n");
  res = realpath("emptyfolder/../file.txt", buf);
  assert(res);
  printf("emptyfolder/../file.txt is at %s.\n", buf);
  // res = realpath("pthreadfs/../file.txt", buf);
  // assert(res);
  // printf("pthreadfs/../file.txt is at %s.\n", buf);
  
  res = realpath("pthreadfs/pthreadfile.txt", buf);
  assert(res);
  printf("pthreadfs/pthreadfile.txt is at %s.\n", buf);
  res = realpath("pthreadfs/doesnotexist.txt", buf);
  assert(!res);
  printf("pthreadfs/doesnotexist.txt does not exist.\n");
  res = realpath("emptyfolder/../pthreadfs/pthreadfsfile.txt", buf);
  assert(res);
  printf("emptyfolder/../pthreadfs/pthreadfsfile.txt is at %s.\n", buf);
  res = realpath("pthreadfs/emptypthreadfsfolder/../file.txt", buf);
  assert(res);
  printf("pthreadfs/emptypthreadfsfolder/../file.txt is at %s.\n", buf);

  puts("success");
}

int main() {
  emscripten_init_pthreadfs();
  puts("WARNING: This test will fail. Update this message if the test succeeds.");
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}