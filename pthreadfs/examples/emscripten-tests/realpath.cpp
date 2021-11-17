
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include <emscripten.h>

void create_file(const char* path, const char* buffer, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err == (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  mkdir("persistent/folder", 0777);
  mkdir("nonpersistent", 0777);
  create_file("persistent/folder/file", "abcdef", 0777);
  create_file("nonpersistent/file2", "ghijkl", 0777);
}

void cleanup() {
  unlink("persistent/folder/file");
  unlink("nonpersistent/file2");
  rmdir("persistent/folder");
  rmdir("nonpersistent");
}

bool test_path(const char* provided_path, const char* expected_path) {
  char computed_path[PATH_MAX];
  char* res = realpath(provided_path, computed_path);
  int success = strcmp(expected_path, computed_path);
  return res && success;
}

void test() {
  const char* provided_paths[] = {"persistent/folder/../folder/file",
    "persistent/../persistent/folder/file", "persistent/folder/./file", "/persistent/folder/file"};
  const char* expected_paths[] = {"persistent/folder/file", "persistent/folder/file",
    "persistent/folder/file", "persistent/folder/file"};
  for (int i = 0; i < sizeof(provided_paths) / sizeof(char*); i++) {
    if (!test_path(provided_paths[i], expected_paths[i])) {
      char* errStr = strerror(errno);
      printf("Realpath failed for path %d: %s. Error string: %s\n", i, provided_paths[i], errStr);
      return;
    }
  }
  puts("success");
}

int main() {
  setup();
  test();
  cleanup();
  return EXIT_SUCCESS;
}
