#include <assert.h>
#include <fcntl.h>
#include <limits.h> /* PATH_MAX */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>


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
  err = mkdir("persistent/emptypthreadfsfolder", 0777);
  assert(!err);
  create_file("file.txt", "Some non-pthreadfs file content", 0666);
  create_file("persistent/pthreadfile.txt", "ride into the super dangerous pthreadFS zone", 0666);
}

void cleanup() {
  rmdir("emptyfolder");
  unlink("file.txt");
  unlink("persistent/file.txt");
}

void test() {
  char buf[PATH_MAX];
  char *res = realpath("file.txt", buf);
  // TODO: Assert that the return value is correct.
  assert(res);
  printf("file.txt is at %s.\n", buf);
  res = realpath("doesnotexist.txt", buf);
  assert(!res);
  printf("doesnotexist.txt does not exist.\n");
  res = realpath("emptyfolder/../file.txt", buf);
  assert(res);
  printf("emptyfolder/../file.txt is at %s.\n", buf);

  res = realpath("persistent/pthreadfile.txt", buf);
  assert(res);
  printf("persistent/pthreadfile.txt is at %s.\n", buf);
  res = realpath("persistent/doesnotexist.txt", buf);
  assert(!res);
  printf("persistent/doesnotexist.txt does not exist.\n");
  res = realpath("emptyfolder/../persistent/pthreadfsfile.txt", buf);
  assert(res);
  printf("emptyfolder/../persistent/pthreadfsfile.txt is at %s.\n", buf);
  res = realpath("persistent/emptypthreadfsfolder/../file.txt", buf);
  assert(res);
  printf("persistent/emptypthreadfsfolder/../file.txt is at %s.\n", buf);

  puts("success");
}

int main() {
  puts("WARNING: This test will fail. Update this message if the test succeeds.");
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}