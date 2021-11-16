
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


void create_file(const char *path, const char *buffer, int mode) {
  int fd = open(path, O_CREAT | O_TRUNC | O_RDWR , mode);
  assert(fd >= 0);

  int err = write(fd, buffer, sizeof(char) * strlen(buffer));
  assert(err ==  (sizeof(char) * strlen(buffer)));

  close(fd);
}

void setup() {
  mkdir("persistent/folder", 0777);
  create_file("persistent/folder/file", "abcdef", 0777);
}

void cleanup() {
  unlink("persistent/folder/file");
  rmdir("persistent/folder");
}

void test() {
    char buf[PATH_MAX];
    char *res = realpath("persistent/folder/../folder/./file", buf);
    if (res) {
        printf("The file's real path is at %s.\n", buf);
    } else {
        char* errStr = strerror(errno);
        printf("error string: %s\n", errStr);
    }
}

int main() {
  setup();
  test();
  cleanup();
  puts("success");
  return EXIT_SUCCESS;
}



